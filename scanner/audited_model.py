#!/usr/bin/env python3
"""Independent, causal historical floor-range classifier for five shards.

All CSV rows through 2026-09-25 are read. A confirmed pivot uses two future
sessions relative to the low, but is only available as of its confirmation date.
Each snapshot uses rows dated at or before that date. Episode dates refer to
when the algorithm could have known the pattern, not to an ex-post optimum.
"""
from __future__ import annotations
import argparse, csv, io, zipfile, math
from collections import Counter
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
END='2026-09-25'
SHARD=2

def float_s(x): return round(float(x), 2)

def visits_for(cluster, high, floor, max_idx):
    """Cooldown plus an actual interim excursion separate consecutive contacts."""
    kept=[]
    for idx in sorted(cluster):
        if not kept: kept.append(idx); continue
        prior=kept[-1]
        if idx-prior>=2 and np.max(high[prior+1:idx+1]) >= floor*1.035:
            kept.append(idx)
        elif idx-prior>=6:
            kept.append(idx)
        elif idx-prior<=2 and len(kept)>0 and idx<=max_idx:
            # A lower local low in the same visit supersedes the earlier event.
            pass
    return kept

def classify_snapshot(date, low, high, close, pivots, end, discontinuity):
    # Anchor the base after the largest peak of the last 80 sessions. This
    # avoids blending an older range with a fresh post-selloff range.
    peak_start=max(0,end-80)
    if np.any(discontinuity[peak_start:end+1]): return None
    peak_idx=peak_start+int(np.argmax(high[peak_start:end-7])) if end-peak_start>12 else peak_start
    base_start=max(peak_idx+1,end-35)
    # A near-complete recovery toward the previous peak starts a new trading
    # regime. MUSA's Aug 18 rally is such a reset; APP's modest rebound is not.
    peak_value=float(high[peak_idx])
    recovery_peaks=[j for j in range(peak_idx+3,end-6)
                    if high[j]>=peak_value*.93 and high[j]>=max(high[j-2:j])
                    and high[j]>max(high[j+1:j+3])]
    if recovery_peaks: base_start=max(base_start,recovery_peaks[-1]+1)
    if end-base_start<12: return None
    event=list(range(base_start,end+1))
    proposals=[]
    for center_i in event:
        center=low[center_i]
        if not np.isfinite(center) or center<=0: continue
        # A narrow density mode excludes isolated 1.5–3% undercuts; the
        # lower low is evaluated separately for dip/recovery semantics.
        cl=[j for j in event if .988<=low[j]/center<=1.012]
        if len(cl)<3: continue
        support=float(np.median(low[cl]))
        # Keep the original narrow band. Recentering on its median can prune
        # a genuine lower contact when repeated days sit at the upper edge.
        visits=visits_for(cl,high,support,end)
        if len(visits)<3: continue
        first=visits[0]
        if end-first>80 or end-first<12: continue
        # The price had fallen into its first base contact; the peak is strictly earlier.
        peak=float(high[peak_idx]) if peak_idx<first else 0
        drop=1-support/peak if peak else 0
        if drop<.12: continue
        # Lower envelope of modal cluster, not the minimum of the chart.
        vlow=np.array([low[j] for j in visits]);
        lower=float(np.min(vlow)); upper=float(np.max(vlow))
        width=(upper-lower)/support
        if width>.022: continue
        # A recurring lower mode disproves the proposed (higher) floor.
        # One-off recovered undercuts remain possible dips.
        undercut_days=[j for j in range(first,end+1) if low[j]<lower*.987]
        undercut_visits=[]
        for j in undercut_days:
            if not undercut_visits or j-undercut_visits[-1]>=5:
                undercut_visits.append(j)
        if len(undercut_visits)>=2: continue
        # Reject drifting/downtrending levels, and require a usable range.
        ih=high[first:end+1]
        ceiling=float(np.quantile(ih,.78))
        room=ceiling/support-1
        if room<.04 or room>.45: continue
        bounced=[]
        for k,j in enumerate(visits):
            next_touch=visits[k+1] if k+1<len(visits) else end+1
            hi=min(j+11,next_touch,end+1)
            if hi<=j+1:
                bounced.append(False)
            else:
                bounced.append(float(np.max(close[j+1:hi]))/low[j]-1 >= .035)
        if sum(bounced[:-1])<2: continue
        # Require the modal support not to have been invalidated by persistent closes.
        closed_below=(close[first:end+1] < lower*.99)
        trailing=closed_below[-min(3,len(closed_below)):]
        broken=(close[end]<lower*.97) or (sum(trailing)>=2)
        sustained=any(bool(closed_below[k] and closed_below[k+1] and closed_below[k+2])
                      for k in range(len(closed_below)-2))
        if broken or sustained: continue
        # Detect recovered penetrations, never label sustained sub-support prices as dips.
        dips=[]; breaches=[]; recurrent=[]
        for j in range(first,end+1):
            if low[j] < lower*.987:
                if j>first and j-1>=first and low[j-1] < lower*.987 and close[j-1]<lower*.997:
                    continue
                # Recovery visible no later than this snapshot; intraday low + strong close qualifies.
                rec=[u for u in range(j,min(j+6,end+1)) if close[u]>=lower*.997]
                if not rec: continue
                rec_at=rec[0]
                below_count=int(np.sum(close[j:rec_at+1]<lower*.99))
                if below_count>=3: continue
                similar=[u for u in range(max(base_start,j-60),j+1)
                         if abs(low[u]/low[j]-1)<=.0035]
                if len(similar)>=3 and similar[-1]-similar[0]>=10:
                    recurrent.append((j,rec_at,float(low[j])))
                    continue
                (dips if below_count==0 and rec_at<=j+2 else breaches).append((j,rec_at,float(low[j])))
        # Once a third independent low confirms a lower repeated shelf,
        # previously provisional nearby dips are reclassified AS OF that
        # third contact, not on their original historical event date.
        if recurrent:
            repeated_low=min(x[2] for x in recurrent)
            dips=[x for x in dips if abs(x[2]/repeated_low-1)>.0035]
            breaches=[x for x in breaches if abs(x[2]/repeated_low-1)>.0035]
        # Exclude a materially newer, much lower mode (old floor broken).
        score= len(visits)*2 + sum(bounced) + max(0, 1-width/.022) - (end-visits[-1])*.025
        proposals.append(dict(score=score, first=first, last=visits[-1], end=end,
            floor=lower, floor_high=upper, mode=support, min=float(np.min(low[first:end+1])),
            ceiling=ceiling, visits=len(visits), bounces=sum(bounced), drop=drop,
            dip=dips, breach=breaches, lower_recurrent=recurrent, room=room))
    if not proposals: return None
    proposals.sort(key=lambda p:(p['score'],p['last']),reverse=True)
    best=proposals[0]
    # When two close horizontal shelves both qualify, the repeatedly defended
    # lower shelf is the trade floor; upper contacts are secondary resistance.
    comparable=[p for p in proposals if p['score']>=best['score']-3 and p['mode']>=best['mode']*.965]
    return min(comparable,key=lambda p:(p['mode'],-p['score']))

def classify_file(name,zf):
    ticker=Path(name).stem
    df=pd.read_csv(io.BytesIO(zf.read(name)),usecols=['Date','Open','High','Low','Close','Adj Close','Volume'])
    df=df[(df.Date>='2015-01-01')&(df.Date<=END)].sort_values('Date').drop_duplicates('Date')
    df=df.dropna(subset=['Open','High','Low','Close']); df=df[(df.Low>0)&(df.High>=df.Low)&(df.Close>0)]
    if df.empty: return ticker,[],dict(ticker=ticker,rows=0,first_date='',last_date='',patterns=0,note='no_valid_rows')
    d=df.Date.to_numpy(); low=df.Low.to_numpy(float); high=df.High.to_numpy(float); close=df.Close.to_numpy(float); opening=df.Open.to_numpy(float)
    n=len(df)
    factor=df['Adj Close'].to_numpy(float)/close
    factor_prev=np.roll(factor,1)
    shift=np.isfinite(factor)&np.isfinite(factor_prev)&(factor>0)&(factor_prev>0)
    ratio=np.ones(n); ratio[shift]=factor[shift]/factor_prev[shift]
    adjustment_jump=np.abs(np.log(ratio))>np.log(1.15)
    calendar_dates=pd.to_datetime(d)
    calendar_gap=(calendar_dates.to_series(index=range(n)).diff().dt.days.fillna(0).to_numpy()>14)
    adjustment_jump[0]=False
    # An internally inconsistent/extreme daily bar can manufacture a false
    # floor even when Adj Close and Close share the same (bad) adjustment.
    with np.errstate(divide='ignore',invalid='ignore'):
        bar_span=high/low
        intraday_change=np.maximum(opening/close,close/opening)
    extreme_ohlc=(bar_span>1.5)|(intraday_change>1.5)|(~np.isfinite(intraday_change))
    discontinuity=adjustment_jump|calendar_gap|extreme_ohlc
    # Evaluate at each confirmed local low, but support visits may be any
    # session in the lookback (including a low preceding a deeper wick).
    pivots=[i for i in range(2,n-2) if low[i]<=min(low[i-2:i]) and low[i]<min(low[i+1:i+3])]
    snapshots=[]
    dates=sorted(set([i+2 for i in pivots if i+2>=75]+([n-1] if n>=75 else [])))
    skipped_due_discontinuity=0
    for end in dates:
        if np.any(discontinuity[max(0,end-80):end+1]):
            skipped_due_discontinuity+=1
            continue
        p=classify_snapshot(d,low,high,close,pivots,end,discontinuity)
        if p: snapshots.append(p)
    # Deduplicate snapshots into episodes; retain first causal alert and strongest evidence.
    episodes=[]
    for p in snapshots:
        if (episodes and p['end']-episodes[-1]['seen_end']<=22
            and abs(p['mode']/episodes[-1]['best']['mode']-1)<=.035
            and abs(p['first']-episodes[-1]['first_contact'])<=10):
            ep=episodes[-1]; ep['seen_end']=p['end']
            ep['best']=p  # most recent observable state, never an obsolete best score
        else:
            episodes.append(dict(alert=p['end'],seen_end=p['end'],first_contact=p['first'],best=p))
    out=[]
    for ep in episodes:
        p=ep['best']; alert=ep['alert']; seen=ep['seen_end']; status='historical'
        if n-1-seen<=10: status='recent'
        # Once a formed pattern is broken, record the first date known to have invalidated it.
        threshold=p['floor']*.99
        break_date=''
        discontinuity_date=''
        for j in range(seen+1,n):
            if discontinuity[j]:
                discontinuity_date=str(d[j]); status='data_discontinuity';break
            recent_closes=close[max(ep['first_contact'],j-2):j+1]
            if close[j]<p['floor']*.97 or np.sum(recent_closes<threshold)>=2:
                break_date=str(d[j]); status='broken_later';break
        # A one-session wick can be certified the day it closes back above support.
        dips=p['dip']; breaches=p['breach']
        lower_recurrent=p['lower_recurrent']
        principal=min(dips,key=lambda x:x[2]) if dips else None
        temporal=min(breaches,key=lambda x:x[2]) if breaches else None
        lower_contact=min(lower_recurrent,key=lambda x:x[2]) if lower_recurrent else None
        gap=(p['floor']-p['min'])/p['floor']
        conf=min(.95,max(.40,.4+.07*(p['visits']-3)+.05*(p['bounces']-2)+.1*min(p['drop']/.2,1)-.03*(len(breaches)>0)))
        out.append(dict(ticker=ticker,first_contact=str(d[ep['first_contact']]),first_detectable=str(d[alert]),last_confirmed=str(d[seen]),snapshot=str(d[p['end']]),
         modal_floor_low=float_s(p['floor']),modal_floor_high=float_s(p['floor_high']),modal_floor_center=float_s(p['mode']),absolute_min=float_s(p['min']),
         extreme_gap_pct=round(100*gap,2),recovered_wick_dip_date=str(d[principal[0]]) if principal else '',
         recovered_wick_dip_low=float_s(principal[2]) if principal else '',recovered_wick_dip_recovery=str(d[principal[1]]) if principal else '',
         temporary_breach_date=str(d[temporal[0]]) if temporal else '',temporary_breach_low=float_s(temporal[2]) if temporal else '',
         temporary_breach_recovery=str(d[temporal[1]]) if temporal else '',visits=p['visits'],prior_bounces=p['bounces'],
         lower_repeated_contact_date=str(d[lower_contact[0]]) if lower_contact else '',
         lower_repeated_contact_low=float_s(lower_contact[2]) if lower_contact else '',
         prior_drop_pct=round(100*p['drop'],1),ceiling=float_s(p['ceiling']),room_pct=round(100*p['room'],1),
         status=status,break_confirmed=break_date,discontinuity_date=discontinuity_date,
         confidence=round(conf,2),reason='cluster_of_confirmed_lows_and_two_bounces',
         classification_asof=str(d[p['end']])))
    return ticker,out,dict(ticker=ticker,rows=n,first_date=str(d[0]),last_date=str(d[-1]),patterns=len(out),
        adjustment_jump_bars=int(adjustment_jump.sum()),calendar_gap_bars=int(calendar_gap.sum()),
        extreme_ohlc_bars=int(extreme_ohlc.sum()),discontinuity_bars=int(discontinuity.sum()),
        skipped_candidate_dates=skipped_due_discontinuity,note='')

def main():
    global END
    parser=argparse.ArgumentParser()
    parser.add_argument('--shard',type=int,choices=range(5))
    parser.add_argument('--ticker',action='append',help='targeted validation')
    parser.add_argument('--date',default=END)
    args=parser.parse_args()
    if args.shard is None and not args.ticker:
        parser.error('specify --shard 0..4 or --ticker SYMBOL')
    END=args.date
    with zipfile.ZipFile(ROOT/'data/prices.zip') as zf:
        names=sorted(n for n in zf.namelist() if n.startswith('prices/') and n.endswith('.csv') and '.ipynb_checkpoints' not in n)
        wanted={x.upper() for x in args.ticker or []}
        own=[n for i,n in enumerate(names) if (args.shard is not None and i%5==args.shard)
             or Path(n).stem in wanted]
        assert len(names)==2431,len(names)
        rows=[]; coverage=[]
        for k,name in enumerate(own,1):
            try:
                _,res,cov=classify_file(name,zf);rows.extend(res);coverage.append(cov)
            except Exception as ex:
                coverage.append(dict(ticker=Path(name).stem,rows=0,first_date='',last_date='',patterns=0,note=f'ERROR:{type(ex).__name__}:{ex}'))
            if k%80==0: print(f'{k}/{len(own)} tickers; {len(rows)} patterns',flush=True)
    out=ROOT/'analysis'
    label=f'shard_{args.shard}_unified' if args.shard is not None else 'unified_validation'
    pd.DataFrame(rows).to_csv(out/f'{label}.csv',index=False)
    pd.DataFrame(coverage).to_csv(out/f'{label}_coverage.csv',index=False)
    print(f'Done: {len(own)} tickers, {sum(x["rows"] for x in coverage)} rows, {len(rows)} patterns, errors {sum(bool(x["note"]) for x in coverage)}')
    for t in sorted(wanted):
        print(t,[r for r in rows if r['ticker']==t][-2:])
if __name__=='__main__': main()
