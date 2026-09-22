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
if 'WFGG_RADAR_MAIL_CAMPAIGN_AUTOQUEUE_WORKER_V627' not in worker:
    anchor = '      // WFGG_RADAR_INTERNAL_MAIL_OUTBOX_ROUTE_V626\n'
    route = r'''      // WFGG_RADAR_MAIL_CAMPAIGN_AUTOQUEUE_WORKER_V627
      if (url.pathname === '/api/radar/mail/campaign/queue' && request.method === 'POST') {
        const session = await requireSession(request, env);
        assertCapability(session.role, 'radar.search');
        const input = await bodyJson(request);
        const campaignId = String(input.campaignId || '').trim();
        const title = String(input.title || '');
        const contents = String(input.contents || '');
        const targets = Array.isArray(input.targets) ? input.targets : [];
        const enc = new TextEncoder();
        if (!campaignId || campaignId.length > 128) throw Object.assign(new Error('MAIL_CAMPAIGN_ID_INVALID_V627'), { status: 400 });
        if (!title.trim() || enc.encode(title).length > 50) throw Object.assign(new Error('MAIL_TITLE_INVALID_V627'), { status: 400 });
        if (!contents.trim() || enc.encode(contents).length > 2000) throw Object.assign(new Error('MAIL_CONTENT_INVALID_V627'), { status: 400 });
        if (targets.length < 1 || targets.length > 25) throw Object.assign(new Error('MAIL_CAMPAIGN_TARGET_COUNT_INVALID_V627'), { status: 400 });

        const seen = new Set();
        const normalized = targets.map(item => {
          const targetUid = String(item?.targetUid || '').trim();
          const targetName = String(item?.targetName || '').trim();
          if (!/^\d{6,64}$/.test(targetUid)) throw Object.assign(new Error('MAIL_TARGET_UID_INVALID_V627'), { status: 400 });
          if (!targetName || enc.encode(targetName).length > 256) throw Object.assign(new Error('MAIL_TARGET_NAME_INVALID_V627'), { status: 400 });
          if (seen.has(targetUid)) throw Object.assign(new Error('MAIL_CAMPAIGN_DUPLICATE_TARGET_V627'), { status: 400 });
          seen.add(targetUid);
          return { targetUid, targetName };
        });

        const queued = await mailerRequestV626(env, '/v1/outbox/queue-batch', {
          campaignId, title, contents, targets: normalized
        });
        if (queued?.lastwarWrite !== false || queued?.lastwarMutation !== false || queued?.mailSendExecuted !== false) {
          throw Object.assign(new Error('MAIL_CAMPAIGN_DRY_RUN_INVARIANT_V627'), { status: 502 });
        }
        await audit(env, session.gameUid, 'radar.mail.campaign.queue', campaignId, {
          targetCount: normalized.length,
          queued: Number(queued?.queued || 0),
          duplicates: Number(queued?.duplicates || 0),
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
    worker = replace_once(worker, anchor, route + anchor, 'V627 worker route')

WORKER.write_text(worker, encoding='utf-8')

ui = UI.read_text(encoding='utf-8')
if 'WFGG_RADAR_MAIL_CAMPAIGN_AUTOQUEUE_UI_V627' not in ui:
    css = r'''
/* WFGG_RADAR_MAIL_CAMPAIGN_AUTOQUEUE_UI_V627 */
.mail-v627-campaign{border:1px solid #496c8b;background:#0e1b25;color:#b9ddff;border-radius:9px;padding:8px 10px;font:900 9px ui-monospace,monospace}
.mail-v627-campaign:disabled{opacity:.4}
.mail-v627-targets{font:10px ui-monospace,monospace;color:#a9bd99;border:1px solid #34472c;background:#091108;border-radius:10px;padding:9px;margin:8px 0}
'''
    ui = replace_once(ui, '</style>', css + '\n</style>', 'V627 UI css')

    js_anchor = 'async function health(){'
    js = r'''/* WFGG_RADAR_MAIL_CAMPAIGN_AUTOQUEUE_UI_V627 */
let mailCampaignPlayersV627=[];
const mailCampaignEncoderV627=new TextEncoder();
function updateMailCampaignButtonV627(){
  const b=$('mailCampaignV627');
  if(!b)return;
  const n=Math.min(mailCampaignPlayersV627.length,25);
  b.disabled=n<1;
  b.textContent=n?'CAMPAGNE OUTBOX · '+n:'CAMPAGNE OUTBOX';
}
function validateMailCampaignV627(){
  const id=$('mailV627CampaignId'),title=$('mailV627Title'),content=$('mailV627Content'),go=$('mailV627Queue');
  if(!id||!title||!content||!go)return false;
  const tb=mailCampaignEncoderV627.encode(title.value).length;
  const cb=mailCampaignEncoderV627.encode(content.value).length;
  $('mailV627TitleCount').textContent=tb+'/50 octets';
  $('mailV627ContentCount').textContent=cb+'/2000 octets';
  const count=Math.min(mailCampaignPlayersV627.length,25);
  const ok=Boolean(id.value.trim())&&id.value.trim().length<=128&&tb>0&&tb<=50&&cb>0&&cb<=2000&&count>0;
  go.disabled=!ok;
  return ok;
}
function openMailCampaignV627(){
  const count=Math.min(mailCampaignPlayersV627.length,25);
  if(!count)return;
  $('mailV627Targets').textContent=count+' joueur(s) seront ajoutés à l’Outbox · maximum 25 par lot.';
  $('mailV627Status').textContent='DRY-RUN : la campagne prépare les brouillons mais ne transmet rien à Last War.';
  $('mailV627Overlay').classList.add('show');
  $('mailV627Overlay').setAttribute('aria-hidden','false');
  validateMailCampaignV627();
}
function closeMailCampaignV627(){
  $('mailV627Overlay')?.classList.remove('show');
  $('mailV627Overlay')?.setAttribute('aria-hidden','true');
}
async function queueMailCampaignV627(){
  if(!validateMailCampaignV627())return;
  const button=$('mailV627Queue');button.disabled=true;
  const targets=mailCampaignPlayersV627.slice(0,25).map(p=>({
    targetUid:String(p?.gameUid||p?.game_uid||'').trim(),
    targetName:String(p?.pseudo||p?.name||'').trim()
  })).filter(x=>/^\d{6,64}$/.test(x.targetUid)&&x.targetName);
  $('mailV627Status').textContent='Préparation de '+targets.length+' brouillon(s)…';
  try{
    const d=await api('/api/radar/mail/campaign/queue',{
      method:'POST',
      headers:{'content-type':'application/json'},
      body:JSON.stringify({
        campaignId:$('mailV627CampaignId').value.trim(),
        title:$('mailV627Title').value,
        contents:$('mailV627Content').value,
        targets
      })
    });
    if(d?.lastwarMutation!==false||d?.mailSendExecuted!==false)throw new Error('MAIL_CAMPAIGN_DRY_RUN_INVARIANT_V627');
    $('mailV627Status').textContent='Outbox : '+Number(d?.queued||0)+' ajouté(s) · '+Number(d?.duplicates||0)+' doublon(s) ignoré(s) · aucun envoi Last War.';
    setStatus('CAMPAGNE EN OUTBOX',Number(d?.queued||0)+' nouveau(x) brouillon(s)','ok');
  }catch(err){
    $('mailV627Status').textContent='Campagne impossible : '+String(err?.message||err);
    setStatus('CAMPAGNE OUTBOX IMPOSSIBLE',String(err?.message||err),'error');
  }finally{
    validateMailCampaignV627();
  }
}
function setupMailCampaignV627(){
  if($('mailCampaignV627'))return;
  const close=$('intelClose');
  if(!close)return;
  const b=document.createElement('button');
  b.id='mailCampaignV627';b.type='button';b.className='mail-v627-campaign';b.textContent='CAMPAGNE OUTBOX';b.disabled=true;
  b.addEventListener('click',openMailCampaignV627);
  close.insertAdjacentElement('beforebegin',b);
  document.body.insertAdjacentHTML('beforeend','<div id="mailV627Overlay" class="mail-v626-overlay" aria-hidden="true"><div class="mail-v626-modal" role="dialog" aria-modal="true" aria-labelledby="mailV627Heading"><div class="mail-v626-head"><div id="mailV627Heading" class="mail-v626-title">CAMPAGNE RECRUTEMENT · OUTBOX DRY-RUN</div><button id="mailV627Close" class="mail-v626-close" type="button">FERMER</button></div><div id="mailV627Targets" class="mail-v627-targets">—</div><div class="mail-v626-safe">🔒 Préparation automatique uniquement. Aucun brouillon de cette campagne ne peut être envoyé à Last War en V6.27.</div><div class="mail-v626-field"><label>ID CAMPAGNE</label><input id="mailV627CampaignId" value="recruitment-v627" autocomplete="off"></div><div class="mail-v626-field"><label>TITRE</label><input id="mailV627Title" autocomplete="off" placeholder="Titre commun"><div id="mailV627TitleCount" class="mail-v626-count">0/50 octets</div></div><div class="mail-v626-field"><label>CONTENU</label><textarea id="mailV627Content" placeholder="Message commun aux joueurs sélectionnés"></textarea><div id="mailV627ContentCount" class="mail-v626-count">0/2000 octets</div></div><button id="mailV627Queue" class="mail-v626-queue" type="button" disabled>PRÉPARER LA CAMPAGNE DANS L’OUTBOX</button><div id="mailV627Status" class="mail-v626-status"></div></div></div>');
  $('mailV627Close').addEventListener('click',closeMailCampaignV627);
  $('mailV627Overlay').addEventListener('click',e=>{if(e.target===$('mailV627Overlay'))closeMailCampaignV627()});
  for(const id of ['mailV627CampaignId','mailV627Title','mailV627Content'])$(id).addEventListener('input',validateMailCampaignV627);
  $('mailV627Queue').addEventListener('click',queueMailCampaignV627);
  updateMailCampaignButtonV627();
}
queueMicrotask(setupMailCampaignV627);

'''
    ui = replace_once(ui, js_anchor, js + js_anchor, 'V627 UI JS')

    old = "const players=Array.isArray(d&&d.players)?d.players:[],alls=Array.isArray(d&&d.alliances)?d.alliances:[],alliance=alls.length===1?alls[0]:null;"
    new = "const players=Array.isArray(d&&d.players)?d.players:[];mailCampaignPlayersV627=players.slice(0,25);updateMailCampaignButtonV627();const alls=Array.isArray(d&&d.alliances)?d.alliances:[],alliance=alls.length===1?alls[0]:null;"
    ui = replace_once(ui, old, new, 'V627 intelligence results hook')

UI.write_text(ui, encoding='utf-8')

print('RADAR_V627_MAIL_CAMPAIGN_AUTOQUEUE=READY')
print('RADAR_V627_MAX_TARGETS=25')
print('RADAR_V627_LASTWAR_WRITE=DISABLED')
print('RADAR_V627_MAIL_SEND_EXECUTED=NO')
