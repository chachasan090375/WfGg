(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const TACTICS_KEY='wfgg-simulator-tactics-v2';
  const OPTIMIZER_KEY='wfgg-simulator-optimizer-ui-v1';
  const SCHEMA='wfgg-simulator-profile-v1';
  const nativeGet=Storage.prototype.getItem;
  const nativeSet=Storage.prototype.setItem;
  const parse=v=>{try{return JSON.parse(v)||{};}catch(_){return {};}};
  const clone=v=>JSON.parse(JSON.stringify(v));
  const stamp=p=>{p.metadata=p.metadata||{};p.metadata.schema=p.metadata.schema||SCHEMA;p.metadata.updatedAt=new Date().toISOString();return p;};
  const numeric=el=>el.type==='number'?Number(el.value||0):el.value;
  const fieldValue=el=>el.type==='checkbox'?el.checked:(el.type==='number'?(el.value===''?'':Number(el.value)):el.value);
  const isPlain=v=>!!v&&typeof v==='object'&&!Array.isArray(v);

  function profile(){return parse(nativeGet.call(localStorage,PROFILE_KEY));}
  function writeProfile(p){nativeSet.call(localStorage,PROFILE_KEY,JSON.stringify(stamp(p)));}

  function preserveMissing(existing,incoming){
    if(Array.isArray(incoming)){
      const old=Array.isArray(existing)?existing:[];
      return incoming.map((v,i)=>preserveMissing(old[i],v));
    }
    if(isPlain(incoming)){
      const out={...incoming};
      const old=isPlain(existing)?existing:{};
      Object.keys(old).forEach(k=>{
        if(!(k in out))out[k]=clone(old[k]);
        else out[k]=preserveMissing(old[k],out[k]);
      });
      return out;
    }
    return incoming;
  }

  function preserveAutosavedHeroes(existing,incoming){
    if(!Array.isArray(incoming))return incoming;
    const old=Array.isArray(existing)?existing:[];
    return incoming.map((hero,i)=>{
      if(!isPlain(hero)||!isPlain(old[i]))return hero;
      return {...hero,...clone(old[i])};
    });
  }

  // Any full-profile write from the legacy app is reconciled with the form that
  // is actually visible at that instant. This prevents an older in-memory copy
  // from erasing the last character/value typed immediately before navigation,
  // reload, backgrounding or another module save.
  function overlayLiveForm(p){
    if(typeof document==='undefined'||!document.querySelector)return p;
    try{
      p.account=p.account||{};
      document.querySelectorAll('[data-account]').forEach(el=>{p.account[el.dataset.account]=fieldValue(el);});
      p.account.troopCenters=p.account.troopCenters||{};
      document.querySelectorAll('[data-center]').forEach(el=>{p.account.troopCenters[el.dataset.center]=fieldValue(el);});
      p.account.marchSizeAdditional=p.account.marchSizeAdditional||{};
      document.querySelectorAll('[data-march]').forEach(el=>{p.account.marchSizeAdditional[el.dataset.march]=fieldValue(el);});

      const heroCards=[...document.querySelectorAll('.hero-card')];
      if(heroCards.length&&Array.isArray(p.heroes))heroCards.forEach((card,order)=>{
        const raw=Number(card.dataset.index),i=Number.isInteger(raw)&&raw>=0?raw:order;
        if(i>=p.heroes.length)return;
        p.heroes[i]=p.heroes[i]||{};
        card.querySelectorAll('[data-field]').forEach(el=>{p.heroes[i][el.dataset.field]=fieldValue(el);});
      });

      const gearCards=[...document.querySelectorAll('.gear-card')];
      if(gearCards.length&&Array.isArray(p.gear))gearCards.forEach((card,i)=>{
        if(i>=p.gear.length)return;
        p.gear[i]=p.gear[i]||{};
        card.querySelectorAll('[data-field]').forEach(el=>{p.gear[i][el.dataset.field]=fieldValue(el);});
      });

      p.research=p.research||{};
      document.querySelectorAll('[data-research-level]').forEach(el=>{const id=el.dataset.researchLevel;p.research[id]=p.research[id]||{};p.research[id].level=fieldValue(el);});
      document.querySelectorAll('[data-research-bonus]').forEach(el=>{const id=el.dataset.researchBonus;p.research[id]=p.research[id]||{};p.research[id].displayedBonusPct=fieldValue(el);});

      p.season6=p.season6||{};p.season6.totemLevels=p.season6.totemLevels||{};p.season6.tacticsCards=p.season6.tacticsCards||{};
      document.querySelectorAll('[data-totem]').forEach(el=>{p.season6.totemLevels[el.dataset.totem]=fieldValue(el);});
      document.querySelectorAll('[data-card]').forEach(el=>{p.season6.tacticsCards[el.dataset.card]=fieldValue(el);});
    }catch(_){}
    return p;
  }

  function enrichProfileString(value){
    const incoming=parse(value),existing=profile();
    const merged=preserveMissing(existing,incoming);
    if(Array.isArray(incoming.heroes)) merged.heroes=preserveAutosavedHeroes(existing.heroes,incoming.heroes);
    merged.season6=merged.season6||{};
    if(merged.season6.tacticsV2==null && existing.season6?.tacticsV2!=null) merged.season6.tacticsV2=existing.season6.tacticsV2;
    merged.simulatorUi=merged.simulatorUi||{};
    if(merged.simulatorUi.optimizer==null && existing.simulatorUi?.optimizer!=null) merged.simulatorUi.optimizer=existing.simulatorUi.optimizer;
    overlayLiveForm(merged);
    return JSON.stringify(stamp(merged));
  }

  function mirrorSidecar(key,value){
    const p=profile();p.season6=p.season6||{};p.simulatorUi=p.simulatorUi||{};
    if(key===TACTICS_KEY)p.season6.tacticsV2=parse(value);
    if(key===OPTIMIZER_KEY)p.simulatorUi.optimizer=parse(value);
    writeProfile(overlayLiveForm(p));
  }

  if(!window.__wfggProfileStoragePatched){
    window.__wfggProfileStoragePatched=true;
    Storage.prototype.setItem=function(key,value){
      if(this===localStorage&&key===PROFILE_KEY)value=enrichProfileString(value);
      nativeSet.call(this,key,value);
      if(this===localStorage&&(key===TACTICS_KEY||key===OPTIMIZER_KEY))mirrorSidecar(key,value);
    };
  }

  function migrate(){
    const tactics=nativeGet.call(localStorage,TACTICS_KEY),optimizer=nativeGet.call(localStorage,OPTIMIZER_KEY);
    if(tactics!=null)mirrorSidecar(TACTICS_KEY,tactics);
    if(optimizer!=null)mirrorSidecar(OPTIMIZER_KEY,optimizer);
  }

  function saveMainInput(el){
    const p=profile();let changed=true;
    if(el.dataset.account){p.account=p.account||{};p.account[el.dataset.account]=el.type==='checkbox'?el.checked:numeric(el);}
    else if(el.dataset.center){p.account=p.account||{};p.account.troopCenters=p.account.troopCenters||{};p.account.troopCenters[el.dataset.center]=numeric(el);}
    else if(el.dataset.march){p.account=p.account||{};p.account.marchSizeAdditional=p.account.marchSizeAdditional||{};p.account.marchSizeAdditional[el.dataset.march]=numeric(el);}
    else if(el.dataset.field&&el.closest('.hero-card')){
      const card=el.closest('.hero-card'),i=Number(card.dataset.index);p.heroes=Array.isArray(p.heroes)?p.heroes:[];p.heroes[i]=p.heroes[i]||{};p.heroes[i][el.dataset.field]=el.type==='checkbox'?el.checked:numeric(el);
    } else if(el.dataset.field&&el.closest('.gear-card')){
      const card=el.closest('.gear-card'),cards=[...document.querySelectorAll('.gear-card')],i=cards.indexOf(card);p.gear=Array.isArray(p.gear)?p.gear:[];p.gear[i]=p.gear[i]||{};p.gear[i][el.dataset.field]=numeric(el);
    } else if(el.dataset.researchLevel){p.research=p.research||{};const id=el.dataset.researchLevel;p.research[id]=p.research[id]||{};p.research[id].level=numeric(el);}
    else if(el.dataset.researchBonus){p.research=p.research||{};const id=el.dataset.researchBonus;p.research[id]=p.research[id]||{};p.research[id].displayedBonusPct=el.value===''?'':Number(el.value);}
    else if(el.dataset.totem){p.season6=p.season6||{};p.season6.totemLevels=p.season6.totemLevels||{};p.season6.totemLevels[el.dataset.totem]=numeric(el);}
    else if(el.dataset.card){p.season6=p.season6||{};p.season6.tacticsCards=p.season6.tacticsCards||{};p.season6.tacticsCards[el.dataset.card]=numeric(el);}
    else changed=false;
    if(changed)writeProfile(overlayLiveForm(p));
    return changed;
  }

  function autosave(e){
    const el=e.target;
    if(!el?.matches?.('input,textarea,select'))return;
    if(el.closest?.('#tacticsCardsV2'))return;
    saveMainInput(el);
  }
  document.addEventListener('input',autosave,{capture:true});
  document.addEventListener('change',autosave,{capture:true});

  function commitFocused(){
    const el=document.activeElement;
    if(!el||!el.matches?.('input,select,textarea')||el.disabled||el.readOnly)return;
    if(el.closest?.('#tacticsCardsV2'))return;
    try{saveMainInput(el);}catch(_){}
  }
  window.addEventListener('pagehide',commitFocused,{capture:true});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)commitFocused();},{capture:true});
  window.addEventListener('beforeunload',commitFocused,{capture:true});
  migrate();
  window.WfGgProfilePersistence=Object.freeze({version:'2.4.0',revision:'live-dom-authority-v2',PROFILE_KEY,TACTICS_KEY,OPTIMIZER_KEY,migrate,commitFocused,profile:()=>clone(profile())});
})();
