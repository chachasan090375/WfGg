(() => {
'use strict';
const cfg=window.WFGG_PORTAL_CONFIG||{API_BASE:'',MODULES:{}};
const LEGACY=window.WFGG_LEGACY_AVATARS||{};
const TOKEN_KEY='wfgg_portal_session', LANG_KEY='wfgg_portal_language', LANG_SOURCE_KEY='wfgg_portal_language_source';
const SUPPORTED_LANGS=['fr','it','en','es'];
const normalizeLanguage=v=>{
  const x=String(v||'').trim().toLowerCase().replace('_','-').split('-')[0];
  return SUPPORTED_LANGS.includes(x)?x:'';
};
const detectDeviceLanguage=()=>{
  const candidates=[...(Array.isArray(navigator.languages)?navigator.languages:[]),navigator.language];
  for(const candidate of candidates){
    const lang=normalizeLanguage(candidate);
    if(lang)return lang;
  }
  return 'fr';
};
const initialLanguage=()=>{
  const source=localStorage.getItem(LANG_SOURCE_KEY);
  const saved=normalizeLanguage(localStorage.getItem(LANG_KEY));
  if(saved&&['manual','profile'].includes(source))return saved;
  return detectDeviceLanguage()||saved||'fr';
};
const RANKS=['R5','R4','R3','R2','R1'];
const OFFICES=['','WARLORD','RECRUITER','MUSE','BUTLER'];
const OFFICE_FR={WARLORD:'Seigneur de guerre',RECRUITER:'Recruteur',MUSE:'Muse',BUTLER:'Majordome'};
const state={user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},lang:initialLanguage(),members:[],filters:new Set(),search:'',settingsTab:'profile',sessions:[],trainRotationSummary:null,trainRotationLoading:false};
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const I18N={
 fr:{auth:{title:'Portail',subtitle:'Entrez votre code WfGg pour vous connecter.',code:'Code d’authentification',login:'Se connecter',bad:'Code invalide ou compte désactivé.'},home:{portal:'Portail',welcome:'Bienvenue',settings:'⚙️ Paramètres',logout:'Déconnexion',profileIncomplete:'Votre profil est incomplet. Vous pouvez le compléter dans Paramètres.',guidesSub:'Saison 6 et Inter-Saison',trainSub:'Organisation et rotations',settingsSub:'Profil, alliance et administration'},settings:{title:'Paramètres',profile:'Mon profil',alliance:'Alliance',application:'Application',rights:'Droits & accès',save:'Enregistrer',security:'Sécurité de mon profil',sessions:'Mes sessions'},members:{title:'Joueurs de l’alliance',add:'Ajouter un joueur',search:'Rechercher un pseudo…',edit:'Modifier',disable:'Désactiver',enable:'Réactiver'}},
 it:{auth:{title:'Portale',subtitle:'Inserisci il tuo codice WfGg per accedere.',code:'Codice di autenticazione',login:'Accedi',bad:'Codice non valido o account disattivato.'},home:{portal:'Portale',welcome:'Benvenuto',settings:'⚙️ Impostazioni',logout:'Disconnetti',profileIncomplete:'Il tuo profilo è incompleto. Puoi completarlo nelle Impostazioni.',guidesSub:'Stagione 6 e Interstagione',trainSub:'Organizzazione e rotazioni',settingsSub:'Profilo, alleanza e amministrazione'},settings:{title:'Impostazioni',profile:'Il mio profilo',alliance:'Alleanza',application:'Applicazione',rights:'Diritti e accesso',save:'Salva',security:'Sicurezza del mio profilo',sessions:'Le mie sessioni'},members:{title:'Giocatori dell’alleanza',add:'Aggiungi giocatore',search:'Cerca un nome…',edit:'Modifica',disable:'Disattiva',enable:'Riattiva'}},
 en:{auth:{title:'Portal',subtitle:'Enter your WfGg code to sign in.',code:'Authentication code',login:'Sign in',bad:'Invalid code or disabled account.'},home:{portal:'Portal',welcome:'Welcome',settings:'⚙️ Settings',logout:'Sign out',profileIncomplete:'Your profile is incomplete. You can complete it in Settings.',guidesSub:'Season 6 and Interseason',trainSub:'Organisation and rotations',settingsSub:'Profile, alliance and administration'},settings:{title:'Settings',profile:'My profile',alliance:'Alliance',application:'Application',rights:'Rights & access',save:'Save',security:'My profile security',sessions:'My sessions'},members:{title:'Alliance players',add:'Add player',search:'Search a player…',edit:'Edit',disable:'Disable',enable:'Enable'}},
 es:{auth:{title:'Portal',subtitle:'Introduce tu código WfGg para iniciar sesión.',code:'Código de autenticación',login:'Entrar',bad:'Código no válido o cuenta desactivada.'},home:{portal:'Portal',welcome:'Bienvenido',settings:'⚙️ Ajustes',logout:'Cerrar sesión',profileIncomplete:'Tu perfil está incompleto. Puedes completarlo en Ajustes.',guidesSub:'Temporada 6 e Intertemporada',trainSub:'Organización y rotaciones',settingsSub:'Perfil, alianza y administración'},settings:{title:'Ajustes',profile:'Mi perfil',alliance:'Alianza',application:'Aplicación',rights:'Derechos y acceso',save:'Guardar',security:'Seguridad de mi perfil',sessions:'Mis sesiones'},members:{title:'Jugadores de la alianza',add:'Añadir jugador',search:'Buscar jugador…',edit:'Editar',disable:'Desactivar',enable:'Reactivar'}}
};
Object.assign(I18N.fr.home,{
  welcomeText:'Choisissez votre espace WfGg.',
  guidesTitle:'Guides',
  trainTitle:'Train',
  profileMenu:'Menu du profil',
  mainNav:'Navigation principale'
});
Object.assign(I18N.it.home,{
  welcomeText:'Scegli il tuo spazio WfGg.',
  guidesTitle:'Guide',
  trainTitle:'Treno',
  profileMenu:'Menu del profilo',
  mainNav:'Navigazione principale'
});
Object.assign(I18N.en.home,{
  welcomeText:'Choose your WfGg space.',
  guidesTitle:'Guides',
  trainTitle:'Train',
  profileMenu:'Profile menu',
  mainNav:'Main navigation'
});
Object.assign(I18N.es.home,{
  welcomeText:'Elige tu espacio WfGg.',
  guidesTitle:'Guías',
  trainTitle:'Tren',
  profileMenu:'Menú del perfil',
  mainNav:'Navegación principal'
});
Object.assign(I18N.fr.settings,{saving:'Enregistrement…',saved:'✓ Enregistré'});
Object.assign(I18N.it.settings,{saving:'Salvataggio…',saved:'✓ Salvato'});
Object.assign(I18N.en.settings,{saving:'Saving…',saved:'✓ Saved'});
Object.assign(I18N.es.settings,{saving:'Guardando…',saved:'✓ Guardado'});
const t=path=>path.split('.').reduce((o,k)=>o?.[k],I18N[state.lang]||I18N.fr)||path;
const isAdmin=()=>Boolean(state.permissions?.can_admin_members && ['R4','R5'].includes(state.membership?.rank));
const profileComplete=()=>Boolean(state.user?.profile_completed);
function setView(id){['bootView','authView','portalView'].forEach(x=>$(x)?.classList.add('hidden'));$(id)?.classList.remove('hidden')}
function token(){return localStorage.getItem(TOKEN_KEY)}
async function api(path,options={}){const h=new Headers(options.headers||{});if(token())h.set('Authorization',`Bearer ${token()}`);if(options.body&&!(options.body instanceof FormData)&&!h.has('Content-Type'))h.set('Content-Type','application/json');const r=await fetch(`${cfg.API_BASE}${path}`,{...options,headers:h,cache:'no-store'});let d=null;try{d=await r.json()}catch{}if(r.status===401){clearSession();showAuth();throw new Error('UNAUTHORIZED')}if(!r.ok)throw new Error(d?.error||`HTTP_${r.status}`);return d}
const PORTAL_TRAIN_ADMIN_API='https://wfgg-train.chachasan090375.workers.dev';
/* WFGG_PORTAL_TRAIN_ADMIN_API_V1
   Les données d'activité restent produites par Train, mais leur administration
   appartient au Portail. Le token Portail est envoyé uniquement par header.
*/
async function trainAdminApi(path,options={}){
  const h=new Headers(options.headers||{}),tk=token();
  if(!tk)throw new Error('NO_PORTAL_SESSION');
  h.set('X-WfGg-Portal-Token',tk);
  if(options.body&&!h.has('Content-Type'))h.set('Content-Type','application/json');
  const r=await fetch(`${PORTAL_TRAIN_ADMIN_API}${path}`,{...options,headers:h,cache:'no-store',credentials:'omit',mode:'cors'});
  let d=null;try{d=await r.json()}catch{}
  if(!r.ok)throw new Error(d?.error||`HTTP_${r.status}`);
  return d;
}
function clearSession(){localStorage.removeItem(TOKEN_KEY);Object.assign(state,{user:null,membership:null,alliance:null,system:null,permissions:null,portalSettings:{},members:[],sessions:[],trainRotationSummary:null,trainRotationLoading:false});}
function initials(n='?'){return n.trim().split(/\s+/).slice(0,2).map(x=>x[0]?.toUpperCase()).join('')||'?'}
function avatarUrl(u){return u?.avatar_url||LEGACY[u?.player_name]||LEGACY[u?.display_name]||''}
function paintAvatar(el,u){if(!el||!u)return;const src=avatarUrl(u);el.innerHTML=src?`<img src="${esc(src)}" alt="${esc(u.display_name||u.player_name||'joueur')}">`:esc(initials(u.display_name||u.player_name))}
function applyLanguage(){
  document.documentElement.lang=state.lang;
  document.title='WfGg · '+t('home.portal');
  document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el=>el.placeholder=t(el.dataset.i18nPlaceholder));
  document.querySelectorAll('[data-lang]').forEach(b=>b.classList.toggle('active',b.dataset.lang===state.lang));
  if($('profileChip'))$('profileChip').setAttribute('aria-label',t('home.profileMenu'));
  const mainNav=document.querySelector('.module-grid');
  if(mainNav)mainNav.setAttribute('aria-label',t('home.mainNav'));
  renderHome();
}
function hydrate(d){
  state.user=d.user;
  state.membership=d.membership;
  state.alliance=d.alliance;
  state.system=d.system||{};
  state.permissions=d.permissions||{};
  state.portalSettings=d.portal_settings||{};

  const serverLang=normalizeLanguage(d.user?.language);
  const localLang=normalizeLanguage(localStorage.getItem(LANG_KEY));
  const localSource=localStorage.getItem(LANG_SOURCE_KEY);
  const completed=Boolean(d.user?.profile_completed);

  if(serverLang&&(completed||serverLang!=='fr')){
    state.lang=serverLang;
    localStorage.setItem(LANG_KEY,state.lang);
    localStorage.setItem(LANG_SOURCE_KEY,'profile');
  }else if(localLang&&localSource==='manual'){
    state.lang=localLang;
  }else{
    state.lang=detectDeviceLanguage()||serverLang||'fr';
    localStorage.setItem(LANG_KEY,state.lang);
    localStorage.setItem(LANG_SOURCE_KEY,'device');
  }
  applyLanguage();
}
function showAuth(){setView('authView');setTimeout(()=>$('authCode')?.focus(),30)}
function showPortal(){setView('portalView');renderHome();}
function returnPortalTop(){
  const active=document.activeElement;
  if(active&&typeof active.blur==='function')active.blur();

  closeSettings();
  showPortal();

  if('scrollRestoration' in history)history.scrollRestoration='manual';

  const forceTop=()=>{
    const root=document.scrollingElement||document.documentElement;
    const portal=$('portalView');

    document.documentElement.style.scrollBehavior='auto';
    document.body.style.scrollBehavior='auto';

    root.scrollTop=0;
    document.documentElement.scrollTop=0;
    document.body.scrollTop=0;
    window.scrollTo({top:0,left:0,behavior:'auto'});
    portal?.scrollIntoView({block:'start',inline:'nearest',behavior:'auto'});

    root.scrollTop=0;
    document.documentElement.scrollTop=0;
    document.body.scrollTop=0;
  };

  forceTop();
  requestAnimationFrame(forceTop);
  requestAnimationFrame(()=>requestAnimationFrame(forceTop));
  setTimeout(forceTop,60);
  setTimeout(forceTop,180);
  setTimeout(forceTop,420);
}
const DEFAULT_ALLIANCE_LOGOS={
  fr:'assets/wfgg-logo-premium-transparent-v2.png',
  it:'assets/wfgg-logo-premium-it.png',
  en:'assets/wfgg-logo-premium-en.png',
  es:'assets/wfgg-logo-premium-es.png'
};
function isMasterLogoReference(custom){
  return !custom||/(wfgg-train-app\.pages\.dev\/assets\/icon-192\.png|wfgg-logo-transparent-r2q\.webp|wfgg-logo-premium-transparent-v2\.png|wfgg-logo-premium-(?:it|en|es)\.png)/i.test(custom);
}
function setAllianceLogo(imgId,fallbackId){
  const img=$(imgId),fallback=$(fallbackId);
  if(!img||!fallback)return;

  img.onload=null;
  img.onerror=null;

  const custom=String(state.alliance?.logo_url||'').trim();
  const useMaster=isMasterLogoReference(custom);
  const src=useMaster
    ? (DEFAULT_ALLIANCE_LOGOS[state.lang]||DEFAULT_ALLIANCE_LOGOS.fr)
    : custom;

  const renderToken=`${state.lang}|${src}|${Date.now()}`;
  img.dataset.renderToken=renderToken;
  img.classList.toggle('premium-integrated-logo',useMaster);
  img.alt=`Logo WfGg ${String(state.lang||'fr').toUpperCase()}`;

  fallback.classList.remove('hidden');
  img.classList.add('hidden');

  if(!src)return;

  img.onload=()=>{
    if(img.dataset.renderToken!==renderToken)return;
    img.classList.remove('hidden');
    fallback.classList.add('hidden');
  };
  img.onerror=()=>{
    if(img.dataset.renderToken!==renderToken)return;
    img.classList.add('hidden');
    fallback.classList.remove('hidden');
  };
  img.src=src;
}

/* WFGG_PORTAL_TRAIN_ROTATION_READONLY_V1
   Le Portail ne génère jamais le planning Train. Il lit uniquement le snapshot
   autoritatif fourni par Train puis en extrait les passages déjà programmés. */
function trainRotationLabels(){
  const all={
    fr:{title:'Ma rotation Train',driverA:'Conducteur A',driverB:'Conducteur B',vip:'VIP',total:'Total',last:'Dernier',next:'Prochain',none:'—',statsTitle:'Rotations par joueur',statsDesc:'Historique et prochains passages issus directement du planning Train.'},
    it:{title:'La mia rotazione Treno',driverA:'Conducente A',driverB:'Conducente B',vip:'VIP',total:'Totale',last:'Ultimo',next:'Prossimo',none:'—',statsTitle:'Rotazioni per giocatore',statsDesc:'Storico e prossimi turni letti direttamente dal calendario Treno.'},
    en:{title:'My Train rotation',driverA:'Driver A',driverB:'Driver B',vip:'VIP',total:'Total',last:'Last',next:'Next',none:'—',statsTitle:'Rotations by player',statsDesc:'History and upcoming turns read directly from the Train schedule.'},
    es:{title:'Mi rotación del Tren',driverA:'Conductor A',driverB:'Conductor B',vip:'VIP',total:'Total',last:'Último',next:'Próximo',none:'—',statsTitle:'Rotaciones por jugador',statsDesc:'Historial y próximos turnos leídos directamente del calendario del Tren.'}
  };
  return all[state.lang]||all.fr;
}
function trainLocalISO(d=new Date()){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}
function trainHistoryKey(v){return String(v||'').trim().normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function trainManualBase(snapshot,user,role){
  const mh=snapshot?.state?.manualHistory||{},counts=mh?.counts?.[role]||{},links=mh?.links||{};
  const linked=links[user?.id];
  if(linked&&counts[linked])return counts[linked];
  const key=trainHistoryKey(user?.pseudo||user?.display_name||user?.player_name||'');
  return Object.values(counts).find(x=>trainHistoryKey(x?.name)===key)||{count:0,last:null};
}
function trainRotationForUser(snapshot,user){
  const schedule=Array.isArray(snapshot?.schedule)?snapshot.schedule:[],today=trainLocalISO(),mh=snapshot?.state?.manualHistory||{};
  const cutoff=String(mh.cutoff||'0000-00-00'),id=String(user?.id||'');
  const baseDriver=trainManualBase(snapshot,user,'driver'),baseVip=trainManualBase(snapshot,user,'vip');
  const past=schedule.filter(x=>x?.date>cutoff&&x.date<today);
  const pastDriver=past.filter(x=>String(x.driverId||'')===id),pastVip=past.filter(x=>String(x.vipId||'')===id);
  const nextDriver=schedule.find(x=>x?.date>=today&&String(x.driverId||'')===id)||null;
  const nextVip=schedule.find(x=>x?.date>=today&&String(x.vipId||'')===id)||null;
  const lastDriver=pastDriver.length?pastDriver[pastDriver.length-1].date:(baseDriver.last||null);
  const lastVip=pastVip.length?pastVip[pastVip.length-1].date:(baseVip.last||null);
  const rank=String(user?.rank||'').toUpperCase();
  const driverRole=nextDriver?.driverClass==='officer'||['R4','R5'].includes(rank)?'A':'B';
  return {id:user?.id,pseudo:user?.pseudo||user?.display_name||user?.player_name||'',rank,
    driver:Number(baseDriver.count||0)+pastDriver.length,driverLast:lastDriver,driverNext:nextDriver?.date||null,driverRole,
    vip:Number(baseVip.count||0)+pastVip.length,vipLast:lastVip,vipNext:nextVip?.date||null};
}
function trainDateLabel(ds){if(!ds)return trainRotationLabels().none;try{return new Date(`${ds}T12:00:00`).toLocaleDateString(state.lang==='en'?'en-GB':state.lang==='it'?'it-IT':state.lang==='es'?'es-ES':'fr-FR',{day:'2-digit',month:'2-digit',year:'2-digit'});}catch{return ds}}
function renderHomeTrainRotationCard(){
  const grid=document.querySelector('.module-grid');if(!grid)return;
  let card=$('homeTrainRotationCard');
  if(!card){card=document.createElement('section');card.id='homeTrainRotationCard';card.className='glass-card settings-card-block';grid.parentNode.insertBefore(card,grid);}
  const x=trainRotationLabels(),r=state.trainRotationSummary;
  if(!r){card.innerHTML=`<div class="section-heading"><h3>🚂 ${esc(x.title)}</h3></div><span class="muted">…</span>`;return;}
  const driverLabel=r.driverRole==='A'?x.driverA:x.driverB;
  card.innerHTML=`<div class="section-heading"><h3>🚂 ${esc(x.title)}</h3></div><div class="readonly-grid"><div><small>${esc(driverLabel)} · ${esc(x.total)}</small><strong>${r.driver||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.driverLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.driverNext))}</small></div><div><small>⭐ ${esc(x.vip)} · ${esc(x.total)}</small><strong>${r.vip||0}</strong><small>${esc(x.last)} : ${esc(trainDateLabel(r.vipLast))}<br>${esc(x.next)} : ${esc(trainDateLabel(r.vipNext))}</small></div></div>`;
}
async function loadHomeTrainRotation(){
  if(!state.user||state.trainRotationLoading)return;
  state.trainRotationLoading=true;renderHomeTrainRotationCard();
  try{const snap=await trainAdminApi('/api/snapshot',{method:'GET'});state.trainRotationSummary=trainRotationForUser(snap,snap.me||{});}catch(_){state.trainRotationSummary=null;}finally{state.trainRotationLoading=false;renderHomeTrainRotationCard();}
}
function buildPlayerRotationRows(analytics,snapshot){
  const users=(snapshot?.roster||[]).filter(x=>x&&x.active!==false),baseline=Object.fromEntries((analytics?.historyActive||[]).map(x=>[String(x.id),x]));
  const today=trainLocalISO(),cutoff=String(snapshot?.state?.manualHistory?.cutoff||'0000-00-00'),schedule=Array.isArray(snapshot?.schedule)?snapshot.schedule:[];
  return users.map(u=>{
    const b=baseline[String(u.id)]||{driver:0,driverLast:null,vip:0,vipLast:null};
    const past=schedule.filter(x=>x?.date>cutoff&&x.date<today),pd=past.filter(x=>String(x.driverId||'')===String(u.id)),pv=past.filter(x=>String(x.vipId||'')===String(u.id));
    const nd=schedule.find(x=>x?.date>=today&&String(x.driverId||'')===String(u.id)),nv=schedule.find(x=>x?.date>=today&&String(x.vipId||'')===String(u.id));
    const rank=String(u.rank||'').toUpperCase(),driverRole=nd?.driverClass==='officer'||['R4','R5'].includes(rank)?'A':'B';
    return {id:u.id,pseudo:u.pseudo,rank,driver:Number(b.driver||0)+pd.length,driverLast:pd.length?pd[pd.length-1].date:b.driverLast,driverNext:nd?.date||null,driverRole,vip:Number(b.vip||0)+pv.length,vipLast:pv.length?pv[pv.length-1].date:b.vipLast,vipNext:nv?.date||null};
  }).sort((a,b)=>({R5:1,R4:2,R3:3,R2:4,R1:5}[a.rank]||9)-({R5:1,R4:2,R3:3,R2:4,R1:5}[b.rank]||9)||String(a.pseudo).localeCompare(String(b.pseudo)));
}

function paintAllianceIdentity(){
  const allianceName=state.alliance?.name||'WfGg';
  const server=state.alliance?.server||'—';
  const serverLabel={fr:'Alliance · Serveur',it:'Alleanza · Server',en:'Alliance · Server',es:'Alianza · Servidor'}[state.lang]||'Alliance · Serveur';
  if($('heroAllianceName'))$('heroAllianceName').textContent=allianceName;
  if($('heroAllianceServer'))$('heroAllianceServer').textContent=serverLabel+' '+server;
  setAllianceLogo('heroAllianceLogo','heroAllianceFallback');
}
function renderHome(){
  if(!state.user)return;
  paintAllianceIdentity();
  const name=state.user.display_name||state.user.player_name;
  if($('heroName'))$('heroName').textContent=name;
  paintAvatar($('topAvatar'),state.user);
  $('profileRequiredBanner').classList.toggle('hidden',profileComplete());

  const useFrenchMaster=state.lang==='fr';
  $('homeWelcome').textContent=(useFrenchMaster&&state.portalSettings?.welcome_text)||t('home.welcomeText');
  $('guidesCardTitle').textContent=(useFrenchMaster&&state.portalSettings?.guides_title)||t('home.guidesTitle');
  $('trainCardTitle').textContent=(useFrenchMaster&&state.portalSettings?.train_title)||t('home.trainTitle');
  refreshModuleLinks();
  renderHomeTrainRotationCard();
  if(!state.trainRotationLoading)loadHomeTrainRotation();
}
function normalizeUnifiedModuleUrl(k,raw){
  const value=String(raw||'').trim();
  if(!value)return '';

  try{
    const u=new URL(value,location.href);

    if(u.hostname==='wfgg-guides.pages.dev'){
      if(k==='simulator'){
        return '/simulateur/';
      }
      return '/guides'+(u.pathname==='/'?'/':u.pathname)+u.search+u.hash;
    }

    if(u.hostname==='wfgg-train-app.pages.dev'){
      return '/train'+(u.pathname==='/'?'/':u.pathname)+u.search+u.hash;
    }
  }catch{}

  return value;
}
const CANONICAL_MODULE_ROUTES={
  guides:'/guides/',
  train:'/train/',
  simulator:'/simulateur/'
};
function moduleUrl(k){
  if(CANONICAL_MODULE_ROUTES[k])return CANONICAL_MODULE_ROUTES[k];
  const stored=state.portalSettings?.[`${k}_url`];
  const raw=stored||cfg.MODULES?.[k]||'';
  return normalizeUnifiedModuleUrl(k,raw);
}
function localizedModuleUrl(k){
  const raw=moduleUrl(k); if(!raw)return '';
  try{
    const u=new URL(raw,location.href);
    u.searchParams.set('lang',state.lang);
    return u.toString();
  }catch{return raw}
}
function refreshModuleLinks(){
  const guides=$('guidesModuleLink');
  const train=$('trainModuleLink');
  if(guides)guides.href=localizedModuleUrl('guides');
  if(train)train.href=localizedModuleUrl('train');
}
function openModule(k){const u=localizedModuleUrl(k);if(u)location.assign(u)}
function showMessage(id,text,error=false){const el=$(id);if(!el)return;el.textContent=text;el.className=`form-message${error?' error':''}`;setTimeout(()=>el.classList.add('hidden'),3500)}
async function handleLanguageRelay(){
  const url=new URL(location.href);
  const relayLang=normalizeLanguage(url.searchParams.get('setlang'));
  if(!relayLang)return false;
  const returnUrl=url.searchParams.get('return')||'';
  state.lang=relayLang;
  localStorage.setItem(LANG_KEY,relayLang);
  localStorage.setItem(LANG_SOURCE_KEY,token()?'profile':'manual');
  applyLanguage();
  if(token()){
    try{
      const updated=await api('/api/profile/language',{method:'PATCH',body:JSON.stringify({language:relayLang})});
      hydrate(updated);
    }catch(e){
      console.warn('WfGg language relay:',e);
    }
  }
  if(returnUrl){
    try{
      const target=new URL(returnUrl);
      if(/^https:$/.test(target.protocol)){location.replace(target.toString());return true}
    }catch{}
  }
  url.searchParams.delete('setlang');url.searchParams.delete('return');
  history.replaceState(null,'',url.pathname+url.search+url.hash);
  return false;
}
async function boot(){
  applyLanguage();
  if(await handleLanguageRelay())return;
  if(!token())return showAuth();

  let d;
  try{
    d=await api('/api/me');
  }catch(e){
    /* api() gère déjà le vrai 401 et supprime seulement une session refusée. */
    if(e.message!=='UNAUTHORIZED')console.error('SESSION_CHECK_ERROR',e);
    return showAuth();
  }

  try{
    hydrate(d);
    showPortal();
  }catch(e){
    console.error('PORTAL_RENDER_ERROR',e);
    /* La session reste intacte : pas de faux retour à l'écran code. */
    setView('portalView');
  }
}

// auth + main navigation
$('authForm').addEventListener('submit',async e=>{
  e.preventDefault();
  $('authError').classList.add('hidden');

  let d;
  try{
    d=await api('/api/auth',{
      method:'POST',
      body:JSON.stringify({code:$('authCode').value.trim()})
    });
  }catch(err){
    $('authError').textContent=t('auth.bad');
    $('authError').classList.remove('hidden');
    return;
  }

  /* À partir d'ici, le code a été accepté par l'API. */
  localStorage.setItem(TOKEN_KEY,d.session_token);
  $('authCode').value='';

  try{
    hydrate(d);
    showPortal();
    window.scrollTo({top:0,left:0,behavior:'auto'});
  }catch(err){
    console.error('POST_LOGIN_RENDER_ERROR',err);
    /* Ne jamais transformer une erreur de rendu en "code invalide". */
    location.reload();
  }
});
$('languageStrip').addEventListener('click',e=>{
  const b=e.target.closest('[data-lang]');
  if(!b)return;
  state.lang=normalizeLanguage(b.dataset.lang)||'fr';
  localStorage.setItem(LANG_KEY,state.lang);
  localStorage.setItem(LANG_SOURCE_KEY,'manual');
  applyLanguage();
});
$('profileChip').addEventListener('click',()=>{$('profileMenu').classList.toggle('hidden')});
$('homeButton')?.addEventListener('click',()=>{showPortal();scrollTo({top:0,behavior:'smooth'})});
document.addEventListener('click',async e=>{const module=e.target.closest('[data-module]');if(module){if(module.tagName==='A')return;return openModule(module.dataset.module)}const a=e.target.closest('[data-action]');if(!a)return;const x=a.dataset.action;if(x==='settings')return openSettings('profile');if(x==='profile')return openSettings('profile');if(x==='logout'){try{await api('/api/logout',{method:'POST'})}catch{}clearSession();$('settingsOverlay').classList.add('hidden');$('membersView').classList.add('hidden');showAuth();return}if(x==='close-settings')return closeSettings();if(x==='close-members')return closeMembers();if(x==='add-member')return openMemberModal();if(x==='edit-member')return openMemberModal(a.dataset.id);if(x==='toggle-member')return toggleMember(a.dataset.id);if(x==='close-modal')return closeModal();if(x==='save-member')return saveMember();if(x==='reset-member-code')return resetMemberCode(a.dataset.id);if(x==='transfer-r5')return openTransfer(a.dataset.id);if(x==='confirm-transfer')return confirmTransfer(a.dataset.id);if(x==='copy-code')return copyText(a.dataset.code,a);if(x==='revoke-others')return revokeOthers();});

// settings
const tabDefs=()=>[{id:'profile',label:t('settings.profile')},...(isAdmin()?[{id:'alliance',label:t('settings.alliance')},{id:'members',label:portalAdminLabels().membersTab},{id:'statistics',label:portalAdminLabels().statsTab},{id:'application',label:t('settings.application')},{id:'rights',label:t('settings.rights')}]:[])];
function openSettings(tab='profile'){$('profileMenu').classList.add('hidden');state.settingsTab=isAdmin()||tab==='profile'?tab:'profile';$('settingsOverlay').classList.remove('hidden');renderSettings()}
function closeSettings(){$('settingsOverlay').classList.add('hidden')}
function renderSettings(){const tabs=$('settingsTabs');tabs.innerHTML=tabDefs().map(x=>`<button class="tab ${state.settingsTab===x.id?'active':''}" type="button" data-settings-tab="${x.id}">${esc(x.label)}</button>`).join('');renderSettingsContent()}
$('settingsTabs').addEventListener('click',e=>{const b=e.target.closest('[data-settings-tab]');if(!b)return;const id=b.dataset.settingsTab;if(id!=='profile'&&!isAdmin())return;state.settingsTab=id;renderSettings()});
function readonly(){return `<div class="readonly-grid"><div><small>Alliance</small><strong>${esc(state.alliance?.name||'—')}</strong></div><div><small>Serveur</small><strong>${esc(state.alliance?.server||'—')}</strong></div><div><small>Rang</small><strong>${esc(state.membership?.rank||'—')}</strong></div></div>`}
function renderSettingsContent(){const c=$('settingsContent');if(state.settingsTab==='profile')c.innerHTML=profileSettingsHtml();else if(state.settingsTab==='alliance'&&isAdmin())c.innerHTML=allianceSettingsHtml();else if(state.settingsTab==='members'&&isAdmin())c.innerHTML=membersSettingsHtml();else if(state.settingsTab==='statistics'&&isAdmin())c.innerHTML=playerStatisticsHtml();else if(state.settingsTab==='application'&&isAdmin())c.innerHTML=applicationSettingsHtml();else if(state.settingsTab==='rights'&&isAdmin())c.innerHTML=rightsHtml();else{state.settingsTab='profile';c.innerHTML=profileSettingsHtml()}bindSettingsForms();}
function profileSettingsHtml(){const name=state.user?.display_name||state.user?.player_name||'';return `<div class="settings-section"><form id="profileForm" class="settings-form"><div class="settings-card-block"><div class="avatar-editor"><span id="settingsAvatar" class="avatar large"></span><div><label class="secondary-button file-button">📷 Changer la photo<input id="avatarInput" class="hidden" type="file" accept="image/jpeg,image/png,image/webp"></label><small class="muted">JPG, PNG ou WebP · 2 Mo max · carré 1:1</small></div></div><label class="field-label">Pseudo affiché</label><input id="displayName" maxlength="40" value="${esc(name)}"><label class="field-label">Langue</label><select id="languageSelect"><option value="fr">Français</option><option value="it">Italiano</option><option value="en">English</option><option value="es">Español</option></select>${readonly()}<button class="primary-button" type="submit">${esc(t('settings.save'))}</button><div id="profileMessage" class="hidden"></div></div></form><div class="settings-card-block"><h3>🔐 ${esc(t('settings.security'))}</h3><form id="codeForm" class="settings-form"><label class="field-label">Code actuel</label><input id="currentCode" type="password" inputmode="numeric" maxlength="6" placeholder="••••••"><label class="field-label">Nouveau code</label><input id="newCode" type="password" inputmode="numeric" maxlength="6" placeholder="••••••"><button class="secondary-button" type="submit">Changer mon code</button><div id="codeMessage" class="hidden"></div></form><div class="section-heading" style="margin-top:16px"><h3>${esc(t('settings.sessions'))}</h3><button id="refreshSessions" class="secondary-button" type="button">Actualiser</button></div><div id="sessionList" class="session-list"><span class="muted">Chargement…</span></div><div class="setting-actions"><button class="secondary-button" type="button" data-action="revoke-others">Fermer les autres sessions</button></div></div></div>`}
function allianceSettingsHtml(){return `<div class="settings-section"><form id="allianceForm" class="settings-form"><div class="settings-card-block"><h3>🏰 Alliance</h3><label class="field-label">Nom</label><input id="allianceName" maxlength="50" value="${esc(state.alliance?.name||'')}"><label class="field-label">Serveur</label><input id="allianceServer" maxlength="30" value="${esc(state.alliance?.server||'')}"><label class="field-label">Logo (URL)</label><input id="allianceLogo" maxlength="500" value="${esc(state.alliance?.logo_url||'')}"><button class="primary-button" type="submit">${esc(t('settings.save'))}</button><div id="allianceMessage" class="hidden"></div></div></form></div>`}
/* WFGG_PORTAL_PLAYER_STATS_V1 */
function portalAdminLabels(){
  const all={
    fr:{membersTab:'Joueurs & accès',statsTab:'Statistiques joueurs',membersTitle:'Joueurs & accès',membersDesc:'Profils, rangs, fonctions R4, activation et réinitialisation des codes.',manage:'Gérer les joueurs',statsTitle:'Statistiques joueurs',statsDesc:'Activité des joueurs sur les 30 derniers jours et synthèse des rotations issue de Train.',refresh:'Actualiser',loading:'Chargement…',empty:'Aucune activité enregistrée sur cette période.',actions7:'Actions · 7 j',actions30:'Actions · 30 j',active:'Joueurs actifs',actions:'actions',profile:'Profil',exchanges:'Échanges',members:'Admin joueurs',settings:'Réglages'},
    it:{membersTab:'Giocatori e accessi',statsTab:'Statistiche giocatori',membersTitle:'Giocatori e accessi',membersDesc:'Profili, gradi, funzioni R4, attivazione e reimpostazione dei codici.',manage:'Gestisci giocatori',statsTitle:'Statistiche giocatori',statsDesc:'Attività dei giocatori negli ultimi 30 giorni e sintesi delle rotazioni proveniente dal Treno.',refresh:'Aggiorna',loading:'Caricamento…',empty:'Nessuna attività registrata in questo periodo.',actions7:'Azioni · 7 g',actions30:'Azioni · 30 g',active:'Giocatori attivi',actions:'azioni',profile:'Profilo',exchanges:'Scambi',members:'Admin giocatori',settings:'Impostazioni'},
    en:{membersTab:'Players & access',statsTab:'Player statistics',membersTitle:'Players & access',membersDesc:'Profiles, ranks, R4 roles, activation and access-code resets.',manage:'Manage players',statsTitle:'Player statistics',statsDesc:'Player activity over the last 30 days and a rotation summary read from Train.',refresh:'Refresh',loading:'Loading…',empty:'No activity recorded in this period.',actions7:'Actions · 7d',actions30:'Actions · 30d',active:'Active players',actions:'actions',profile:'Profile',exchanges:'Swaps',members:'Player admin',settings:'Settings'},
    es:{membersTab:'Jugadores y accesos',statsTab:'Estadísticas jugadores',membersTitle:'Jugadores y accesos',membersDesc:'Perfiles, rangos, funciones R4, activación y restablecimiento de códigos.',manage:'Gestionar jugadores',statsTitle:'Estadísticas jugadores',statsDesc:'Actividad de jugadores durante los últimos 30 días y resumen de rotaciones leído del Tren.',refresh:'Actualizar',loading:'Cargando…',empty:'No hay actividad registrada en este período.',actions7:'Acciones · 7 d',actions30:'Acciones · 30 d',active:'Jugadores activos',actions:'acciones',profile:'Perfil',exchanges:'Intercambios',members:'Admin jugadores',settings:'Ajustes'}
  };
  return all[state.lang]||all.fr;
}
function membersSettingsHtml(){const x=portalAdminLabels();return `<div class="settings-section"><div class="settings-card-block"><div class="section-heading"><div><h3>👥 ${esc(x.membersTitle)}</h3><p class="muted">${esc(x.membersDesc)}</p></div><button id="openMembersButton" class="primary-button" type="button">${esc(x.manage)}</button></div></div></div>`}
function playerStatisticsHtml(){const x=portalAdminLabels();return `<div class="settings-section"><div class="settings-card-block"><div class="section-heading"><div><h3>📊 ${esc(x.statsTitle)}</h3><p class="muted">${esc(x.statsDesc)}</p></div><button id="refreshPlayerStats" class="secondary-button" type="button">${esc(x.refresh)}</button></div><div id="playerStatsHost" class="portal-player-stats"><span class="muted">${esc(x.loading)}</span></div></div></div>`}
async function loadPlayerStatistics(){
  const host=$('playerStatsHost');if(!host||!isAdmin())return;
  const x=portalAdminLabels();host.innerHTML=`<span class="muted">${esc(x.loading)}</span>`;
  try{
    const [d,snapshot]=await Promise.all([trainAdminApi('/api/admin/analytics',{method:'GET'}),trainAdminApi('/api/snapshot',{method:'GET'})]),s=d.summary||{};
    const rows=[...(d.activityByActor||[])].sort((a,b)=>(b.total||0)-(a.total||0)||String(a.pseudo||'').localeCompare(String(b.pseudo||'')));
    const rotations=buildPlayerRotationRows(d,snapshot),rx=trainRotationLabels();
    if(!$('playerStatsHost'))return;
    host.innerHTML=`<div class="portal-stats-kpis"><div><small>${esc(x.actions7)}</small><strong>${s.actions7||0}</strong></div><div><small>${esc(x.actions30)}</small><strong>${s.actions30||0}</strong></div><div><small>${esc(x.active)}</small><strong>${s.activeMembers||0}</strong></div></div><div class="portal-player-stats-list">${rows.length?rows.map(row=>`<div class="portal-player-stat-row"><div class="portal-stat-avatar">${esc(initials(row.pseudo||'?'))}</div><div class="portal-stat-main"><b>${esc(row.pseudo||'—')}</b><small>${esc(row.rank||'')} · ${row.total||0} ${esc(x.actions)}</small><div class="portal-stat-breakdown"><span>👤 ${esc(x.profile)} ${row.players||0}</span><span>🔄 ${esc(x.exchanges)} ${row.exchanges||0}</span><span>👥 ${esc(x.members)} ${row.members||0}</span><span>⚙️ ${esc(x.settings)} ${row.settings||0}</span></div></div><strong class="portal-stat-total">${row.total||0}</strong></div>`).join(''):`<div class="empty-state">${esc(x.empty)}</div>`}</div><div class="section-heading" style="margin-top:22px"><div><h3>🚂 ${esc(rx.statsTitle)}</h3><p class="muted">${esc(rx.statsDesc)}</p></div></div><div class="portal-player-stats-list">${rotations.map(r=>{const dl=r.driverRole==='A'?rx.driverA:rx.driverB;return `<div class="portal-player-stat-row"><div class="portal-stat-avatar">${esc(initials(r.pseudo||'?'))}</div><div class="portal-stat-main"><b>${esc(r.pseudo||'—')}</b><small>${esc(r.rank||'')}</small><div class="portal-stat-breakdown"><span>🚂 ${esc(dl)} : <b>${r.driver||0}</b> · ${esc(rx.last)} ${esc(trainDateLabel(r.driverLast))} · ${esc(rx.next)} ${esc(trainDateLabel(r.driverNext))}</span><span>⭐ ${esc(rx.vip)} : <b>${r.vip||0}</b> · ${esc(rx.last)} ${esc(trainDateLabel(r.vipLast))} · ${esc(rx.next)} ${esc(trainDateLabel(r.vipNext))}</span></div></div></div>`}).join('')}</div>`;
  }catch(error){if($('playerStatsHost'))host.innerHTML=`<div class="form-message error">${esc(error.message)}</div>`;}
}
function applicationSettingsHtml(){const p=state.portalSettings||{};return `<form id="applicationForm" class="settings-form"><div class="settings-card-block"><h3>✨ Application</h3><p class="muted">Réglages généraux du portail. Les paramètres de rotation restent dans Train.</p><label class="field-label">Texte d’accueil</label><textarea id="welcomeText" maxlength="180" rows="3">${esc(p.welcome_text||'Choisissez votre espace WfGg.')}</textarea><label class="field-label">Titre Guides</label><input id="guidesTitle" maxlength="40" value="${esc(p.guides_title||'Guides')}"><label class="field-label">URL Guides</label><input id="guidesUrl" maxlength="500" value="${esc(p.guides_url||cfg.MODULES?.guides||'')}"><label class="field-label">Titre Train</label><input id="trainTitle" maxlength="40" value="${esc(p.train_title||'Train')}"><label class="field-label">URL Train</label><input id="trainUrl" maxlength="500" value="${esc(p.train_url||cfg.MODULES?.train||'')}"><button class="primary-button" type="submit">${esc(t('settings.save'))}</button><div id="applicationMessage" class="hidden"></div></div></form>`}
function rightsHtml(){const rank=state.membership?.rank||'—',owner=state.system?.role==='OWNER';return `<div class="settings-section"><div class="settings-card-block"><h3>🛡️ Politique des droits</h3><p class="muted">Les droits sont calculés côté API à chaque requête. Un changement de rang invalide la session du joueur concerné.</p><div class="permission-grid"><div class="permission-row"><b>Fonction</b><strong>R4/R5</strong><strong>R1–R3</strong></div>${['Profil personnel','Paramètres généraux','Alliance & membres','Gestion des rangs','Fonctions R4','Changer le R5','Administration'].map((x,i)=>`<div class="permission-row"><span>${x}</span><strong class="ok">✓</strong><strong class="${i===0?'ok':'no'}">${i===0?'✓':'—'}</strong></div>`).join('')}</div></div><div class="settings-card-block"><h3>Ton accès</h3><p>Rang : <strong>${esc(rank)}</strong>${state.membership?.officer_title?` · ${esc(OFFICE_FR[state.membership.officer_title]||state.membership.officer_title)}`:''}${owner?' · <strong>OWNER</strong>':''}</p><p class="muted">OWNER est un rôle système séparé du rang de jeu et reste protégé.</p></div></div>`}
function bindSettingsForms(){paintAvatar($('settingsAvatar'),state.user);if($('languageSelect'))$('languageSelect').value=state.user?.language||state.lang;$('profileForm')?.addEventListener('submit',saveProfile);$('avatarInput')?.addEventListener('change',uploadAvatar);$('codeForm')?.addEventListener('submit',changeOwnCode);$('refreshSessions')?.addEventListener('click',loadSessions);$('allianceForm')?.addEventListener('submit',saveAlliance);$('applicationForm')?.addEventListener('submit',saveApplication);$('openMembersButton')?.addEventListener('click',openMembers);$('refreshPlayerStats')?.addEventListener('click',loadPlayerStatistics);if(state.settingsTab==='profile')loadSessions();if(state.settingsTab==='statistics')loadPlayerStatistics();}
async function saveProfile(e){
  e.preventDefault();
  const form=e.currentTarget;
  const btn=e.submitter||form.querySelector('button[type="submit"]');
  const requestedLang=normalizeLanguage($('languageSelect').value)||'fr';

  if(btn){
    btn.disabled=true;
    btn.setAttribute('aria-busy','true');
    btn.textContent=t('settings.saving');
  }

  try{
    const displayName=$('displayName').value.trim();
    let updated;

    if(requestedLang!==state.user?.language){
      updated=await api('/api/profile/language',{
        method:'PATCH',
        body:JSON.stringify({language:requestedLang})
      });

      if(displayName && displayName!==(updated.user?.display_name||'')){
        updated=await api('/api/profile',{
          method:'PATCH',
          body:JSON.stringify({display_name:displayName,language:requestedLang})
        });
      }
    }else{
      updated=await api('/api/profile',{
        method:'PATCH',
        body:JSON.stringify({display_name:displayName,language:requestedLang})
      });
    }

    localStorage.setItem(LANG_KEY,requestedLang);
    localStorage.setItem(LANG_SOURCE_KEY,'profile');
    hydrate(updated);

    if(btn){
      btn.textContent=t('settings.saved');
      btn.classList.add('saved');
    }
    showMessage('profileMessage',t('settings.saved'));

    await new Promise(r=>setTimeout(r,550));
    returnPortalTop();
  }catch(err){
    showMessage('profileMessage',err.message,true);
  }finally{
    if(btn && document.body.contains(btn)){
      btn.disabled=false;
      btn.removeAttribute('aria-busy');
      btn.classList.remove('saved');
      btn.textContent=t('settings.save');
    }
  }
}
async function uploadAvatar(e){const f=e.target.files?.[0];if(!f)return;if(f.size>2*1024*1024)return showMessage('profileMessage','Fichier trop volumineux.',true);const fd=new FormData();fd.append('avatar',f);try{hydrate(await api('/api/profile/avatar',{method:'POST',body:fd}));paintAvatar($('settingsAvatar'),state.user);showMessage('profileMessage','Photo enregistrée.')}catch(err){showMessage('profileMessage',err.message,true)}e.target.value=''}
async function changeOwnCode(e){e.preventDefault();const cur=$('currentCode').value.trim(),n=$('newCode').value.trim();if(!/^\d{6}$/.test(cur)||!/^\d{6}$/.test(n))return showMessage('codeMessage','Deux codes à 6 chiffres sont requis.',true);try{await api('/api/me/code',{method:'PATCH',body:JSON.stringify({current_code:cur,new_code:n})});$('currentCode').value='';$('newCode').value='';showMessage('codeMessage','Code modifié. Les autres sessions ont été fermées.');loadSessions()}catch(err){showMessage('codeMessage',err.message,true)}}
async function loadSessions(){const el=$('sessionList');if(!el)return;try{const d=await api('/api/me/sessions');state.sessions=d.sessions||[];el.innerHTML=state.sessions.map(s=>`<div class="session-row"><div><strong>${s.current?'Session actuelle':'Session'}</strong><br><small>${esc(s.user_agent||'Appareil inconnu')}</small></div><small>${new Date(s.last_seen_at).toLocaleString(state.lang)}</small></div>`).join('')||'<span class="muted">Aucune session.</span>'}catch(err){el.innerHTML=`<span class="error-text">${esc(err.message)}</span>`}}
async function revokeOthers(){try{await api('/api/me/sessions/others',{method:'DELETE'});loadSessions()}catch(err){alert(err.message)}}
async function saveAlliance(e){e.preventDefault();try{const d=await api('/api/alliance',{method:'PATCH',body:JSON.stringify({name:$('allianceName').value.trim(),server:$('allianceServer').value.trim(),logo_url:$('allianceLogo').value.trim()||null})});state.alliance=d.alliance;renderHome();showMessage('allianceMessage','Enregistré.')}catch(err){showMessage('allianceMessage',err.message,true)}}
async function saveApplication(e){e.preventDefault();try{const d=await api('/api/portal/settings',{method:'PATCH',body:JSON.stringify({welcome_text:$('welcomeText').value.trim(),guides_title:$('guidesTitle').value.trim(),guides_url:$('guidesUrl').value.trim(),train_title:$('trainTitle').value.trim(),train_url:$('trainUrl').value.trim()})});state.portalSettings=d.portal_settings||{};renderHome();showMessage('applicationMessage','Enregistré.')}catch(err){showMessage('applicationMessage',err.message,true)}}

// Members
function openMembers(){if(!isAdmin())return;closeSettings();$('membersView').classList.remove('hidden');$('membersView').setAttribute('aria-hidden','false');state.filters.clear();state.search='';$('memberSearch').value='';renderRankFilters();loadMembers()}
function closeMembers(){$('membersView').classList.add('hidden');$('membersView').setAttribute('aria-hidden','true');openSettings('alliance')}
function renderRankFilters(){const el=$('rankFilters');const items=['ALL',...RANKS];el.innerHTML=items.map(r=>{const active=r==='ALL'?state.filters.size===0:state.filters.has(r);return `<button type="button" class="rank-filter ${active?'active':''}" data-rank="${r}" aria-pressed="${active}">${r==='ALL'?'TOUS':r}</button>`}).join('')}
$('rankFilters').addEventListener('click',e=>{const b=e.target.closest('[data-rank]');if(!b)return;const r=b.dataset.rank;if(r==='ALL')state.filters.clear();else state.filters.has(r)?state.filters.delete(r):state.filters.add(r);renderRankFilters();renderMembers()});
$('memberSearch').addEventListener('input',e=>{state.search=e.target.value||'';renderMembers()});
async function loadMembers(){try{const d=await api('/api/admin/members');state.members=d.members||[];renderMembers()}catch(err){$('memberList').innerHTML=`<div class="empty-state">${esc(err.message)}</div>`}}
function memberAvatar(m){const src=avatarUrl(m);return `<span class="member-avatar">${src?`<img src="${esc(src)}" alt="${esc(m.display_name||m.player_name||'joueur')}">`:esc(initials(m.display_name||m.player_name))}</span>`}
function relative(v){if(!v)return'jamais connecté';const ms=Date.now()-new Date(v).getTime();if(ms<120000)return'en ligne';const h=Math.floor(ms/3600000);if(h<1)return`il y a ${Math.max(1,Math.floor(ms/60000))} min`;if(h<24)return`il y a ${h} h`;const d=Math.floor(h/24);return`il y a ${d} jour${d>1?'s':''}`}
function filtered(){const q=state.search.trim().toLocaleLowerCase(state.lang);return state.members.filter(m=>(!state.filters.size||state.filters.has(m.rank))&&(!q||`${m.display_name||''} ${m.player_name||''} ${m.rank||''} ${m.officer_title||''}`.toLocaleLowerCase(state.lang).includes(q)))}
function toggleAllowed(m){return m.id!==state.user?.id&&m.rank!=='R5'&&m.system_role!=='OWNER'}
function renderMembers(){const list=filtered();$('membersCount').textContent=`${list.length} / ${state.members.length}`;$('memberList').innerHTML=list.length?list.map(m=>`<article class="member-row ${m.active?'':'inactive'}">${memberAvatar(m)}<div class="member-main"><b>${esc(m.display_name||m.player_name)}</b><div class="member-meta"><span class="rank-badge">${esc(m.rank)}</span> · ${m.active?'actif':'désactivé'}${m.officer_title?` · ${esc(OFFICE_FR[m.officer_title]||m.officer_title)}`:''}${m.system_role==='OWNER'?' · OWNER':''}</div><div class="member-last">🕒 ${esc(relative(m.last_login_at))}</div></div><div class="member-actions"><button class="small-btn edit" type="button" data-action="edit-member" data-id="${esc(m.id)}">✏️ ${esc(t('members.edit'))}</button><button class="small-btn" type="button" data-action="toggle-member" data-id="${esc(m.id)}" ${toggleAllowed(m)?'':'disabled'}>${toggleAllowed(m)?(m.active?esc(t('members.disable')):esc(t('members.enable'))):'Protégé'}</button></div></article>`).join(''):'<div class="empty-state">Aucun joueur trouvé.</div>'}
function openModal(html){$('modalBody').innerHTML=html;$('modal').classList.remove('hidden')}
function closeModal(){$('modal').classList.add('hidden');$('modalBody').innerHTML=''}
function rankOptions(m){return ['R4','R3','R2','R1'].map(r=>`<option value="${r}" ${m?.rank===r?'selected':''}>${r}</option>`).join('')}
function officeOptions(m){return OFFICES.map(o=>`<option value="${o}" ${m?.officer_title===o?'selected':''}>${o?(OFFICE_FR[o]||o):'Aucune'}</option>`).join('')}
function openMemberModal(id=''){const m=id?state.members.find(x=>x.id===id):null;if(!m){openModal(`<div class="modal-title"><div><p class="eyebrow">Administration</p><h3>＋ Ajouter un joueur</h3></div></div><div class="settings-form"><label class="field-label">Pseudo exact</label><input id="mName" maxlength="40"><div class="form-grid"><div><label class="field-label">Rang</label><select id="mRank">${rankOptions(null)}</select></div><div><label class="field-label">Fonction R4</label><select id="mOffice">${officeOptions(null)}</select></div></div><div id="memberModalMessage" class="hidden"></div><div class="modal-actions"><button class="primary-button" type="button" data-action="save-member">💾 Enregistrer</button><button class="secondary-button" type="button" data-action="close-modal">Annuler</button></div></div>`);$('mRank').addEventListener('change',syncOffice);syncOffice();return}const isR5=m.rank==='R5';openModal(`<div class="modal-title">${memberAvatar(m)}<div><p class="eyebrow">Administration</p><h3>${esc(m.display_name||m.player_name)}</h3></div></div><input id="mId" type="hidden" value="${esc(m.id)}"><div class="form-grid"><div><label class="field-label">Rang</label>${isR5?`<input value="R5" disabled>`:`<select id="mRank">${rankOptions(m)}</select>`}</div><div><label class="field-label">Fonction R4</label><select id="mOffice" ${isR5?'disabled':''}>${officeOptions(m)}</select></div></div><label class="toggle-row"><span>Profil actif</span><input id="mActive" type="checkbox" ${m.active?'checked':''} ${!toggleAllowed(m)?'disabled':''}></label><div id="memberModalMessage" class="hidden"></div><div class="modal-actions">${!isR5?'<button class="primary-button" type="button" data-action="save-member">💾 Enregistrer</button>':''}<button class="secondary-button" type="button" data-action="reset-member-code" data-id="${esc(m.id)}">🔑 Nouveau code</button>${m.rank==='R4'?`<button class="secondary-button" type="button" data-action="transfer-r5" data-id="${esc(m.id)}">♛ Nommer R5</button>`:''}<button class="secondary-button" type="button" data-action="close-modal">Fermer</button></div>`);if($('mRank')){$('mRank').addEventListener('change',syncOffice);syncOffice()}}
function syncOffice(){const r=$('mRank'),o=$('mOffice');if(!o||!r)return;o.disabled=r.value!=='R4';if(o.disabled)o.value=''}
function randomCode(){const a=new Uint32Array(1);crypto.getRandomValues(a);return String(a[0]%1000000).padStart(6,'0')}
async function saveMember(){const id=$('mId')?.value||'';if(!id){const name=$('mName').value.trim(),rank=$('mRank').value,off=rank==='R4'?($('mOffice').value||null):null;if(!name)return showMessage('memberModalMessage','Pseudo obligatoire.',true);let last;for(let i=0;i<8;i++){const code=randomCode();try{await api('/api/admin/members',{method:'POST',body:JSON.stringify({player_name:name,rank,officer_title:off,code})});await loadMembers();openModal(`<p class="eyebrow">Joueur ajouté</p><h3>${esc(name)}</h3><p>Code personnel :</p><div class="new-code">${code}</div><p class="muted">Copiez ce code avant de fermer.</p><div class="modal-actions"><button class="primary-button" data-action="copy-code" data-code="${code}">📋 Copier</button><button class="secondary-button" data-action="close-modal">Fermer</button></div>`);return}catch(e){last=e;if(!/CODE|EXISTS/i.test(e.message))break}}return showMessage('memberModalMessage',last?.message||'Erreur',true)}const m=state.members.find(x=>x.id===id);if(!m)return;const rank=$('mRank')?.value||m.rank,off=rank==='R4'?($('mOffice')?.value||null):null,active=$('mActive')?.checked??m.active;try{if(m.officer_title&&rank!=='R4')await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({officer_title:null})});if(rank!==m.rank)await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({rank})});if(rank==='R4'&&off!==(m.officer_title||null))await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({officer_title:off})});if(Boolean(active)!==Boolean(m.active))await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({active:Boolean(active)})});await loadMembers();closeModal()}catch(e){showMessage('memberModalMessage',e.message,true)}}
async function toggleMember(id){const m=state.members.find(x=>x.id===id);if(!m||!toggleAllowed(m))return;try{await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'PATCH',body:JSON.stringify({active:!m.active})});await loadMembers()}catch(e){alert(e.message)}}
async function resetMemberCode(id){const code=randomCode();try{await api(`/api/admin/members/${encodeURIComponent(id)}/code`,{method:'POST',body:JSON.stringify({code})});openModal(`<p class="eyebrow">Nouveau code</p><div class="new-code">${code}</div><p class="muted">Les anciennes sessions de ce joueur ont été fermées.</p><div class="modal-actions"><button class="primary-button" data-action="copy-code" data-code="${code}">📋 Copier</button><button class="secondary-button" data-action="close-modal">Fermer</button></div>`)}catch(e){showMessage('memberModalMessage',e.message,true)}}
function openTransfer(id){const m=state.members.find(x=>x.id===id);if(!m)return;openModal(`<p class="eyebrow">Leadership</p><h3>♛ Nommer ${esc(m.display_name||m.player_name)} R5</h3><p class="muted">Le R5 actuel sera rétrogradé R4. Confirme avec ton propre code à 6 chiffres.</p><input id="transferCode" type="password" inputmode="numeric" maxlength="6" placeholder="••••••"><div id="memberModalMessage" class="hidden"></div><div class="modal-actions"><button class="primary-button" data-action="confirm-transfer" data-id="${esc(id)}">Confirmer</button><button class="secondary-button" data-action="close-modal">Annuler</button></div>`)}
async function confirmTransfer(id){const code=$('transferCode').value.trim();if(!/^\d{6}$/.test(code))return showMessage('memberModalMessage','Code à 6 chiffres requis.',true);try{await api('/api/admin/leadership/transfer',{method:'POST',body:JSON.stringify({target_user_id:id,current_code:code})});await loadMembers();closeModal()}catch(e){showMessage('memberModalMessage',e.message,true)}}
async function copyText(text,btn){try{await navigator.clipboard.writeText(text)}catch{const ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');ta.remove()}if(btn)btn.textContent='✅ Copié'}

boot();
})();
