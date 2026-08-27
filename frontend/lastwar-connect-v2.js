(()=>{
'use strict';

const TOKEN_KEY='wfgg_portal_session';
const LANG_KEY='wfgg_portal_language';
const PENDING_UID_KEY='wfgg_lastwar_pending_uid';
const AUTH_TX_KEY='wfgg_lastwar_auth_tx';
const CONNECTOR_API=(window.WFGG_PORTAL_CONFIG?.LASTWAR_CONNECTOR_API||'').replace(/\/+$/,'');

const TXT={
 fr:{title:'Connexion Last War',card:'Last War',sub:'Reliez votre compte et mettez le simulateur à jour automatiquement.',stateOff:'Non relié',stateOn:'Compte synchronisé',last:'Dernière mise à jour',refresh:'Mettre à jour',unlink:'Dissocier mon compte',privacy:'WfGg ne vous demandera jamais votre mot de passe Last War. Le code reçu par e-mail est utilisé une seule fois et n’est jamais conservé.',uidTitle:'Votre UID Last War',uidText:'Commencez par votre identifiant de personnage. Dans Last War : Profil → Paramètres → Copier ID.',uidLabel:'UID Last War',uidPlaceholder:'Ex. 1234567890123456',continue:'Continuer',uidBad:'Vérifiez votre UID Last War.',resolving:'Recherche du compte…',contactTitle:'Vérification du compte',contactText:'WfGg vérifie si Last War peut identifier le contact lié à ce UID.',accountFound:'Compte identifié',masked:'Le code sera envoyé à',emailFallback:'Last War ne fournit pas encore l’adresse liée à partir du UID. Saisissez l’adresse e-mail associée au compte.',emailLabel:'Adresse e-mail liée à Last War',emailPlaceholder:'votre@email.com',sendCode:'Envoyer le code',sending:'Envoi du code…',forgot:'Je ne sais plus quelle adresse e-mail est liée',helpTitle:'Retrouver l’adresse liée',helpText:'Dans Last War, ouvrez votre profil puis Compte. Vérifiez l’adresse e-mail liée, puis revenez ici : votre UID restera enregistré.',back:'Retour',codeTitle:'Code de vérification',codeText:'Entrez le code à 6 chiffres envoyé par Last War.',codeLabel:'Code à 6 chiffres',codePlaceholder:'••••••',verify:'Vérifier et synchroniser',verifying:'Vérification…',codeSent:'Code envoyé',verifiedTitle:'Compte vérifié',verifiedText:'Votre compte Last War est vérifié. La synchronisation peut maintenant démarrer.',notReady:'Le moteur de connexion Last War est prêt côté WfGg mais le broker de production n’est pas encore activé sur cette branche.',service:'Le service de connexion Last War est temporairement indisponible.',uidNotFound:'Ce UID Last War n’a pas été trouvé.',emailMismatch:'Cette adresse ne correspond pas au compte Last War.',codeInvalid:'Le code est incorrect ou a expiré.',rateLimited:'Trop de tentatives. Réessayez dans quelques minutes.'},
 it:{title:'Connessione Last War',card:'Last War',sub:'Collega il tuo account e aggiorna automaticamente il simulatore.',stateOff:'Non collegato',stateOn:'Account sincronizzato',last:'Ultimo aggiornamento',refresh:'Aggiorna',unlink:'Scollega il mio account',privacy:'WfGg non ti chiederà mai la password di Last War. Il codice e-mail viene usato una sola volta e non viene conservato.',uidTitle:'Il tuo UID Last War',uidText:'Inizia dall’ID del personaggio. In Last War: Profilo → Impostazioni → Copia ID.',uidLabel:'UID Last War',uidPlaceholder:'Es. 1234567890123456',continue:'Continua',uidBad:'Controlla il tuo UID Last War.',resolving:'Ricerca dell’account…',contactTitle:'Verifica account',contactText:'WfGg controlla se Last War può identificare il contatto collegato a questo UID.',accountFound:'Account identificato',masked:'Il codice verrà inviato a',emailFallback:'Last War non fornisce ancora l’indirizzo collegato partendo dal UID. Inserisci l’e-mail associata all’account.',emailLabel:'E-mail collegata a Last War',emailPlaceholder:'tuo@email.com',sendCode:'Invia il codice',sending:'Invio del codice…',forgot:'Non ricordo quale e-mail è collegata',helpTitle:'Trova l’e-mail collegata',helpText:'In Last War apri il profilo e poi Account. Controlla l’e-mail collegata e torna qui: il tuo UID resterà salvato.',back:'Indietro',codeTitle:'Codice di verifica',codeText:'Inserisci il codice a 6 cifre inviato da Last War.',codeLabel:'Codice a 6 cifre',codePlaceholder:'••••••',verify:'Verifica e sincronizza',verifying:'Verifica…',codeSent:'Codice inviato',verifiedTitle:'Account verificato',verifiedText:'Il tuo account Last War è verificato. La sincronizzazione può ora iniziare.',notReady:'Il motore di connessione WfGg è pronto, ma il broker di produzione non è ancora attivo su questo ramo.',service:'Il servizio di connessione Last War non è temporaneamente disponibile.',uidNotFound:'Questo UID Last War non è stato trovato.',emailMismatch:'Questa e-mail non corrisponde all’account Last War.',codeInvalid:'Il codice non è corretto o è scaduto.',rateLimited:'Troppi tentativi. Riprova tra qualche minuto.'},
 en:{title:'Last War connection',card:'Last War',sub:'Link your account and keep the simulator updated automatically.',stateOff:'Not linked',stateOn:'Account synced',last:'Last update',refresh:'Update now',unlink:'Unlink my account',privacy:'WfGg will never ask for your Last War password. The email code is used once and is never stored.',uidTitle:'Your Last War UID',uidText:'Start with your character ID. In Last War: Profile → Settings → Copy ID.',uidLabel:'Last War UID',uidPlaceholder:'E.g. 1234567890123456',continue:'Continue',uidBad:'Check your Last War UID.',resolving:'Finding account…',contactTitle:'Account verification',contactText:'WfGg checks whether Last War can identify the contact linked to this UID.',accountFound:'Account identified',masked:'The code will be sent to',emailFallback:'Last War does not yet provide the linked address from the UID. Enter the email associated with the account.',emailLabel:'Email linked to Last War',emailPlaceholder:'you@email.com',sendCode:'Send code',sending:'Sending code…',forgot:'I no longer know which email is linked',helpTitle:'Find the linked email',helpText:'In Last War, open your profile and then Account. Check the linked email and come back here: your UID will remain saved.',back:'Back',codeTitle:'Verification code',codeText:'Enter the 6-digit code sent by Last War.',codeLabel:'6-digit code',codePlaceholder:'••••••',verify:'Verify and sync',verifying:'Verifying…',codeSent:'Code sent',verifiedTitle:'Account verified',verifiedText:'Your Last War account is verified. Synchronization can now start.',notReady:'The WfGg connection engine is ready, but the production broker is not enabled on this test branch yet.',service:'The Last War connection service is temporarily unavailable.',uidNotFound:'This Last War UID was not found.',emailMismatch:'This email does not match the Last War account.',codeInvalid:'The code is incorrect or has expired.',rateLimited:'Too many attempts. Try again in a few minutes.'},
 es:{title:'Conexión Last War',card:'Last War',sub:'Vincula tu cuenta y mantén actualizado el simulador automáticamente.',stateOff:'No vinculado',stateOn:'Cuenta sincronizada',last:'Última actualización',refresh:'Actualizar',unlink:'Desvincular mi cuenta',privacy:'WfGg nunca te pedirá la contraseña de Last War. El código recibido por correo se usa una sola vez y nunca se guarda.',uidTitle:'Tu UID de Last War',uidText:'Empieza con el ID del personaje. En Last War: Perfil → Ajustes → Copiar ID.',uidLabel:'UID Last War',uidPlaceholder:'Ej. 1234567890123456',continue:'Continuar',uidBad:'Comprueba tu UID de Last War.',resolving:'Buscando la cuenta…',contactTitle:'Verificación de cuenta',contactText:'WfGg comprueba si Last War puede identificar el contacto vinculado a este UID.',accountFound:'Cuenta identificada',masked:'El código se enviará a',emailFallback:'Last War todavía no proporciona la dirección vinculada a partir del UID. Introduce el correo asociado a la cuenta.',emailLabel:'Correo vinculado a Last War',emailPlaceholder:'tu@email.com',sendCode:'Enviar código',sending:'Enviando código…',forgot:'Ya no sé qué correo está vinculado',helpTitle:'Encontrar el correo vinculado',helpText:'En Last War abre tu perfil y después Cuenta. Comprueba el correo vinculado y vuelve aquí: tu UID seguirá guardado.',back:'Volver',codeTitle:'Código de verificación',codeText:'Introduce el código de 6 cifras enviado por Last War.',codeLabel:'Código de 6 cifras',codePlaceholder:'••••••',verify:'Verificar y sincronizar',verifying:'Verificando…',codeSent:'Código enviado',verifiedTitle:'Cuenta verificada',verifiedText:'Tu cuenta Last War está verificada. La sincronización ya puede comenzar.',notReady:'El motor de conexión WfGg está listo, pero el broker de producción aún no está activado en esta rama.',service:'El servicio de conexión Last War no está disponible temporalmente.',uidNotFound:'No se ha encontrado este UID de Last War.',emailMismatch:'Este correo no corresponde a la cuenta Last War.',codeInvalid:'El código es incorrecto o ha caducado.',rateLimited:'Demasiados intentos. Vuelve a intentarlo en unos minutos.'}
};

let status={connected:false,last_sync_at:null,snapshot:null};
let step='uid';
let maskedContact='';
let resolvedPlayer='';
let resolvedServer='';

const lang=()=>{const x=(localStorage.getItem(LANG_KEY)||document.documentElement.lang||'fr').slice(0,2);return TXT[x]?x:'fr'};
const t=k=>TXT[lang()][k]||TXT.fr[k]||k;
const token=()=>localStorage.getItem(TOKEN_KEY)||'';
const uidValue=()=>sessionStorage.getItem(PENDING_UID_KEY)||'';
const authTx=()=>sessionStorage.getItem(AUTH_TX_KEY)||'';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function ensureCard(){
 const grid=document.querySelector('.module-grid');
 if(!grid||document.getElementById('lastWarConnectCard'))return;
 const b=document.createElement('button');
 b.id='lastWarConnectCard';b.type='button';b.className='module-card glass-card lastwar-link-card';
 b.innerHTML='<span class="module-icon">🔗</span><span class="lastwar-link-status-dot"></span><span class="module-arrow">→</span><span class="module-copy"><strong data-lw="card"></strong><small data-lw="sub"></small></span>';
 b.addEventListener('click',open);grid.appendChild(b);paintCard();
}
function paintCard(){const b=document.getElementById('lastWarConnectCard');if(!b)return;b.classList.toggle('is-connected',!!status.connected);b.querySelector('[data-lw="card"]').textContent=t('card');b.querySelector('[data-lw="sub"]').textContent=status.connected?t('stateOn'):t('sub')}
function ensureOverlay(){
 if(document.getElementById('lastWarConnectOverlay'))return;
 const o=document.createElement('div');o.id='lastWarConnectOverlay';o.className='lw-connect-overlay hidden';
 o.innerHTML='<section class="lw-connect-panel" role="dialog" aria-modal="true"><div class="lw-connect-handle"></div><div class="lw-connect-head"><div><p class="eyebrow">WfGg</p><h2 class="lw-connect-title"></h2></div><button class="lw-connect-close" type="button">×</button></div><p class="lw-connect-sub"></p><div id="lwBody"></div><div class="lw-connect-actions"><button id="lwPrimary" class="lw-connect-primary" type="button"></button><button id="lwSecondary" class="lw-connect-secondary" type="button" hidden></button><button id="lwDanger" class="lw-connect-danger" type="button" hidden></button></div><div id="lwProgress" class="lw-connect-progress" hidden><span></span></div><div id="lwMessage" class="lw-connect-message" hidden></div><p class="lw-connect-privacy"></p></section>';
 o.addEventListener('click',e=>{if(e.target===o)close()});o.querySelector('.lw-connect-close').addEventListener('click',close);document.body.appendChild(o);
}
function setMessage(text,type=''){const m=document.getElementById('lwMessage');if(!m)return;m.hidden=!text;m.className='lw-connect-message'+(type?' '+type:'');m.textContent=text||''}
function setBusy(on,label){const p=document.getElementById('lwProgress'),b=document.getElementById('lwPrimary'),s=document.getElementById('lwSecondary');if(p)p.hidden=!on;if(b){b.disabled=on;if(label)b.textContent=label}if(s)s.disabled=on}
function field(label,id,type,placeholder,value='',attrs=''){return `<label class="lw-connect-field"><span>${esc(label)}</span><input id="${id}" type="${type}" placeholder="${esc(placeholder)}" value="${esc(value)}" ${attrs}></label>`}
function stateBox(icon,title,text){return `<div class="lw-connect-state"><div class="lw-connect-state-row"><div class="lw-connect-badge">${icon}</div><div><strong>${esc(title)}</strong><small>${esc(text||'')}</small></div></div></div>`}
function accountMeta(){const bits=[];if(resolvedPlayer)bits.push(resolvedPlayer);if(resolvedServer)bits.push(`S${resolvedServer}`);return bits.join(' · ')}

function render(){
 ensureOverlay();const o=document.getElementById('lastWarConnectOverlay');o.querySelector('.lw-connect-title').textContent=t('title');o.querySelector('.lw-connect-sub').textContent=t('sub');o.querySelector('.lw-connect-privacy').textContent=t('privacy');
 const body=document.getElementById('lwBody'),primary=document.getElementById('lwPrimary'),secondary=document.getElementById('lwSecondary'),danger=document.getElementById('lwDanger');
 setMessage('');setBusy(false);secondary.hidden=true;danger.hidden=true;
 if(status.connected){body.innerHTML=stateBox('✓',t('stateOn'),status.last_sync_at?`${t('last')} : ${new Date(status.last_sync_at).toLocaleString(lang())}`:'');primary.textContent=t('refresh');primary.onclick=refresh;danger.hidden=false;danger.textContent=t('unlink');danger.onclick=unlinkLocal;paintCard();return}
 if(step==='uid'){
  body.innerHTML=stateBox('🪪',t('uidTitle'),t('uidText'))+field(t('uidLabel'),'lwUid','text',t('uidPlaceholder'),uidValue(),'inputmode="numeric" autocomplete="off" maxlength="24"');
  primary.textContent=t('continue');primary.onclick=submitUid;
 }else if(step==='contact'){
  const detail=accountMeta()||t('contactText');
  const intro=maskedContact?`${t('masked')} ${maskedContact}`:t('emailFallback');
  body.innerHTML=stateBox('🔐',maskedContact?t('accountFound'):t('contactTitle'),detail)+`<p class="lw-connect-inline-copy">${esc(intro)}</p>`+(maskedContact?'':field(t('emailLabel'),'lwEmail','email',t('emailPlaceholder'),'','autocomplete="email"'));
  primary.textContent=t('sendCode');primary.onclick=sendCode;
  secondary.hidden=false;secondary.textContent=t('forgot');secondary.onclick=showHelp;
 }else if(step==='help'){
  body.innerHTML=stateBox('💡',t('helpTitle'),t('helpText'));primary.textContent=t('back');primary.onclick=()=>{step='contact';render()};
 }else if(step==='code'){
  const detail=maskedContact?`${t('codeText')} ${maskedContact}`:t('codeText');
  body.innerHTML=stateBox('✉️',t('codeTitle'),detail)+field(t('codeLabel'),'lwCode','text',t('codePlaceholder'),'','inputmode="numeric" autocomplete="one-time-code" maxlength="6"');
  primary.textContent=t('verify');primary.onclick=verifyCode;secondary.hidden=false;secondary.textContent=t('back');secondary.onclick=()=>{step='contact';render()};
 }else if(step==='verified'){
  body.innerHTML=stateBox('✓',t('verifiedTitle'),t('verifiedText'));primary.textContent=t('refresh');primary.onclick=refresh;
 }
 paintCard();
}

async function connector(path,options={}){const h=new Headers(options.headers||{});const tk=token();if(tk)h.set('Authorization',`Bearer ${tk}`);if(options.body&&!h.has('Content-Type'))h.set('Content-Type','application/json');const r=await fetch(CONNECTOR_API+path,{...options,headers:h,cache:'no-store'});let d={};try{d=await r.json()}catch{}if(!r.ok){const e=new Error(d.error||`HTTP_${r.status}`);e.status=r.status;e.data=d;throw e}return d}
async function loadStatus(){if(!token())return;try{status=await connector('/api/lastwar/status');paintCard()}catch{status={connected:false,last_sync_at:null,snapshot:null};paintCard()}}
function normalizeUid(v){return String(v||'').replace(/\D/g,'').slice(0,24)}
function friendlyError(e){const c=String(e?.message||'');if(c==='LASTWAR_UID_NOT_FOUND')return t('uidNotFound');if(c==='LASTWAR_EMAIL_MISMATCH')return t('emailMismatch');if(c==='LASTWAR_VERIFY_CODE_INVALID'||c==='LASTWAR_VERIFY_CODE_EXPIRED')return t('codeInvalid');if(c==='LASTWAR_RATE_LIMITED')return t('rateLimited');if(c==='LASTWAR_BROKER_NOT_CONFIGURED')return t('notReady');return t('service')}

async function submitUid(){
 const uid=normalizeUid(document.getElementById('lwUid')?.value);if(uid.length<8){setMessage(t('uidBad'),'error');return}
 sessionStorage.setItem(PENDING_UID_KEY,uid);sessionStorage.removeItem(AUTH_TX_KEY);maskedContact='';resolvedPlayer='';resolvedServer='';setBusy(true,t('resolving'));setMessage('');
 try{const d=await connector('/api/lastwar/identity/resolve',{method:'POST',body:JSON.stringify({uid})});maskedContact=d.contact_hint||'';resolvedPlayer=d.player_name||'';resolvedServer=d.server_id||'';step='contact';render()}catch(e){setBusy(false);setMessage(friendlyError(e),'error')}
}
function showHelp(){step='help';render()}

async function sendCode(){
 const uid=uidValue();if(!uid){step='uid';render();return}
 const email=maskedContact?'':String(document.getElementById('lwEmail')?.value||'').trim();
 if(!maskedContact&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)){setMessage(t('emailFallback'),'error');return}
 setBusy(true,t('sending'));setMessage('');
 try{const d=await connector('/api/lastwar/identity/send-code',{method:'POST',body:JSON.stringify({uid,email:email||undefined})});if(d.auth_transaction)sessionStorage.setItem(AUTH_TX_KEY,d.auth_transaction);if(d.contact_hint)maskedContact=d.contact_hint;step='code';render();setMessage(maskedContact?`${t('codeSent')} · ${maskedContact}`:t('codeSent'),'success')}catch(e){setBusy(false);setMessage(friendlyError(e),'error')}
}

async function verifyCode(){
 const uid=uidValue(),tx=authTx(),code=String(document.getElementById('lwCode')?.value||'').replace(/\D/g,'');
 if(code.length!==6){setMessage(t('codeInvalid'),'error');return}if(!uid||!tx){step='contact';render();return}
 setBusy(true,t('verifying'));setMessage('');
 try{const d=await connector('/api/lastwar/identity/verify-code',{method:'POST',body:JSON.stringify({uid,auth_transaction:tx,code})});sessionStorage.removeItem(AUTH_TX_KEY);resolvedPlayer=d.player_name||resolvedPlayer;resolvedServer=d.server_id||resolvedServer;step='verified';render();setMessage(t('verifiedText'),'success');await loadStatus()}catch(e){setBusy(false);setMessage(friendlyError(e),'error')}
}

async function refresh(){setBusy(true,t('refresh'));try{await connector('/api/lastwar/cloud-sync',{method:'POST',body:'{}'});await loadStatus();setBusy(false);render()}catch(e){setBusy(false);setMessage(friendlyError(e),'error')}}
async function unlinkLocal(){
 const danger=document.getElementById('lwDanger');
 if(danger)danger.disabled=true;
 setMessage('');
 try{
  await connector('/api/lastwar/identity/unlink',{method:'POST',body:'{}'});
  sessionStorage.removeItem(PENDING_UID_KEY);
  sessionStorage.removeItem(AUTH_TX_KEY);
  maskedContact='';resolvedPlayer='';resolvedServer='';
  status={connected:false,last_sync_at:null,snapshot:null};
  step='uid';
  render();
  paintCard();
 }catch(e){
  if(danger)danger.disabled=false;
  setMessage(friendlyError(e),'error');
 }
}
function open(){ensureOverlay();if(status.connected)step='uid';else if(authTx())step='code';else if(uidValue())step='contact';else step='uid';render();document.getElementById('lastWarConnectOverlay').classList.remove('hidden');loadStatus().then(()=>{if(status.connected)render()})}
function close(){document.getElementById('lastWarConnectOverlay')?.classList.add('hidden')}
function boot(){ensureCard();ensureOverlay();loadStatus();new MutationObserver(()=>ensureCard()).observe(document.body,{childList:true,subtree:true});document.addEventListener('click',()=>setTimeout(paintCard,0),true)}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
