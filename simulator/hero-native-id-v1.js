(() => {
  'use strict';
  const PROFILE_KEY='wfgg-simulator-profile-v1';
  const norm=v=>String(v||'').trim().toLowerCase();
  const previousSet=Storage.prototype.setItem;
  let catalog=[];
  let byName=new Map();
  let ready=false;

  function currentCatalog(){
    try{return window.WfGgHeroRosterV2?.catalog?.()||[];}catch(_){return []}
  }
  function parse(value){try{return JSON.parse(value)||{};}catch(_){return {}}}
  function enrichProfile(profile){
    if(!profile||!Array.isArray(profile.heroes)||!ready)return false;
    let changed=false;
    profile.heroes.forEach(hero=>{
      if(!hero||typeof hero!=='object')return;
      let cat=null;
      if(hero.nativeId!=null)cat=catalog.find(x=>Number(x.nativeId)===Number(hero.nativeId))||null;
      if(!cat&&hero.catalogId)cat=catalog.find(x=>x.id===hero.catalogId)||null;
      if(!cat&&hero.heroId)cat=byName.get(norm(hero.heroId))||null;
      if(!cat||cat.nativeId==null)return;
      if(Number(hero.nativeId)!==Number(cat.nativeId)){hero.nativeId=Number(cat.nativeId);changed=true;}
      if(hero.catalogId!==cat.id){hero.catalogId=cat.id;changed=true;}
      if(hero.nativeSource!=='lw_hero'){hero.nativeSource='lw_hero';changed=true;}
    });
    if(changed){
      profile.metadata=profile.metadata||{};
      profile.metadata.nativeHeroIds='lw_hero:type=1';
      profile.metadata.nativeHeroIdsUpdatedAt=new Date().toISOString();
    }
    return changed;
  }

  if(!window.__wfggNativeHeroIdStoragePatch){
    window.__wfggNativeHeroIdStoragePatch=true;
    Storage.prototype.setItem=function(key,value){
      if(this===localStorage&&key===PROFILE_KEY&&ready){
        const profile=parse(value);
        enrichProfile(profile);
        value=JSON.stringify(profile);
      }
      return previousSet.call(this,key,value);
    };
  }

  function migrateStoredProfile(){
    const profile=parse(localStorage.getItem(PROFILE_KEY));
    if(!enrichProfile(profile))return false;
    Storage.prototype.setItem.call(localStorage,PROFILE_KEY,JSON.stringify(profile));
    try{window.dispatchEvent(new CustomEvent('wfgg:native-hero-ids-migrated'));}catch(_){}
    return true;
  }

  function bootstrap(attempt=0){
    catalog=currentCatalog().filter(x=>x&&x.nativeId!=null);
    if(!catalog.length){
      if(attempt<120)setTimeout(()=>bootstrap(attempt+1),100);
      return;
    }
    byName=new Map(catalog.map(x=>[norm(x.name),x]));
    ready=true;
    migrateStoredProfile();
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>bootstrap(),{once:true});
  else bootstrap();

  window.WfGgNativeHeroIds=Object.freeze({
    version:'1.0.0',
    migrate:migrateStoredProfile,
    catalog:()=>catalog.slice()
  });
})();
