(() => {
'use strict';

const PORTAL_TOKEN_KEY='wfgg_portal_session';
const TRAIN_API='https://wfgg-train.chachasan090375.workers.dev';
let trainRosterIds=null;
let showFormer=false;

function token(){return localStorage.getItem(PORTAL_TOKEN_KEY)||''}

async function portalApi(path,options={}){
  const headers=new Headers(options.headers||{});
  const tk=token();
  if(tk)headers.set('Authorization',`Bearer ${tk}`);
  if(options.body&&!headers.has('Content-Type'))headers.set('Content-Type','application/json');
  const response=await fetch(path,{...options,headers,cache:'no-store'});
  let data=null;try{data=await response.json()}catch{}
  if(!response.ok)throw new Error(data?.message||data?.error||`HTTP_${response.status}`);
  return data;
}

async function trainApi(path,options={}){
  const headers=new Headers(options.headers||{});
  const tk=token();
  if(!tk)throw new Error('Session Portail absente');
  headers.set('X-WfGg-Portal-Token',tk);
  const response=await fetch(`${TRAIN_API}${path}`,{...options,headers,cache:'no-store',credentials:'omit',mode:'cors'});
  let data=null;try{data=await response.json()}catch{}
  if(!response.ok&&response.status!==404)throw new Error(data?.error||`HTTP_${response.status}`);
  return {status:response.status,data};
}

async function refreshTrainRoster(){
  try{
    const {data}=await trainApi('/api/snapshot',{method:'GET'});
    trainRosterIds=new Set((data?.roster||[]).map(row=>String(row?.id||'')).filter(Boolean));
  }catch(error){
    console.warn('WFGG_MEMBER_DEPARTURE_TRAIN_ROSTER',String(error?.message||error));
    trainRosterIds=null;
  }
  decorateFormerMembers();
}

function ensureFormerToggle(){
  const tools=document.querySelector('.members-tools');
  if(!tools||tools.querySelector('[data-wfgg-former-toggle]'))return;
  const button=document.createElement('button');
  button.type='button';
  button.className='small-btn';
  button.dataset.wfggFormerToggle='1';
  button.textContent='🗃️ Anciens membres';
  button.addEventListener('click',()=>{
    showFormer=!showFormer;
    decorateFormerMembers();
  });
  tools.appendChild(button);
}

function decorateFormerMembers(){
  ensureFormerToggle();
  if(!trainRosterIds)return;
  let formerCount=0;
  document.querySelectorAll('#memberList .member-row').forEach(row=>{
    const edit=row.querySelector('[data-action="edit-member"][data-id]');
    const id=String(edit?.dataset.id||'');
    const former=Boolean(id&&row.classList.contains('inactive')&&!trainRosterIds.has(id));
    row.dataset.wfggFormer=former?'1':'0';
    if(former){
      formerCount+=1;
      const meta=row.querySelector('.member-meta');
      if(meta){
        const next=meta.innerHTML.replace(/désactivé|inactif/gi,'ancien membre');
        if(next!==meta.innerHTML)meta.innerHTML=next;
      }
      row.style.display=showFormer?'':'none';
    }else{
      row.style.display='';
    }
  });
  const toggle=document.querySelector('[data-wfgg-former-toggle]');
  if(toggle){
    const base=showFormer?'🗃️ Masquer anciens membres':'🗃️ Anciens membres';
    const label=`${base}${formerCount?` (${formerCount})`:''}`;
    if(toggle.textContent!==label)toggle.textContent=label;
  }
}

function enhanceMemberModal(){
  const body=document.getElementById('modalBody');
  const id=body?.querySelector('#mId')?.value;
  const actions=body?.querySelector('.modal-actions');
  if(!id||!actions||actions.querySelector('[data-action="remove-alliance-member"]'))return;

  const activeToggle=body.querySelector('#mActive');
  const rankControl=body.querySelector('#mRank')||body.querySelector('input[value="R5"]');
  const rank=String(rankControl?.value||'').toUpperCase();
  if(rank==='R5'||activeToggle?.disabled)return;

  const button=document.createElement('button');
  button.type='button';
  button.className='secondary-button';
  button.dataset.action='remove-alliance-member';
  button.dataset.id=id;
  button.style.borderColor='rgba(255,110,110,.7)';
  button.style.color='#ffaaaa';
  button.textContent='🚪 Retirer de l’Alliance';
  actions.insertBefore(button,actions.lastElementChild||null);
}

async function removeFromAlliance(button){
  const body=document.getElementById('modalBody');
  const id=String(button.dataset.id||body?.querySelector('#mId')?.value||'');
  const name=body?.querySelector('.modal-title h3')?.textContent?.trim()||'ce joueur';
  const rankControl=body?.querySelector('#mRank')||body?.querySelector('input[value="R5"]');
  const rank=String(rankControl?.value||'').toUpperCase();
  if(!id)return;
  if(rank==='R5'){
    alert('Le R5 doit d’abord transmettre le leadership avant de quitter l’Alliance.');
    return;
  }

  const ok=confirm(`Retirer ${name} de l’Alliance ?\n\nCette action :\n• le retire immédiatement des rotations Train futures ;\n• annule ses annonces d’échange ouvertes ;\n• supprime ses indisponibilités et alertes Train ;\n• ferme ses sessions ;\n• désactive son accès au Portail.\n\nSon historique passé reste conservé.`);
  if(!ok)return;

  const oldText=button.textContent;
  button.disabled=true;
  button.textContent='Suppression…';
  try{
    const train=await trainApi(`/api/admin/members/${encodeURIComponent(id)}`,{method:'DELETE'});
    await portalApi(`/api/admin/members/${encodeURIComponent(id)}`,{
      method:'PATCH',
      body:JSON.stringify({active:false})
    });
    alert(`${name} a été retiré de l’Alliance et des rotations.${train.status===404?'\nLe joueur était déjà absent de Train.':''}`);
    location.reload();
  }catch(error){
    alert(`Impossible de terminer le retrait de ${name}.\n\n${String(error?.message||error)}\n\nAucune confirmation de succès n’est affichée tant que les deux côtés ne sont pas cohérents.`);
    button.disabled=false;
    button.textContent=oldText;
    refreshTrainRoster();
  }
}

document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action="remove-alliance-member"]');
  if(button){event.preventDefault();event.stopPropagation();removeFromAlliance(button);}
},true);

const observer=new MutationObserver(()=>{
  enhanceMemberModal();
  decorateFormerMembers();
});
observer.observe(document.documentElement,{childList:true,subtree:true});

window.WFGG_MEMBER_DEPARTURE_V1={
  version:'member-departure-v1',
  refresh:refreshTrainRoster
};

if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',refreshTrainRoster,{once:true});
else refreshTrainRoster();
})();
