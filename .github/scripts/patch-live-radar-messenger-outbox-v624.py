#!/usr/bin/env python3
from pathlib import Path
import re

P=Path('/tmp/wfgg-radar/public/live-radar.html')
h=P.read_text(encoding='utf-8')
marker='WFGG_RADAR_MESSENGER_OUTBOX_UI_V624'
if marker not in h:
    css=r'''
/* WFGG_RADAR_MESSENGER_OUTBOX_UI_V624 */
.profile-actions{grid-template-columns:1fr 1fr}.message-player{width:100%;min-height:40px;border:1px solid #4c8d73;border-radius:10px;background:#10251d;color:#a8ffe0;font:900 10px ui-monospace,monospace;letter-spacing:.05em}.message-player:disabled{opacity:.45}.mail-composer{display:none;margin:0 13px 12px;padding:12px;border:1px solid #386854;border-radius:12px;background:#08130f}.mail-composer.show{display:block}.mail-compose-title{font-size:11px;font-weight:900;color:#baffdf;margin-bottom:9px}.mail-input,.mail-textarea{width:100%;border:1px solid #355848;background:#070d0a;color:#eafff3;border-radius:9px;padding:10px;font:12px ui-monospace,monospace;outline:none}.mail-textarea{min-height:120px;resize:vertical;margin-top:8px}.mail-counts{display:flex;justify-content:space-between;gap:8px;margin:6px 2px 9px;color:#789889;font-size:9px}.mail-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.mail-action{min-height:38px;border-radius:9px;border:1px solid #527b68;background:#183126;color:#cffff0;font:900 9px ui-monospace,monospace}.mail-action.secondary{background:#151b17;color:#a8b9b0;border-color:#405047}.mail-compose-note{margin-top:8px;color:#79988a;font-size:9px;line-height:1.35}.mail-compose-note.ok{color:#a8ffba}.mail-compose-note.error{color:#ff9b89}
'''
    h=h.replace('</style>',css+'\n</style>',1)

    pat=re.compile(r'(<div class="profile-actions">)(.*?id="refreshProfile".*?</button>)(</div>)',re.S)
    m=pat.search(h)
    if not m:
        raise SystemExit('V624_UI_PROFILE_ACTIONS_ANCHOR_MISSING')
    replacement=m.group(1)+m.group(2)+'<button id="messagePlayer" class="message-player" type="button" disabled>✉ MESSAGE</button>'+m.group(3)
    h=h[:m.start()]+replacement+h[m.end():]

    note_idx=h.find('<div id="profileNote"')
    if note_idx<0: raise SystemExit('V624_UI_PROFILE_NOTE_MISSING')
    close=h.find('</section>',note_idx)
    if close<0: raise SystemExit('V624_UI_RESULT_SECTION_END_MISSING')
    composer=r'''
      <div id="mailComposer" class="mail-composer">
        <div id="mailComposeTitle" class="mail-compose-title">✉ MESSAGE INTERNE · —</div>
        <input id="mailTitle" class="mail-input" maxlength="50" placeholder="Titre du message">
        <textarea id="mailContents" class="mail-textarea" maxlength="2000" placeholder="Message"></textarea>
        <div class="mail-counts"><span id="mailTitleCount">0/50 octets</span><span id="mailContentsCount">0/2000 octets</span></div>
        <div class="mail-actions">
          <button id="mailQueue" class="mail-action" type="button">METTRE EN FILE</button>
          <button id="mailClose" class="mail-action secondary" type="button">FERMER</button>
        </div>
        <div id="mailComposeNote" class="mail-compose-note">DRY-RUN V6.24 · aucun message n’est envoyé à Last War.</div>
      </div>
'''
    h=h[:close]+composer+h[close:]

    refresh="$('refreshProfile').disabled=!currentProfileUID;"
    if refresh not in h: raise SystemExit('V624_UI_SHOW_PLAYER_REFRESH_ANCHOR_MISSING')
    h=h.replace(refresh,refresh+"$('messagePlayer').disabled=!currentProfileUID;",1)

    listener="$('refreshProfile').addEventListener('click',refreshCurrentProfile);"
    if listener not in h: raise SystemExit('V624_UI_LISTENER_ANCHOR_MISSING')
    js=r'''
const V624_ENCODER=new TextEncoder();
function v624Bytes(value){return V624_ENCODER.encode(String(value||'')).length}
function v624UpdateMailCounts(){const tb=v624Bytes($('mailTitle').value),cb=v624Bytes($('mailContents').value);$('mailTitleCount').textContent=`${tb}/50 octets`;$('mailContentsCount').textContent=`${cb}/2000 octets`;return tb<=50&&cb<=2000}
function v624OpenComposer(){const uid=String(currentProfileUID||'').trim();if(!uid)return;const name=$('rname').textContent||'—';$('mailComposeTitle').textContent='✉ MESSAGE INTERNE · '+name;$('mailComposer').classList.add('show');$('mailComposeNote').textContent='DRY-RUN V6.24 · aucun message n’est envoyé à Last War.';$('mailComposeNote').className='mail-compose-note';v624UpdateMailCounts();$('mailTitle').focus()}
function v624CloseComposer(){$('mailComposer').classList.remove('show')}
async function v624QueueMessage(){const targetUid=String(currentProfileUID||'').trim(),targetName=String($('rname').textContent||'').trim(),targetServer=Number(String($('rserver').textContent||'').replace(/[^0-9-]/g,''))||0,title=$('mailTitle').value,contents=$('mailContents').value;if(!targetUid||!targetName||!title.trim()||!contents.trim()){$('mailComposeNote').textContent='Destinataire, titre et message sont obligatoires.';$('mailComposeNote').className='mail-compose-note error';return}if(!v624UpdateMailCounts()){$('mailComposeNote').textContent='Limite dépassée : titre 50 octets, message 2000 octets.';$('mailComposeNote').className='mail-compose-note error';return}const b=$('mailQueue');b.disabled=true;$('mailComposeNote').textContent='Création du brouillon et mise en file…';try{const d=await api('/api/radar/messenger/outbox',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({targetName,targetUid,targetServer,title,contents,queue:true})});const id=String(d?.created?.outbox?.record?.id||'');const state=String(d?.queued?.outbox?.state||d?.created?.outbox?.record?.state||'QUEUED');$('mailComposeNote').textContent=`${state} · ${id||'ID local'} · aucun envoi Last War`;$('mailComposeNote').className='mail-compose-note ok';setStatus('MESSAGE MIS EN FILE',targetName+' · DRY-RUN','ok')}catch(err){$('mailComposeNote').textContent='Outbox : '+String(err.message||err);$('mailComposeNote').className='mail-compose-note error'}finally{b.disabled=false}}
$('messagePlayer').addEventListener('click',v624OpenComposer);
$('mailClose').addEventListener('click',v624CloseComposer);
$('mailQueue').addEventListener('click',v624QueueMessage);
$('mailTitle').addEventListener('input',v624UpdateMailCounts);
$('mailContents').addEventListener('input',v624UpdateMailCounts);
'''
    h=h.replace(listener,js+'\n'+listener,1)

P.write_text(h,encoding='utf-8')
print('RADAR_V624_MESSENGER_OUTBOX_UI=READY')
print('RADAR_V624_UI_SEND_BUTTON=NO')
print('RADAR_V624_LASTWAR_MUTATION=NO')
