'use strict';
const app=document.querySelector('#app'), nav=document.querySelector('#nav');
let access={}, screen='', state=null, busy=false, online=false, setupAccepted=false, headsetDirty=false;
const monitor=location.pathname==='/monitor';
const $=id=>document.getElementById(id);
const duration=n=>{n=Math.floor(n||0);return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(x=>String(x).padStart(2,'0')).join(':')};
const labels={ready:'Ready',recording:'Recording',saving:'Saving',complete:'Complete',interrupted:'Interrupted',storage_failure:'Storage failure'};
const storageLabels={not_ready:'Not ready',bench_ready:'Bench storage ready',opening:'Opening',writing:'Writing bench data',saved_bench:'Bench files finalized',partial_bench:'Partial bench files finalized',failed:'Write failed',incomplete:'Incomplete after restart'};
const headsetReady=s=>s.headset==='connected'&&s.eeg_fresh===true;
function showError(message){if($('error'))$('error').textContent=message;if($('headset-selection-error'))$('headset-selection-error').textContent=message}
function render(name){if(screen===name)return;screen=name;app.replaceChildren($(name+'-template').content.cloneNode(true));
 if(name==='login'){
  $('setup-note').hidden=!access.setup;
  $('password').autocomplete=access.setup?'new-password':'current-password';
  if(access.setup){app.querySelector('h1').textContent='Welcome to zooo1.';app.querySelector('.lead').textContent='Set up researcher access on this computer.';$('password').minLength=8}
  $('login-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;const p=$('password').value;$('password').value='';try{await request(access.setup?'/api/setup':'/api/login',{password:p});await bootstrap()}catch(e){showError(e.message)}finally{busy=false}});
 }
 if(name==='connected'){
  $('headset-continue').onclick=async()=>{if(busy)return;busy=true;try{await refresh();if(online&&state?.state==='ready'&&headsetReady(state)){setupAccepted=true;paint(state)}}finally{busy=false}};
 }
 if(name==='form'){
  $('dob').max=new Date().toLocaleDateString('en-CA');
  $('participant-form').addEventListener('submit',async e=>{e.preventDefault();if(busy||!state?.can_start||!online)return;const form=e.currentTarget;const data=Object.fromEntries(new FormData(form));await action('/api/start',data);if(state?.state!=='ready')form.reset()});
 }
 if($('end'))$('end').onclick=()=>{if(online&&state?.state==='recording'&&confirm('End this recording and finalize its local files?'))action('/api/end')};
 if($('new'))$('new').onclick=()=>{if(online&&confirm('Prepare a new session? The previous outcome remains in local storage.'))action('/api/reset')};
 if($('marker'))$('marker').onclick=()=>action('/api/marker');
}
async function request(path,data){const abort=new AbortController(), timer=setTimeout(()=>abort.abort(),6000);try{const r=await fetch(path,{method:data===undefined?'GET':'POST',cache:'no-store',headers:data===undefined?{}:{'Content-Type':'application/json','X-CSRF':access.csrf||'','X-Setup':access.setup_token||''},body:data===undefined?undefined:JSON.stringify(data),signal:abort.signal});const result=await r.json();if(!r.ok){if(r.status===401){access.authenticated=false;screen='';render('login');nav.hidden=true;$('headset-choice').hidden=true}throw Error(result.error||'Request failed.')}return result}finally{clearTimeout(timer)}}
async function action(path,data={}){if(busy)return;busy=true;showError('');if(path==='/api/end'){if($('end'))$('end').disabled=true;if($('session-title'))$('session-title').textContent='Ending session…';if($('save-status'))$('save-status').textContent='End requested. Waiting for the local service to confirm finalization.';if($('m-state'))$('m-state').textContent='End requested'}try{await request(path,data);await refresh()}catch(e){showError(e.name==='AbortError'?'The service did not respond. Check the monitor before retrying.':e.message)}finally{busy=false}}
function paintHeadsets(s){
 const select=$('headset-select'), button=$('headset-apply'), options=s.headset_options||[];
 $('headset-choice').hidden=!access.authenticated;
 const key=JSON.stringify(options);
 if(select.dataset.options!==key){
  select.replaceChildren(...options.map(h=>{const o=document.createElement('option');o.value=h.address;o.textContent=h.label+' · '+h.address;return o}));
  select.dataset.options=key;
 }
 if(!headsetDirty)select.value=s.headset_requested||s.headset_address||'';
 const enabled=online&&s.can_switch_headset&&!busy;
 select.disabled=!enabled;button.disabled=!enabled||select.value===s.headset_address;
 const selected=options.find(h=>h.address===s.headset_address);
 $('headset-selection-status').textContent=s.headset_requested?'Changing headset; waiting for the old connection to stop.':!s.can_switch_headset?['recording','saving'].includes(s.state)?'Headset selection is locked until recording and saving finish.':s.detail:'Selected: '+(selected?.label||'Muse')+'. Use a different headset on the other Pi when running both.';
}
$('headset-select').onchange=()=>{headsetDirty=true;if(state)paintHeadsets(state)};
$('headset-apply').onclick=async()=>{if(busy||!online||!state?.can_switch_headset)return;const address=$('headset-select').value;headsetDirty=false;setupAccepted=false;await action('/api/headset',{address})};
function paint(s){
 paintHeadsets(s);
 const active=['recording','saving'].includes(s.state), terminal=s.state!=='ready'&&!active;
 if(s.state!=='ready')setupAccepted=false;
 render(monitor?'monitor':s.state!=='ready'?'session':setupAccepted?'form':headsetReady(s)?'connected':'connect');
 if(screen==='connect'){
  const dependency=s.connection_issue==='dependencies', cleanup=s.connection_issue==='cleanup';
  $('headset-status').textContent=dependency?'Connection software unavailable':cleanup?'Connection needs attention':s.headset==='connecting'?'Checking headset connection…':s.headset==='connected'?'Waiting for fresh EEG':'Headset not connected';
  $('headset-help').textContent=dependency?'Ask the researcher to check the reviewed OpenMuse environment on the acquisition computer. No headset search can run until the required software is available. The service retries automatically.':cleanup?s.detail:s.headset==='connected'?'Fresh EEG is not arriving. Check headset power and Bluetooth range. The service will reconnect automatically if the stream remains stale.':s.headset==='connecting'?'The local service is attempting to connect to your assigned Muse headset. Keep the headset turned on and nearby.':s.detail;
 }
 if(screen==='connected')$('headset-continue').disabled=!online||!headsetReady(s);
 if(screen==='form'){
  $('start').disabled=!s.can_start||!online;
  $('readiness').textContent=s.can_start?'Headset connected · local bench recording ready.':s.storage==='not_ready'?'Recording is not ready. Production storage has not been configured.':s.detail;
 }
 if(screen==='session'){
  $('session-label').textContent=terminal?'SESSION ENDED':'SESSION IN PROGRESS';
  $('session-title').textContent=({recording:'You’re all set.',saving:'Finishing up.',complete:'Session complete.',interrupted:'Session interrupted.',storage_failure:'Recording needs attention.'})[s.state]||'Please wait.';
  $('session-description').textContent=({recording:'Your researcher will guide you from here.',saving:'Please wait while the local files are finalized.',complete:'The bench recording has ended.',interrupted:'A data interruption ended this recording. Reconnection will not resume it.',storage_failure:'Storage did not confirm a successful save. Keep the Pi powered on and notify the researcher.'})[s.state];
  $('session-time').textContent=duration(s.elapsed);
  $('save-status').textContent=(storageLabels[s.storage]||s.storage)+' · '+s.confirmed.toLocaleString()+' samples confirmed written';
  $('end').hidden=terminal;$('end').disabled=s.state!=='recording'||!online;
  $('new').hidden=!terminal;$('new').disabled=!online;
  $('session-code').textContent=s.session_id?'Session '+s.session_id.slice(0,8):'';
 }
 if(screen==='monitor'){
  $('network').textContent='Connected to the local acquisition service.';$('network').className='readiness';
  $('m-state').textContent=labels[s.state]||s.state;$('m-time').textContent=duration(s.elapsed);
  $('m-headset').textContent=({connected:'Connected',connecting:'Connecting',switching:'Changing headset',unavailable:'Unavailable'})[s.headset];
  $('m-age').textContent=s.sample_age===null?'No samples received':s.sample_age.toFixed(1)+' seconds since last samples';
  $('m-storage').textContent=storageLabels[s.storage]||s.storage;
  $('m-count').textContent=s.confirmed.toLocaleString()+' confirmed / '+s.received.toLocaleString()+' received';
  $('m-detail').textContent=s.detail;
  $('end').disabled=s.state!=='recording'||!online;$('marker').disabled=s.state!=='recording'||!online;
  $('new').hidden=!terminal;$('new').disabled=!online;
  $('events').replaceChildren(...s.events.slice().reverse().map(e=>{const li=document.createElement('li');li.textContent=new Date(e.utc*1000).toLocaleTimeString()+' · '+e.kind.replaceAll('_',' ');return li}));
  draw(s);
 }
}
function draw(s){const c=$('traces');if(!c)return;const ratio=devicePixelRatio||1,w=c.clientWidth,h=300;c.width=w*ratio;c.height=h*ratio;const ctx=c.getContext('2d');ctx.scale(ratio,ratio);ctx.clearRect(0,0,w,h);const rows=s.points||[], channels=s.channels||[];
 $('trace-caption').textContent=rows.length?'Real samples · last '+(rows.at(-1)[0]-rows[0][0]).toFixed(1)+' s':'Waiting for real samples';
 if(!rows.length){ctx.fillStyle='#706a68';ctx.font='13px -apple-system, sans-serif';ctx.fillText('No live EEG data available',20,150);return}
 const height=h/channels.length,start=rows[0][0],span=rows.at(-1)[0]-start||1;
 channels.forEach((label,i)=>{const vals=rows.map(r=>r[i+1]),lo=Math.min(...vals),hi=Math.max(...vals),mid=(hi+lo)/2,scale=(height-25)/(hi-lo||1),y=height*(i+.5);ctx.strokeStyle='#e6e0dd';ctx.beginPath();ctx.moveTo(48,y);ctx.lineTo(w,y);ctx.stroke();ctx.fillStyle='#706a68';ctx.font='9px -apple-system, sans-serif';ctx.fillText(label,5,y+3);ctx.strokeStyle='#500000';ctx.lineWidth=1;ctx.beginPath();rows.forEach((r,j)=>{const x=50+(w-58)*(r[0]-start)/span,yy=y-(r[i+1]-mid)*scale;if(j===0||r[0]-rows[j-1][0]>.1)ctx.moveTo(x,yy);else ctx.lineTo(x,yy)});ctx.stroke()});
}
function disconnected(){online=false;$('headset-select').disabled=true;$('headset-apply').disabled=true;if(screen==='connected'){render('connect')}if(screen==='connect'){$('headset-status').textContent='Connection status unavailable';$('headset-help').textContent='Connection to the local service was lost. Keep this page open; status will update when it reconnects.';}if($('network')){$('network').textContent='Remote monitor connection lost. The Pi may still be recording locally. Reconnect to confirm its status.';$('network').className='readiness warning';$('m-state').textContent='Unknown (offline)';$('m-headset').textContent='Unknown (offline)';$('m-storage').textContent='Unconfirmed (offline)';$('m-age').textContent='Live status unavailable';$('m-count').textContent='Write progress unavailable'}else if($('readiness'))$('readiness').textContent='Connection to the service lost. Reconnect before continuing.';else if($('save-status'))$('save-status').textContent='Monitor connection lost. Recording status is unknown; the Pi may still be recording.';['start','end','new','marker','headset-continue'].forEach(id=>{if($(id))$(id).disabled=true});if($('traces'))draw({points:[],channels:[]})}
async function refresh(){if(!access.authenticated)return;try{const s=await request('/api/state');state=s;online=true;paint(s)}catch(e){disconnected()}}
async function bootstrap(){setupAccepted=false;try{access=await request('/api/access');nav.hidden=!access.authenticated;$('headset-choice').hidden=!access.authenticated;$('monitor-link').hidden=monitor;if(access.authenticated){screen='';await refresh()}else render('login')}catch(e){app.textContent='The local service is unavailable. Reopen zooo1 to reconnect.'}}
$('logout').onclick=async()=>{await action('/api/logout');screen='';await bootstrap()};
window.addEventListener('offline',disconnected);window.addEventListener('resize',()=>{if(monitor&&online&&state)draw(state)});
(async()=>{await bootstrap();async function poll(){await refresh();setTimeout(poll,1000)}setTimeout(poll,1000)})();
