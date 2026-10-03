const LABELS={PENETRACION_PENDIENTE:"Penetración pendiente",VISITANDO_SUELO:"Visitando suelo",CERCA_DEL_SUELO:"Cerca del suelo",EN_RANGO:"En rango"};
const REF=new Set(["SES","APP","SGI","MUSA"]);let DATA=null;
const $=id=>document.getElementById(id);
function money(v){const d=v<1?4:v<10?3:2;return new Intl.NumberFormat("es-ES",{style:"currency",currency:"USD",minimumFractionDigits:d,maximumFractionDigits:d}).format(v)}
function pct(v,s=false){return `${s&&v>0?"+":""}${Number(v).toLocaleString("es-ES",{minimumFractionDigits:1,maximumFractionDigits:1})}%`}
function date(v){const [y,m,d]=v.split("-");return `${d}/${m}/${y}`}
function compact(v){return new Intl.NumberFormat("es-ES",{notation:"compact",maximumFractionDigits:1}).format(v)}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
function status(s){return `<span class="status s-${s.toLowerCase()}">${LABELS[s]||esc(s)}</span>`}
function dipLabel(x){
  const labels=[];
  if(x.wick_dip)labels.push("mecha recuperada");
  if(x.recovered_breach)labels.push("cierre recuperado");
  if(x.lower_repeated_contact)labels.push("nivel inferior repetido");
  return labels.join(" · ")||"Sin dip aislado";
}
function rangeChart(x){
  if(!x.chart?.length)return "";
  const W=580,H=230,left=12,right=76,top=20,bottom=30;
  const values=x.chart.flatMap(p=>[p.low,p.high]);values.push(x.floor,x.floor_zone_high,x.ceiling);
  const lo=Math.min(...values)*.98,hi=Math.max(...values)*1.02;
  const px=i=>left+i*(W-left-right)/Math.max(1,x.chart.length-1);
  const py=v=>top+(hi-v)/(hi-lo)*(H-top-bottom);
  const closeLine=x.chart.map((p,i)=>`${px(i).toFixed(1)},${py(p.close).toFixed(1)}`).join(" ");
  const wicks=x.chart.map((p,i)=>`<line x1="${px(i)}" x2="${px(i)}" y1="${py(p.low)}" y2="${py(p.high)}" stroke="#b2c0bd"><title>${p.date}: ${money(p.close)}</title></line>`).join("");
  const dips=x.chart.map((p,i)=>p.low<x.floor*.987?`<circle cx="${px(i)}" cy="${py(p.low)}" r="2.7" fill="#b76729"><title>${p.date}: mínimo ${money(p.low)}</title></circle>`:"").join("");
  const bandY=py(x.floor_zone_high),bandH=Math.max(1,py(x.floor)-bandY);
  return `<section class="range-chart"><h3>Cierres, mínimos y zona habitual</h3><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gráfico de ${esc(x.ticker)}, banda de rebotes y mínimos inferiores"><rect x="${left}" y="${bandY}" width="${W-left-right}" height="${bandH}" fill="#d4eee4"/>${wicks}<polyline fill="none" stroke="#183d38" stroke-width="2" points="${closeLine}"/>${dips}<line x1="${left}" x2="${W-right}" y1="${py(x.ceiling)}" y2="${py(x.ceiling)}" stroke="#a57127" stroke-dasharray="5 4"/><text x="${W-right+5}" y="${py(x.floor)+4}" font-size="10" fill="#248757">F ${x.floor.toFixed(2)}</text><text x="${W-right+5}" y="${py(x.floor_zone_high)+4}" font-size="10" fill="#248757">${x.floor_zone_high.toFixed(2)}</text><text x="${W-right+5}" y="${py(x.ceiling)+4}" font-size="10" fill="#a57127">T ${x.ceiling.toFixed(2)}</text><text x="${left}" y="${H-5}" font-size="10">${date(x.chart[0].date)}</text><text x="${W-right}" y="${H-5}" text-anchor="end" font-size="10">${date(x.as_of)}</text></svg><p>Verde: banda habitual. Los puntos naranjas muestran mínimos más de 1,3% por debajo; su tipo y fecha de recuperación figuran debajo.</p></section>`;
}
function eventRows(x){
  const rows=[];
  if(x.wick_dip)rows.push(["Mecha recuperada",x.wick_dip]);
  if(x.recovered_breach)rows.push(["Cierre bajo recuperado",x.recovered_breach]);
  if(x.lower_repeated_contact)rows.push(["Contacto inferior repetido",x.lower_repeated_contact]);
  if(!rows.length)return `<p>No se ha clasificado un dip aislado en esta base. El mínimo sigue visible para compararlo con la zona.</p>`;
  return `<div class="episode-table"><div class="episode-row head"><span>Tipo</span><span>Fecha</span><span>Mínimo</span><span>Recuperación</span></div>${rows.map(([label,e])=>`<div class="episode-row"><span>${label}</span><span>${date(e.date)}</span><strong>${money(e.low)}</strong><span>${e.recovered_at?date(e.recovered_at):"Nivel repetido"}</span></div>`).join("")}</div>`;
}
function showDrawer(x){
  $("drawer").innerHTML=`<button class="close" id="closeDrawer">×</button><div class="drawer-head"><div><p class="eyebrow">Base desde ${date(x.range_start)} · detectable ${date(x.first_detectable)}</p><h2>${esc(x.ticker)} ${REF.has(x.ticker)?"<em>referencia</em>":""}</h2></div>${status(x.state)}</div><div class="pricebox"><div><span>Cierre</span><strong>${money(x.last_close)}</strong><small>${pct(x.distance_to_floor_pct)} sobre F</small></div><div><span>Suelo habitual</span><strong>${money(x.floor)}–${money(x.floor_zone_high)}</strong><small>mínimo base ${money(x.minimum_since_first_visit)}</small></div></div>${rangeChart(x)}<div class="metrics"><div><span>Visitas independientes</span><strong>${x.visit_count}</strong></div><div><span>Rebotes observados ≥3,5% al cierre</span><strong>${x.successful_rebounds}</strong></div><div><span>Caída previa</span><strong>−${pct(x.prior_drop_pct)}</strong></div><div><span>Espacio al techo desde cierre</span><strong>${pct(x.room_to_ceiling_pct)}</strong></div><div><span>Evidencia estructural</span><strong>${x.pattern_score.toFixed(0)}/100</strong></div><div><span>Liquidez mediana</span><strong>${compact(x.median_dollar_volume_20)} $</strong></div></div><section><div class="section-title"><h3>Incursiones bajo la banda</h3><span>fechas observables</span></div>${eventRows(x)}<p>Una mecha anterior a la detección del rango se reconoce retrospectivamente a partir de ${date(x.first_detectable)}. El score es heurístico y no estima la probabilidad de rebote.</p></section>`;
  $("overlay").classList.remove("hidden");$("closeDrawer").onclick=hideDrawer;
}
function hideDrawer(){$("overlay").classList.add("hidden")}
function render(){
  const q=$("search").value.trim().toLowerCase(),st=$("stateFilter").value,minV=+$("minVisits").value,maxD=+$("maxDist").value,sort=$("sort").value;
  const rows=DATA.candidates.filter(x=>(!q||x.ticker.toLowerCase().includes(q))&&(st==="TODOS"||x.state===st)&&x.visit_count>=minV&&x.distance_to_floor_pct<=maxD);
  rows.sort((a,b)=>sort==="visits"?(b.visit_count-a.visit_count||b.pattern_score-a.pattern_score):sort==="quality"?(b.pattern_score-a.pattern_score||a.distance_to_floor_pct-b.distance_to_floor_pct):(a.distance_to_floor_pct-b.distance_to_floor_pct||b.pattern_score-a.pattern_score));
  $("resultCount").textContent=rows.length;
  const nearCount=DATA.candidates.filter(x=>x.distance_to_floor_pct<=5).length;
  $("resultContext").textContent=`de ${DATA.candidates.length} patrones · ${nearCount} a ≤5% del suelo`;
  $("rows").innerHTML=rows.map((x,i)=>`<tr data-ticker="${esc(x.ticker)}"><td>${i+1}</td><td><strong>${esc(x.ticker)}</strong>${REF.has(x.ticker)?'<small class="tag">REF</small>':''}</td><td>${status(x.state)}</td><td><b>${money(x.floor)}–${money(x.floor_zone_high)}</b></td><td>${money(x.minimum_since_first_visit)}</td><td><small>${dipLabel(x)}</small></td><td><strong>${x.visit_count}</strong><small>${x.successful_rebounds} rebotes</small></td><td><strong>${x.pattern_score.toFixed(0)}/100</strong><small>primera señal ${date(x.first_detectable)}</small></td><td>${money(x.last_close)}<small>${pct(x.day_return_pct,true)} día</small></td><td><strong>${pct(x.distance_to_floor_pct)}</strong></td></tr>`).join("");
  document.querySelectorAll("tbody tr[data-ticker]").forEach(tr=>tr.onclick=()=>showDrawer(DATA.candidates.find(x=>x.ticker===tr.dataset.ticker)));
}
async function loadData(){
  const r=await fetch("/data/current.json",{cache:"no-store"});if(!r.ok)throw new Error("data");DATA=await r.json();
  const validated=DATA.strategy?.version===9;
  $("validationNotice").classList.toggle("hidden",validated);
  if(!validated)DATA={...DATA,candidates:[],state_counts:{},universe:{...DATA.universe,candidates:0}};
  $("asOfTop").textContent=`cierre ${date(DATA.as_of)}`;
  $("candidateCount").textContent=validated?DATA.universe.candidates:"—";
  $("universeText").textContent=`de ${DATA.universe.files_scanned.toLocaleString("es-ES")} tickers`;
  $("statTouching").textContent=DATA.state_counts.VISITANDO_SUELO||0;
  $("statNear").textContent=DATA.state_counts.CERCA_DEL_SUELO||0;
  $("statFive").textContent=DATA.candidates.filter(x=>x.wick_dip||x.recovered_breach).length;
  $("statZone").textContent=DATA.state_counts.PENETRACION_PENDIENTE||0;
  $("benchmarkButtons").innerHTML=["SES","APP","SGI","MUSA"].map(t=>{const x=DATA.candidates.find(c=>c.ticker===t);return x?`<button data-bench="${t}"><b>${t}</b><span>${x.visit_count} visitas · ${money(x.floor)}–${money(x.floor_zone_high)}</span></button>`:""}).join("");
  document.querySelectorAll("[data-bench]").forEach(b=>b.onclick=()=>showDrawer(DATA.candidates.find(x=>x.ticker===b.dataset.bench)));
  const update=DATA.generated_at?` Actualizado ${new Date(DATA.generated_at).toLocaleString("es-ES",{timeZone:"Europe/Madrid"})} (Madrid). Cobertura: ${DATA.quality.valid}/${DATA.quality.requested} símbolos; ${DATA.quality.excluded} excluidos. Actualización programada a las 02:00 de Madrid.`:"";
  $("footerText").textContent=`Velas diarias hasta ${date(DATA.as_of)}.${update} Modelo auditado de zonas recurrentes y mínimos puntuales; investigación estructural, no backtest de operaciones.`;
  render();
}
async function init(){
  await loadData();
  ["search","stateFilter","minVisits","maxDist","sort"].forEach(id=>$(id).addEventListener(id==="search"?"input":"change",render));
  $("methodBtn").onclick=()=>$('method').classList.toggle("hidden");$("overlay").onmousedown=e=>{if(e.target===$("overlay"))hideDrawer()};document.addEventListener("keydown",e=>{if(e.key==="Escape")hideDrawer()});
  let refreshing=false;
  const refresh=async()=>{if(document.hidden||refreshing)return;refreshing=true;try{await loadData()}catch{$("asOfTop").textContent=`cierre ${date(DATA.as_of)} · actualización no disponible`}finally{refreshing=false}};
  setInterval(refresh,15*60*1000);document.addEventListener("visibilitychange",()=>{if(!document.hidden)refresh()});
}
init().catch(()=>{document.body.innerHTML='<main class="page"><h2>No se pudieron cargar los datos del escáner.</h2></main>'});
