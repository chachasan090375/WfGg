(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const TACTICS_KEY='wfgg-simulator-tactics-v2';
  const OPTIMIZER_KEY='wfgg-simulator-optimizer-ui-v1';
  const nativeGet=Storage.prototype.getItem;
  const nativeSet=Storage.prototype.setItem;
  const nativeRemove=Storage.prototype.removeItem;
  const parse=v=>{try{return JSON.parse(v)||{};}catch(_){return {};}};
  const stamp=p=>{p.metadata=p.metadata||{};p.metadata.updatedAt=new Date().toISOString();return p;};

  function enrichProfileString(value){
    const incoming=parse(value);
    const existing=parse(nativeGet.call(localStorage,PROFILE_KEY));
    incoming.season6=incoming.season6||{};
    if(incoming.season6.tacticsV2==null && existing.season6?.tacticsV2!=null) incoming.season6.tacticsV2=existing.season6.tacticsV2;
    incoming.simulatorUi=incoming.simulatorUi||{};
    if(incoming.simulatorUi.optimizer==null && existing.simulatorUi?.optimizer!=null) incoming.simulatorUi.optimizer=existing.simulatorUi.optimizer;
    return JSON.stringify(stamp(incoming));
  }

  function mirrorSidecar(key,value){
    const profile=parse(nativeGet.call(localStorage,PROFILE_KEY));
    profile.season6=profile.season6||{};
    profile.simulatorUi=profile.simulatorUi||{};
    if(key===TACTICS_KEY) profile.season6.tacticsV2=parse(value);
    if(key===OPTIMIZER_KEY) profile.simulatorUi.optimizer=parse(value);
    nativeSet.call(localStorage,PROFILE_KEY,JSON.stringify(stamp(profile)));
  }

  if(!window.__wfggProfileStoragePatched){
    window.__wfggProfileStoragePatched=true;
    Storage.prototype.setItem=function(key,value){
      if(this===localStorage && key===PROFILE_KEY) value=enrichProfileString(value);
      nativeSet.call(this,key,value);
      if(this===localStorage && (key===TACTICS_KEY||key===OPTIMIZER_KEY)) mirrorSidecar(key,value);
    };
  }

  function migrate(){
    const tactics=nativeGet.call(localStorage,TACTICS_KEY);
    const optimizer=nativeGet.call(localStorage,OPTIMIZER_KEY);
    if(tactics!=null) mirrorSidecar(TACTICS_KEY,tactics);
    if(optimizer!=null) mirrorSidecar(OPTIMIZER_KEY,optimizer);
  }

  function commitFocused(){
    const el=document.activeElement;
    if(!el || !el.matches?.('input,select,textarea') || el.disabled || el.readOnly) return;
    try{el.dispatchEvent(new Event('change',{bubbles:true}));}catch(_){}
  }

  window.addEventListener('pagehide',commitFocused,{capture:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)commitFocused();},{capture:true});
  window.addEventListener('beforeunload',commitFocused,{capture:true});
  migrate();
  window.WfGgProfilePersistence=Object.freeze({version:'2.0.0',PROFILE_KEY,TACTICS_KEY,OPTIMIZER_KEY,migrate,commitFocused});
})();
