from pathlib import Path

path = Path('frontend/_worker.js')
src = path.read_text(encoding='utf-8')

old_probe_tail = """        const code=String((data&&data.error)||('HTTP_'+response.status));
        const bridge=response.headers.get('X-WfGg-Portal-Bridge')||'';
        sessionStorage.setItem(
          'wfgg_train_bridge_probe_v1',
          JSON.stringify({
            ok:response.ok,
            status:response.status,
            code,
            bridge,
            at:Date.now()
          })
        );
        return {ok:response.ok,code,bridge};
"""
new_probe_tail = """        const code=String((data&&data.error)||('HTTP_'+response.status));
        const bridge=response.headers.get('X-WfGg-Portal-Bridge')||'';
        const meId=String(data&&data.me&&data.me.id||'');
        const rosterHasMe=!!(
          meId &&
          data &&
          Array.isArray(data.roster) &&
          data.roster.some(row=>String(row&&row.id||'')===meId)
        );
        sessionStorage.setItem(
          'wfgg_train_bridge_probe_v1',
          JSON.stringify({
            ok:response.ok,
            status:response.status,
            code,
            bridge,
            meId:meId?meId.slice(0,24):'',
            rosterHasMe,
            at:Date.now()
          })
        );
        return {ok:response.ok,code,bridge,meId,rosterHasMe};
"""

old_attempts = """    let attempts=0;
    const maxAttempts=80;
    const open=()=>{
"""
new_attempts = """    let attempts=0;
    let successfulProbe=null;
    const maxAttempts=80;

    const bootDiagnostic=()=>{
      try{
        if(!window.W||typeof window.W.showTrainEntry!=='function'){
          return 'BOOT_W_NOT_READY';
        }

        const app=document.getElementById('appView');
        if(!app)return 'BOOT_APPVIEW_MISSING';

        let trainState={};
        try{
          trainState=JSON.parse(localStorage.getItem('wfgg_train_v13')||'{}')||{};
        }catch(_){return 'BOOT_STATE_INVALID';}

        const currentUserId=String(trainState.currentUserId||'');
        if(!currentUserId){
          if(successfulProbe&&successfulProbe.meId){
            return successfulProbe.rosterHasMe
              ? 'BOOT_STATE_USER_MISSING'
              : 'SNAPSHOT_ROSTER_USER_MISSING';
          }
          return 'BOOT_STATE_USER_MISSING';
        }

        let roster=[];
        try{
          roster=JSON.parse(localStorage.getItem('wfgg_train_roster_cache')||'[]');
        }catch(_){return 'BOOT_ROSTER_CACHE_INVALID';}

        if(!Array.isArray(roster)||!roster.some(row=>String(row&&row.id||'')===currentUserId)){
          return 'BOOT_LOCAL_ROSTER_USER_MISSING';
        }

        return app.classList.contains('hidden')
          ? 'BOOT_APPVIEW_STILL_HIDDEN'
          : 'BOOT_UNKNOWN';
      }catch(_){
        return 'BOOT_DIAGNOSTIC_ERROR';
      }
    };

    const open=()=>{
"""

old_timeout = """      hideLegacyEntry();
      if(attempts<maxAttempts)setTimeout(open,150);
      else fail();
    };

    probePortalTrain().then((probe)=>{
      if(!probe.ok){
        fail(probe.code);
        return;
      }
      open();
    });
"""
new_timeout = """      hideLegacyEntry();
      if(attempts<maxAttempts)setTimeout(open,150);
      else fail(bootDiagnostic());
    };

    probePortalTrain().then((probe)=>{
      if(!probe.ok){
        fail(probe.code);
        return;
      }
      successfulProbe=probe;
      if(probe.meId&&!probe.rosterHasMe){
        fail('SNAPSHOT_ROSTER_USER_MISSING');
        return;
      }
      open();
    });
"""

for old, new, label in [
    (old_probe_tail, new_probe_tail, 'probe summary'),
    (old_attempts, new_attempts, 'boot diagnostic helper'),
    (old_timeout, new_timeout, 'diagnostic timeout')
]:
    if old not in src:
        raise SystemExit(f'Expected {label} not found; refusing blind patch')
    src = src.replace(old, new, 1)

path.write_text(src, encoding='utf-8')
print('TRAIN_BOOT_DIAGNOSTIC_PATCH=OK')
