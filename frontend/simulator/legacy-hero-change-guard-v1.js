(() => {
  'use strict';
  const STRUCTURAL=new Set(['heroId','troopType','role']);
  // app.js still binds onchange directly to every hero control and immediately
  // re-renders the whole hero list. For non-structural values this is both
  // unnecessary and destructive while the user is entering several fields in
  // sequence. The persistence bridge has already stored the change during the
  // capture phase, so stop the legacy target handler for these fields only.
  document.addEventListener('change',e=>{
    const el=e.target;
    if(!el?.dataset?.field||!el.closest?.('.hero-card'))return;
    if(STRUCTURAL.has(el.dataset.field))return;
    e.stopPropagation();
  },{capture:true});
  window.WfGgLegacyHeroChangeGuard=Object.freeze({version:'1.0.0',structural:[...STRUCTURAL]});
})();
