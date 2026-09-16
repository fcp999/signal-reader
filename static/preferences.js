const preferenceDefaults={theme:'dark',textSize:'medium',font:'serif',spacing:'normal',width:'normal',density:'comfortable',images:true,autoRead:true};
let preferences={...preferenceDefaults};
try{const saved=JSON.parse(localStorage.getItem('signal.preferences')||'{}');for(const key of Object.keys(preferenceDefaults)){const input=document.getElementById(key);if(typeof preferenceDefaults[key]==='boolean'){if(typeof saved[key]==='boolean')preferences[key]=saved[key]}else if([...input.options].some(o=>o.value===saved[key]))preferences[key]=saved[key]}}catch{}
function applyPreferences(){for(const [key,value] of Object.entries(preferences)){document.documentElement.dataset[key]=String(value);const input=document.getElementById(key);if(input.type==='checkbox')input.checked=value;else input.value=value}}
function savePreferences(){applyPreferences();try{localStorage.setItem('signal.preferences',JSON.stringify(preferences))}catch{document.getElementById('status').textContent='Browser storage unavailable. Preferences apply for this visit only.'}}
for(const key of Object.keys(preferenceDefaults)){document.getElementById(key).addEventListener('change',e=>{preferences[key]=e.target.type==='checkbox'?e.target.checked:e.target.value;savePreferences()})}
document.getElementById('preferences').onclick=()=>document.getElementById('settings').showModal();
document.getElementById('resetSettings').onclick=()=>{preferences={...preferenceDefaults};savePreferences()};
applyPreferences();
