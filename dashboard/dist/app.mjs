import {fields,sum,money,number,percent,selectRows,summarize,group,questions,answerQuestion,csvReport} from './metrics.mjs';

const $ = id => document.getElementById(id);
let snapshot, selected = [], allStates = false;
const filters = () => ({from:$('from').value,to:$('to').value,state:$('state').value});
const scopeText = () => `${$('from').value} → ${$('to').value} · ${$('state').value === 'all' ? 'All customer states' : `Customer state ${$('state').value}`}`;
const monthLabel = month => new Date(`${month}-01T12:00:00Z`).toLocaleDateString('en-US',{month:'short',year:'numeric',timeZone:'UTC'});
function cell(row,text,tag='td') { const node=document.createElement(tag); node.textContent=text; row.append(node); return node; }
function renderChart(months) {
  const root=$('chart'); root.replaceChildren();
  if (!months.length) {root.textContent='No orders in this selection.';return;}
  // Include empty months so lines never silently jump across missing periods.
  const sequence=[]; const byMonth=new Map(months.map(m=>[m.key,m]));
  let date=new Date(`${$('from').value}-01T12:00:00Z`), end=new Date(`${$('to').value}-01T12:00:00Z`);
  while (date<=end) {const key=date.toISOString().slice(0,7);sequence.push(byMonth.get(key)||{key,gmv_cents:0,delivered:0});date.setUTCMonth(date.getUTCMonth()+1);}
  const ns='http://www.w3.org/2000/svg';
  function svgNode(tag,attrs,parent,text) {const n=document.createElementNS(ns,tag); for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;parent.append(n);return n;}
  const svg=svgNode('svg',{viewBox:'0 0 720 230',role:'img','aria-label':`Monthly delivered item GMV, ${scopeText()}. Exact values are in the monthly data table.`},root);
  const W=720,H=230,left=67,right=13,top=18,bottom=40,max=Math.max(...sequence.map(m=>m.gmv_cents),100);
  const x=i=>left+(W-left-right)*(sequence.length===1?.5:i/(sequence.length-1));
  const y=v=>H-bottom-(v/max)*(H-top-bottom);
  for(let i=0;i<=4;i++) { const value=max*i/4,py=y(value);svgNode('line',{x1:left,x2:W-right,y1:py,y2:py,stroke:'#e9edf2','stroke-dasharray':'3 4'},svg);svgNode('text',{x:left-10,y:py+3,'text-anchor':'end',fill:'#8b98a3','font-size':9},svg,`R$${new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(value/100)}`);}
  const points=sequence.map((m,i)=>`${x(i)},${y(m.gmv_cents)}`);
  svgNode('polygon',{points:`${x(0)},${H-bottom} ${points.join(' ')} ${x(sequence.length-1)},${H-bottom}`,fill:'#efedfc'},svg);
  svgNode('polyline',{points:points.join(' '),fill:'none',stroke:'#7264db','stroke-width':2.5,'stroke-linejoin':'round'},svg);
  sequence.forEach((m,i)=>{const dot=svgNode('circle',{cx:x(i),cy:y(m.gmv_cents),r:sequence.length>18?2.5:3.5,fill:'#7264db',stroke:'#fff','stroke-width':1},svg);svgNode('title',{},dot,`${monthLabel(m.key)}: ${money(m.gmv_cents)} · ${number(m.delivered)} delivered orders`);if(i===0||i===sequence.length-1||i%Math.max(1,Math.ceil(sequence.length/5))===0)svgNode('text',{x:x(i),y:H-14,'text-anchor':'middle',fill:'#8b98a3','font-size':9},svg,monthLabel(m.key));});
}
function renderStates() {
  const table=$('states-table');table.replaceChildren();
  const states=group(selected,'state').sort((a,b)=>b.gmv_cents-a.gmv_cents||a.key.localeCompare(b.key));
  const total=sum(selected).gmv_cents;
  for(const state of states.slice(0,allStates?states.length:7)) {
    const tr=document.createElement('tr');const td=cell(tr,'');const badge=document.createElement('span');badge.className='state-pill';badge.textContent=state.key;td.append(badge);
    cell(tr,number(state.delivered));cell(tr,money(state.gmv_cents));
    const share=total?state.gmv_cents/total:0;const last=cell(tr,'');const wrap=document.createElement('span');wrap.className='share-cell';const track=document.createElement('span');track.className='share-track';track.setAttribute('aria-hidden','true');const bar=document.createElement('i');bar.style.width=`${share*100}%`;track.append(bar);wrap.append(track,document.createTextNode(percent(share)));last.append(wrap);table.append(tr);
  }
  if(!states.length){const tr=document.createElement('tr');const td=cell(tr,'No orders in this selection.');td.colSpan=4;table.append(tr);}
  $('show-states').textContent=allStates?'Show top states':`View all ${states.length} states`;
  $('show-states').hidden=states.length<=7;
  $('show-states').setAttribute('aria-expanded',String(allStates));
}
function render() {
  $('error').hidden=true;
  try {selected=selectRows(snapshot,filters());}
  catch(error){$('error').textContent=error.message;$('error').hidden=false;$('content').hidden=true;$('download').disabled=true;return;}
  $('content').hidden=false;$('download').disabled=!selected.length;
  $('messages').replaceChildren(); // Old answers must not appear to use the new selection.
  const t=summarize(selected),months=group(selected,'month');
  $('scope').textContent=scopeText();$('group-count').textContent=`${number(t.orders)} orders in selection`;
  $('gmv').textContent=money(t.gmv_cents);$('delivered').textContent=number(t.delivered);
  $('orders-detail').textContent=`Of ${number(t.orders)} orders across all statuses`;
  $('late').textContent=percent(t.lateRate);$('late-detail').textContent=`${number(t.late)} late / ${number(t.labeled)} labeled deliveries`;
  $('aov').textContent=t.aovCents===null?'Not available':money(t.aovCents);
  const onTime=t.labeled-t.late,onTimeRate=t.labeled?onTime/t.labeled:null;
  $('on-time').textContent=percent(onTimeRate);$('on-time-count').textContent=number(onTime);$('late-count').textContent=number(t.late);
  $('donut').style.background=t.labeled?`conic-gradient(#208875 0 ${onTimeRate*100}%,#d39943 ${onTimeRate*100}% 100%)`:'#e8eef0';
  $('donut').setAttribute('aria-label',t.labeled?`${percent(onTimeRate)} on time among ${number(t.labeled)} labeled deliveries`:'No labeled deliveries in this selection');
  $('missing-note').textContent=`${number(t.delivered-t.labeled)} delivered orders without a usable label are excluded.`;
  $('trend-note').textContent='Source calendar months · boundary months may be partial';renderChart(months);renderStates();
  $('monthly-table').replaceChildren();
  for(const month of months){const tr=document.createElement('tr');[monthLabel(month.key),number(month.delivered),money(month.gmv_cents),percent(month.lateRate)].forEach(v=>cell(tr,v));$('monthly-table').append(tr);}
}
function ask(question) {
  if(!snapshot||!question.trim())return;
  const answer=answerQuestion(question,selected);const card=document.createElement('div');card.className='answer';
  const title=document.createElement('h3');title.textContent=question;const text=document.createElement('p');text.textContent=answer.text;card.append(title,text);
  const scope=document.createElement('small');scope.textContent=`Scope: ${scopeText()}`;card.append(scope);
  if(answer.formula){const detail=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Show calculation & source';const p=document.createElement('p');p.textContent=`${answer.formula} Source: analytics.order_summary; snapshot exported ${new Date(snapshot.exported_at).toLocaleDateString('en-US',{timeZone:'UTC'})} (UTC).`;detail.append(summary,p);card.append(detail);}
  $('messages').replaceChildren(card);$('question').value='';
}
for(const [,question] of questions){const button=document.createElement('button');button.type='button';button.textContent=question;button.addEventListener('click',()=>ask(question));$('suggestions').append(button);}
$('filters').addEventListener('submit',event=>event.preventDefault());
$('filters').addEventListener('change',()=>{allStates=false;render();});
$('reset').addEventListener('click',()=>{if(!snapshot)return;$('from').value=snapshot.source_period.from;$('to').value=snapshot.source_period.to;$('state').value='all';allStates=false;render();});
$('show-states').addEventListener('click',()=>{allStates=!allStates;renderStates();});
$('ask-form').addEventListener('submit',event=>{event.preventDefault();ask($('question').value);});
$('download').addEventListener('click',()=>{const blob=new Blob([csvReport(selected)],{type:'text/csv;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`insightflow-${$('from').value}-${$('to').value}-${$('state').value}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
async function init() {
  try {
    const response=await fetch('./snapshot.json');if(!response.ok)throw new Error('Snapshot request failed.');snapshot=await response.json();
    if(snapshot.schema_version!==1||!Array.isArray(snapshot.rows)||!snapshot.rows.length||fields.some(k=>sum(snapshot.rows)[k]!==snapshot.totals[k]))throw new Error('Snapshot validation failed.');
    const months=[...new Set(snapshot.rows.map(r=>r.month))].sort();
    for(const id of ['from','to'])for(const month of months){const option=document.createElement('option');option.value=month;option.textContent=monthLabel(month);$(id).append(option);}
    for(const state of [...new Set(snapshot.rows.map(r=>r.state))].sort()){const option=document.createElement('option');option.value=state;option.textContent=state;$('state').append(option);}
    $('from').value=months[0];$('to').value=months.at(-1);for(const id of ['from','to','state'])$(id).disabled=false;
    $('source-period').textContent=`Coverage: ${monthLabel(months[0])}–${monthLabel(months.at(-1))}.`;
    $('provenance').textContent=`Warehouse build #${snapshot.warehouse_build_id} · Exported ${new Date(snapshot.exported_at).toLocaleString('en-US',{timeZone:'UTC'})} UTC · Source fingerprint ${snapshot.source_fingerprint.slice(0,12)}…`;
    $('provenance').title=`Full source fingerprint: ${snapshot.source_fingerprint}; aggregate SHA-256: ${snapshot.aggregate_sha256}`;
    $('loading').hidden=true;render();
  } catch(error){$('loading').hidden=true;$('content').hidden=true;$('error').textContent='The verified snapshot could not be loaded. Please reload the page or contact the project owner.';$('error').hidden=false;$('provenance').textContent='Snapshot unavailable.';console.error(error);}
}
init();
