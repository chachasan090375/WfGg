(()=>{
'use strict';
const TOKEN_KEY='wfgg_portal_session';
const LANG_KEY='wfgg_portal_language';
const PENDING_UID_KEY='wfgg_lastwar_pending_uid';
const CONNECTOR_API=(window.WFGG_PORTAL_CONFIG?.LASTWAR_CONNECTOR_API||'https://wfgg-lastwar-connector.workers.dev').replace(/\/+$/,'');
const TXT={
 fr:{title:'Connexion Last War',card:'Last War',sub:'Reliez votre compte et mettez le simulateur à jour automatiquement.',stateOff:'Non relié',stateOn:'Compte synchronisé',link:'Relier mon compte Last War',refresh:'Mettre à jour',unlink:'Dissocier mon compte',last:'Dernière mise à jour',privacy:'WfGg ne vous demandera jamais votre mot de passe Last War. Le code reçu par e-mail est utilisé une seule fois et n’est jamais conservé.',uidTitle:'Votre UID Last War',uidText:'Commencez par votre identifiant de personnage. Vous le trouvez dans Last War : Profil → Paramètres → Copier ID.',uidLabel:'UID Last War',uidPlaceholder:'Ex. 1234567890123456',continue:'Continuer',uidBad:'Vérifiez votre UID Last War.',contactTitle:'Vérification du compte',contactText:'Nous essayons d’identifier automatiquement l’adresse liée à ce compte. Si Last War la fournit, seule une version masquée sera affichée.',masked:'Code envoyé à',emailFallback:'Pour confirmer que ce compte vous appartient, Last War demande actuellement l’adresse e-mail associée.',emailLabel:'Adresse e-mail liée à Last War',emailPlaceholder:'votre@email.com',sendCode:'Envoyer le code',forgot:'Je ne sais plus quelle adresse e-mail est liée',helpTitle:'Retrouver l’adresse liée',helpText:'Dans Last War, ouvrez votre profil puis Compte. L’adresse e-mail liée à votre compte y est affichée. Revenez ensuite ici : votre UID restera enregistré.',back:'Retour',codeTitle:'Code de vérification',codeText:'Entrez le code à 6 chiffres envoyé par Last War.',codeLabel:'Code à 6 chiffres',codePlaceholder:'••••••',verify:'Vérifier et synchroniser',connecting:'Connexion à Last War…',authorizing:'Autorisation…',syncing:'Synchronisation…',notReady:'Le service de connexion Last War est en cours d’activation sur cette branche de test.',service:'Service de connexion temporairement indisponible.',close:'Fermer'},
 it:{title:'Connessione Last War',card:'Last War',sub:'Collega il tuo account e aggiorna automaticamente il simulatore.',stateOff:'Non collegato',stateOn:'Account sincronizzato',link:'Collega il mio account Last War',refresh:'Aggiorna',unlink:'Scollega il mio account',last:'Ultimo aggiornamento',privacy:'WfGg non ti chiederà mai la password di Last War. Il codice ricevuto via e-mail viene usato una sola volta e non viene conservato.',uidTitle:'Il tuo UID Last War',uidText:'Inizia dal tuo identificatore del personaggio. In Last War: Profilo → Impostazioni → Copia ID.',uidLabel:'UID Last War',uidPlaceholder:'Es. 1234567890123456',continue:'Continua',uidBad:'Controlla il tuo UID Last War.',contactTitle:'Verifica account',contactText:'Cerchiamo di identificare automaticamente l’indirizzo collegato. Se Last War lo fornisce, mostreremo solo una versione mascherata.',masked:'Codice inviato a',emailFallback:'Per confermare che l’account è tuo, Last War richiede attualmente l’indirizzo e-mail associato.',emailLabel:'E-mail collegata a Last War',emailPlaceholder:'tuo@email.com',sendCode:'Invia il codice',forgot:'Non ricordo quale e-mail è collegata',helpTitle:'Trova l’e-mail collegata',helpText:'In Last War apri il profilo e poi Account. L’e-mail collegata è mostrata lì. Torna qui: il tuo UID resterà salvato.',back:'Indietro',codeTitle:'Codice di verifica',codeText:'Inserisci il codice a 6 cifre inviato da Last War.',codeLabel:'Codice a 6 cifre',codePlaceholder:'••••••',verify:'Verifica e sincronizza',connecting:'Connessione a Last War…',authorizing:'Autorizzazione…',syncing:'Sincronizzazione…',notReady:'Il servizio di connessione Last War è in fase di attivazione su questo ramo di test.',service:'Servizio di connessione temporaneamente non disponibile.',close:'Chiudi'},
 en:{title:'Last War connection',card:'Last War',sub:'Link your account and keep the simulator updated automatically.',stateOff:'Not linked',stateOn:'Account synced',link:'Link my Last War account',refresh:'Update now',unlink:'Unlink my account',last:'Last update',privacy:'WfGg will never ask for your Last War password. The email code is used once and is never stored.',uidTitle:'Your Last War UID',uidText:'Start with your character ID. In Last War: Profile → Settings → Copy ID.',uidLabel:'Last War UID',uidPlaceholder:'E.g. 1234567890123456',continue:'Continue',uidBad:'Check your Last War UID.',contactTitle:'Account verification',contactText:'We try to identify the linked address automatically. If Last War provides it, only a masked version will be shown.',masked:'Code sent to',emailFallback:'To confirm this account belongs to you, Last War currently requires the linked email address.',emailLabel:'Email linked to Last War',emailPlaceholder:'you@email.com',sendCode:'Send code',forgot:'I no longer know which email is linked',helpTitle:'Find the linked email',helpText:'In Last War, open your profile and then Account. The linked email address is shown there. Come back here: your UID will remain saved.',back:'Back',codeTitle:'Verification code',codeText:'Enter the 6-digit code sent by Last War.',codeLabel:'6-digit code',codePlaceholder:'••••••',verify:'Verify and sync',connecting:'Connecting to Last War…',authorizing:'Authorizing…',syncing:'Syncing…',notReady:'The Last War connection service is being enabled on this test branch.',service:'Connection service is temporarily unavailable.',close:'Close'},
 es:{title:'Conexión Last War',card:'Last War',sub:'Vincula tu cuenta y mantén actualizado el simulador automáticamente.',stateOff:'No vinculado',stateOn:'Cuenta sincronizada',link:'Vincular mi cuenta Last War',refresh:'Actualizar',unlink:'Desvincular mi cuenta',last:'Última actualización',privacy:'WfGg nunca te pedirá la contraseña de Last War. El código recibido por correo se usa una sola vez y nunca se guarda.',uidTitle:'Tu UID de Last War',uidText:'Empieza con el identificador del personaje. En Last War: Perfil → Ajustes → Copiar ID.',uidLabel:'UID Last War',uidPlaceholder:'Ej. 1234567890123456',continue:'Continuar',uidBad:'Comprueba tu UID de Last War.',contactTitle:'Verificación de cuenta',contactText:'Intentamos identificar automáticamente la dirección vinculada. Si Last War la proporciona, solo mostraremos una versión enmascarada.',masked:'Código enviado a',emailFallback:'Para confirmar que la cuenta es tuya, Last War requiere actualmente el correo asociado.',emailLabel:'Correo vinculado a Last War',emailPlaceholder:'tu@email.com',sendCode:'Enviar código',forgot:'Ya no sé qué correo está vinculado',helpTitle:'Encontrar el correo vinculado',helpText:'En Last War abre tu perfil y después Cuenta. Allí aparece el correo vinculado. Vuelve aquí: tu UID seguirá guardado.',back:'Volver',codeTitle:'Código de verificación',codeText:'Introduce el código de 6 cifras enviado por Last War.',codeLabel:'Código de 6 cifras',codePlaceholder:'••••••',verify:'Verificar y sincronizar',connecting:'Conectando con Last War…',authorizing:'Autorizando…',syncing:'Sincronizando…',notReady:'El servicio de conexión Last War se está activando en esta rama de prueba.',service:'El servicio de conexión no está disponible temporalmente.',close:'Cerrar'}
};
let status={connected:false,last_sync_at:null,snapshot:null};
let step='uid';
let maskedContact='';
const lang=()=>{const x=(localStorage.getItem(LANG_KEY)||document.documentElement.lang||'fr').slice(0,2);return TXT[x]?x:'fr'};
const t=k=>TXT[lang()][k]||TXT.fr[k]||k;
const token=()=>localStorage.getItem(TOKEN_KEY)||'';
const uidValue=()=>sessionStorage.getItem(PENDING_UID_KEY)||'';

function ensureCard(){
 const grid=document.querySelector('.module-grid');if(!grid||document.getElementById('lastWarConnectCard'))return;
 const b=document.createElement('button');b.id='lastWarConnectCard';b.type='button';b.className='module-card glass-card lastwar-link-card';b.innerHTML='<span class="module-icon">🔗</span><span class="lastwar-link-status-dot"></span><span class="module-arrow">→</span><span class="module-copy"><strong data-lw="card"></strong><small data-lw="sub"></small></span>';
 b.addEventListener('click',open);grid.appendChild(b);paintCard();
}
function paintCard(){const b=document.getElementById('lastWarConnectCard');if(!b)return;b.classList.toggle('is-connected',!!status.connected);b.querySelector('[data-lw="card"]').textContent=t('card');b.querySelector('[data-lw="sub"]').textContent=status.connected?t('stateOn'):t('sub')}
function ensureOverlay(){if(document.getElementById('lastWarConnectOverlay'))return;const o=document.createElement('div');o.id='lastWarConnectOverlay';o.className='lw-connect-overlay hidden';o.innerHTML='<section class="lw-connect-panel" role="dialog" aria-modal="true"><div class="lw-connect-handle"></div><div class="lw-connect-head"><div><p class="eyebrow">WfGg</p><h2 class="lw-connect-title"></h2></div><button class="lw-connect-close" type="button">×</button></div><p class="lw-connect-sub"></p><div id="lwBody"></div><div class="lw-connect-actions"><button id="lwPrimary" class="lw-connect-primary" type="button"></button><button id="lwSecondary" class="lw-connect-secondary" type="button" hidden></button><button id="lwDanger" class="lw-connect-danger" type="button" hidden></button></div><div id="lwProgress" class="lw-connect-progress" hidden><span></span></div><div id="lwMessage" class="lw-connect-message" hidden></div><p class="lw-connect-privacy"></p></section>';
 o.addEventListener('click',e=>{if(e.target===o)close()});o.querySelector('.lw-connect-close').addEventListener('click',close);document.body.appendChild(o);
}
function setMessage(text,type=''){const m=document.getElementById('lwMessage');if(!m)return;m.hidden=!text;m.className='lw-connect-message'+(type?' '+type:'');m.textContent=text||''}
function setBusy(on,label){const p=document.getElementById('lwProgress'),b=document.getElementById('lwPrimary');if(p)p.hidden=!on;if(b){b.disabled=on;if(label)b.textContent=label}}
function field(label,id,type,placeholder,value='',attrs=''){return `<label class="lw-connect-field"><span>${label}</span><input id="${id}" type="${type}" placeholder="${placeholder}" value="${String(value).replace(/"/g,'&quot;')}" ${attrs}></label>`}
function stateBox(icon,title,text){return `<div class="lw-connect-state"><div class="lw-connect-state-row"><div class="lw-connect-badge">${icon}</div><div><strong>${title}</strong><small>${text||''}</small></div></div></div>`}
function render(){
 ensureOverlay();const o=document.getElementById('lastWarConnectOverlay');o.querySelector('.lw-connect-title').textContent=t('title');o.querySelector('.lw-connect-sub').textContent=t('sub');o.querySelector('.lw-connect-privacy').textContent=t('privacy');
 const body=document.getElementById('lwBody'),primary=document.getElementById('lwPrimary'),secondary=document.getElementById('lwSecondary'),danger=document.getElementById('lwDanger');
 setMessage('');setBusy(false);secondary.hidden=true;danger.hidden=true;
 if(status.connected){body.innerHTML=stateBox('✓',t('stateOn'),status.last_sync_at?`${t('last')} : ${new Date(status.last_sync_at).toLocaleString(lang())}`:'');primary.textContent=t('refresh');primary.onclick=refresh;danger.hidden=false;danger.textContent=t('unlink');danger.onclick=unlinkLocal;paintCard();return}
 if(step==='uid'){
  body.innerHTML=stateBox('🪪',t('uidTitle'),t('uidText'))+field(t('uidLabel'),'lwUid','text',t('uidPlaceholder'),uidValue(),'inputmode="numeric" autocomplete="off" maxlength="24"');
  primary.textContent=t('continue');primary.onclick=submitUid;
 }else if(step==='contact'){
  const intro=maskedContact?`${t('masked')} ${maskedContact}`:t('emailFallback');
  body.innerHTML=stateBox('🔐',t('contactTitle'),t('contactText'))+`<p class="lw-connect-inline-copy">${intro}</p>`+(maskedContact?'':field(t('emailLabel'),'lwEmail','email',t('emailPlaceholder'),'','autocomplete="email"'));
  primary.textContent=maskedContact?t('sendCode'):t('sendCode');primary.onclick=sendCode;
  secondary.hidden=false;secondary.textContent=t('forgot');secondary.onclick=showHelp;
 }else if(step==='help'){
  body.innerHTML=stateBox('💡',t('helpTitle'),t('helpText'));
  primary.textContent=t('back');primary.onclick=()=>{step='contact';render()};
 }else if(step==='code'){
  body.innerHTML=stateBox('✉️',t('codeTitle'),t('codeText'))+field(t('codeLabel'),'lwCode','text',t('codePlaceholder'),'','inputmode="numeric" autocomplete="one-time-code" maxlength="6"');
  primary.textContent=t('verify');primary.onclick=verifyCode;
  secondary.hidden=false;secondary.textContent=t('back');secondary.onclick=()=>{step='contact';render()};
 }
 paintCard();
}
async function connector(path,options={}){const h=new Headers(options.headers||{});const tk=token();if(tk)h.set('Authorization',`Bearer ${tk}`);if(options.body&&!h.has('Content-Type'))h.set('Content-Type','application/json');const r=await fetch(CONNECTOR_API+path,{...options,headers:h,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok){const e=new Error(d.error||`HTTP_${r.status}`);e.status=r.status;e.data=d;throw e}return d}
async function loadStatus(){if(!token())return;try{status=await connector('/api/lastwar/status');paintCard()}catch{status={connected:false,last_sync_at:null,snapshot:null};paintCard()}}
function normalizeUid(v){return String(v||'').replace(/\D/g,'').slice(0,24)}
async function submitUid(){const el=document.getElementById('lwUid');const uid=normalizeUid(el?.value);if(uid.length<8){setMessage(t('uidBad'),'error');return}sessionStorage.setItem(PENDING_UID_KEY,uid);maskedContact='';step='contact';render();}
function showHelp(){step='help';render()}
async function sendCode(){
 const uid=uidValue();if(!uid){step='uid';render();return}
 const email=maskedContact?'':String(document.getElementById('lwEmail')?.value||'').trim();
 if(!maskedContact&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){setMessage(t('emailFallback'),'error');return}
 setBusy(true,t('connecting'));setMessage('');
 try{
  await connector('/api/lastwar/pair/start',{method:'POST',body:JSON.stringify({uid,email:email||undefined})});
  step='code';render();setMessage(t('notReady'));
 }catch(e){setBusy(false);setMessage(e.status===404?t('notReady'):t('service'),'error')}
}
async function verifyCode(){const code=String(document.getElementById('lwCode')?.value||'').replace(/\D/g,'');if(code.length!==6){setMessage(t('codeText'),'error');return}setBusy(true,t('syncing'));setMessage(t('notReady'));setTimeout(()=>setBusy(false),650)}
async function refresh(){setBusy(true,t('syncing'));setMessage(t('notReady'));setTimeout(()=>setBusy(false),650)}
async function unlinkLocal(){setMessage(t('notReady'))}
function open(){ensureOverlay();step=status.connected?'uid':(uidValue()?'contact':'uid');render();document.getElementById('lastWarConnectOverlay').classList.remove('hidden');loadStatus().then(()=>{if(status.connected)render()})}
function close(){document.getElementById('lastWarConnectOverlay')?.classList.add('hidden')}
function boot(){ensureCard();ensureOverlay();loadStatus();new MutationObserver(()=>ensureCard()).observe(document.body,{childList:true,subtree:true});document.addEventListener('click',()=>setTimeout(paintCard,0),true)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
