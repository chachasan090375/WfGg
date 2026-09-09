(() => {
  'use strict';

  const VERSION='WFGG_PORTAL_TRAIN_CLEANBOOT_V1';
  const LINK_ID='trainModuleLink';
  let opening=false;

  const timeout=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));

  async function cleanupTrainRuntime(){
    try{
      sessionStorage.removeItem('wfgg_train_sw_reset_v1');
      sessionStorage.removeItem('wfgg_train_sw_reset_v2');
      sessionStorage.removeItem('wfgg_train_snapshot_seed_reload_v1');
    }catch(_){ }

    if('serviceWorker' in navigator){
      try{
        const regs=await Promise.race([
          navigator.serviceWorker.getRegistrations(),
          timeout(700).then(()=>[])
        ]);
        await Promise.all((regs||[]).map(async reg=>{
          try{
            const scopePath=new URL(reg.scope).pathname;
            const active=reg.active?.scriptURL||reg.waiting?.scriptURL||reg.installing?.scriptURL||'';
            const scriptPath=active?new URL(active).pathname:'';
            if(scopePath.startsWith('/train/') && scriptPath!=='/train/wfgg-push-sw.js'){
              await reg.unregister();
            }
          }catch(_){ }
        }));
      }catch(_){ }
    }

    if('caches' in window){
      try{
        const keys=await Promise.race([
          caches.keys(),
          timeout(700).then(()=>[])
        ]);
        await Promise.all(
          (keys||[])
            .filter(key=>/train|wfgg/i.test(key))
            .map(key=>caches.delete(key).catch(()=>false))
        );
      }catch(_){ }
    }
  }

  function cleanBootUrl(link){
    const target=new URL(link?.href||'/train/',location.href);
    target.searchParams.set('wfgg_cleanboot','v1-'+Date.now());
    const lang=String(localStorage.getItem('wfgg_portal_language')||'').trim().toLowerCase();
    if(lang && !target.searchParams.has('lang')) target.searchParams.set('lang',lang);
    return target.toString();
  }

  async function openTrainCleanly(event){
    const link=event.target?.closest?.('#'+LINK_ID);
    if(!link || opening) return;
    opening=true;
    event.preventDefault();
    event.stopImmediatePropagation();

    const url=cleanBootUrl(link);
    try{
      await Promise.race([cleanupTrainRuntime(),timeout(1200)]);
    }catch(_){ }
    location.assign(url);
  }

  document.addEventListener('click',openTrainCleanly,true);
  window.WFGG_TRAIN_CLEANBOOT={version:VERSION,cleanupTrainRuntime};
})();
