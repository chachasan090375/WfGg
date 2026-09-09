import fs from 'node:fs';

function patchFile(path, patches) {
  let source = fs.readFileSync(path, 'utf8');
  for (const [from, to, label] of patches) {
    if (!source.includes(from)) {
      throw new Error(`PATCH_MISSING ${path} :: ${label}`);
    }
    source = source.replace(from, to);
  }
  fs.writeFileSync(path, source);
}

patchFile('frontend/train-native/sentinel-train-v1.js', [
  ["const VERSION = 'sentinel-train-v5';", "const VERSION = 'sentinel-train-v7';", 'sentinel version'],
  ["let ownerConfirmed = false;", "let accessConfirmed = false;\n  let accessRole = '';\n  let launchLocked = false;", 'access state'],
  ["ownerOnly: 'Accès OWNER uniquement.'", "ownerOnly: 'Accès OWNER ou SUPERVISEUR uniquement.'", 'fr access text'],
  ["ownerOnly: 'OWNER access only.'", "ownerOnly: 'OWNER or SUPERVISOR access only.'", 'en access text'],
  ["ownerOnly: 'Accesso solo OWNER.'", "ownerOnly: 'Accesso solo OWNER o SUPERVISOR.'", 'it access text'],
  ["ownerOnly: 'Acceso solo OWNER.'", "ownerOnly: 'Acceso solo OWNER o SUPERVISOR.'", 'es access text'],
  [
`  async function confirmOwner() {
    if (!token()) return false;
    try {
      const { response, data } = await portalFetch('/api/me');
      ownerConfirmed = response.ok && data?.system?.role === 'OWNER';
      return ownerConfirmed;
    } catch (_) {
      ownerConfirmed = false;
      return false;
    }
  }`,
`  async function confirmAccess() {
    if (!token()) return false;
    try {
      const { response, data } = await portalFetch('/api/me');
      accessRole = String(data?.system?.role || '');
      accessConfirmed = response.ok && ['OWNER', 'SUPERVISOR'].includes(accessRole);
      return accessConfirmed;
    } catch (_) {
      accessRole = '';
      accessConfirmed = false;
      return false;
    }
  }`,
    'access confirmation'
  ],
  [
`  function injectButton() {
    if (!ownerConfirmed) return false;`,
`  async function launchFromEvent(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    event?.stopImmediatePropagation?.();
    if (launchLocked) return;
    launchLocked = true;
    try {
      await openPopup();
    } finally {
      setTimeout(() => { launchLocked = false; }, 350);
    }
  }

  function installLaunchCapture() {
    if (window.__WFGG_SENTINEL_LAUNCH_CAPTURE_V7__) return;
    window.__WFGG_SENTINEL_LAUNCH_CAPTURE_V7__ = true;
    const handler = (event) => {
      if (event?.target?.closest?.('#' + BUTTON_ID)) launchFromEvent(event);
    };
    document.addEventListener('pointerup', handler, true);
    document.addEventListener('click', handler, true);
  }

  function injectButton() {
    if (!accessConfirmed) return false;`,
    'android launch capture'
  ],
  [
"      button.addEventListener('click', (event) => { event.preventDefault(); event.stopPropagation(); openPopup(); });",
"      button.addEventListener('click', launchFromEvent, true);",
    'button launch listener'
  ],
  [
"    if (!ownerConfirmed && !(await confirmOwner())) return;",
"    if (!accessConfirmed && !(await confirmAccess())) return;",
    'popup access gate'
  ],
  [
"if (response.status === 403) { ownerConfirmed = false; throw new Error(t('ownerOnly')); }",
"if (response.status === 403) { accessConfirmed = false; accessRole = ''; throw new Error(t('ownerOnly')); }",
    'run access reset'
  ],
  [
`  async function init() {
    installStyle();
    /* WFGG_SENTINEL_OWNER_RETRY_V5
       Le script est chargé juste après le boot ; la session Portail peut encore
       être en train de se stabiliser. On retente sans jamais afficher le bouton
       tant que OWNER n'a pas été validé par le serveur. */
    let ownerTry = 0;
    while (ownerTry < 8 && !(await confirmOwner())) {
      ownerTry += 1;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (!ownerConfirmed) {
      console.warn('WFGG_SENTINEL_OWNER_V5=NOT_CONFIRMED');
      return;
    }
    console.info('WFGG_SENTINEL_OWNER_V5=CONFIRMED');
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 120) clearInterval(timer); }, 120);
    const observer = new MutationObserver(() => { if (ownerConfirmed) injectButton(); });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }`,
`  async function init() {
    installStyle();
    installLaunchCapture();
    /* WFGG_SENTINEL_ACCESS_RETRY_V7
       OWNER et SUPERVISOR sont validés côté serveur. Le lanceur reste absent
       pour tous les autres profils, quel que soit leur rang d'alliance. */
    let accessTry = 0;
    while (accessTry < 10 && !(await confirmAccess())) {
      accessTry += 1;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    if (!accessConfirmed) {
      console.warn('WFGG_SENTINEL_ACCESS_V7=NOT_CONFIRMED');
      return;
    }
    console.info('WFGG_SENTINEL_ACCESS_V7=CONFIRMED role=' + accessRole);
    let tries = 0;
    const timer = setInterval(() => { tries += 1; if (injectButton() || tries > 140) clearInterval(timer); }, 120);
    const observer = new MutationObserver(() => { if (accessConfirmed) injectButton(); });
    observer.observe(document.documentElement,{childList:true,subtree:true});
  }`,
    'init access retry'
  ]
]);

patchFile('frontend/_worker.js', [
  ["script.src='/train/sentinel-train-v1.js?v=005';", "script.src='/train/sentinel-train-v1.js?v=007';", 'sentinel cache bust'],
  [
`/* WFGG_SENTINEL_EDGE_RUNNER_V6
   Sentinel reste strictement OWNER et lecture seule, mais sa recette est exécutée
   par le Worker Pages déjà déployé. Cela évite de dépendre d'un second déploiement
   wfgg-api tout en conservant la validation OWNER côté serveur. */`,
`/* WFGG_SENTINEL_EDGE_ACCESS_V7
   Sentinel reste strictement en lecture seule. Son accès est réservé aux rôles
   système OWNER et SUPERVISOR, indépendamment du rang d'alliance R1..R5. */`,
    'edge marker'
  ],
  [
`  if(meCall.data?.system?.role!=='OWNER'){
    return sentinelEdgeJson({ok:false,error:'SENTINEL_OWNER_ONLY'},403);
  }

  const checks=[];
  checks.push(sentinelEdgeCheck(
    'owner-access','Sécurité','ok','Accès Sentinel','Rôle système OWNER','OWNER validé côté serveur',
    'Le bouton et la recette restent inaccessibles aux autres rangs.',''
  ));`,
`  const sentinelRole=String(meCall.data?.system?.role||'');
  if(!['OWNER','SUPERVISOR'].includes(sentinelRole)){
    return sentinelEdgeJson({ok:false,error:'SENTINEL_ACCESS_FORBIDDEN'},403);
  }

  const checks=[];
  checks.push(sentinelEdgeCheck(
    'sentinel-access','Sécurité','ok','Accès Sentinel','Rôle système OWNER ou SUPERVISOR',sentinelRole+' validé côté serveur',
    'Le rang d’alliance reste indépendant de ce droit système.',''
  ));`,
    'edge access gate'
  ],
  ["version:'sentinel-edge-v6'", "version:'sentinel-edge-v7'", 'edge response version']
]);

console.log('WFGG_SENTINEL_SUPERVISOR_PATCH_V7=OK');
