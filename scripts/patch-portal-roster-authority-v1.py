from pathlib import Path


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'anchor missing: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'anchor not unique: {label} count={text.count(old)}')
    return text.replace(old, new, 1)

# --- worker/src/core.js -----------------------------------------------------
p = Path('worker/src/core.js')
s = p.read_text()

s = replace_once(s,
"""      } else if (url.pathname === '/api/train/context' && request.method === 'GET') {
        response = await trainContext(request, env);""",
"""      } else if (url.pathname === '/api/alliance/roster' && request.method === 'GET') {
        response = await trainContext(request, env);
      } else if (url.pathname === '/api/train/context' && request.method === 'GET') {
        response = await trainContext(request, env);""",
'alliance roster route')

s = replace_once(s,
"""      } else if (/^\\/api\\/admin\\/members\\/[^/]+$/.test(url.pathname) && request.method === 'PATCH') {
        response = await updateMember(request, env, decodeURIComponent(url.pathname.split('/').pop()));
      } else if (/^\\/api\\/admin\\/members\\/[^/]+\\/code$/.test(url.pathname) && request.method === 'POST') {""",
"""      } else if (/^\\/api\\/admin\\/members\\/[^/]+$/.test(url.pathname) && request.method === 'PATCH') {
        response = await updateMember(request, env, decodeURIComponent(url.pathname.split('/').pop()));
      } else if (/^\\/api\\/admin\\/members\\/[^/]+$/.test(url.pathname) && request.method === 'DELETE') {
        response = await removeMember(request, env, decodeURIComponent(url.pathname.split('/').pop()));
      } else if (/^\\/api\\/admin\\/members\\/[^/]+\\/code$/.test(url.pathname) && request.method === 'POST') {""",
'member delete route')

s = replace_once(s,
"""    SELECT
      u.id,
      u.player_name,""",
"""    SELECT
      u.id,
      u.created_at,
      u.player_name,""",
'roster created_at select')

s = replace_once(s,
"""    ok: true,
    source: 'wfgg-portal',
    me: {""",
"""    ok: true,
    source: 'wfgg-portal-roster-v1',
    authority: 'portal',
    roster_authoritative: true,
    me: {""",
'roster source marker')

s = replace_once(s,
"""      id: row.id,
      pseudo: row.display_name || row.player_name,""",
"""      id: row.id,
      created_at: row.created_at || null,
      pseudo: row.display_name || row.player_name,""",
'roster created_at output')

remove_member = r'''
async function removeMember(request, env, userId) {
  const ctx = await sessionContext(request, env);
  requireAllianceAdmin(ctx);

  const target = await getTargetMembership(env, ctx.alliance_id, userId);
  if (!target) fail('MEMBER_NOT_FOUND', 404);
  if (userId === ctx.id) fail('CANNOT_REMOVE_SELF', 409);
  if (target.rank === 'R5') fail('TRANSFER_R5_BEFORE_REMOVE', 409);
  if (target.system_role === SYSTEM_OWNER) fail('OWNER_CANNOT_BE_REMOVED', 409);
  if (target.rank === 'R4') requireR5OrOwner(ctx);

  const ts = now();
  await env.DB.batch([
    env.DB.prepare('UPDATE users SET active=0,updated_at=? WHERE id=?').bind(ts, userId),
    env.DB.prepare('DELETE FROM sessions WHERE user_id=?').bind(userId),
    env.DB.prepare('DELETE FROM system_roles WHERE user_id=?').bind(userId),
    env.DB.prepare('DELETE FROM memberships WHERE user_id=? AND alliance_id=?').bind(userId, ctx.alliance_id)
  ]);

  await audit(env, ctx.id, 'MEMBER_DEPARTURE', 'user', userId, {
    previous_rank: target.rank,
    previous_officer_title: target.officer_title || null,
    access_revoked: true,
    membership_removed: true
  });

  return json({
    ok: true,
    removed: true,
    access_revoked: true,
    history_preserved: true
  });
}

'''
s = replace_once(s, 'async function transferLeadership(request, env) {', remove_member + 'async function transferLeadership(request, env) {', 'remove member function')

p.write_text(s)

# --- worker/src/index.js ----------------------------------------------------
p = Path('worker/src/index.js')
s = p.read_text()

s = replace_once(s,
"""const SENTINEL_VERSION = 'sentinel-owner-v1';
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };""",
"""const SENTINEL_VERSION = 'sentinel-owner-v1';
const JSON_HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };
const TRAIN_API = 'https://wfgg-train.chachasan090375.workers.dev';""",
'index train api')

s = replace_once(s,
"""    if (url.pathname === '/api/sentinel/run' && request.method === 'GET') {
      return sentinelRun(request, env, executionContext);
    }
    return core.fetch(request, env, executionContext);""",
"""    if (url.pathname === '/api/sentinel/run' && request.method === 'GET') {
      return sentinelRun(request, env, executionContext);
    }
    const response = await core.fetch(request, env, executionContext);
    if (response.ok && shouldSyncTrainRoster(url.pathname, request.method)) {
      const task = notifyTrainRosterSync(request).catch((error) => {
        console.warn('WFGG_PORTAL_ROSTER_SYNC_NOTIFY', String(error?.message || error));
      });
      if (executionContext?.waitUntil) executionContext.waitUntil(task);
    }
    return response;""",
'index core wrapper')

helper = r'''
function shouldSyncTrainRoster(pathname, method) {
  if (pathname === '/api/admin/members' && (method === 'GET' || method === 'POST')) return true;
  if (/^\/api\/admin\/members\/[^/]+$/.test(pathname) && (method === 'PATCH' || method === 'DELETE')) return true;
  if (pathname === '/api/admin/leadership/transfer' && method === 'POST') return true;
  return false;
}

async function notifyTrainRosterSync(request) {
  const token = bearerToken(request);
  if (!token) return null;
  const response = await fetch(`${TRAIN_API}/api/portal-roster/sync`, {
    method: 'POST',
    headers: {
      'X-WfGg-Portal-Token': token,
      'Cache-Control': 'no-store'
    },
    redirect: 'manual'
  });
  if (!response.ok) {
    let detail = '';
    try { detail = await response.text(); } catch (_) {}
    throw new Error(`TRAIN_ROSTER_SYNC_${response.status}${detail ? ':' + detail.slice(0, 180) : ''}`);
  }
  return response;
}

'''
s = replace_once(s, 'function severityRank(level) {', helper + 'function severityRank(level) {', 'index sync helpers')
p.write_text(s)

# --- frontend/portal-v070.js -----------------------------------------------
p = Path('frontend/portal-v070.js')
s = p.read_text()

repls = {
"Code invalide ou compte désactivé.": "Accès réservé aux membres de l’Alliance WfGg. Si vous venez de rejoindre WfGg et n’avez pas encore reçu votre accès, contactez un R4/R5.",
"Codice non valido o account disattivato.": "Accesso riservato ai membri dell’alleanza WfGg. Se sei appena entrato in WfGg e non hai ancora ricevuto l’accesso, contatta un R4/R5.",
"Invalid code or disabled account.": "Access is reserved for WfGg Alliance members. If you have just joined WfGg and have not received your access yet, contact an R4/R5.",
"Código no válido o cuenta desactivada.": "Acceso reservado a los miembros de la Alianza WfGg. Si acabas de unirte a WfGg y aún no has recibido tu acceso, contacta con un R4/R5."
}
for old,new in repls.items():
    if old not in s:
        raise SystemExit(f'auth message missing: {old}')
    s = s.replace(old,new)

old_api = "async function api(path,options={}){const h=new Headers(options.headers||{});if(token())h.set('Authorization',`Bearer ${token()}`);if(options.body&&!(options.body instanceof FormData)&&!h.has('Content-Type'))h.set('Content-Type','application/json');const r=await fetch(`${cfg.API_BASE}${path}`,{...options,headers:h,cache:'no-store'});let d=null;try{d=await r.json()}catch{}if(r.status===401){clearSession();showAuth();throw new Error('UNAUTHORIZED')}if(!r.ok)throw new Error(d?.error||`HTTP_${r.status}`);return d}"
new_api = "async function api(path,options={}){const h=new Headers(options.headers||{}),hadSession=!!token();if(token())h.set('Authorization',`Bearer ${token()}`);if(options.body&&!(options.body instanceof FormData)&&!h.has('Content-Type'))h.set('Content-Type','application/json');const r=await fetch(`${cfg.API_BASE}${path}`,{...options,headers:h,cache:'no-store'});let d=null;try{d=await r.json()}catch{}if(r.status===401){clearSession();showAuth();if(hadSession&&$('authError')){$('authError').textContent=t('auth.bad');$('authError').classList.remove('hidden')}throw new Error('UNAUTHORIZED')}if(!r.ok)throw new Error(d?.error||`HTTP_${r.status}`);return d}"
s = replace_once(s, old_api, new_api, 'portal api 401')

s = replace_once(s,
"if(x==='toggle-member')return toggleMember(a.dataset.id);if(x==='close-modal')",
"if(x==='toggle-member')return toggleMember(a.dataset.id);if(x==='remove-member')return confirmRemoveMember(a.dataset.id);if(x==='confirm-remove-member')return removeMember(a.dataset.id);if(x==='close-modal')",
'member click handlers')

needle = "${m.rank==='R4'?`<button class=\"secondary-button\" type=\"button\" data-action=\"transfer-r5\" data-id=\"${esc(m.id)}\">♛ Nommer R5</button>`:''}<button class=\"secondary-button\" type=\"button\" data-action=\"close-modal\">Fermer</button>"
replacement = "${m.rank==='R4'?`<button class=\"secondary-button\" type=\"button\" data-action=\"transfer-r5\" data-id=\"${esc(m.id)}\">♛ Nommer R5</button>`:''}${toggleAllowed(m)?`<button class=\"secondary-button\" style=\"border-color:#a33;color:#d66\" type=\"button\" data-action=\"remove-member\" data-id=\"${esc(m.id)}\">🚪 Retirer de l’Alliance</button>`:''}<button class=\"secondary-button\" type=\"button\" data-action=\"close-modal\">Fermer</button>"
s = replace_once(s, needle, replacement, 'remove member button')

member_funcs = r'''
function confirmRemoveMember(id){const m=state.members.find(x=>x.id===id);if(!m||!toggleAllowed(m))return;openModal(`<p class="eyebrow">Départ de l’Alliance</p><h3>🚪 Retirer ${esc(m.display_name||m.player_name)} de WfGg ?</h3><div class="warning">Cette action est différente de « Désactiver » : le joueur ne fera plus partie de l’Alliance et son accès au Portail sera révoqué immédiatement.</div><p class="muted">Son historique Train est conservé. Train le retirera automatiquement des rotations futures, de la Bourse et des rappels lors de la synchronisation du roster central.</p><div id="memberModalMessage" class="hidden"></div><div class="modal-actions"><button class="primary-button" style="background:#7a2020" type="button" data-action="confirm-remove-member" data-id="${esc(id)}">Confirmer le départ</button><button class="secondary-button" type="button" data-action="close-modal">Annuler</button></div>`)}
async function removeMember(id){try{await api(`/api/admin/members/${encodeURIComponent(id)}`,{method:'DELETE'});await loadMembers();closeModal()}catch(e){showMessage('memberModalMessage',e.message,true)}}
'''
s = replace_once(s, 'async function resetMemberCode(id){', member_funcs + 'async function resetMemberCode(id){', 'remove member functions')

s = s.replace("<p class=\"muted\">Copiez ce code avant de fermer.</p>", "<p class=\"muted\">Copiez ce code avant de fermer. Ce joueur est désormais enregistré dans le roster central du Portail ; Train et les futurs modules l’utiliseront automatiquement.</p>")

p.write_text(s)

print('portal roster authority patch applied')
