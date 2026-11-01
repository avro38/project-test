'use strict';
(()=>{
const local=['localhost','127.0.0.1'].includes(location.hostname),listeners=new Set();let state={},queue=Promise.resolve();
const pending=new Map();window.addEventListener('pagehide',()=>{if(local)for(const item of pending.values())navigator.sendBeacon('/api/personal',new Blob([JSON.stringify(item)],{type:'application/json'}));});
const ready=local?fetch('/api/personal',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Сервер сохранения недоступен');return r.json();}).then(s=>{state=s;}).catch(()=>{}):Promise.resolve();
window.PMPersonal={ready,get:k=>state[k],subscribe:fn=>{listeners.add(fn);return()=>listeners.delete(fn);},put(k,value,updatedAt){
 if(!local)return Promise.resolve(false);
 const copy=JSON.parse(JSON.stringify(value));pending.set(k,{key:k,value:copy,updatedAt});
 const operation=queue.catch(()=>{}).then(()=>ready).then(async()=>{const r=await fetch('/api/personal',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:k,value:copy,updatedAt})});if(!r.ok)throw Error('Не удалось сохранить в файл');const result=await r.json();state[k]=result;if(pending.get(k)?.updatedAt===updatedAt)pending.delete(k);listeners.forEach(fn=>fn(k,result));return true;});
 queue=operation;return operation;
}};
})();
