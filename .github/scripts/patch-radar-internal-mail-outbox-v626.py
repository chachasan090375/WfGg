#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
WORKER = ROOT / 'src/worker.js'
UI = ROOT / 'public/live-radar.html'

def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)

worker = WORKER.read_text(encoding='utf-8')
if 'WFGG_RADAR_INTERNAL_MAIL_OUTBOX_WORKER_V626' not in worker:
    helper_anchor = 'export default {\n'
    helper = r'''// WFGG_RADAR_INTERNAL_MAIL_OUTBOX_WORKER_V626
function hexV626(value) {
  return [...new Uint8Array(value)].map(x => x.toString(16).padStart(2, '0')).join('');
}

async function mailerRequestV626(env, path, payload) {
  const baseUrl = String(env.RADAR_MAILER_URL || '').replace(/\/+$/, '');
  if (!baseUrl) throw Object.assign(new Error('RADAR_MAILER_NOT_CONFIGURED_V626'), { status: 503 });
  const sharedKey = requireSecret(env.RADAR_MAILER_SHARED_KEY, 'RADAR_MAILER_SHARED_KEY');
  const body = JSON.stringify(payload);
  const enc = new TextEncoder();
  const bodyBytes = enc.encode(body);
  const bodyHash = hexV626(await crypto.subtle.digest('SHA-256', bodyBytes));
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = crypto.randomUUID().replace(/-/g, '');
  const canonical = ['POST', path, timestamp, nonce, bodyHash].join('\n');
  const key = await crypto.subtle.importKey(
    'raw', enc.encode(sharedKey), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
  );
  const signature = hexV626(await crypto.subtle.sign('HMAC', key, enc.encode(canonical)));
  const response = await fetch(baseUrl + path, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'X-Radar-Timestamp': timestamp,
      'X-Radar-Nonce': nonce,
      'X-Radar-Signature': signature
    },
    body
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Object.assign(new Error(String(data.error || 'RADAR_MAILER_REQUEST_FAILED_V626')), { status: response.status });
  }
  return data;
}

'''
    worker = replace_once(worker, helper_anchor, helper + helper_anchor, 'V626 worker helper')

    route_anchor = '      // WFGG_RADAR_RECRUITMENT_UX_WORKER_V621\n'
    route = r'''      // WFGG_RADAR_INTERNAL_MAIL_OUTBOX_ROUTE_V626
      if (url.pathname === '/api/radar/mail/outbox' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const input = await bodyJson(request);
        const targetUid = String(input.targetUid || '').trim();
        const targetName = String(input.targetName || '').trim();
        const campaignId = String(input.campaignId || 'manual-v626').trim();
        const title = String(input.title || '');
        const contents = String(input.contents || '');
        const enc = new TextEncoder();
        if (!/^\d{6,64}$/.test(targetUid)) throw Object.assign(new Error('MAIL_TARGET_UID_INVALID_V626'), { status: 400 });
        if (!targetName || enc.encode(targetName).length > 256) throw Object.assign(new Error('MAIL_TARGET_NAME_INVALID_V626'), { status: 400 });
        if (!campaignId || campaignId.length > 128) throw Object.assign(new Error('MAIL_CAMPAIGN_INVALID_V626'), { status: 400 });
        if (!title.trim() || enc.encode(title).length > 50) throw Object.assign(new Error('MAIL_TITLE_INVALID_V626'), { status: 400 });
        if (!contents.trim() || enc.encode(contents).length > 2000) throw Object.assign(new Error('MAIL_CONTENT_INVALID_V626'), { status: 400 });

        const queued = await mailerRequestV626(env, '/v1/outbox/queue', {
          campaignId, targetUid, targetName, title, contents
        });
        if (queued?.lastwarWrite !== false || queued?.lastwarMutation !== false || queued?.mailSendExecuted !== false) {
          throw Object.assign(new Error('MAIL_OUTBOX_DRY_RUN_INVARIANT_V626'), { status: 502 });
        }
        await audit(env, session.gameUid, 'radar.mail.outbox.queue', targetUid, {
          campaignId,
          duplicate: Boolean(queued?.duplicate),
          dryRun: true,
          lastwarMutation: false,
          mailSendExecuted: false
        });
        return json({
          ...queued,
          dryRun: true,
          lastwarMutation: false,
          mailSendExecuted: false,
          tokenUsed: false
        }, 202);
      }

'''
    worker = replace_once(worker, route_anchor, route + route_anchor, 'V626 worker route')

WORKER.write_text(worker, encoding='utf-8')

ui = UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_INTERNAL_MAIL_OUTBOX_UI_V626' not in ui:
    css = r'''
/* WFGG_RADAR_INTERNAL_MAIL_OUTBOX_UI_V626 */
.mail-v626-btn{border:1px solid #647d40;border-radius:11px;background:linear-gradient(#243318,#111b0d);color:#d9efa8;padding:10px 12px;font:900 10px ui-monospace,monospace;letter-spacing:.04em}
.mail-v626-btn:disabled{opacity:.4}
.mail-v626-overlay{position:fixed;inset:0;z-index:6200;background:#000c;display:none;align-items:flex-end;justify-content:center;padding:8px}
.mail-v626-overlay.show{display:flex}
.mail-v626-modal{width:min(620px,100%);max-height:92vh;overflow:auto;background:linear-gradient(180deg,#11190e,#071006);border:1px solid #60783c;border-radius:20px 20px 12px 12px;box-shadow:0 22px 70px #000;padding:14px;color:#dcebcf}
.mail-v626-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}
.mail-v626-title{font:900 13px ui-monospace,monospace;color:#d9f4a6}
.mail-v626-close{border:1px solid #566d3a;background:#15200f;color:#d9eca9;border-radius:9px;padding:8px 10px;font:900 10px ui-monospace,monospace}
.mail-v626-target,.mail-v626-safe{border:1px solid #33472a;background:#091108;border-radius:11px;padding:9px 10px;font:10px ui-monospace,monospace;color:#9db58d;line-height:1.45;margin:8px 0}
.mail-v626-safe{border-color:#496c8b;background:#0c1821;color:#b9ddff}
.mail-v626-field{display:grid;gap:5px;margin:10px 0}
.mail-v626-field label{font:900 9px ui-monospace,monospace;color:#8ea57e}
.mail-v626-field input,.mail-v626-field textarea{box-sizing:border-box;width:100%;border:1px solid #425a32;border-radius:10px;background:#050d04;color:#e2efd7;padding:10px;font:11px ui-monospace,monospace}
.mail-v626-field textarea{min-height:150px;resize:vertical}
.mail-v626-count{text-align:right;font:9px ui-monospace,monospace;color:#809673}
.mail-v626-count.bad{color:#ef9b85}
.mail-v626-queue{width:100%;border:1px solid #91a84d;border-radius:11px;background:linear-gradient(#b4d94f,#718c29);color:#101806;padding:12px;font:900 11px ui-monospace,monospace}
.mail-v626-queue:disabled{opacity:.45}
.mail-v626-status{min-height:20px;margin-top:9px;font:10px ui-monospace,monospace;color:#a7bc97}
'''
    ui = replace_once(ui, '</style>', css + '\n</style>', 'V626 UI css')

    js_anchor = 'async function health(){'
    js = r'''/* WFGG_RADAR_INTERNAL_MAIL_OUTBOX_UI_V626 */
const mailEncoderV626=new TextEncoder();
function mailBytesV626(v){return mailEncoderV626.encode(String(v||'')).length}
function updateMailButtonV626(){
  const b=$('mailOutboxV626');
  if(b)b.disabled=!/^\d{6,64}$/.test(String(currentProfileUID||''));
}
function validateMailDraftV626(){
  const t=$('mailV626Title'),c=$('mailV626Content'),q=$('mailV626Queue');
  if(!t||!c||!q)return false;
  const tb=mailBytesV626(t.value),cb=mailBytesV626(c.value);
  $('mailV626TitleCount').textContent=tb+'/50 octets';
  $('mailV626ContentCount').textContent=cb+'/2000 octets';
  $('mailV626TitleCount').classList.toggle('bad',tb>50);
  $('mailV626ContentCount').classList.toggle('bad',cb>2000);
  const ok=/^\d{6,64}$/.test(String(currentProfileUID||''))&&tb>0&&tb<=50&&cb>0&&cb<=2000;
  q.disabled=!ok;
  return ok;
}
function openMailOutboxV626(){
  if(!/^\d{6,64}$/.test(String(currentProfileUID||'')))return;
  $('mailV626Target').textContent=String($('rname')?.textContent||'—')+' · UID '+String(currentProfileUID);
  $('mailV626Status').textContent='Aucun envoi Last War : ce formulaire place uniquement un brouillon dans l’Outbox.';
  $('mailV626Overlay').classList.add('show');
  $('mailV626Overlay').setAttribute('aria-hidden','false');
  validateMailDraftV626();
}
function closeMailOutboxV626(){
  $('mailV626Overlay')?.classList.remove('show');
  $('mailV626Overlay')?.setAttribute('aria-hidden','true');
}
async function queueMailDraftV626(){
  if(!validateMailDraftV626())return;
  const q=$('mailV626Queue');q.disabled=true;
  $('mailV626Status').textContent='Écriture dans l’Outbox WfGg…';
  try{
    const d=await api('/api/radar/mail/outbox',{
      method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({
        campaignId:'manual-v626',
        targetUid:String(currentProfileUID),
        targetName:String($('rname')?.textContent||'').trim(),
        title:$('mailV626Title').value,
        contents:$('mailV626Content').value
      })
    });
    if(d?.lastwarMutation!==false||d?.mailSendExecuted!==false)throw new Error('MAIL_OUTBOX_DRY_RUN_INVARIANT_V626');
    $('mailV626Status').textContent=d?.duplicate
      ?'Déjà présent dans l’Outbox · aucun doublon ajouté · aucun envoi Last War.'
      :'Ajouté à l’Outbox · DRY-RUN · aucun envoi Last War.';
    setStatus('MESSAGE EN OUTBOX',d?.duplicate?'Brouillon déjà présent':'Brouillon enregistré','ok');
  }catch(err){
    $('mailV626Status').textContent='Outbox indisponible : '+String(err?.message||err);
    setStatus('OUTBOX IMPOSSIBLE',String(err?.message||err),'error');
  }finally{
    validateMailDraftV626();
  }
}
function setupMailOutboxV626(){
  if($('mailOutboxV626'))return;
  const refresh=$('refreshProfile');
  if(!refresh)return;
  const b=document.createElement('button');
  b.id='mailOutboxV626';b.type='button';b.className='mail-v626-btn';b.textContent='✉ MESSAGE · OUTBOX';
  b.disabled=true;b.addEventListener('click',openMailOutboxV626);
  refresh.insertAdjacentElement('afterend',b);
  document.body.insertAdjacentHTML('beforeend',\`
    <div id="mailV626Overlay" class="mail-v626-overlay" aria-hidden="true">
      <div class="mail-v626-modal" role="dialog" aria-modal="true" aria-labelledby="mailV626Heading">
        <div class="mail-v626-head"><div id="mailV626Heading" class="mail-v626-title">MESSAGE INTERNE · OUTBOX DRY-RUN</div><button id="mailV626Close" class="mail-v626-close" type="button">FERMER</button></div>
        <div id="mailV626Target" class="mail-v626-target">—</div>
        <div class="mail-v626-safe">🔒 V6.26 ne peut pas envoyer dans Last War. Le brouillon est uniquement validé, dédupliqué et enregistré dans l’Outbox WfGg.</div>
        <div class="mail-v626-field"><label>TITRE</label><input id="mailV626Title" autocomplete="off" placeholder="Titre du message"><div id="mailV626TitleCount" class="mail-v626-count">0/50 octets</div></div>
        <div class="mail-v626-field"><label>CONTENU</label><textarea id="mailV626Content" placeholder="Message au joueur"></textarea><div id="mailV626ContentCount" class="mail-v626-count">0/2000 octets</div></div>
        <button id="mailV626Queue" class="mail-v626-queue" type="button" disabled>AJOUTER À L’OUTBOX · DRY-RUN</button>
        <div id="mailV626Status" class="mail-v626-status"></div>
      </div>
    </div>\`);
  $('mailV626Close').addEventListener('click',closeMailOutboxV626);
  $('mailV626Overlay').addEventListener('click',e=>{if(e.target===$('mailV626Overlay'))closeMailOutboxV626()});
  $('mailV626Title').addEventListener('input',validateMailDraftV626);
  $('mailV626Content').addEventListener('input',validateMailDraftV626);
  $('mailV626Queue').addEventListener('click',queueMailDraftV626);
  updateMailButtonV626();
}
queueMicrotask(setupMailOutboxV626);

'''
    ui = replace_once(ui, js_anchor, js + js_anchor, 'V626 UI JS')

    uid_anchor = "currentProfileUID=uid?String(uid):'';if(currentProfileUID){scheduleResolvedProfileRefreshV622(currentProfileUID);}"
    ui = replace_once(ui, uid_anchor, uid_anchor + "updateMailButtonV626();", 'V626 profile UID hook')

UI.write_text(ui, encoding='utf-8')

print('RADAR_V626_INTERNAL_MAIL_OUTBOX=READY')
print('RADAR_V626_LASTWAR_WRITE=DISABLED')
print('RADAR_V626_MAIL_SEND_EXECUTED=NO')
print('RADAR_V626_TOKEN_TO_MAILER=NO')
