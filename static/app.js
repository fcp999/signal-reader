const $=id=>document.getElementById(id);
let offset=0,last=null,polling=false,serial=0,category='',catalog=[],needsReload=false;
let excluded=new Set();
try{const saved=JSON.parse(localStorage.getItem('signal.excluded')||'[]');if(Array.isArray(saved))excluded=new Set(saved.filter(n=>typeof n==='string'))}catch{}
async function api(path,options={}){const r=await fetch('api/'+path,options);if(!r.ok)throw Error('Request failed ('+r.status+')');return r.json()}
const post=path=>api(path,{method:'POST',headers:{'X-Reader-Request':'1'}});
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function date(ts){return new Date(ts*1000).toLocaleString()}
function sourceControls(){
 const selected=$('source').value;
 $('source').replaceChildren(new Option('All enabled sources',''),...catalog.filter(f=>!excluded.has(f.name)&&(!category||f.category===category)).map(f=>new Option(f.name,f.name)));
 if([...$('source').options].some(o=>o.value===selected))$('source').value=selected;
 $('enabledCount').textContent=catalog.filter(f=>!excluded.has(f.name)).length+' of '+catalog.length+' sources enabled';
}
async function loadCatalog(){
 catalog=await api('feeds');const groups=[...new Set(catalog.map(f=>f.category))];
 const order=['US','World','Florida','Tech & security','Science','Networking','Other'];groups.sort((a,b)=>order.indexOf(a)-order.indexOf(b));
 $('categories').replaceChildren();
 for(const group of ['',...groups]){const b=node('button',group||'All');b.type='button';b.setAttribute('aria-pressed',String(category===group));b.onclick=()=>{category=group;for(const child of $('categories').children)child.setAttribute('aria-pressed',String(child===b));sourceControls();load()};$('categories').append(b)}
 $('sourceSettings').replaceChildren();
 for(const group of groups){const field=node('fieldset');field.append(node('legend',group));for(const f of catalog.filter(f=>f.category===group)){const label=node('label'),input=node('input');input.type='checkbox';input.checked=!excluded.has(f.name);input.onchange=()=>{if(input.checked)excluded.delete(f.name);else excluded.add(f.name);try{localStorage.setItem('signal.excluded',JSON.stringify([...excluded]))}catch{$('status').textContent='Source choices could not be saved in this browser.'}sourceControls();load()};label.append(input,document.createTextNode(f.name));field.append(label)}$('sourceSettings').append(field)}
 sourceControls();
}
async function load(reset=true){
 const ticket=++serial;if(reset)offset=0;
 const query=new URLSearchParams({q:$('search').value,source:$('source').value,unread:$('unread').checked,offset,category,excluded:JSON.stringify([...excluded])});
 $('more').disabled=true;
 try{const d=await api('articles?'+query);if(ticket!==serial)return;
 if(reset){$('list').replaceChildren();needsReload=false;}$('count').textContent=d.total+' articles';
 for(const a of d.items)renderStory(a);offset+=d.items.length;$('more').hidden=offset>=d.total;
 if(!d.total)$('list').append(node('p','No articles match your selections. Change your filters or click UPDATE.','empty'));
 }catch(e){$('status').textContent=e.message}finally{if(ticket===serial)$('more').disabled=false}
}
function renderStory(a){
 const section=node('section',undefined,'story'+(a.is_read?' read':''));
 const button=node('button',undefined,'headline');button.type='button';button.setAttribute('aria-expanded','false');button.setAttribute('aria-controls','article-'+a.id);
 const meta=node('span',undefined,'story-meta');const info=node('span',a.source+' · '+date(a.published));const arrow=node('span','＋');arrow.setAttribute('aria-hidden','true');meta.append(info,arrow);
 button.append(meta,node('h2',a.title),node('span',a.excerpt+(a.excerpt.length>=220?'…':''),'summary'));
 const body=node('article',undefined,'expanded');body.id='article-'+a.id;body.hidden=true;
 let loaded=false,pending=false;
 function setOpen(open){body.hidden=!open;section.classList.toggle('open',open);button.setAttribute('aria-expanded',String(open));arrow.textContent=open?'−':'＋';if(!open){body.querySelectorAll('audio').forEach(el=>el.pause());if(needsReload&&!$('list').querySelector('.open'))load()}}
 async function toggle(){
  if(!body.hidden){setOpen(false);return}setOpen(true);
  if(pending)return;
  if(!loaded){pending=true;body.replaceChildren(node('p','Loading article…'));try{
   const detail=await api('articles/'+a.id);body.replaceChildren();const actions=node('div',undefined,'actions'),link=node('a','Open original ↗');link.href=detail.url;link.target='_blank';link.rel='noopener noreferrer';actions.append(link,node('span',detail.mode+' · '+Math.max(1,Math.ceil(detail.body.split(/\s+/).length/220))+' min read','meta'));body.append(actions);
   if(detail.image){const img=node('img');img.src=detail.image;img.alt='';img.loading='lazy';img.referrerPolicy='no-referrer';img.onerror=()=>img.remove();body.append(img)}
   if(detail.audio){const audio=node('audio');audio.src=detail.audio;audio.controls=true;audio.preload='none';body.append(audio)}
   body.append(node('div',detail.body,'body'));loaded=true;
  }catch(e){body.replaceChildren(node('p','Unable to load this article. Close and reopen to retry.'));$('status').textContent=e.message}finally{pending=false}}
  if(loaded&&!body.hidden&&preferences.autoRead&&!a.is_read){try{await post('articles/'+a.id+'/read');a.is_read=1;section.classList.add('read')}catch(e){$('status').textContent=e.message}}
 }
 button.onclick=toggle;body.onclick=e=>{if(e.target.closest('a,button,audio,input,select')||window.getSelection()?.toString())return;setOpen(false)};
 section.append(button,body);$('list').append(section);
}
async function poll(){if(polling)return;polling=true;try{
 const s=await api('status');$('update').disabled=s.running;$('update').textContent=s.running?'↻ UPDATING…':'↻ UPDATE';$('status').textContent=s.running?'Collecting new stories…':s.error?'Update failed: '+s.error:s.last_update?'Last checked '+date(s.last_update)+(s.next_update?' · Next '+date(s.next_update):''):'Ready for your first edition';$('health').textContent=s.sources.map(f=>f.name+': '+(f.error||f.added+' new articles, '+f.excerpts+' excerpts')).join('\n');
 if(s.last_update!==last){last=s.last_update;await loadCatalog();if(!$('list').querySelector('.open'))await load();else {needsReload=true;$('status').textContent+=' · New stories will appear after you close the open articles';}}
 }catch(e){$('status').textContent='Connection lost. Retrying automatically.'}finally{polling=false}}
$('update').onclick=async()=>{try{$('update').disabled=true;await post('update');await poll()}catch(e){$('status').textContent=e.message;$('update').disabled=false}};
let debounce;$('search').oninput=()=>{clearTimeout(debounce);debounce=setTimeout(()=>load(),300)};$('source').onchange=()=>load();$('unread').onchange=()=>load();$('more').onclick=()=>load(false);
const resetAppearance=$('resetSettings').onclick;$('resetSettings').onclick=()=>{resetAppearance();excluded.clear();try{localStorage.removeItem('signal.excluded')}catch{}loadCatalog().then(()=>load()).catch(e=>$('status').textContent=e.message)};
(async()=>{try{await loadCatalog();await load();await poll()}catch(e){$('status').textContent=e.message}setInterval(poll,5000)})();
