from __future__ import annotations

import argparse, io, json, math, zipfile
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
    min_visit_span_sessions: int = 8
    decline_threshold_pct: float = 10.0
    decline_lookback_sessions: int = 50
    min_dollar_volume: float = 2_000_000
    near_floor_pct: float = 5.0
    watch_floor_pct: float = 10.0
    stop_floor_buffer_pct: float = 1.0
    atr_stop_fraction: float = 0.25
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

def atr20_arrays(high, low, close):
    h=high[-20:]; l=low[-20:]; c=close[-21:]
    if len(h)==0:return math.nan
    prev=c[:-1] if len(c)==len(h)+1 else np.r_[close[-len(h)-1], close[-len(h):-1]]
    tr=np.maximum(h-l,np.maximum(np.abs(h-prev),np.abs(l-prev)))
    return float(np.nanmean(tr))

def detect_episodes(dates, highs, lows, floor, cfg):
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
                if highs[i]>=reset: armed=True
            continue
        if (not armed) and highs[i]>=reset: armed=True
    if active is not None: eps.append(active)
    out=[]
    for j,(a,b,li,lv) in enumerate(eps):
        nxt=eps[j+1][0] if j+1<len(eps) else len(lows)
        if li+1<nxt:
            seg=highs[li+1:nxt]; rel=int(np.argmax(seg)); pi=li+1+rel; peak=float(highs[pi])
        else: pi=li; peak=lv
        bounce=100*(peak/lv-1)
        out.append({"start_idx":a,"end_idx":b,"low_idx":li,"low":lv,
            "start_date":str(pd.Timestamp(dates[a]).date()),"end_date":str(pd.Timestamp(dates[b]).date()),"test_date":str(pd.Timestamp(dates[li]).date()),
            "bounce_high":round(peak,6),"bounce_date":str(pd.Timestamp(dates[pi]).date()),"bounce_pct":round(bounce,2),
            "successful_rebound":bool(bounce+1e-9>=cfg.reset_pct)})
    return out,touching

def evaluate_window(d,start,cfg):
    n=len(d); x=d.iloc[start:]
    if len(x)<cfg.min_window_sessions:return None
    dates=x["Date"].to_numpy(); highs=x["High"].to_numpy(float); lows=x["Low"].to_numpy(float)
    floor=float(np.min(lows)); zone=floor*(1+cfg.floor_zone_pct/100)
    eps,touching=detect_episodes(dates,highs,lows,floor,cfg)
    if len(eps)<cfg.min_visits:return None
    span=max(1,eps[-1]["start_idx"]-eps[0]["start_idx"]+1)
    if span<cfg.min_visit_span_sessions:return None
    hist=eps[:-1]; succ=sum(e["successful_rebound"] for e in hist)
    if succ<cfg.min_successful_rebounds:return None
    reliability=succ/len(hist) if hist else 0.0
    first_abs=start+eps[0]["start_idx"]
    prior=d.iloc[max(0,first_abs-cfg.decline_lookback_sessions):first_abs+1]
    if len(prior)<10:return None
    prior_peak=float(prior["Close"].max()); decline=100*(1-floor/prior_peak)
    if decline<cfg.decline_threshold_pct:return None
    closes=d["Close"].to_numpy(float); volumes=d["Volume"].to_numpy(float)
    dv=float(np.median((closes*volumes)[-20:]));
    if dv<cfg.min_dollar_volume:return None
    current=d.iloc[-1]; previous=d.iloc[-2]
    close=float(current.Close); low=float(current.Low); dist=100*(close/floor-1); dist_zone=100*(close/zone-1)
    touch=low<=zone; age=(len(x)-1)-eps[-1]["end_idx"]
    vals=[e["bounce_pct"] for e in hist if e["successful_rebound"]]; med=float(np.median(vals)) if vals else 0.0
    density=len(eps)/span*20
    if touch: state="VISITANDO_SUELO"
    elif dist<=cfg.near_floor_pct: state="CERCA_DEL_SUELO"
    elif age<=5 and dist<=cfg.watch_floor_pct: state="REBOTE_RECIENTE"
    else: state="VIGILAR"
    high_all=d["High"].to_numpy(float); low_all=d["Low"].to_numpy(float)
    atr=atr20_arrays(high_all,low_all,closes)
    buffer=max(cfg.stop_floor_buffer_pct/100*floor,cfg.atr_stop_fraction*atr); stop=floor-buffer
    visits_score=min(40,5*len(eps)); density_score=min(15,5*density); rel_score=15*reliability
    prox_score=max(0,25-2.5*max(dist,0)); fresh_score=max(0,10-1.5*age); score=visits_score+density_score+rel_score+prox_score+fresh_score
    return {"score":round(score,2),"state":state,"as_of":str(pd.Timestamp(current.Date).date()),
        "range_start":str(pd.Timestamp(x.iloc[0].Date).date()),"range_sessions":int(len(x)),
        "first_visit":eps[0]["start_date"],"last_visit":eps[-1]["start_date"],"visit_span_sessions":int(span),
        "floor":round(floor,6),"floor_zone_high":round(zone,6),"floor_zone_pct":cfg.floor_zone_pct,
        "last_close":round(close,6),"day_low":round(low,6),"day_return_pct":round(100*(close/float(previous.Close)-1),2),
        "distance_to_floor_pct":round(dist,2),"distance_to_zone_pct":round(dist_zone,2),"current_touch":bool(touch),
        "current_episode_days":int(eps[-1]["end_idx"]-eps[-1]["start_idx"]+1 if touch else 0),"last_visit_age":int(age),
        "visit_count":int(len(eps)),"touching_days":int(touching),"visit_density_20":round(density,2),
        "successful_rebounds":int(succ),"historical_visits":int(len(hist)),"rebound_reliability_pct":round(100*reliability,1),
        "median_bounce_pct":round(med,2),"decline_pct":round(decline,2),"prior_peak":round(prior_peak,6),
        "median_dollar_volume_20":round(dv,2),"atr20":round(atr,6),"suggested_stop":round(stop,6),
        "stop_below_floor_pct":round(100*(1-stop/floor),2),"episodes":[{k:v for k,v in e.items() if not k.endswith("_idx")} for e in eps]}

def best_candidate(d,cfg):
    n=len(d); lengths=[25,35,50,70,90,cfg.search_sessions]; best=None
    for L in lengths:
        if n<cfg.min_window_sessions:break
        start=max(0,n-L); item=evaluate_window(d,start,cfg)
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
    cand.sort(key=lambda r:(-r["score"],-r["visit_count"],r["distance_to_floor_pct"],r["ticker"]))
    for i,r in enumerate(cand,1):r["rank"]=i
    states={}
    for r in cand:states[r["state"]]=states.get(r["state"],0)+1
    payload={"as_of":str(max(dates).date()) if dates else None,"strategy":{"name":"Repeated Floor Visits","floor_zone_pct":cfg.floor_zone_pct,
        "reset_pct":cfg.reset_pct,"decline_threshold_pct":cfg.decline_threshold_pct,
        "description":"Busca un mínimo estructural visitado repetidamente; cada nueva visita exige una separación previa de al menos 5%."},
        "universe":{"files_scanned":scanned,"valid_series":valid,"candidates":len(cand)},"state_counts":states,"candidates":cand,"config":asdict(cfg)}
    frame=pd.DataFrame([{k:v for k,v in r.items() if k!="episodes"} for r in cand]); return frame,payload

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--source",required=True,type=Path);ap.add_argument("--config",type=Path);ap.add_argument("--out",type=Path,default=Path("current.json"));a=ap.parse_args()
    cfg=Config.from_json(a.config) if a.config else Config(); frame,p=scan(a.source,cfg);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(p,ensure_ascii=False,allow_nan=False,separators=(",",":")));frame.to_csv(a.out.with_suffix(".csv"),index=False)
    print(json.dumps({"as_of":p["as_of"],"candidates":len(p["candidates"]),"states":p["state_counts"]},ensure_ascii=False))
if __name__=="__main__":main()
