"""Publish the unchanged audited classifier as a current-session snapshot."""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

import audited_model

REQUIRED = ["Date", "Open", "High", "Low", "Close", "Volume"]
MODEL_SHA256 = "4ea487270d818fe6ea851464cbe0e80bf6a24395570f18748d095d93bd686003"


@dataclass(frozen=True)
class Config:
    near_floor_pct: float = 5.0

    @classmethod
    def from_json(cls, path):
        return cls(**json.loads(Path(path).read_text()))


def clean_prices(raw):
    """Validate downloaded bars, retaining Adj Close for the split guard."""
    if not set(REQUIRED).issubset(raw.columns):
        return pd.DataFrame(columns=REQUIRED + ["Adj Close"])
    fields = REQUIRED + (["Adj Close"] if "Adj Close" in raw else [])
    d = raw[fields].copy()
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    for col in fields[1:]:
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=REQUIRED).sort_values("Date").drop_duplicates("Date", keep="last")
    ok = ((d[["Open", "High", "Low", "Close"]] > 0).all(axis=1)
          & (d.Volume >= 0)
          & (d.High >= d[["Open", "Low", "Close"]].max(axis=1))
          & (d.Low <= d[["Open", "Close"]].min(axis=1)))
    return d.loc[ok].reset_index(drop=True)


def iter_frames(source):
    if source.is_dir():
        for path in sorted(source.glob("*.csv")):
            if path.stem != "download_report":
                yield path.stem.upper(), pd.read_csv(path)
    else:
        with zipfile.ZipFile(source) as archive:
            for name in sorted(archive.namelist()):
                if (name.startswith("prices/") and name.count("/") == 1
                        and name.endswith(".csv") and Path(name).stem != "download_report"):
                    yield Path(name).stem.upper(), pd.read_csv(io.BytesIO(archive.read(name)))


class FrameArchive:
    """Adapt a DataFrame to the frozen classifier's zipfile read interface."""
    def __init__(self, frame):
        prepared = frame.copy()
        if "Adj Close" not in prepared:
            prepared["Adj Close"] = prepared["Close"]
        self.content = prepared.to_csv(index=False).encode("utf-8")

    def read(self, _name):
        return self.content


def model_bars(raw, cutoff):
    """Select chart bars by exactly the same validity rules as the frozen core."""
    d = raw.copy()
    d["Date"] = d.Date.astype(str).str[:10]
    d = d[(d.Date >= "2015-01-01") & (d.Date <= cutoff)]
    d = d.sort_values("Date").drop_duplicates("Date")
    for col in ("Open", "High", "Low", "Close"):
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d = d.dropna(subset=["Open", "High", "Low", "Close"])
    d = d[(d.Low > 0) & (d.High >= d.Low) & (d.Close > 0)]
    return d.reset_index(drop=True)


def candidate(ticker, episode, bars, cfg):
    cutoff = str(bars.Date.iloc[-1])
    if episode["last_confirmed"] != cutoff or episode["status"] != "recent":
        return None
    first = episode["first_contact"]
    base = bars[bars.Date >= first]
    floor, upper = float(episode["modal_floor_low"]), float(episode["modal_floor_high"])
    close, previous = float(bars.Close.iloc[-1]), float(bars.Close.iloc[-2])
    low = float(bars.Low.iloc[-1])
    recent = base.Close.tail(3).to_numpy(float)
    if close < floor * .97 or int(np.sum(recent < floor * .99)) >= 2:
        # The historical classifier can retain an episode whose original first
        # contact predates the latest proposal. If the current bars contradict
        # its rounded support, exclude this candidate without aborting the
        # complete daily snapshot.
        return None
    distance = 100 * (close / floor - 1)
    if close < floor:
        state = "PENETRACION_PENDIENTE"
    elif low <= upper and close <= upper:
        state = "VISITANDO_SUELO"
    elif distance <= cfg.near_floor_pct:
        state = "CERCA_DEL_SUELO"
    else:
        state = "EN_RANGO"

    def recovered(date_field, low_field, recovery_field):
        day = episode[date_field]
        if not day or day < first:
            return None
        return {"date": day, "low": float(episode[low_field]),
                "recovered_at": episode[recovery_field]}

    wick = recovered("recovered_wick_dip_date", "recovered_wick_dip_low",
                     "recovered_wick_dip_recovery")
    breach = recovered("temporary_breach_date", "temporary_breach_low",
                       "temporary_breach_recovery")
    repeated_date = episode["lower_repeated_contact_date"]
    repeated = ({"date": repeated_date, "low": float(episode["lower_repeated_contact_low"])}
                if repeated_date and repeated_date >= first else None)
    if repeated:
        if wick and wick["date"] < repeated_date and abs(wick["low"] / repeated["low"] - 1) <= .0035:
            wick = None
        if breach and breach["date"] < repeated_date and abs(breach["low"] / repeated["low"] - 1) <= .0035:
            breach = None

    ceiling = float(episode["ceiling"])
    volume = pd.to_numeric(bars.Volume, errors="coerce").fillna(0).to_numpy(float)
    dollar_volume = float(np.median(bars.Close.to_numpy(float)[-20:] * volume[-20:]))
    chart = [{"date": row.Date, "open": round(float(row.Open), 6),
              "high": round(float(row.High), 6), "low": round(float(row.Low), 6),
              "close": round(float(row.Close), 6)}
             for row in base.itertuples(index=False)]
    return {
        "ticker": ticker, "as_of": cutoff, "state": state,
        "pattern_score": round(float(episode["confidence"]) * 100, 1),
        "first_detectable": episode["first_detectable"],
        "last_confirmed": episode["last_confirmed"],
        "range_start": first, "range_sessions": len(base),
        "prior_drop_pct": float(episode["prior_drop_pct"]),
        "floor": floor, "floor_zone_high": upper,
        "minimum_since_first_visit": round(float(base.Low.min()), 6),
        "ceiling": ceiling, "last_close": round(close, 6),
        "day_low": round(low, 6),
        "day_return_pct": round(100 * (close / previous - 1), 2),
        "distance_to_floor_pct": round(distance, 2),
        "distance_to_zone_pct": round(100 * (close / upper - 1), 2),
        "room_to_ceiling_pct": round(100 * (ceiling / close - 1), 2),
        "visit_count": int(episode["visits"]),
        "successful_rebounds": int(episode["prior_bounces"]),
        "median_dollar_volume_20": round(dollar_volume, 2),
        "wick_dip": wick, "recovered_breach": breach,
        "lower_repeated_contact": repeated, "chart": chart,
    }


def scan(source, cfg, as_of=None):
    source = Path(source)
    if as_of is None:
        dates = Counter(str(raw.Date.iloc[-1])[:10] for _, raw in iter_frames(source)
                        if "Date" in raw and not raw.empty)
        as_of = dates.most_common(1)[0][0] if dates else None
    if as_of is None:
        raise ValueError("No daily price data")
    audited_model.END = as_of
    candidates = []
    scanned = valid = episodes_seen = 0
    for ticker, raw in iter_frames(source):
        scanned += 1
        if not set(REQUIRED).issubset(raw):
            continue
        _, history, coverage = audited_model.classify_file(f"prices/{ticker}.csv", FrameArchive(raw))
        if coverage["rows"] == 0:
            continue
        valid += 1
        episodes_seen += len(history)
        bars = model_bars(raw, as_of)
        if bars.empty or bars.Date.iloc[-1] != as_of or len(bars) < 2:
            continue
        current = [e for e in history if e["last_confirmed"] == as_of]
        if current:
            chosen = max(current, key=lambda e: e["first_detectable"])
            item = candidate(ticker, chosen, bars, cfg)
            if item:
                candidates.append(item)
    candidates.sort(key=lambda x: (-x["pattern_score"], x["distance_to_floor_pct"], x["ticker"]))
    for rank, item in enumerate(candidates, 1):
        item["rank"] = rank
    payload = {
        "as_of": as_of,
        "strategy": {"name": "Audited recurrent floor and punctual dips", "version": 9,
                     "classifier_sha256": MODEL_SHA256,
                     "description": "Zona modal de visitas y rebotes; mínimos puntuales y contactos inferiores separados."},
        "universe": {"files_scanned": scanned, "valid_series": valid,
                     "candidates": len(candidates), "historical_episodes": episodes_seen},
        "state_counts": dict(Counter(x["state"] for x in candidates)),
        "candidates": candidates, "config": asdict(cfg),
    }
    frame = pd.DataFrame([
        {**{k: v for k, v in row.items()
            if k not in {"chart", "wick_dip", "recovered_breach", "lower_repeated_contact"}},
         "wick_dip_date": row["wick_dip"]["date"] if row["wick_dip"] else "",
         "wick_dip_low": row["wick_dip"]["low"] if row["wick_dip"] else "",
         "breach_date": row["recovered_breach"]["date"] if row["recovered_breach"] else "",
         "breach_recovery": row["recovered_breach"]["recovered_at"] if row["recovered_breach"] else "",
         "lower_repeated_contact_date": (row["lower_repeated_contact"]["date"]
                                          if row["lower_repeated_contact"] else "")}
        for row in candidates
    ])
    return frame, payload


def main():
    parser = argparse.ArgumentParser(description="Audited recurrent floor scanner")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("config.json"))
    parser.add_argument("--out", type=Path, default=Path("current.json"))
    parser.add_argument("--as-of", help="Closed session (defaults to modal last date)")
    args = parser.parse_args()
    frame, payload = scan(args.source, Config.from_json(args.config), args.as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
    frame.to_csv(args.out.with_suffix(".csv"), index=False)
    print(json.dumps({"as_of": payload["as_of"], "candidates": len(payload["candidates"]),
                      "states": payload["state_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
