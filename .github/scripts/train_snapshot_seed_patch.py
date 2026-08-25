from pathlib import Path

path=Path('frontend/_worker.js')
src=path.read_text(encoding='utf-8')

old = """        const rosterHasMe=!!(
          meId &&
          data &&
          Array.isArray(data.roster) &&
          data.roster.some(row=>String(row&&row.id||'')===meId)
        );
        sessionStorage.setItem(
"""
new = """        const rosterHasMe=!!(
          meId &&
          data &&
          Array.isArray(data.roster) &&
          data.roster.some(row=>String(row&&row.id||'')===meId)
        );

        /* WFGG_PORTAL_TRAIN_SNAPSHOT_SEED_V1
           Le snapshot authentifié est exactement la source que le frontend
           Train applique dans applySnapshot(). On la précharge dans les mêmes
           clés locales afin que le prochain boot connaisse déjà currentUserId
           et le roster avant même l'exécution de init().
        */
        let seeded=false;
        if(response.ok&&meId&&rosterHasMe&&data&&data.state){
          try{
            let previous={};
            try{
              previous=JSON.parse(localStorage.getItem('wfgg_train_v13')||'{}')||{};
            }catch(_){previous={};}

            const localVariants=previous.messageVariant||{
              weekly:0,daily:0,driver:0,vip:0
            };

            const seededState={
              ...(data.state||{}),
              currentUserId:meId,
              messageVariant:localVariants,
              playerEdits:{},
              addedPlayers:[],
              removedPlayers:[]
            };

            localStorage.setItem(
              'wfgg_train_roster_cache',
              JSON.stringify(data.roster||[])
            );
            localStorage.setItem(
              'wfgg_train_v13',
              JSON.stringify(seededState)
            );
            seeded=true;
          }catch(_){seeded=false;}
        }

        sessionStorage.setItem(
"""

old_store = """            meId:meId?meId.slice(0,24):'',
            rosterHasMe,
            at:Date.now()
          })
        );
        return {ok:response.ok,code,bridge,meId,rosterHasMe};
"""
new_store = """            meId:meId?meId.slice(0,24):'',
            rosterHasMe,
            seeded,
            at:Date.now()
          })
        );
        return {ok:response.ok,code,bridge,meId,rosterHasMe,seeded};
"""

old_success = """      successfulProbe=probe;
      if(probe.meId&&!probe.rosterHasMe){
        fail('SNAPSHOT_ROSTER_USER_MISSING');
        return;
      }
      open();
"""
new_success = """      successfulProbe=probe;
      if(probe.meId&&!probe.rosterHasMe){
        fail('SNAPSHOT_ROSTER_USER_MISSING');
        return;
      }

      const seedReloadKey='wfgg_train_snapshot_seed_reload_v1';
      if(
        probe.seeded &&
        sessionStorage.getItem(seedReloadKey)!=='1'
      ){
        sessionStorage.setItem(seedReloadKey,'1');
        const fresh=new URL(location.href);
        fresh.searchParams.set('wfgg_seed','v1');
        location.replace(fresh.toString());
        return;
      }

      open();
"""

for old_text,new_text,label in [
    (old,new,'snapshot seed insertion'),
    (old_store,new_store,'probe seed status'),
    (old_success,new_success,'seed reload')
]:
    if old_text not in src:
        raise SystemExit(f'Expected {label} not found; refusing blind patch')
    src=src.replace(old_text,new_text,1)

path.write_text(src,encoding='utf-8')
print('TRAIN_SNAPSHOT_SEED_PATCH=OK')
