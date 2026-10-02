const LABELS={VISITANDO_SUELO:"Visitando suelo",CERCA_DEL_SUELO:"Cerca del suelo",EN_RANGO:"En rango"};
const REF=new Set(["SES","APP","SGI"]);let DATA=null;
const $=id=>document.getElementById(id);
function money(v){const d=v<1?4:v<10?3:2;return new Intl.NumberFormat("es-ES",{style:"currency",currency:"USD",minimumFractionDigits:d,maximumFractionDigits:d}).format(v)}
function pct(v,s=false){return `${s&&v>0?"+":""}${Number(v).toLocaleString("es-ES",{minimumFractionDigits:1,maximumFractionDigits:1})}%`}
function date(v){const [y,m,d]=v.split("-");return `${d}/${m}/${y}`}
function compact(v){return new Intl.NumberFormat("es-ES",{notation:"compact",maximumFractionDigits:1}).format(v)}
function status(s){return `<span class="status s-${s.toLowerCase()}">${LABELS[s]}</span>`}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function rangeChart(x){
  if(!x.chart?.length)return '';
  const W=580,H=230,left=12,right=72,top=20,bottom=30;
  const values=x.chart.flatMap(p=>[p.low,p.high]);values.push(x.floor,x.ceiling);
  const lo=Math.min(...values)*.98,hi=Math.max(...values)*1.02;
  const px=i=>left+i*(W-left-right)/Math.max(1,x.chart.length-1);
  const py=v=>top+(hi-v)/(hi-lo)*(H-top-bottom);
  const start=Math.max(0,x.chart.findIndex(p=>p.date>=x.range_start));
  const points=x.chart.map((p,i)=>`${px(i).toFixed(1)},${py(p.close).toFixed(1)}`).join(' ');
  const wicks=x.chart.map((p,i)=>`<line x1="${px(i)}" x2="${px(i)}" y1="${py(p.low)}" y2="${py(p.high)}" stroke="#b2c0bd"><title>${p.date}: ${money(p.close)}</title></line>`).join('');
  return `<section class="range-chart"><h3>Precio diario y rango detectado</h3><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico diario de ${esc(x.ticker)}, suelo y techo del rango"><rect x="${px(start)}" y="${py(x.ceiling)}" width="${W-right-px(start)}" height="${py(x.floor)-py(x.ceiling)}" fill="#e4f1ea"/>${wicks}<polyline fill="none" stroke="#183d38" stroke-width="2" points="${points}"/><line x1="${px(start)}" x2="${W-right}" y1="${py(x.floor)}" y2="${py(x.floor)}" stroke="#248757" stroke-dasharray="5 4"/><line x1="${px(start)}" x2="${W-right}" y1="${py(x.ceiling)}" y2="${py(x.ceiling)}" stroke="#a57127" stroke-dasharray="5 4"/><text x="${W-right+5}" y="${py(x.floor)+4}" font-size="10" fill="#248757">F ${x.floor.toFixed(2)}</text><text x="${W-right+5}" y="${py(x.ceiling)+4}" font-size="10" fill="#a57127">T ${x.ceiling.toFixed(2)}</text><text x="${left}" y="${H-5}" font-size="10">${date(x.chart[0].date)}</text><text x="${W-right}" y="${H-5}" text-anchor="end" font-size="10">${date(x.as_of)}</text></svg><p>La línea une cierres; las barras muestran mínimos y máximos. Verde: rango desde ${date(x.range_start)}.</p><p><b>Amplitud:</b> ${pct(x.range_width_pct)} · <b>Deriva del precio:</b> ${pct(x.trend_drift_pct,true)} · <b>Dispersión de pruebas:</b> ${pct(x.floor_test_spread_pct)}</p></section>`;
}
function showDrawer(x){
  const a=new Date(x.first_visit).getTime(),b=new Date(x.as_of).getTime(),span=Math.max(1,b-a);
  const dots=x.episodes.map((e,i)=>{const p=Math.max(1,Math.min(99,100*(new Date(e.test_date).getTime()-a)/span));return `<i class="visit ${e.successful_rebound?"success":"pending"}" style="left:${p}%" title="${e.test_date} · ${pct(e.bounce_pct,true)}"></i>`}).join("");
  const eps=x.episodes.map(e=>`<div class="episode-row"><span>${date(e.test_date)}</span><strong>${money(e.low)}</strong><b class="${e.successful_rebound?"ok":"pending-text"}">${pct(e.bounce_pct,true)}<small>cierre ${pct(e.bounce_close_pct||0,true)}</small></b><span>${money(e.bounce_high)}</span></div>`).join("");
  $("drawer").innerHTML=`<button class="close" id="closeDrawer">×</button><div class="drawer-head"><div><p class="eyebrow">Rango desde ${date(x.range_start)}</p><h2>${esc(x.ticker)} ${REF.has(x.ticker)?"<em>benchmark</em>":""}</h2></div>${status(x.state)}</div><div class="pricebox"><div><span>Cierre</span><strong>${money(x.last_close)}</strong><small>${pct(x.distance_to_floor_pct)} sobre F</small></div><div><span>Suelo F</span><strong>${money(x.floor)}</strong><small>zona hasta ${money(x.floor_zone_high)}</small></div></div><div class="visit-strip"><span class="zone-line"></span>${dots}</div><div class="metrics"><div><span>Visitas independientes</span><strong>${x.visit_count}</strong></div><div><span>Visitas en ${x.recent_visit_sessions} sesiones</span><strong>${x.recent_visit_count}</strong></div><div><span>Días tocando zona</span><strong>${x.touching_days}</strong></div><div><span>Rebotes ≥5% intradía</span><strong>${x.successful_rebounds}/${x.historical_visits}</strong></div><div><span>Rebotes ≥5% al cierre</span><strong>${x.close_confirmed_rebounds}/${x.historical_visits}</strong></div><div><span>Rebote mediano intradía</span><strong>${pct(x.median_bounce_pct)}</strong></div><div><span>Estructura del rango</span><strong>${x.pattern_score.toFixed(0)}/100</strong></div><div><span>Densidad /20 sesiones</span><strong>${x.visit_density_20.toFixed(1)}</strong></div><div><span>Caída al cierre</span><strong>−${pct(x.closing_decline_pct)}</strong></div><div><span>Liquidez mediana</span><strong>${compact(x.median_dollar_volume_20)} $</strong></div></div><section><div class="section-title"><h3>Historial de visitas</h3><span>suelo → separación → regreso</span></div><div class="episode-table"><div class="episode-row head"><span>Visita</span><span>Mínimo</span><span>Salto</span><span>Máximo</span></div>${eps}</div></section>`;
  $("drawer").querySelector('.pricebox').insertAdjacentHTML('afterend',rangeChart(x));
  $("overlay").classList.remove("hidden");$("closeDrawer").onclick=hideDrawer;
}
function hideDrawer(){ $("overlay").classList.add("hidden") }
function render(){
  const q=$("search").value.trim().toLowerCase(),st=$("stateFilter").value,minV=+$('minVisits').value,maxD=+$('maxDist').value,sort=$("sort").value;
  let rows=DATA.candidates.filter(x=>(!q||x.ticker.toLowerCase().includes(q))&&(st==="TODOS"||x.state===st)&&x.visit_count>=minV&&x.distance_to_floor_pct<=maxD);
  rows.sort((a,b)=>sort==="visits"?(b.visit_count-a.visit_count||b.pattern_score-a.pattern_score):sort==="quality"?(b.pattern_score-a.pattern_score||a.distance_to_floor_pct-b.distance_to_floor_pct):(a.distance_to_floor_pct-b.distance_to_floor_pct||b.pattern_score-a.pattern_score));
  $("resultCount").textContent=rows.length;
  const nearCount=DATA.candidates.filter(x=>x.distance_to_floor_pct<=5).length;
  $("resultContext").textContent=`de ${DATA.candidates.length} patrones · ${nearCount} a ≤5% del suelo`;
  $("rows").innerHTML=rows.map((x,i)=>`<tr data-ticker="${esc(x.ticker)}"><td>${i+1}</td><td><strong>${esc(x.ticker)}</strong>${REF.has(x.ticker)?'<small class="tag">REF</small>':''}</td><td>${status(x.state)}</td><td><b>${money(x.floor)}</b><small>→ ${money(x.floor_zone_high)}</small></td><td><strong>${x.visit_count}</strong><small>${x.recent_visit_count} en ${x.recent_visit_sessions} ses.</small></td><td><strong>${x.successful_rebounds}/${x.historical_visits}</strong><small>cierre ${x.close_confirmed_rebounds}/${x.historical_visits}</small></td><td><strong>${x.pattern_score.toFixed(0)}/100</strong><small>${x.range_sessions} sesiones</small></td><td>${money(x.last_close)}<small>${pct(x.day_return_pct,true)} día</small></td><td><strong>${pct(x.distance_to_floor_pct)}</strong></td><td>${money(x.ceiling)}</td></tr>`).join("");
  document.querySelectorAll("tbody tr[data-ticker]").forEach(tr=>tr.onclick=()=>showDrawer(DATA.candidates.find(x=>x.ticker===tr.dataset.ticker)));
}
async function loadData(){
  const r=await fetch('/data/current.json',{cache:'no-store'});if(!r.ok)throw new Error('data');DATA=await r.json();
  const validated=DATA.strategy?.version>=8;
  // v4 snapshots contain the same range classification; normalize descriptive states.
  DATA.candidates=DATA.candidates.map(x=>({...x,state:x.current_touch&&x.last_close<=x.floor_zone_high?'VISITANDO_SUELO':x.distance_to_floor_pct<=DATA.config.near_floor_pct?'CERCA_DEL_SUELO':'EN_RANGO'}));
  DATA.state_counts=DATA.candidates.reduce((counts,x)=>(counts[x.state]=(counts[x.state]||0)+1,counts),{});
  $("validationNotice").classList.toggle('hidden',validated);
  if(!validated)DATA={...DATA,candidates:[],state_counts:{},universe:{...DATA.universe,candidates:0}};
  $("asOfTop").textContent=`cierre ${date(DATA.as_of)}`;$("candidateCount").textContent=DATA.universe.candidates;$("universeText").textContent=`de ${DATA.universe.files_scanned.toLocaleString('es-ES')} tickers`;
  if(!validated)$("candidateCount").textContent='—';
  $("statTouching").textContent=DATA.state_counts.VISITANDO_SUELO||0;$("statNear").textContent=DATA.state_counts.CERCA_DEL_SUELO||0;$("statFive").textContent=DATA.candidates.filter(x=>x.visit_count>=5).length;$("statZone").textContent=`+${DATA.strategy.floor_zone_pct}%`;
  $("benchmarkButtons").innerHTML=["SES","APP","SGI"].map(t=>{const x=DATA.candidates.find(c=>c.ticker===t);return x?`<button data-bench="${t}"><b>${t}</b><span>${x.visit_count} visitas · F ${money(x.floor)}</span></button>`:""}).join("");
  document.querySelectorAll('[data-bench]').forEach(b=>b.onclick=()=>showDrawer(DATA.candidates.find(x=>x.ticker===b.dataset.bench)));
  const refreshInfo=DATA.generated_at?` Actualizado ${new Date(DATA.generated_at).toLocaleString('es-ES',{timeZone:'Europe/Madrid'})} (Madrid). Cobertura: ${DATA.quality.valid}/${DATA.quality.requested} símbolos; ${DATA.quality.excluded} excluidos por datos ausentes o incompletos. Actualización diaria programada a las 02:00 de Madrid.`:'';
  $("footerText").textContent=`Velas diarias hasta ${date(DATA.as_of)}.${refreshInfo} Explorador de caídas seguidas de rango. Los niveles describen el patrón observado.`;
  render();
}
async function init(){
  await loadData();
  ["search","stateFilter","minVisits","maxDist","sort"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",render));
  $("methodBtn").onclick=()=>$("method").classList.toggle("hidden");$("overlay").onmousedown=e=>{if(e.target===$("overlay"))hideDrawer()};document.addEventListener('keydown',e=>{if(e.key==='Escape')hideDrawer()});
  let refreshing=false;
  const refresh=async()=>{
    if(document.hidden||refreshing)return;
    refreshing=true;
    try{await loadData()}catch{ $("asOfTop").textContent=`cierre ${date(DATA.as_of)} · actualización no disponible`; }
    finally{refreshing=false}
  };
  setInterval(refresh,15*60*1000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh()});
}
init().catch(()=>{document.body.innerHTML='<main class="page"><h2>No se pudieron cargar los datos del escáner.</h2></main>'});
