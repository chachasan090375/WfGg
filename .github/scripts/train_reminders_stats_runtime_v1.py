from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
if 'WFGG_TRAIN_REMINDER_STATS_RUNTIME_V1' in s:
    print('TRAIN_REMINDER_STATS=ALREADY_APPLIED')
    raise SystemExit(0)

anchor="""      return WFGG_NATIVE_FETCH(input,options);\n    };\n  }\n\n  const norm=v=>{\n"""
if anchor not in s:
    raise SystemExit('missing Train fetch bridge anchor')

block=r'''      return WFGG_NATIVE_FETCH(input,options);
    };

    /* WFGG_TRAIN_REMINDER_STATS_RUNTIME_V1
       1) Les rappels personnels s'appuient sur le flux calendrier privé du
          backend Train : J-1 et -30 min, recalculé depuis le planning serveur.
       2) Les statistiques disposent d'un fallback local autoritatif si la
          route analytics échoue ou ne répond pas sur mobile.
    */
    function wfggTrainReadJson(key,fallback){
      try{return JSON.parse(localStorage.getItem(key)||'null')||fallback}catch(_){return fallback}
    }
    function wfggTrainAddDaysISO(ds,n){
      const d=new Date(String(ds)+'T12:00:00Z');d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);
    }
    function wfggTrainAnalyticsFallbackData(){
      const st=wfggTrainReadJson('wfgg_train_v13',{}),roster=wfggTrainReadJson('wfgg_train_roster_cache',[]),schedule=Array.isArray(st.__serverSchedule)?st.__serverSchedule:[];
      const today=new Date().toISOString().slice(0,10),out=new Set((st.outRotation||[]).map(String));
      const active=(Array.isArray(roster)?roster:[]).filter(x=>x&&x.active!==false&&!out.has(String(x.id)));
      function rot(days){
        const end=wfggTrainAddDaysISO(today,days-1),rows=schedule.filter(x=>x&&x.date>=today&&x.date<=end);
        const pools={officer:active.filter(x=>x.rank==='R5'||x.rank==='R4'),r3driver:active.filter(x=>x.rank==='R3'),vip:active.filter(x=>x.rank==='R3')};
        function counts(pool,role,driverClass){
          const map={};pool.forEach(x=>map[String(x.id)]=0);
          rows.forEach(row=>{
            if(driverClass&&row.driverClass!==driverClass)return;
            const id=String(role==='vip'?row.vipId||'':row.driverId||'');if(Object.prototype.hasOwnProperty.call(map,id))map[id]++;
          });
          return pool.map(x=>({id:x.id,pseudo:x.pseudo,rank:x.rank,count:map[String(x.id)]||0})).sort((a,b)=>b.count-a.count||String(a.pseudo).localeCompare(String(b.pseudo)));
        }
        function spread(list){if(!list.length)return 0;const v=list.map(x=>x.count||0);return Math.max.apply(null,v)-Math.min.apply(null,v)}
        const officer=counts(pools.officer,'driver','officer'),r3driver=counts(pools.r3driver,'driver','r3'),vip=counts(pools.vip,'vip',null);
        return {days:days,from:today,to:end,officer:officer,r3driver:r3driver,vip:vip,spread:{officer:spread(officer),r3driver:spread(r3driver),vip:spread(vip)}};
      }
      const mh=st.manualHistory||{},links=mh.links||{},hc=mh.counts||{};
      function histKey(v){return String(v||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
      const historyActive=active.map(u=>{
        const k=links[u.id]||histKey(u.pseudo),d=(hc.driver||{})[k]||{},v=(hc.vip||{})[k]||{};
        return {id:u.id,pseudo:u.pseudo,rank:u.rank,driver:Number(d.count||0),driverLast:d.last||null,vip:Number(v.count||0),vipLast:v.last||null};
      });
      return {ok:true,fallback:true,summary:{actions7:0,actions30:0,activeMembers:active.length,outRotation:(st.outRotation||[]).length,unavailablePlayers:Object.values(st.unavailable||{}).filter(v=>Array.isArray(v)&&v.length).length,openExchanges:(st.exchanges||[]).filter(x=>x&&x.status==='open').length,manualOverrides:Object.keys(st.overrides||{}).length},activityByActor:[],actionCounts:{},rotation30:rot(30),rotation90:rot(90),manualHistory:mh,historyActive:historyActive,entries:[],users:roster,serverTime:new Date().toISOString()};
    }
    function wfggTrainAnalyticsFallbackResponse(){
      return new Response(JSON.stringify(wfggTrainAnalyticsFallbackData()),{status:200,headers:{'content-type':'application/json; charset=utf-8','cache-control':'no-store','x-wfgg-analytics-fallback':'v1'}});
    }
    const WFGG_TRAIN_FETCH_WITH_BRIDGE=window.fetch;
    window.fetch=async function(input,init){
      let path='';try{const raw=typeof input==='string'||input instanceof URL?String(input):input&&input.url;path=new URL(raw||'',location.href).pathname}catch(_){}
      if(path!=='/api/admin/analytics')return WFGG_TRAIN_FETCH_WITH_BRIDGE(input,init);
      try{
        const live=WFGG_TRAIN_FETCH_WITH_BRIDGE(input,init);
        const response=await Promise.race([live,new Promise(resolve=>setTimeout(()=>resolve(null),4500))]);
        if(!response||!response.ok)return wfggTrainAnalyticsFallbackResponse();
        try{
          const data=await response.clone().json();
          if(!data||!data.rotation30||!data.rotation90||!data.manualHistory)return wfggTrainAnalyticsFallbackResponse();
        }catch(_){return wfggTrainAnalyticsFallbackResponse()}
        return response;
      }catch(_){return wfggTrainAnalyticsFallbackResponse()}
    };

    function wfggTrainCurrentAlertsEnabled(){
      const st=wfggTrainReadJson('wfgg_train_v13',{}),id=st.currentUserId;return !!(id&&st.alertsEnabled&&st.alertsEnabled[id]);
    }
    function wfggTrainReminderOverlay(feedPath){
      document.getElementById('wfgg-calendar-subscribe-overlay')?.remove();
      const httpsUrl=location.origin+feedPath,webcal=httpsUrl.replace(/^https:/i,'webcal:');
      const wrap=document.createElement('div');wrap.id='wfgg-calendar-subscribe-overlay';
      wrap.style.cssText='position:fixed;inset:0;z-index:99999;background:rgba(0,12,28,.78);display:flex;align-items:center;justify-content:center;padding:20px';
      const box=document.createElement('div');box.style.cssText='max-width:520px;width:100%;background:#092443;border:1px solid #b89546;border-radius:22px;padding:22px;color:#fff;box-shadow:0 20px 70px rgba(0,0,0,.45)';
      box.innerHTML='<h2 style="margin-top:0">🔔 Rappels automatiques</h2><p>Ce calendrier privé suit le planning WfGg automatiquement. Les rappels sont programmés à <b>J-1</b> et <b>30 minutes avant</b>.</p><a id="wfgg-calendar-open" style="display:block;text-align:center;text-decoration:none;background:#f5c552;color:#08203a;font-weight:800;padding:14px;border-radius:14px;margin:14px 0" href="'+webcal+'">📅 S’abonner dans mon calendrier</a><button id="wfgg-calendar-copy" style="width:100%;padding:12px;border-radius:12px;border:1px solid #7892ad;background:#123659;color:#fff;font-weight:700">Copier l’adresse du calendrier</button><button id="wfgg-calendar-close" style="width:100%;padding:12px;border:0;background:transparent;color:#d6dfeb;margin-top:8px">Fermer</button>';
      wrap.appendChild(box);document.body.appendChild(wrap);
      box.querySelector('#wfgg-calendar-copy').onclick=async()=>{try{await navigator.clipboard.writeText(httpsUrl);box.querySelector('#wfgg-calendar-copy').textContent='✅ Adresse copiée'}catch(_){location.href=httpsUrl}};
      box.querySelector('#wfgg-calendar-close').onclick=()=>wrap.remove();wrap.onclick=e=>{if(e.target===wrap)wrap.remove()};
    }
    window.__WFGG_OPEN_TRAIN_CALENDAR_FEED__=async function(){
      try{
        const r=await window.fetch('/api/me/calendar-link',{method:'GET',cache:'no-store'});const d=await r.json();if(!r.ok||!d.feedPath)throw new Error(d.error||'Calendrier indisponible');wfggTrainReminderOverlay(d.feedPath);
      }catch(e){alert(String(e&&e.message||e))}
    };
    function wfggTrainEnhanceAlerts(){
      const screen=document.getElementById('alertsScreen');if(!screen)return;
      const old=screen.querySelector('[data-wfgg-calendar-reminders]');if(old)old.remove();
      if(!wfggTrainCurrentAlertsEnabled())return;
      const card=document.createElement('div');card.className='alert-card';card.setAttribute('data-wfgg-calendar-reminders','v1');
      card.innerHTML='<h3>🔔 Rappels automatiques synchronisés</h3><p>Abonne ton calendrier une seule fois. Les changements du planning, échanges et corrections seront repris au prochain rafraîchissement du calendrier.</p><button class="btn gold full" type="button">Configurer mes rappels J-1 / -30 min</button>';
      card.querySelector('button').onclick=()=>window.__WFGG_OPEN_TRAIN_CALENDAR_FEED__();
      const hour=Array.from(screen.querySelectorAll('.alert-card')).find(x=>/Heure du train/.test(x.textContent||''));if(hour)screen.insertBefore(card,hour);else screen.appendChild(card);
    }
    const wfggTrainAlertObserver=new MutationObserver(()=>wfggTrainEnhanceAlerts());
    if(document.documentElement)wfggTrainAlertObserver.observe(document.documentElement,{subtree:true,childList:true});
    const wfggTrainHook=setInterval(()=>{
      if(!window.W||typeof window.W.toggleAlerts!=='function')return;
      if(!window.W.__wfggReminderHooked){
        const original=window.W.toggleAlerts.bind(window.W);window.W.toggleAlerts=async function(){const v=await original();setTimeout(wfggTrainEnhanceAlerts,100);return v};
        window.W.__wfggReminderHooked=true;window.W.openReminderCalendar=window.__WFGG_OPEN_TRAIN_CALENDAR_FEED__;
      }
      wfggTrainEnhanceAlerts();clearInterval(wfggTrainHook);
    },120);
  }

  const norm=v=>{
'''

s=s.replace(anchor,block,1)
p.write_text(s,encoding='utf-8')
print('TRAIN_REMINDER_STATS=OK')
