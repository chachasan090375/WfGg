import fs from 'node:fs';
import crypto from 'node:crypto';

const APP='frontend/train-native/app.v15.js';
const SHA='frontend/train-native/app.v15.js.sha256';
const src=fs.readFileSync(APP,'utf8');

const pattern=/        \/\* WFGG_PORTAL_DIRECT_TRAIN_V1[\s\S]*?        \} else \{\n          showPortal\(\);\n        \}/;
if(!pattern.test(src)){
  throw new Error('WFGG_PORTAL_DIRECT_TRAIN_V1 block not found exactly once');
}

const replacement=`        /* WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2
           Sous /train/, ne jamais décider à partir du seul cache local Train.
           Le Portail possède la session autoritative : on hydrate d'abord le
           snapshot same-origin, puis seulement on ouvre l'application.
           En cas d'échec, on reste sur /train/ avec un diagnostic au lieu de
           renvoyer silencieusement l'utilisateur vers l'accueil du Portail.
        */
        if (location.pathname === '/train' ||
            location.pathname.startsWith('/train/')) {

          let ready = !!(state.currentUserId && user());
          let bootstrapError = '';

          if (!ready) {
            try {
              const refreshed = await syncSnapshot({ render: false, quiet: true });
              ready = !!(refreshed && state.currentUserId && user());
              if (!ready) bootstrapError = 'snapshot_without_identity';
            } catch (e) {
              bootstrapError = String(e && e.message || e || 'snapshot_failed');
            }
          }

          if (ready) {
            console.info('WFGG_PORTAL_TRAIN_BOOTSTRAP_V2=READY');
            bootApp();
          } else {
            console.error('WFGG_PORTAL_TRAIN_BOOTSTRAP_V2=FAILED', bootstrapError || 'identity_missing');
            const note = document.querySelector('.login-note');
            if (note) {
              note.innerHTML = '⚠️ Impossible de synchroniser ta session Train pour le moment. ' +
                '<button type="button" class="btn outline" onclick="location.reload()">Réessayer</button>';
            }
            const login = document.getElementById('loginView');
            if (login) login.classList.remove('hidden');
            const app = document.getElementById('appView');
            if (app) app.classList.add('hidden');
          }

        } else {
          showPortal();
        }`;

const out=src.replace(pattern,replacement);
if(out===src) throw new Error('Patch produced no change');
if((out.match(/WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2/g)||[]).length!==1){
  throw new Error('Unexpected V2 marker count');
}
if(out.includes("console.warn('WFGG_PORTAL_TRAIN_IDENTITY_MISSING');\n            location.replace('/');")){
  throw new Error('Legacy automatic redirect still present');
}

fs.writeFileSync(APP,out);
const digest=crypto.createHash('sha256').update(fs.readFileSync(APP)).digest('hex');
fs.writeFileSync(SHA,`${digest}  frontend/train-native/app.v15.js\n`);
console.log('WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2=PATCHED');
