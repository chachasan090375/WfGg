(()=>{
'use strict';
/* Explorer UI bootstrap. Advanced explorer controls are progressively enhanced here; keeping this
   file present also makes the server-injected explorer script deterministic instead of generating
   a 404 on every viewer load. */
async function refreshStatus(){
  try{
    const r=await fetch('/api/v33/explorer-status',{cache:'no-store'});if(!r.ok)return;
    const d=await r.json();
    window.WFGGExplorerV33={version:'33.1',status:d,ready:true};
  }catch(e){window.WFGGExplorerV33={version:'33.1',ready:false,error:String(e)};}
}
refreshStatus();
})();
