from __future__ import annotations

import argparse, io, json, zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED = ["Date","Open","High","Low","Close","Volume"]

@dataclass(frozen=True)
class Config:
    floor_zone_pct: float = 3.5
    reset_pct: float = 5.0
    search_sessions: int = 110
    min_window_sessions: int = 15
    min_visits: int = 3
    min_successful_rebounds: int = 2
    recent_visit_sessions: int = 40
    max_visit_gap_sessions: int = 12
    min_visit_span_sessions: int = 15
    decline_threshold_pct: float = 12.0
    decline_lookback_sessions: int = 20
    min_median_regime_drop_pct: float = 8.0
    floor_cluster_pct: float = 3.5
    floor_wick_buffer_pct: float = 1.0
    max_later_floor_wick_breaches: int = 1
    max_range_width_pct: float = 25.0
    max_trend_drift_pct: float = 8.0
    max_trend_fraction_of_range: float = 0.5
    bounce_window_sessions: int = 5
    min_dollar_volume: float = 2_000_000
    near_floor_pct: float = 5.0
    @classmethod
    def from_json(cls, path): return cls(**json.loads(Path(path).read_text()))

def clean_prices(raw):
    if not set(REQUIRED).issubset(raw.columns): return pd.DataFrame(columns=REQUIRED)
    d=raw[REQUIRED].copy(); d["Date"]=pd.to_datetime(d["Date"],errors="coerce")
    for c in REQUIRED[1:]: d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna().sort_values("Date").drop_duplicates("Date",keep="last")
    ok=((d[["Open","High","Low","Close"]]>0).all(axis=1)&(d["Volume"]>=0)&
        (d["High"]>=d[["Open","Low","Close"]].max(axis=1))&
        (d["Low"]<=d[["Open","High","Close"]].min(axis=1)))
    return d.loc[ok].reset_index(drop=True)

def detect_episodes(dates, highs, lows, closes, floor, cfg):
    zone=floor*(1+cfg.floor_zone_pct/100); reset=floor*(1+cfg.reset_pct/100)
    eps=[]; active=None; armed=True; touching=0
    for i in range(len(lows)):
        touch=lows[i] <= zone
        touching += int(touch)
        if armed and touch and active is None:
            active=[i,i,i,float(lows[i])]; armed=False; continue
        if active is not None:
            if touch:
                active[1]=i
                if lows[i]<active[3]: active[2]=i; active[3]=float(lows[i])
            else:
                eps.append(active); active=None
                if closes[i]>=reset: armed=True
            continue
        if (not armed) and closes[i]>=reset: armed=True
    if active is not None: eps.append(active)
    out=[]
    for j,(a,b,li,lv) in enumerate(eps):
        nxt=eps[j+1][0] if j+1<len(eps) else len(lows)
        horizon=min(nxt,li+1+cfg.bounce_window_sessions)
        if li+1<horizon:
            seg=highs[li+1:horizon]; rel=int(np.argmax(seg)); pi=li+1+rel; peak=float(highs[pi])
            close_peak=float(np.max(closes[li+1:horizon]))
        else: pi=li; peak=lv; close_peak=lv
        bounce=100*(peak/lv-1)
        close_bounce=100*(close_peak/lv-1)
        out.append({"start_idx":a,"end_idx":b,"low_idx":li,"low":lv,
            "start_date":str(pd.Timestamp(dates[a]).date()),"end_date":str(pd.Timestamp(dates[b]).date()),"test_date":str(pd.Timestamp(dates[li]).date()),
            "bounce_high":round(peak,6),"bounce_date":str(pd.Timestamp(dates[pi]).date()),"bounce_pct":round(bounce,2),
            "bounce_close_pct":round(close_bounce,2),
            "successful_rebound":bool(bounce+1e-9>=cfg.reset_pct),
            "close_confirmed_rebound":bool(close_bounce+1e-9>=cfg.reset_pct)})
    return out,touching

def evaluate_window(d,start,cfg):
    n=len(d); x=d.iloc[start:]
    if len(x)<cfg.min_window_sessions:return None
    dates=x["Date"].to_numpy(); highs=x["High"].to_numpy(float); lows=x["Low"].to_numpy(float)
    # Establish the support from the FIRST TWO independent tests. Never move it
    # down to the latest low: a later close underneath invalidates this base.
    initial_floor=float(lows[0])
    prior=d.iloc[max(0,start-cfg.decline_lookback_sessions):start]
    if len(prior)<10:return None
    prior_peak=float(prior["Close"].max())
    decline=100*(1-initial_floor/prior_peak)
    if decline<cfg.decline_threshold_pct:return None
    base_closes=x["Close"].to_numpy(float)
    # A wick alone cannot establish the fall. The base starts with a daily
    # close at least as far below the prior peak as the decline threshold.
    closing_decline=100*(1-base_closes[0]/prior_peak)
    if closing_decline<cfg.decline_threshold_pct:return None
    # The fall must leave a lower price regime, not just one low wick inside a
    # higher trading area (a common topping/distribution false positive).
    regime_drop=100*(1-float(np.median(base_closes))/prior_peak)
    if regime_drop<cfg.min_median_regime_drop_pct:return None
    initial_eps,_=detect_episodes(dates,highs,lows,base_closes,initial_floor,cfg)
    if len(initial_eps)<cfg.min_visits:return None
    seed=initial_eps[:2]
    if not all(e["successful_rebound"] for e in seed):return None
    seed_lows=[e["low"] for e in seed]
    if 100*(max(seed_lows)/min(seed_lows)-1)>cfg.floor_cluster_pct:return None
    floor=float(min(seed_lows)); zone=floor*(1+cfg.floor_zone_pct/100)
    eps,touching=detect_episodes(dates,highs,lows,base_closes,floor,cfg)
    if len(eps)<cfg.min_visits:return None
    if eps[0]["start_idx"]!=0:return None
    # One lower wick is tolerated. Repeated independent breaks below the first
    # two visits mean the apparent floor is drifting lower.
    first_two_floor=min(e["low"] for e in eps[:2])
    later_floor_breaches=sum(e["low"]<first_two_floor*(1-cfg.floor_wick_buffer_pct/100) for e in eps[2:])
    if later_floor_breaches>cfg.max_later_floor_wick_breaches:return None
    # A floor revisited after a long hiatus is not an actively ranging floor.
    if any(b["start_idx"]-a["end_idx"]>cfg.max_visit_gap_sessions for a,b in zip(eps,eps[1:])):return None
    test_lows=[e["low"] for e in eps]
    floor_spread=100*(max(test_lows)/min(test_lows)-1)
    if floor_spread>cfg.floor_cluster_pct:return None
    if np.any(base_closes < floor*(1-1e-8)):return None
    # A lower floor in the final third signals deterioration, even if the
    # individual contacts still fit the broad visit band.
    thirds=np.array_split(lows,3)
    lower_band_drift=100*(np.quantile(thirds[-1],.2)/np.quantile(thirds[0],.2)-1)
    if lower_band_drift < -cfg.floor_cluster_pct:return None
    ceiling=float(np.quantile(highs,.85))
    width=100*(ceiling/floor-1)
    if width<cfg.reset_pct or width>cfg.max_range_width_pct:return None
    drift=100*float(np.expm1(np.polyfit(np.arange(len(base_closes)),np.log(base_closes),1)[0]*(len(base_closes)-1)))
    if abs(drift)>min(cfg.max_trend_drift_pct,width*cfg.max_trend_fraction_of_range):return None
    if base_closes[-1]>ceiling*1.02:return None
    span=max(1,eps[-1]["start_idx"]-eps[0]["start_idx"]+1)
    if span<cfg.min_visit_span_sessions:return None
    # Old tests cannot validate an active trading range indefinitely. Demand
    # repeated, successful interactions in the most recent eight trading weeks.
    recent_eps=[e for e in eps if e["start_idx"]>=max(0,len(x)-cfg.recent_visit_sessions)]
    recent_success=sum(e["successful_rebound"] for e in recent_eps[:-1])
    if len(recent_eps)<cfg.min_visits or recent_success<cfg.min_successful_rebounds:return None
    hist=eps[:-1]; succ=sum(e["successful_rebound"] for e in hist)
    if succ<cfg.min_successful_rebounds:return None
    reliability=succ/len(hist) if hist else 0.0
    closes=d["Close"].to_numpy(float); volumes=d["Volume"].to_numpy(float)
    dv=float(np.median((closes*volumes)[-20:]));
    if dv<cfg.min_dollar_volume:return None
    current=d.iloc[-1]; previous=d.iloc[-2]
    close=float(current.Close); low=float(current.Low); dist=100*(close/floor-1); dist_zone=100*(close/zone-1)
    touch=low<=zone; age=(len(x)-1)-eps[-1]["end_idx"]
    vals=[e["bounce_pct"] for e in hist if e["successful_rebound"]]; med=float(np.median(vals)) if vals else 0.0
    close_confirmed=sum(e["close_confirmed_rebound"] for e in hist)
    density=len(eps)/span*20
    if touch and close<=zone: state="VISITANDO_SUELO"
    elif dist<=cfg.near_floor_pct: state="CERCA_DEL_SUELO"
    else: state="EN_RANGO"
    lowest_wick=float(np.min(lows))
    # Structural evidence and distance are deliberately independent. A nearby
    # floor does not make a weak range more convincing.
    stable_limit=min(cfg.max_trend_drift_pct,width*cfg.max_trend_fraction_of_range)
    score=(25*min(1,len(x)/35)+25*min(1,span/30)+15*reliability
           +5*close_confirmed/max(1,len(hist))
           +20*max(0,1-abs(drift)/stable_limit)
           +10*max(0,1-floor_spread/cfg.floor_cluster_pct))
    return {"score":round(score,2),"pattern_score":round(score,2),"state":state,"as_of":str(pd.Timestamp(current.Date).date()),
        "range_validated":True,"ceiling":round(ceiling,6),"range_width_pct":round(width,2),
        "trend_drift_pct":round(drift,2),"floor_test_spread_pct":round(floor_spread,2),
        "lower_band_drift_pct":round(lower_band_drift,2),"median_regime_drop_pct":round(regime_drop,2),
        "later_floor_wick_breaches":int(later_floor_breaches),
        "support_confirmed_at":eps[1]["bounce_date"],
        "chart":[{"date":str(pd.Timestamp(r.Date).date()),"open":round(float(r.Open),6),"close":round(float(r.Close),6),"high":round(float(r.High),6),"low":round(float(r.Low),6)} for r in d.iloc[max(0,start-15):].itertuples()],
        "range_start":str(pd.Timestamp(x.iloc[0].Date).date()),"range_sessions":int(len(x)),
        "first_visit":eps[0]["start_date"],"last_visit":eps[-1]["start_date"],"visit_span_sessions":int(span),
        "floor":round(floor,6),"floor_zone_high":round(zone,6),"floor_zone_pct":cfg.floor_zone_pct,
        "last_close":round(close,6),"day_low":round(low,6),"day_return_pct":round(100*(close/float(previous.Close)-1),2),
        "distance_to_floor_pct":round(dist,2),"distance_to_zone_pct":round(dist_zone,2),"current_touch":bool(touch),
        "current_episode_days":int(eps[-1]["end_idx"]-eps[-1]["start_idx"]+1 if touch else 0),"last_visit_age":int(age),
        "visit_count":int(len(eps)),"touching_days":int(touching),"visit_density_20":round(density,2),
        "recent_visit_count":len(recent_eps),"recent_visit_sessions":cfg.recent_visit_sessions,
        "max_visit_gap_sessions":cfg.max_visit_gap_sessions,
        "recent_successful_rebounds":int(recent_success),
        "successful_rebounds":int(succ),"close_confirmed_rebounds":int(close_confirmed),
        "historical_visits":int(len(hist)),"rebound_reliability_pct":round(100*reliability,1),
        "median_bounce_pct":round(med,2),"decline_pct":round(decline,2),
        "closing_decline_pct":round(closing_decline,2),"prior_peak":round(prior_peak,6),
        "median_dollar_volume_20":round(dv,2),"lowest_wick":round(lowest_wick,6),
        "episodes":[{k:v for k,v in e.items() if not k.endswith("_idx")} for e in eps]}

def best_candidate(d,cfg):
    n=len(d); best=None; lows=d.Low.to_numpy(float)
    # Candidate bases begin at an observed pivot AFTER the decline, not at an
    # arbitrary rolling-window boundary that can include the decline itself.
    for start in range(max(10,n-cfg.search_sessions),n-cfg.min_window_sessions+1):
        if lows[start]>lows[start-1] or lows[start]>lows[start+1]:continue
        if np.min(lows[start:])<lows[start]/(1+cfg.floor_cluster_pct/100):continue
        item=evaluate_window(d,start,cfg)
        if item is None:continue
        key=(item["score"],item["visit_count"],-item["range_sessions"])
        if best is None or key>(best["score"],best["visit_count"],-best["range_sessions"]):best=item
    return best

def iter_frames(source):
    if source.is_dir():
        for p in sorted(source.glob("*.csv")):
            try:yield p.stem.upper(),pd.read_csv(p)
            except:pass
    else:
        with zipfile.ZipFile(source) as zf:
            for name in sorted(zf.namelist()):
                if not name.startswith("prices/") or name.count("/")!=1 or not name.lower().endswith(".csv"):continue
                try:yield Path(name).stem.upper(),pd.read_csv(io.BytesIO(zf.read(name)))
                except:pass

def scan(source,cfg):
    cand=[]; scanned=valid=0; dates=[]
    for ticker,raw in iter_frames(source):
        scanned+=1; d=clean_prices(raw)
        if len(d)<60:continue
        valid+=1; dates.append(d.Date.iloc[-1]); item=best_candidate(d,cfg)
        if item:item["ticker"]=ticker; cand.append(item)
    cand.sort(key=lambda r:(-r["pattern_score"],r["distance_to_floor_pct"],r["ticker"]))
    for i,r in enumerate(cand,1):r["rank"]=i
    states={}
    for r in cand:states[r["state"]]=states.get(r["state"],0)+1
    payload={"as_of":str(max(dates).date()) if dates else None,"strategy":{"name":"Validated Post-Decline Ranges","version":8,"floor_zone_pct":cfg.floor_zone_pct,
        "reset_pct":cfg.reset_pct,"decline_threshold_pct":cfg.decline_threshold_pct,
        "description":"Caída seguida de rango con suelo repetido. La tendencia anterior a la caída no limita la selección. Salida descriptiva: niveles, visitas y distancia al suelo."},
        "universe":{"files_scanned":scanned,"valid_series":valid,"candidates":len(cand)},"state_counts":states,"candidates":cand,"config":asdict(cfg)}
    frame=pd.DataFrame([{k:v for k,v in r.items() if k not in {"episodes","chart"}} for r in cand]); return frame,payload

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--source",required=True,type=Path);ap.add_argument("--config",type=Path);ap.add_argument("--out",type=Path,default=Path("current.json"));a=ap.parse_args()
    cfg=Config.from_json(a.config) if a.config else Config(); frame,p=scan(a.source,cfg);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(p,ensure_ascii=False,allow_nan=False,separators=(",",":")));frame.to_csv(a.out.with_suffix(".csv"),index=False)
    print(json.dumps({"as_of":p["as_of"],"candidates":len(p["candidates"]),"states":p["state_counts"]},ensure_ascii=False))
if __name__=="__main__":main()
