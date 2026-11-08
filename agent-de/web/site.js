import renderFlow from './flow.bundle.js';
const githubApi = 'https://api.github.com/repos/abhisheksd27/Flowpilot';
async function requestJson(path) {
  const response = await fetch(githubApi + path, {cache: 'no-store', headers: {Accept: 'application/vnd.github+json'}});
  if (!response.ok) throw new Error(response.status === 403 || response.status === 429 ? 'GitHub request limit reached. Please try again later.' : `GitHub returned ${response.status}`);
  return response.json();
}
async function loadRequestReports() {
  const status = document.getElementById('request-status');
  const container = document.getElementById('request-reports');
  status.textContent = 'Checking recent requests…';
  try {
    const issues = await requestJson('/issues?state=all&sort=created&direction=desc&per_page=50');
    const requests = issues.filter(issue => !issue.pull_request && issue.title.startsWith('[Pipeline request]')).slice(0, 5);
    const entries = await Promise.all(requests.map(async issue => {
      const comments = issue.comments ? await requestJson(`/issues/${issue.number}/comments?per_page=100`) : [];
      const report = comments.filter(comment => comment.user?.login === 'github-actions[bot]' && comment.body?.includes('Run logs and downloadable results')).at(-1);
      const details = document.createElement('details');
      details.className = 'card';
      const summary = document.createElement('summary');
      summary.textContent = `#${issue.number} · ${issue.title.replace('[Pipeline request]', '').trim()} · ${report ? 'Report available' : 'Awaiting report'}`;
      const request = document.createElement('p');
      request.textContent = issue.body;
      const body = document.createElement('pre');
      body.style.whiteSpace = 'pre-wrap';
      body.textContent = report ? report.body : 'Processing may be queued or running. Open the request to check its activity.';
      const link = document.createElement('a');
      link.href = issue.html_url;
      link.textContent = 'Open full request and download links ↗';
      details.append(summary, request, body, link);
      return details;
    }));
    container.replaceChildren(...entries);
    status.textContent = `${entries.length} recent requests · Checked ${new Date().toLocaleTimeString()}`;
  } catch (error) {
    status.textContent = 'Unable to refresh request reports: ' + error.message + ' · You can still open requests on GitHub using the link above.';
  }
}
document.getElementById('refresh-dashboard').addEventListener('click', async event => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = 'Refreshing…';
  try { await Promise.all([load(), loadRequestReports()]); }
  finally { button.disabled = false; button.textContent = 'Refresh dashboard'; }
});
loadRequestReports();
document.getElementById('request-form').addEventListener('submit', event => {
  event.preventDefault();
  const request = document.getElementById('request-text').value.trim();
  if (!request) return;
  const url = new URL('https://github.com/abhisheksd27/Flowpilot/issues/new');
  url.searchParams.set('title', '[Pipeline request] Weather analysis');
  url.searchParams.set('body', request);
  window.location.assign(url.toString());
});
document.getElementById('city').addEventListener('change', event => {
  document.getElementById('request-text').value = `Track daily weather and air quality for ${event.target.value} and flag anomalies.`;
});
const $=id=>document.getElementById(id);let data,timer,bundle;
function table(id, rows, keys){const t=document.createElement('table'),head=t.createTHead().insertRow();keys.forEach(k=>{const c=document.createElement('th');c.textContent=({temperature_c:'Temperature (°C)',humidity_pct:'Humidity (%)',pm2_5_ug_m3:'PM2.5 (µg/m³)',complete_day:'Day coverage',passed:'Result',check:'Quality check',samples:'Hours recorded',date:'Date',city:'City',detail:'What we checked'})[k]??k.replaceAll('_',' ');head.append(c)});const b=t.createTBody();for(const r of rows){const row=b.insertRow();for(const k of keys){const c=row.insertCell();c.textContent=k==='complete_day'?(r[k]?'Complete':'Partial day'):k==='passed'?(r[k]?'Passed':'Needs attention'):k==='date'?String(r[k]??'').slice(0,10):typeof r[k]==='number'?Number(r[k].toFixed(2)):String(r[k]??'—');if(typeof r[k]==='boolean')c.dataset.result=String(r[k])}}$(id).replaceChildren(t)}
function flow(statuses){renderFlow({parentElement:$('architecture'),data:{diagram:data.diagram,nodeIds:data.nodeIds,statuses}})}
function chart(){const key=$('metric').value,rows=[...data.hourly].filter(r=>Number.isFinite(r[key])).sort((a,b)=>a.time.localeCompare(b.time));if(!rows.length){$('chart').replaceChildren();$('chart-range').textContent='No validated measurements available for this city yet.';return;}const values=rows.map(r=>r[key]),min=Math.min(...values),max=Math.max(...values),range=max-min||1;const ns='http://www.w3.org/2000/svg';$('chart').replaceChildren();const line=document.createElementNS(ns,'polyline');line.setAttribute('points',values.map((v,i)=>`${35+i*940/Math.max(1,values.length-1)},${190-(v-min)*160/range}`).join(' '));line.setAttribute('fill','none');line.setAttribute('stroke','#65d9c0');line.setAttribute('stroke-width','2');$('chart').append(line);for(const [v,y] of [[max,22],[min,207]]){const text=document.createElementNS(ns,'text');text.setAttribute('x','8');text.setAttribute('y',y);text.setAttribute('fill','#aebdd2');text.textContent=v.toFixed(1);$('chart').append(text)}$('chart-range').textContent=`${rows[0].time} → ${rows.at(-1).time} UTC · ${rows.length} records`}
async function load(){try{const response=await fetch(`snapshot.json?t=${Date.now()}`,{cache:'no-store'});if(!response.ok)throw Error(`HTTP ${response.status}`);bundle=await response.json();selectCity();}catch(e){$('error').textContent='Unable to refresh results: '+e.message}}
function selectCity(){const city=$('city').value;const latest=bundle.cities?.[city]??(city==='Bengaluru'?bundle:null);if(!latest)return;data={...latest,diagram:bundle.diagram,nodeIds:bundle.nodeIds};$('city-title').textContent='for '+city;
clearInterval(timer);$('metrics').replaceChildren();for(const [label,value] of [['Data update',data.status==='success'?'Ready':data.status],['Hourly records',data.hourly.length],['Daily summaries',data.daily.length],['Automatic repairs',data.retry_count??0]]){const el=document.createElement('article'),v=document.createElement('strong'),l=document.createElement('span');v.textContent=value;l.textContent=label;el.append(v,l);$('metrics').append(el)}const age=(Date.now()-Date.parse(data.generated_at))/3600000;$('freshness').textContent=`Published ${new Date(data.generated_at).toLocaleString()} · Run ${data.run_id}${age>2?' · Update overdue: check cloud job status':''}`;const statuses={};data.events.forEach(e=>statuses[e.node]=e.status);flow(statuses);$('event').textContent='Latest published run · '+data.status;$('replay').disabled=!data.events.length;table('daily',data.daily,['date','city','temperature_c','humidity_pct','pm2_5_ug_m3','samples','complete_day']);table('validation',data.validation_result?.checks??[],['check','passed','detail']);$('anomalies').replaceChildren();for(const [key,a]of Object.entries(data.anomalies??{})){const p=document.createElement('p');p.textContent=`${key}: ${a.count} flags / ${a.samples} samples · ${a.status}`;$('anomalies').append(p)}$('plan').textContent=JSON.stringify(data.plan,null,2);$('code').textContent=data.code;chart();$('error').textContent=data.status==='not_started'?'This city has not been updated yet. Check again after the next hourly run.':data.status==='failed'?'The latest update for this city failed. Check cloud job status for details.':'';}
$('city').addEventListener('change',()=>{if(bundle)selectCity()});
$('metric').addEventListener('change',chart);$('replay').addEventListener('click',()=>{clearInterval(timer);let i=0;const statuses={};$('replay').disabled=true;flow(statuses);timer=setInterval(()=>{const e=data.events[i++];if(!e){clearInterval(timer);$('replay').disabled=false;$('event').textContent='Recorded run complete · '+data.status;return}statuses[e.node]=e.status;flow(statuses);$('event').textContent=`Recorded event ${i}/${data.events.length}: ${e.node} · ${e.message}`},550)});load();setInterval(load,60000);
