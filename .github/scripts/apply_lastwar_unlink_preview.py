#!/usr/bin/env python3
from pathlib import Path

worker = Path('worker-staging/overrides/lastwar-identity.js')
text = worker.read_text(encoding='utf-8')
marker = "  if (url.pathname === '/api/lastwar/identity/resolve') {"
if "'/api/lastwar/identity/unlink'" not in text:
    block = """  if (url.pathname === '/api/lastwar/identity/unlink') {
    const ts = now();
    await ensureStateTable(env);
    try {
      await env.DB.batch([
        env.DB.prepare('DELETE FROM lastwar_snapshots WHERE user_id=?').bind(ctx.id),
        env.DB.prepare('UPDATE lastwar_devices SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL').bind(ts, ctx.id),
        env.DB.prepare('DELETE FROM lastwar_cloud_state WHERE user_id=?').bind(ctx.id)
      ]);
    } catch (err) {
      console.error('lastwar unlink persistence failed', err?.message || err);
      fail('LASTWAR_UNLINK_FAILED', 500);
    }
    await audit(env, ctx.id, 'LASTWAR_ACCOUNT_UNLINKED', 'lastwar_account', ctx.id, {
      broker_contacted: false,
      state_purged: true
    });
    return json({ ok: true, connected: false, unlinked_at: ts });
  }

"""
    if marker not in text:
        raise SystemExit('Worker resolve marker not found')
    text = text.replace(marker, block + marker, 1)
    worker.write_text(text, encoding='utf-8')

ui = Path('frontend/lastwar-connect-v2.js')
text = ui.read_text(encoding='utf-8')
old = "async function unlinkLocal(){setMessage(t('notReady'))}"
new = """async function unlinkLocal(){
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
}"""
if old in text:
    text = text.replace(old, new, 1)
elif "'/api/lastwar/identity/unlink'" not in text:
    raise SystemExit('Frontend unlink placeholder not found')
ui.write_text(text, encoding='utf-8')

index = Path('frontend/index.html')
text = index.read_text(encoding='utf-8')
old_sig = 'lastwar-connect-v2.js?v=013-container-direct'
new_sig = 'lastwar-connect-v2.js?v=014-real-unlink'
if old_sig in text:
    text = text.replace(old_sig, new_sig, 1)
elif new_sig not in text:
    raise SystemExit('Frontend cache signature not found')
index.write_text(text, encoding='utf-8')

print('Last War unlink preview patch applied')
