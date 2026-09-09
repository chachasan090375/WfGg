import fs from 'node:fs';

const FILE='frontend/_worker.js';
const src=fs.readFileSync(FILE,'utf8');

const before=`  function forceTrainPortalEntry(){
    if(ROUTE!=='train')return;
    if(!localStorage.getItem(PORTAL_TOKEN))return;
`;

const after=`  function forceTrainPortalEntry(){
    if(ROUTE!=='train')return;

    /* WFGG_TRAIN_FORCE_GATE_DISABLED_V3
       L'ancien gate imposait un second bootstrap, un probe et une navigation
       globale par-dessus app.v15. Le bootstrap autoritatif est maintenant
       WFGG_PORTAL_DIRECT_TRAIN_BOOTSTRAP_V2 dans app.v15.js. En mode intégré,
       ce gate ne doit donc plus masquer Train ni pouvoir renvoyer vers '/'.
    */
    console.info('WFGG_TRAIN_FORCE_GATE_DISABLED_V3=ACTIVE');
    return;

    if(!localStorage.getItem(PORTAL_TOKEN))return;
`;

if(src.includes('WFGG_TRAIN_FORCE_GATE_DISABLED_V3')){
  console.log('WFGG_TRAIN_FORCE_GATE_DISABLED_V3=ALREADY_PATCHED');
  process.exit(0);
}
if(!src.includes(before)) throw new Error('forceTrainPortalEntry signature not found');
const out=src.replace(before,after);
if(out===src) throw new Error('No change produced');
fs.writeFileSync(FILE,out);
console.log('WFGG_TRAIN_FORCE_GATE_DISABLED_V3=PATCHED');
