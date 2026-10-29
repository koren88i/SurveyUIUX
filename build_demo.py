from __future__ import annotations

from pathlib import Path
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from survey_loader import load_model, workbook_fingerprint
from evidence import load_evidence, load_status, matches_survey

ROOT = Path(__file__).parent
EXCEL = ROOT / 'data' / 'survey.xlsx'
OUTPUT = ROOT / 'static' / 'demo.html'

HTML_TEMPLATE = r'''<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Survey — חוקר שאלות ו-Lineage</title>
<style>
:root { --navy:#17365D; --blue:#2F75B5; --border:#d0d5dd; --bg:#f6f8fb; --muted:#667085; }
*{box-sizing:border-box} body{margin:0;font-family:Arial,"Noto Sans Hebrew",sans-serif;background:var(--bg);color:#172033}
header{background:linear-gradient(135deg,#17365D,#2F75B5);color:white;padding:24px 32px}
header h1{margin:0 0 8px;font-size:28px} header p{margin:0;opacity:.9}
main{padding:22px;max-width:1800px;margin:auto}.panel{background:white;border:1px solid #e3e8ef;border-radius:14px;padding:18px;margin-bottom:18px;box-shadow:0 2px 8px rgba(16,24,40,.04)}
.controls{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:12px}.control label{display:block;font-size:13px;color:var(--muted);margin-bottom:5px}.control select,.control input{width:100%;padding:9px;border:1px solid var(--border);border-radius:8px;background:white}
.table-wrap{overflow:auto;max-height:640px;border:1px solid var(--border);border-radius:10px}table{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;font-size:13px}th,td{padding:8px 10px;border-left:1px solid #e4e7ec;border-bottom:1px solid #e4e7ec;text-align:center;white-space:nowrap}th{background:var(--navy);color:white;position:sticky;top:0;z-index:3}th:first-child{right:0;z-index:4}td:first-child{position:sticky;right:0;background:white;font-weight:bold;z-index:2}.cell{cursor:pointer;min-width:80px;font-weight:700}.cell:hover{outline:3px solid #f2c94c;outline-offset:-3px}.masked{background:#f2f4f7;color:#98a2b3;cursor:not-allowed}th.sortable{cursor:pointer;user-select:none}th.sortable:hover{background:#244c7a}.sort-arrow{font-weight:900;margin-inline-start:4px}.drag-handle{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;margin-left:7px;border:1px solid var(--border);border-radius:6px;background:#f8fafc;color:#475467;cursor:grab;font-weight:900}.drag-handle:active{cursor:grabbing}tr.dragging{opacity:.55}tr.drop-target td{box-shadow:inset 0 3px 0 #f2c94c}.order-tools{display:flex;justify-content:flex-end;margin:-6px 0 10px}.order-tools button{border:1px solid var(--border);background:white;border-radius:8px;padding:7px 12px;cursor:pointer}.order-tools button:hover{background:#f8fafc}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.kpi{border:1px solid var(--border);border-radius:10px;padding:12px;background:#fbfcfe}.kpi .label{color:var(--muted);font-size:12px}.kpi .value{font-size:23px;font-weight:bold;margin-top:4px;direction:ltr;text-align:right}
.tabs{display:flex;gap:6px;margin:16px 0 10px;flex-wrap:wrap}.tab{border:1px solid var(--border);background:white;border-radius:999px;padding:8px 14px;cursor:pointer}.tab.active{background:var(--navy);color:white}.tab-content{display:none}.tab-content.active{display:block}
.open-question{border:1px solid var(--border);border-radius:12px;margin:14px 0;overflow:hidden}.open-question>summary{cursor:pointer;background:#eef4fb;padding:16px;font-size:17px;font-weight:700;line-height:1.6}.open-question .answer-total{font-size:13px;color:var(--muted);font-weight:400;margin-inline-start:12px}.open-role{padding:0 16px 12px}.open-role h4{margin:16px 0 4px}.source-answer{padding:12px 0;border-bottom:1px solid #e4e7ec}.source-answer:last-child{border-bottom:0}.source-answer .raw-text{margin-top:5px;background:transparent;padding:0;line-height:1.7}
.evidence{border:1px solid var(--border);border-right-width:6px;border-radius:10px;padding:12px;margin:10px 0;background:white}.evidence.support{border-right-color:#2e7d32}.evidence.contradict{border-right-color:#c62828}.meta{color:var(--muted);font-size:12px;margin-top:6px}.notice{padding:12px;border-radius:8px;background:#fff8e1;border:1px solid #ffe082}.empty{padding:18px;color:var(--muted);text-align:center}.raw-text{background:#f8fafc;padding:10px;border-radius:8px;margin-top:8px;white-space:pre-wrap}.lineage{line-height:1.9}.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#eef4ff;color:#1849a9;font-size:12px;margin:2px}.subtitle{color:var(--muted);margin-top:-8px}
.team-dist{margin:20px 0 8px;border:1px solid var(--border);border-radius:12px;padding:14px;background:#fbfcfe}.team-dist h3{margin:0 0 4px}.team-dist-note{color:var(--muted);font-size:12px;margin-bottom:12px}.team-row{display:grid;grid-template-columns:minmax(100px,160px) 1fr 64px 55px;gap:9px;align-items:center;margin:7px 0}.team-name{font-weight:700;overflow:hidden;text-overflow:ellipsis}.team-track{height:24px;background:#eef2f6;border-radius:6px;position:relative;overflow:visible}.team-fill{height:100%;background:#2F75B5;border-radius:6px;min-width:2px}.team-row.selected .team-fill{background:#C62828}.branch-marker{position:absolute;top:-3px;bottom:-3px;border-right:2px dashed #17365D;z-index:2}.team-score{font-weight:700;direction:ltr;text-align:right}.team-n{color:var(--muted);font-size:12px}.team-hidden{color:var(--muted);font-size:12px;margin-top:10px}.score-dist{direction:ltr;display:grid;grid-template-columns:repeat(10,minmax(24px,1fr));gap:8px;align-items:end;margin-top:8px;min-height:170px}.score-bin{display:grid;grid-template-rows:18px 1fr 18px;gap:4px;align-items:end;justify-items:center;min-width:0}.score-track{height:130px;width:100%;max-width:38px;background:#eef2f6;border-radius:6px;overflow:hidden;display:flex;align-items:flex-end}.score-fill{width:100%;height:0;background:#2F75B5;border-radius:6px 6px 0 0;min-height:0}.score-count{font-weight:700;direction:ltr;font-size:12px;line-height:1}.score-label{font-weight:700;color:#475467;font-size:12px;line-height:1}.mean-note{color:var(--muted);font-size:12px;margin:8px 0 12px}.whatif{margin-top:14px;border-top:1px solid #e4e7ec;padding-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}.whatif-title{font-weight:700}.whatif-note{color:var(--muted);font-size:12px}.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:999px;background:#f8fafc;padding:5px 9px;font-size:12px}.chip button,.link-btn{border:0;background:transparent;color:#1849a9;cursor:pointer;font-weight:700;padding:0}.respondent-list{margin-top:14px;border:1px solid var(--border);border-radius:10px;overflow:hidden}.respondent-row{display:grid;grid-template-columns:90px 1fr 90px 105px;gap:10px;align-items:center;padding:9px 10px;border-bottom:1px solid #e4e7ec;background:white}.respondent-row:last-child{border-bottom:0}.respondent-id{font-weight:700;direction:ltr;text-align:right}.respondent-meta{color:var(--muted);font-size:12px}.respondent-score{font-size:20px;font-weight:800;direction:ltr;text-align:right}.exclude-btn{border:1px solid #f0b8b8;background:#fff5f5;color:#b42318;border-radius:8px;padding:7px 10px;cursor:pointer;font-weight:700}.exclude-btn:hover{background:#fee4e2}.cell-tooltip{position:fixed;display:none;z-index:50;min-width:290px;max-width:360px;padding:12px;border:1px solid var(--border);border-radius:10px;background:white;box-shadow:0 14px 34px rgba(16,24,40,.22);pointer-events:none;text-align:right}.cell-tooltip .tooltip-title{font-weight:700;margin-bottom:6px}.cell-tooltip .tooltip-meta{font-size:12px;color:var(--muted);line-height:1.55;margin-bottom:8px}.cell-tooltip .score-dist{min-height:96px;gap:5px}.cell-tooltip .score-bin{grid-template-rows:14px 1fr 14px;gap:3px}.cell-tooltip .score-track{height:72px;width:18px}.cell-tooltip .score-count,.cell-tooltip .score-label{font-size:11px}.cell-tooltip .mean-note{margin:4px 0 8px}
@media(max-width:900px){.controls,.kpis{grid-template-columns:1fr 1fr}main{padding:10px}}
</style>
</head>
<body>
<header><h1>🔎 חוקר שאלות, ציונים וסימוכין</h1><p>כל תא מחושב מהגלם וניתן לפתיחה עד שורת המקור והאמירות התומכות או המסייגות.</p></header>
<main>
<section class="panel">
<div class="controls">
<div class="control"><label>רמת הסתכלות</label><select id="view"><option value="general">כלל הענף</option><option value="team" selected>לפי צוות</option><option value="tenure">לפי ותק</option><option value="team_tenure">צוות לפי ותק</option></select></div>
<div class="control"><label>מדד בתאים</label><select id="metric"><option value="mean">ממוצע</option><option value="delta" selected>פער מהממוצע הענפי</option><option value="high">% ציוני 8–10</option><option value="low">% ציוני 1–5</option><option value="std">סטיית תקן</option><option value="n">מספר משיבים</option></select></div>
<div class="control"><label>תחום</label><select id="domain"><option value="all">הכול</option><option value="manager" selected>הערכת ראש צוות</option><option value="team">אפקטיביות צוות</option><option value="feedback_quality">איכות המשוב</option></select></div>
<div class="control"><label>צוות לפילוח ותק</label><select id="team"></select></div>
<div class="control"><label>מינימום משיבים</label><input id="minN" type="number" min="3" max="10" value="5"></div>
<div class="control" id="roleControl" hidden><label>תפקיד המשיבים</label><select id="role"></select></div>
<div class="control" id="audienceControl" hidden><label>קבוצת שאלות</label><select id="audience"></select></div>
</div>
<p class="subtitle" id="surveyNote"></p>
<div class="notice" id="evidenceStatus"></div>
<div class="whatif" id="whatif"></div>
</section>
<section class="panel"><h2>מפת שאלות</h2><p class="subtitle">לחצו על תא כדי לפתוח את הציונים והסימוכין. בעמידה על תא מוצגים גם מספר האמירות התומכות והמסייגות בשכבת המלל שנטענה.</p><div class="order-tools"><button id="resetOrder" type="button">איפוס סדר</button></div><div class="table-wrap"><table id="matrix"></table></div></section>
<section class="panel" id="detail"><div class="empty">בחרו תא במפה.</div></section>
</main>
<div id="cellTooltip" class="cell-tooltip"></div>
<script>
const DATA = __DATA__;
const catalogById = Object.fromEntries(DATA.catalog.map(q=>[q.question_id,q]));
const respondentById = new Map();
for (const row of DATA.numeric){ if(!respondentById.has(row.response_id)) respondentById.set(row.response_id,row); }
const mean=a=>a.length?a.reduce((x,y)=>x+y,0)/a.length:null;
const std=a=>{if(!a.length)return null;const m=mean(a);return Math.sqrt(mean(a.map(x=>(x-m)**2)))};
const quantile=(a,q)=>{if(!a.length)return null;const b=[...a].sort((x,y)=>x-y);const p=(b.length-1)*q,lo=Math.floor(p),hi=Math.ceil(p);return lo===hi?b[lo]:b[lo]+(b[hi]-b[lo])*(p-lo)};
let excludedIds=new Set();
let currentSelection=null;
function activeNumeric(){const role=document.getElementById('role').value;return DATA.numeric.filter(r=>!excludedIds.has(r.response_id)&&(!role||role==='all'||r.tenure===role))}
function visibleQuestions(){const role=document.getElementById('role').value,audience=document.getElementById('audience').value,domain=document.getElementById('domain').value;return DATA.catalog.filter(q=>(domain==='all'||q.domain===domain)&&(!role||role==='all'||!q.audience||q.audience==='all'||q.audience===role)&&(!audience||audience==='any'||q.audience===audience))}
function branchMean(qid){return mean(activeNumeric().filter(r=>r.question_id===qid).map(r=>r.score))}
function respondentLabel(id){const r=respondentById.get(Number(id));return r?`R${String(r.response_id).padStart(3,'0')} · ${r.team} · ${r.tenure} · row ${r.source_excel_row}`:`R${String(id).padStart(3,'0')}`}
let sortState={qid:null,desc:true};
let manualOrder=[];
let draggedGroup=null;
const teams=[...new Set(DATA.numeric.map(r=>r.team))].sort();
const teamSelect=document.getElementById('team'); teams.forEach(t=>teamSelect.add(new Option(t,t))); teamSelect.value=teams[0]||'';
const survey=DATA.survey||{},groupLabel=survey.group_label||'צוות',splitLabel=survey.split_label||'וותק';
document.getElementById('evidenceStatus').textContent=DATA.status.message||'';
const domainSelect=document.getElementById('domain');domainSelect.replaceChildren(new Option('הכול','all'));for(const [id,label] of new Map(DATA.catalog.map(q=>[q.domain,q.domain_label])))domainSelect.add(new Option(label,id));domainSelect.value=DATA.survey?'all':(DATA.catalog.some(q=>q.domain==='manager')?'manager':'all');
if(DATA.survey){
 document.querySelector('header h1').textContent=survey.label||'חוקר סקר';
 const labels={general:'כלל המשיבים',team:`לפי ${groupLabel}`,tenure:`לפי ${splitLabel}`,team_tenure:`${groupLabel} לפי ${splitLabel}`};for(const option of document.getElementById('view').options)option.textContent=labels[option.value];
 teamSelect.previousElementSibling.textContent=`${groupLabel} לפילוח ${splitLabel}`;
 const roles=[...new Set((DATA.respondents||DATA.numeric).map(r=>r.tenure))].sort();
 const roleSelect=document.getElementById('role');roleSelect.add(new Option('כל התפקידים','all'));roles.forEach(role=>roleSelect.add(new Option(role,role)));document.getElementById('roleControl').hidden=false;
 const audienceSelect=document.getElementById('audience');audienceSelect.add(new Option('כל השאלות','any'));audienceSelect.add(new Option('שאלות משותפות','all'));for(const role of roles)if(DATA.catalog.some(q=>q.audience===role))audienceSelect.add(new Option(`שאלות ייעודיות: ${role}`,role));document.getElementById('audienceControl').hidden=false;
 document.getElementById('surveyNote').textContent='בחירת תפקיד מציגה רק את תשובותיו ואת השאלות שנשאל. שאלות מקבילות משתי גרסאות הטופס משויכות לאותה שאלה; המקור המקורי נשמר בכל ציון. '+(survey.zero_is_missing?'0 = לא רלוונטי, ואינו נכלל בחישובים או ב-N. ':'')+'הממוצע להשוואה מחושב בתוך סינון התפקיד הפעיל.';
 document.querySelector('#metric option[value="delta"]').textContent='פער מהממוצע הכללי';
}
const controls=['view','metric','domain','team','minN','role','audience']; controls.forEach(id=>document.getElementById(id).addEventListener('change',()=>{manualOrder=[];hideCellTooltip();render({scrollDetail:false})}));
document.getElementById('resetOrder').onclick=()=>{manualOrder=[];sortState={qid:null,desc:true};render({scrollDetail:false})};
const tooltip=document.getElementById('cellTooltip');
function groupRows(view,team){
 if(view==='general') return [{key:'כלל המשיבים',filter:r=>true}];
 if(view==='team') return teams.map(t=>({key:t,filter:r=>r.team===t}));
 if(view==='tenure') return [...new Set(activeNumeric().map(r=>r.tenure))].map(t=>({key:t,filter:r=>r.tenure===t}));
 return [...new Set(activeNumeric().filter(r=>r.team===team).map(r=>r.tenure))].map(t=>({key:`${team} · ${t}`,filter:r=>r.team===team&&r.tenure===t}));
}
function calc(rows,qid){const a=rows.filter(r=>r.question_id===qid).map(r=>r.score),m=mean(a),bm=branchMean(qid);return {n:a.length,mean:m,delta:m==null||bm==null?null:m-bm,high:a.length?a.filter(x=>x>=8).length/a.length:null,low:a.length?a.filter(x=>x<=5).length/a.length:null,std:std(a),scores:a};}
function valueText(v,metric){if(v==null||Number.isNaN(v))return '—';if(metric==='high'||metric==='low')return `${Math.round(v*100)}%`;if(metric==='n')return `${v}`;return `${v>=0&&metric==='delta'?'+':''}${v.toFixed(2)}`;}
function scoreCounts(scores){const counts=Object.fromEntries(Array.from({length:10},(_,i)=>[i+1,0]));for(const score of scores){const key=Math.round(score);if(key>=1&&key<=10)counts[key]++}return counts}
function distText(scores){const counts=scoreCounts(scores),parts=Object.entries(counts).filter(([,count])=>count>0).map(([score,count])=>`${score}: ${count}`);return parts.length?parts.join(', '):'—'}
function scoreDistributionHtml(scores,meanValue){const counts=scoreCounts(scores),max=Math.max(1,...Object.values(counts));const rows=Object.entries(counts).sort((a,b)=>Number(a[0])-Number(b[0])).map(([score,count])=>`<div class="score-bin"><div class="score-count">${count}</div><div class="score-track"><div class="score-fill" style="height:${count/max*100}%"></div></div><div class="score-label">${score}</div></div>`).join('');return `<div class="mean-note">ממוצע ${meanValue.toFixed(2)} · סטיית תקן ${std(scores).toFixed(2)} · N=${scores.length}</div><div class="score-dist">${rows}</div>`}
function sortValue(group,qid,metric,minN){const rows=activeNumeric().filter(group.filter),s=calc(rows,qid);if(s.n<minN)return null;const value=s[metric];return value==null||Number.isNaN(value)?null:value}
function sortGroups(groups,qid,metric,minN){if(!qid)return groups;return [...groups].sort((a,b)=>{const av=sortValue(a,qid,metric,minN),bv=sortValue(b,qid,metric,minN),am=av==null,bm=bv==null;if(am&&bm)return a.key.localeCompare(b.key,'he');if(am)return 1;if(bm)return -1;if(av===bv)return a.key.localeCompare(b.key,'he');return sortState.desc?bv-av:av-bv})}
function orderGroups(groups,qid,metric,minN){if(qid)return sortGroups(groups,qid,metric,minN);if(!manualOrder.length)return groups;const byKey=new Map(groups.map(g=>[g.key,g]));const ordered=manualOrder.map(key=>byKey.get(key)).filter(Boolean);const used=new Set(ordered.map(g=>g.key));return [...ordered,...groups.filter(g=>!used.has(g.key))]}
function currentRowKeys(){return [...document.querySelectorAll('#matrix tbody tr[data-group]')].map(row=>row.dataset.group)}
function moveRow(source,target,after){if(!source||!target||source===target)return;const keys=currentRowKeys(),from=keys.indexOf(source);let to=keys.indexOf(target);if(from<0||to<0)return;keys.splice(from,1);if(after)to+=1;if(from<to)to-=1;keys.splice(to,0,source);manualOrder=keys;sortState={qid:null,desc:true};render({scrollDetail:false})}
function enableRowDragging(){document.querySelectorAll('#matrix tbody tr[data-group]').forEach(row=>{const handle=row.querySelector('.drag-handle');if(!handle)return;handle.addEventListener('dragstart',ev=>{draggedGroup=row.dataset.group;row.classList.add('dragging');ev.dataTransfer.effectAllowed='move';ev.dataTransfer.setData('text/plain',draggedGroup)});handle.addEventListener('dragend',()=>{draggedGroup=null;row.classList.remove('dragging');document.querySelectorAll('tr.drop-target').forEach(target=>target.classList.remove('drop-target'))});row.addEventListener('dragover',ev=>{if(!draggedGroup||row.dataset.group===draggedGroup)return;ev.preventDefault();row.classList.add('drop-target')});row.addEventListener('dragleave',()=>row.classList.remove('drop-target'));row.addEventListener('drop',ev=>{ev.preventDefault();const source=draggedGroup||ev.dataTransfer.getData('text/plain'),rect=row.getBoundingClientRect(),after=ev.clientY>rect.top+rect.height/2;row.classList.remove('drop-target');moveRow(source,row.dataset.group,after)})})}
function color(v,metric){if(v==null||Number.isNaN(v))return '#f2f4f7';let t;if(metric==='delta'){t=Math.max(-2.5,Math.min(2.5,v))/5+.5;return mix('#b2182b','#f7f7f7','#2166ac',t)}if(metric==='mean'){t=(v-1)/9;return mix('#b2182b','#fff7bc','#1a9850',t)}if(metric==='high'){return mix('#f7f7f7','#d9ef8b','#1a9850',v)}if(metric==='low'){return mix('#f7f7f7','#fdae61','#b2182b',v)}if(metric==='std'){t=Math.min(v/3,1);return mix('#f7f7f7','#fee08b','#d73027',t)}t=Math.min(v/10,1);return mix('#f7f7f7','#d9ef8b','#1a9850',t)}
function hex(c){return [parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)]}function h(a){return '#'+a.map(x=>Math.round(x).toString(16).padStart(2,'0')).join('')}function mix(a,b,c,t){const A=hex(a),B=hex(b),C=hex(c);let x,y,u;if(t<.5){x=A;y=B;u=t*2}else{x=B;y=C;u=(t-.5)*2}return h(x.map((v,i)=>v+(y[i]-v)*u))}
function renderExclusions(){
 const el=document.getElementById('whatif');if(!el)return;
 if(!excludedIds.size){el.innerHTML='<span class="whatif-title">What-if exclusion</span><span class="whatif-note">Open a cell, then remove any respondent from the raw-score list to recompute the whole demo on the fly.</span>';return}
 const chips=[...excludedIds].sort((a,b)=>a-b).map(id=>`<span class="chip">${esc(respondentLabel(id))}<button type="button" data-restore-id="${id}">restore</button></span>`).join('');
 el.innerHTML=`<span class="whatif-title">Excluded respondents: ${excludedIds.size}</span>${chips}<button type="button" class="link-btn" id="clearExclusions">clear all</button>`;
 document.querySelectorAll('[data-restore-id]').forEach(b=>b.onclick=()=>toggleExclude(Number(b.dataset.restoreId)));
 document.getElementById('clearExclusions').onclick=()=>{excludedIds.clear();render({scrollDetail:false})};
}
function toggleExclude(id){if(excludedIds.has(id)){excludedIds.delete(id)}else{excludedIds.add(id)}manualOrder=[];render({scrollDetail:false})}
function render(options={scrollDetail:false}){
 const scrollDetail=options.scrollDetail===true;
 const view=document.getElementById('view').value,metric=document.getElementById('metric').value,domain=document.getElementById('domain').value,team=teamSelect.value,minN=+document.getElementById('minN').value;
 teamSelect.disabled=view!=='team_tenure';
 const qs=visibleQuestions();if(sortState.qid&&!qs.some(q=>q.question_id===sortState.qid))sortState={qid:null,desc:true};const groups=orderGroups(groupRows(view,team),sortState.qid,metric,minN);let html='<thead><tr><th>קבוצה</th>'+qs.map(q=>`<th class="sortable" data-q="${q.question_id}" title="${esc(q.full_text)}">${esc(q.label)}${sortState.qid===q.question_id?` <span class="sort-arrow">${sortState.desc?'↓':'↑'}</span>`:''}</th>`).join('')+'</tr></thead><tbody>';
 for(const g of groups){html+=`<tr data-group="${escAttr(g.key)}"><td><span class="drag-handle" draggable="true" title="גרור שורה">↕</span>${esc(g.key)}</td>`;const rows=activeNumeric().filter(g.filter);for(const q of qs){const s=calc(rows,q.question_id);if(s.n<minN){html+=`<td class="masked" title="N=${s.n}">&lt;${minN}</td>`}else{const v=s[metric],counts=evidenceCounts(rows,q.question_id,s.delta);const tip=`N=${s.n}
ממוצע: ${s.mean.toFixed(2)}
פער: ${s.delta>=0?'+':''}${s.delta.toFixed(2)}
אמירות תומכות: ${counts.support}
אמירות סותרות/מסייגות: ${counts.contra}
סטיית תקן: ${s.std.toFixed(2)}
התפלגות ציונים: ${distText(s.scores)}`;html+=`<td class="cell" style="background:${color(v,metric)}" data-group="${escAttr(g.key)}" data-q="${q.question_id}" aria-label="${escAttr(tip)}">${valueText(v,metric)}</td>`}}html+='</tr>'}
 html+='</tbody>';document.getElementById('matrix').innerHTML=html;enableRowDragging();document.querySelectorAll('th.sortable').forEach(th=>th.onclick=()=>{const qid=th.dataset.q;manualOrder=[];if(sortState.qid===qid){sortState.desc=!sortState.desc}else{sortState={qid,desc:true}};render({scrollDetail:false})});document.querySelectorAll('.cell').forEach(td=>{td.onclick=()=>showDetail(td.dataset.group,td.dataset.q);td.onmouseenter=ev=>showCellTooltip(ev,td);td.onmousemove=placeTooltip;td.onmouseleave=hideCellTooltip});
 renderExclusions();const currentGroupKeys=new Set(groups.map(g=>g.key));if(currentSelection&&currentGroupKeys.has(currentSelection.group)&&qs.some(q=>q.question_id===currentSelection.qid)){showDetail(currentSelection.group,currentSelection.qid,{scroll:scrollDetail});return}
 const firstCell=document.querySelector('.cell');if(firstCell){showDetail(firstCell.dataset.group,firstCell.dataset.q,{scroll:scrollDetail})}else{currentSelection=null;document.getElementById('detail').innerHTML='<div class="empty">אין תוצאות שעומדות בסף המשיבים בסינון הנוכחי.</div>'}
}
function filterForGroup(group){const view=document.getElementById('view').value,team=teamSelect.value;if(view==='general')return r=>true;if(view==='team')return r=>r.team===group;if(view==='tenure')return r=>r.tenure===group;const tenure=group.split(' · ').slice(1).join(' · ');return r=>r.team===team&&r.tenure===tenure}
function direction(delta){return delta>=.35?'positive':delta<=-.35?'negative':'neutral'}function relation(d,n){if(n==='neutral')return d==='positive'?'חיובית':d==='negative'?'ביקורתית':'מעורבת/ניטרלית';if(d===n)return 'תומכת';if((d==='positive'||d==='negative')&&d!==n)return 'סותרת/מסייגת';return 'הקשר נוסף'}
function evidenceCounts(rows,qid,delta){
 const dir=direction(delta);if(dir==='neutral')return {support:'—',contra:'—'};
 const ids=new Set(rows.filter(r=>r.question_id===qid).map(r=>r.response_id));
 const matched=DATA.evidence.filter(e=>e.question_id===qid&&ids.has(e.response_id));
 const support=new Set(matched.filter(e=>relation(e.direction,dir)==='תומכת').map(e=>e.segment_id)).size;
 const contra=new Set(matched.filter(e=>relation(e.direction,dir)==='סותרת/מסייגת').map(e=>e.segment_id)).size;
 return {support,contra};
}
function cellRows(td){const f=filterForGroup(td.dataset.group);return activeNumeric().filter(r=>r.question_id===td.dataset.q&&f(r))}
function showCellTooltip(ev,td){const q=catalogById[td.dataset.q],rows=cellRows(td),s=calc(rows,td.dataset.q),counts=evidenceCounts(rows,td.dataset.q,s.delta),metric=document.getElementById('metric').value,metricLabel=document.getElementById('metric').selectedOptions[0].textContent,value=s[metric];tooltip.innerHTML=`<div class="tooltip-title">${esc(td.dataset.group)} · ${esc(q.label)}</div><div class="tooltip-meta">${esc(metricLabel)}: ${valueText(value,metric)}<br>N=${s.n}<br>ממוצע: ${s.mean.toFixed(2)}<br>פער: ${s.delta>=0?'+':''}${s.delta.toFixed(2)}<br>סטיית תקן: ${s.std.toFixed(2)}<br>אמירות תומכות: ${counts.support} · סותרות/מסייגות: ${counts.contra}</div>${scoreDistributionHtml(s.scores,s.mean)}`;placeTooltip(ev)}
function placeTooltip(ev){if(!tooltip)return;tooltip.style.display='block';const pad=14;let left=ev.clientX+pad,top=ev.clientY+pad;const rect=tooltip.getBoundingClientRect();if(left+rect.width>window.innerWidth-8)left=ev.clientX-rect.width-pad;if(top+rect.height>window.innerHeight-8)top=ev.clientY-rect.height-pad;tooltip.style.left=`${Math.max(8,left)}px`;tooltip.style.top=`${Math.max(8,top)}px`}
function hideCellTooltip(){if(tooltip)tooltip.style.display='none'}
function showDetail(group,qid,options={}){
 const scroll=options.scroll!==false;
 currentSelection={group,qid};
 const minN=+document.getElementById('minN').value,q=catalogById[qid],f=filterForGroup(group),rows=activeNumeric().filter(r=>r.question_id===qid&&f(r)),s=calc(rows,qid);if(s.n<minN){document.getElementById('detail').innerHTML=`<div class="notice">הקבוצה כוללת ${s.n} משיבים בלבד ולכן הפרטים מוסתרים.</div>`;return}
 const dir=direction(s.delta),ids=new Set(rows.map(r=>r.response_id)),ev=DATA.evidence.filter(e=>e.question_id===qid&&ids.has(e.response_id)).map(e=>({...e,rel:relation(e.direction,dir),score:rows.find(r=>r.response_id===e.response_id)?.score}));
 const support=ev.filter(e=>e.rel==='תומכת'),contra=ev.filter(e=>e.rel==='סותרת/מסייגת');
 let html=`<h2>${esc(group)} — ${esc(q.label)}</h2><p class="subtitle">${esc(q.full_text)}</p><div class="kpis">${kpi('ממוצע קבוצה',s.mean.toFixed(2))}${kpi('ממוצע ענפי',branchMean(qid).toFixed(2))}${kpi('פער',(s.delta>=0?'+':'')+s.delta.toFixed(2))}${kpi('N',s.n)}${kpi('טווח בין־רבעוני',quantile(s.scores,.25).toFixed(1)+'–'+quantile(s.scores,.75).toFixed(1))}</div>`;
 html+=teamDistributionHtml(qid,group,minN);
 html+=`<div class="tabs"><button class="tab active" data-tab="raw">ציונים גולמיים</button>${DATA.open_answers?'<button class="tab" data-tab="openAnswers">תשובות פתוחות בקבוצה</button>':''}<button class="tab" data-tab="support">אמירות תומכות</button><button class="tab" data-tab="contra">אמירות סותרות/מסייגות</button><button class="tab" data-tab="lineage">Lineage</button></div>`;
 html+=`<div id="raw" class="tab-content active">${scoreDistributionHtml(s.scores,s.mean)}${respondentRowsHtml(rows,qid)}</div>`;
 if(DATA.open_answers){const answers=DATA.open_answers.filter(a=>ids.has(a.response_id)&&a.informative);html+=`<div id="openAnswers" class="tab-content"><div class="notice">תשובות המקור של המשיבים שנכללו בתוצאה. אלה אינן בהכרח ראיות לשאלה שנבחרה; התאמה לשאלות מופיעה רק בלשוניות האמירות המסווגות.</div>${openAnswersHtml(answers)}</div>`}
 html+=`<div id="support" class="tab-content"><div class="notice">${esc(DATA.status.message||'')}</div>${evidenceHtml(support,'support','לא נמצאו אמירות תומכות מסווגות.')}</div>`;
 html+=`<div id="contra" class="tab-content">${evidenceHtml(contra,'contradict','לא נמצאו אמירות סותרות או מסייגות.')}</div>`;
 html+=`<div id="lineage" class="tab-content lineage"><ol><li>תא: <b>${esc(group)} × ${esc(q.label)}</b></li><li>גיליון מקור: <code>${esc(survey.sheet||'נתונים גולמיים')}</code></li><li>תאי מקור: <code>${rows.map(r=>esc(r.source_column)+esc(r.source_excel_row)).join(', ')}</code></li><li>ממוצע קבוצה: ${s.mean.toFixed(4)}</li><li>ממוצע כללי בסינון הפעיל: ${branchMean(qid).toFixed(4)}</li><li>פער: ${s.delta.toFixed(4)}</li><li>המודל מסווג מלל בלי לקבל ציונים; תומכת/סותרת נגזר לאחר מכן מכיוון הפער.</li></ol></div>`;
 document.getElementById('detail').innerHTML=html;document.querySelectorAll('[data-exclude-id]').forEach(b=>b.onclick=()=>toggleExclude(Number(b.dataset.excludeId)));document.querySelectorAll('.tab').forEach(b=>b.onclick=()=>{document.querySelectorAll('.tab,.tab-content').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.getElementById(b.dataset.tab).classList.add('active')});if(scroll)document.getElementById('detail').scrollIntoView({behavior:'smooth',block:'start'});
}
function selectedTeamForHighlight(group){const view=document.getElementById('view').value;if(view==='team')return group;if(view==='team_tenure')return teamSelect.value;return null}
function teamDistributionHtml(qid,group,minN){
 const selectedTeam=selectedTeamForHighlight(group),bm=branchMean(qid),rows=[];const hidden=[];
 for(const team of teams){const teamRows=activeNumeric().filter(r=>r.question_id===qid&&r.team===team),s=calc(teamRows,qid);if(s.n<minN){hidden.push(`${team} (${s.n})`);continue}const counts=evidenceCounts(teamRows,qid,s.delta);rows.push({team,n:s.n,mean:s.mean,delta:s.delta,counts})}
 rows.sort((a,b)=>a.mean-b.mean||a.team.localeCompare(b.team,'he'));
 const marker=Math.max(0,Math.min(100,bm/10*100));
 const bars=rows.map(r=>{const width=Math.max(0,Math.min(100,r.mean/10*100)),selected=r.team===selectedTeam?' selected':'',tip=`ממוצע ${r.mean.toFixed(2)} | N=${r.n} | פער ${r.delta>=0?'+':''}${r.delta.toFixed(2)} | תומכות ${r.counts.support} | סותרות ${r.counts.contra}`;return `<div class="team-row${selected}" title="${escAttr(tip)}"><div class="team-name">${esc(r.team)}</div><div class="team-track"><div class="branch-marker" style="right:${marker}%"></div><div class="team-fill" style="width:${width}%"></div></div><div class="team-score">${r.mean.toFixed(2)}</div><div class="team-n">N=${r.n}</div></div>`}).join('');
 return `<div class="team-dist"><h3>השוואת כל הצוותים — ${esc(catalogById[qid].label)}</h3><div class="team-dist-note">העמודות מציגות ממוצע צוות. הקו המקווקו הוא הממוצע הענפי ${bm.toFixed(2)}; הצוות שנבחר מודגש באדום.</div>${bars}${hidden.length?`<div class="team-hidden">לא הוצגו בגלל סף הפרטיות: ${esc(hidden.join(', '))}</div>`:''}</div>`
}
function openAnswersHtml(answers){
 if(!answers.length)return '<div class="empty">אין תשובות תוכן בקבוצה זו.</div>';
 const questions=new Map();
 for(const answer of answers){const key=answer.source_question_id;if(!questions.has(key))questions.set(key,{label:answer.source_question_label,answers:[],roles:new Map()});const question=questions.get(key);question.answers.push(answer);if(!question.roles.has(answer.tenure))question.roles.set(answer.tenure,[]);question.roles.get(answer.tenure).push(answer)}
 return [...questions.values()].map((question,index)=>`<details class="open-question"${index===0?' open':''}><summary>${esc(question.label)} ${[...question.roles.keys()].map(role=>`<span class="badge">${esc(role)}</span>`).join(' ')}<span class="answer-total">${question.answers.length} תשובות</span></summary>${[...question.roles].map(([role,items])=>`<section class="open-role">${question.roles.size>1?`<h4><span class="badge">${esc(splitLabel)}: ${esc(role)}</span><span class="answer-total">${items.length} תשובות</span></h4>`:''}${items.map(answer=>`<div class="source-answer"><div class="meta">R${String(answer.response_id).padStart(3,'0')}</div><div class="raw-text">${esc(answer.raw_text)}</div></div>`).join('')}</section>`).join('')}</details>`).join('');
}
function respondentRowsHtml(rows,qid){
 const ordered=[...rows].sort((a,b)=>a.score-b.score||a.response_id-b.response_id);
 const items=ordered.map(r=>`<div class="respondent-row"><div class="respondent-id">R${String(r.response_id).padStart(3,'0')}</div><div><div>${esc(r.team)}</div><div class="respondent-meta">${esc(r.tenure)} · Excel row ${r.source_excel_row}</div></div><div class="respondent-score">${r.score}</div><button type="button" class="exclude-btn" data-exclude-id="${r.response_id}">exclude</button></div>`).join('');
 return `<div class="respondent-list">${items}</div>`
}function evidenceHtml(items,cls,empty){if(!items.length)return `<div class="empty">${empty}</div>`;return items.map(e=>`<div class="evidence ${cls}"><b>${esc(e.evidence_span)}</b><div>${esc(e.explanation)}</div><div class="meta">R${String(e.response_id).padStart(3,'0')} · ${esc(e.tenure)} · ציון אישי ${e.score} · ${e.relevance} · ${e.confidence}</div><details><summary>תשובת המקור</summary><div class="raw-text">${esc(e.raw_text)}</div></details></div>`).join('')}
function kpi(l,v){return `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div></div>`}function esc(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}function escAttr(s){return esc(s)}
render({scrollDetail:false});
</script>
</body></html>'''


def build_private_demo(excel: Path = EXCEL, output: Path = OUTPUT) -> Path:
    responses, catalog, numeric, open_answers = load_model(excel)
    survey = responses.attrs.get('survey')
    prefix = f'{excel.stem}_' if survey else ''
    evidence = load_evidence(excel.parent / f'{prefix}evidence_links.jsonl')
    status = load_status(excel.parent / f'{prefix}evidence_status.json')
    if survey and not matches_survey(evidence, workbook_fingerprint(excel)):
        evidence = load_evidence(b'')
        status = {'status': 'mismatched', 'message': 'המלל אינו תואם לגרסת הסקר; מוצגים ציונים בלבד.'}
    if status.get('status') == 'missing':
        count = int(open_answers['informative'].sum())
        status = {'status': 'not_classified', 'message': f'נטענו {count} תשובות תוכן פתוחות. טרם בוצע סיווג וקישור לשאלות המספריות. ניתן לקרוא את המקור בלשונית תשובות פתוחות בקבוצה.'}
    payload = {
        'catalog': catalog.to_dict('records'), 'numeric': numeric.to_dict('records'),
        'evidence': evidence.astype(object).where(evidence.notna(), None).to_dict('records'),
        'status': status,
        'open_answers': open_answers.to_dict('records'),
    }
    if survey:
        payload['survey'] = survey
        payload['respondents'] = responses[['response_id', 'team', 'tenure']].to_dict('records')
    json_blob = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('</', '<\\/')
    html = HTML_TEMPLATE.replace('__DATA__', json_blob)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding='utf-8')
    return output


def main():
    parser = argparse.ArgumentParser(description='Build a private survey HTML explorer')
    parser.add_argument('--excel', type=Path, default=EXCEL)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--serve', action='store_true', help='Serve only this private HTML on localhost')
    parser.add_argument('--port', type=int, default=8502)
    args = parser.parse_args()
    output = build_private_demo(args.excel, args.output)
    print(output, flush=True)
    if args.serve:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.split('?', 1)[0] not in {'/', '/index.html'}:
                    self.send_error(404)
                    return
                content = output.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(content)

        print(f'Private HTML: http://127.0.0.1:{args.port}', flush=True)
        ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
