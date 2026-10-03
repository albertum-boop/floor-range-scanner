"""Download finalized daily bars and publish a validated Floor Visit snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import time

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scanner"))
from scanner import Config, REQUIRED, clean_prices, scan


def latest_completed_session(now=None):
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    if current.tzinfo is None:
        raise ValueError("now must include a time zone")
    current = current.tz_convert("America/New_York")
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=(current - pd.Timedelta(days=20)).date(), end_date=current.date()
    )
    # Like the existing scanners, wait until 18:00 ET even on early closes.
    finalizations = pd.DatetimeIndex(schedule.index).tz_localize("America/New_York") + pd.Timedelta(hours=18)
    eligible = schedule.loc[(finalizations <= current) & (schedule.market_close <= current)]
    if eligible.empty:
        raise RuntimeError("No finalized NYSE session found")
    return pd.Timestamp(eligible.index[-1]).tz_localize(None).normalize()


def load_universe(path):
    payload = json.loads(Path(path).read_text())
    symbols = sorted(set(payload["symbols"]))
    if not symbols or any(not re.fullmatch(r"[A-Z0-9^-]+", s) for s in symbols):
        raise ValueError("Invalid or empty ticker universe")
    return symbols


def split_download(downloaded, symbols):
    if downloaded is None or downloaded.empty:
        return {}
    if not isinstance(downloaded.columns, pd.MultiIndex):
        return {symbols[0]: downloaded} if len(symbols) == 1 else {}
    for level in (0, 1):
        available = set(downloaded.columns.get_level_values(level))
        if any(s in available for s in symbols):
            return {s: downloaded.xs(s, axis=1, level=level) for s in symbols if s in available}
    return {}


def finalized_prices(raw, cutoff, sessions):
    data = raw.copy()
    index = pd.to_datetime(data.index, errors="coerce")
    if index.tz is not None:
        index = index.tz_localize(None)
    data["Date"] = index.normalize()
    data = data.reset_index(drop=True)
    data = data.replace([np.inf, -np.inf], np.nan)
    data = clean_prices(data)
    data = data.loc[data.Date.isin(sessions) & (data.Date <= cutoff)].reset_index(drop=True)
    if len(data) < 60:
        raise ValueError("fewer than 60 valid daily bars")
    if data.Date.iloc[-1] != cutoff:
        raise ValueError("latest finalized session missing")
    recent = sessions[-60:]
    if len(set(recent) - set(data.Date)):
        raise ValueError("missing or invalid bar in the last 60 sessions")
    return data


def download_histories(symbols, cutoff, directory, batch_size=80, retries=3):
    start = cutoff - pd.Timedelta(days=400)
    sessions = pd.DatetimeIndex(mcal.get_calendar("NYSE").schedule(
        start_date=start.date(), end_date=cutoff.date()
    ).index).tz_localize(None)
    good, errors = set(), {}
    for offset in range(0, len(symbols), batch_size):
        pending = symbols[offset:offset + batch_size]
        for attempt in range(retries):
            try:
                # Fetch the whole analysis window to incorporate split corrections.
                # Crop locally so an in-progress bar can never become a signal.
                raw = yf.download(pending, start=start.date().isoformat(), interval="1d",
                    auto_adjust=False, actions=False, group_by="ticker", threads=8,
                    progress=False, timeout=25, prepost=False)
                pieces = split_download(raw, pending)
            except Exception as exc:
                pieces = {}
                for symbol in pending:
                    errors[symbol] = type(exc).__name__
            failed = []
            for symbol in pending:
                try:
                    if symbol not in pieces:
                        raise ValueError("no data returned")
                    frame = finalized_prices(pieces[symbol], cutoff, sessions)
                    frame.to_csv(directory / f"{symbol}.csv", index=False)
                    good.add(symbol)
                    errors.pop(symbol, None)
                except (KeyError, TypeError, ValueError) as exc:
                    errors[symbol] = str(exc)
                    failed.append(symbol)
            pending = failed
            if not pending:
                break
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
        print(f"Downloaded {min(offset + batch_size, len(symbols))}/{len(symbols)}; valid {len(good)}", flush=True)
        # Stop early if the feed is entirely unavailable; preserve the published data.
        if offset == 0 and not good:
            raise RuntimeError(f"No usable histories in first batch: {dict(list(errors.items())[:5])}")
    return good, errors


def publish_snapshot(directory, output, symbols, good, errors, cutoff, now, minimum_coverage, fingerprint):
    coverage = len(good) / len(symbols)
    if coverage < minimum_coverage:
        raise RuntimeError(f"Coverage {coverage:.1%} below {minimum_coverage:.0%}; previous snapshot retained")
    expected = cutoff.date().isoformat()
    frame, payload = scan(directory, Config.from_json(ROOT / "scanner/config.json"), as_of=expected)
    if payload["as_of"] != expected or any(row["as_of"] != expected for row in payload["candidates"]):
        raise RuntimeError("Snapshot contains an incorrect market date")
    quality = {"expected_session": expected, "requested": len(symbols), "valid": len(good),
        "excluded": len(errors), "coverage_pct": round(100 * coverage, 2), "excluded_symbols": errors}
    payload.update(generated_at=now.isoformat(), data_source="Yahoo Finance",
        price_basis="Yahoo daily OHLCV; auto_adjust=False", quality=quality,
        refresh={"timezone": "Europe/Madrid", "time": "02:00", "fingerprint": fingerprint})
    payload["universe"].update(files_scanned=len(symbols), valid_series=len(good),
        scope="Full universe; stocks and ETFs", excluded_series=len(errors))
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    csv_text = frame.to_csv(index=False) if not frame.empty else "ticker,as_of,state\n"
    output.mkdir(parents=True, exist_ok=True)
    # All validations and serialization finish before replacing either public file.
    for name, body in {"current.json": encoded, "current.csv": csv_text}.items():
        temporary = output / (name + ".pending")
        temporary.write_text(body, encoding="utf-8")
        temporary.replace(output / name)
    print(json.dumps({"as_of": expected, "patterns": len(frame), "coverage_pct": quality["coverage_pct"]}), flush=True)
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", type=Path, default=ROOT / "scanner/universe.json")
    parser.add_argument("--output", type=Path, default=ROOT / "public/data")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the finalized session is already published")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    cutoff = latest_completed_session(now)
    symbols = load_universe(args.universe)
    fingerprint = hashlib.sha256(args.universe.read_bytes() + (ROOT / "scanner/config.json").read_bytes()
        + (ROOT / "scanner/scanner.py").read_bytes()
        + (ROOT / "scanner/audited_model.py").read_bytes()
        + Path(__file__).read_bytes()).hexdigest()
    current = args.output / "current.json"
    if current.exists():
        previous = json.loads(current.read_text())
        if previous.get("as_of", "") > cutoff.date().isoformat():
            raise RuntimeError("Refusing to replace a newer snapshot")
        if not args.force and previous.get("as_of") == cutoff.date().isoformat() and previous.get("refresh", {}).get("fingerprint") == fingerprint:
            print(f"No new finalized session after {cutoff.date()}; nothing to publish")
            return
    with tempfile.TemporaryDirectory(prefix="floor-prices-") as temporary:
        directory = Path(temporary)
        good, errors = download_histories(symbols, cutoff, directory)
        publish_snapshot(directory, args.output, symbols, good, errors, cutoff, now, 0.95, fingerprint)


if __name__ == "__main__":
    main()
