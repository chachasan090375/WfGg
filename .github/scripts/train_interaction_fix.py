from pathlib import Path

p = Path('frontend/_worker.js')
s = p.read_text(encoding='utf-8')
original = s

old = """    const hideLegacyEntry=()=>{
      document.getElementById('loginView')?.classList.add('hidden');
      document.getElementById('portalView')?.classList.add('hidden');
    };
"""
new = """    const hideLegacyEntry=()=>{
      document.getElementById('loginView')?.classList.add('hidden');
      document.getElementById('portalView')?.classList.add('hidden');
    };

    /* WFGG_PORTAL_TRAIN_SESSION_SWITCH_V1
       Dans le Train intégré, l'ancien bouton d'installation devient le bouton
       explicite de changement de session. Le clic est intercepté en capture
       avant le handler historique d'installation.
    */
    const prepareSessionSwitch=()=>{
      const button=document.getElementById('installBtn');
      if(!button)return;
      const labels={
        fr:'Changer de session',
        it:'Cambia sessione',
        en:'Switch session',
        es:'Cambiar de sesión'
      };
      const current=norm(localStorage.getItem(PORTAL_LANG))||'fr';
      const label=labels[current]||labels.fr;
      button.textContent='🚪';
      button.title=label;
      button.setAttribute('aria-label',label);
      button.dataset.wfggSessionSwitch='1';
    };
"""
if 'WFGG_PORTAL_TRAIN_SESSION_SWITCH_V1' not in s:
    if old not in s:
        raise SystemExit('missing hideLegacyEntry anchor')
    s = s.replace(old, new, 1)

old_selector = "const target=event.target.closest('#brandHome,#logoutBtn,#loginPortalBack');"
new_selector = "const target=event.target.closest('#brandHome,#logoutBtn,#loginPortalBack,#installBtn');"
if old_selector in s:
    s = s.replace(old_selector, new_selector, 1)
elif new_selector not in s:
    raise SystemExit('missing nav guard selector')

old_logout = """      if(localStorage.getItem(TRAIN_TOKEN)===TRAIN_BRIDGE_SENTINEL){
        localStorage.removeItem(TRAIN_TOKEN);
      }
      globalPortal();
"""
new_logout = """      const isSessionSwitch=target.id==='installBtn'||target.id==='logoutBtn';
      if(localStorage.getItem(TRAIN_TOKEN)===TRAIN_BRIDGE_SENTINEL){
        localStorage.removeItem(TRAIN_TOKEN);
      }
      if(isSessionSwitch){
        localStorage.removeItem(PORTAL_TOKEN);
      }
      globalPortal();
"""
if "const isSessionSwitch=target.id==='installBtn'" not in s:
    if old_logout not in s:
        raise SystemExit('missing nav guard logout block')
    s = s.replace(old_logout, new_logout, 1)

old_gate = """    gate();
    hideLegacyEntry();
"""
new_gate = """    gate();
    hideLegacyEntry();
    prepareSessionSwitch();
"""
if 'prepareSessionSwitch();' not in s:
    if old_gate not in s:
        raise SystemExit('missing gate anchor')
    s = s.replace(old_gate, new_gate, 1)

anchor = """    /* WFGG_TRAIN_INIT_LIFECYCLE_FIX_V1
       Le frontend Train attache historiquement init() uniquement à
       DOMContentLoaded. Quand app.js est servi/rechargé tardivement par le
       bridge du Portail, cet événement peut déjà avoir eu lieu : bootApp()
       affiche alors l'écran mais aucun onclick de navigation n'est branché.
       On garde le comportement historique pendant le chargement du DOM et on
       lance init() immédiatement lorsque le DOM est déjà prêt.
    */
"""
if anchor not in s:
    raise SystemExit('missing lifecycle anchor')

dom_guard = """    /* WFGG_TRAIN_INIT_DOM_GUARD_V1
       Le HTML portal-only-auth ne contient plus loginBtn ni loginPortalBack,
       alors que l'ancien init() les déréférence sans contrôle. Le premier
       getElementById(...).onclick lançait donc une exception avant le câblage
       des .nav-btn. On rend uniquement ces deux liaisons optionnelles.
    */
    rewritten = rewritten.replace(
      \"        document.getElementById('loginBtn').onclick = login;\",
      \"        { const el = document.getElementById('loginBtn'); if (el) el.onclick = login; }\"
    );
    rewritten = rewritten.replace(
      \"        document.getElementById('loginPortalBack').onclick = showPortal;\",
      \"        { const el = document.getElementById('loginPortalBack'); if (el) el.onclick = showPortal; }\"
    );

"""
if 'WFGG_TRAIN_INIT_DOM_GUARD_V1' not in s:
    s = s.replace(anchor, dom_guard + anchor, 1)

if s == original:
    print('INTERACTION_PATCH=ALREADY_APPLIED')
else:
    p.write_text(s, encoding='utf-8')
    print('INTERACTION_PATCH=OK')
