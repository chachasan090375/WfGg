(()=>{'use strict';
const TEAMS={
  1:[['50006','Murphy'],['50007','Williams'],['50008','Marshall'],['50009','Kimberly'],['50010','Stetmann']],
  2:[['50019','Carlie'],['50021','Lucius'],['50018','Schuyler'],['50017','DVA'],['50020','Morrison']],
  3:[['50013','McGregor'],['50022','Adam'],['50015','Swift'],['50016','Tesla'],['50014','Fiona']]
};
const TYPE_ICON={1:'master-assets-v1/ui/type-tank.png',2:'master-assets-v1/ui/type-aircraft.png',3:'master-assets-v1/ui/type-missile.png'};
const unitLayer=document.getElementById('unitLayer');
const heroStrip=document.getElementById('heroStrip');
const teamSwitcher=document.getElementById('teamSwitcher');
let team=1,selected='50006';

function iframeCss(){return `
html,body{margin:0!important;width:100%!important;height:100%!important;background:transparent!important;overflow:hidden!important}
.viewer{display:block!important;width:100%!important;height:100%!important;max-width:none!important;border:0!important;background:transparent!important}
.topbar,.hud,.teams,.heroes,.help{display:none!important}
.stage{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;min-height:0!important;background:transparent!important}
#gl{position:absolute!important;inset:0!important;width:100%!important;height:100%!important;background:transparent!important;pointer-events:none!important;touch-action:none!important}
`;}

function selectInFrame(frame,teamNo,heroName){
  let tries=0;
  const run=()=>{
    tries++;
    try{
      const doc=frame.contentDocument;
      if(!doc){if(tries<80)setTimeout(run,75);return;}
      if(!doc.getElementById('formation-embed-style')){
        const st=doc.createElement('style');st.id='formation-embed-style';st.textContent=iframeCss();doc.head.appendChild(st);
      }
      const tb=doc.querySelector(`.teams button[data-team="${teamNo}"]`);
      if(tb&&!tb.classList.contains('active'))tb.click();
      const buttons=[...doc.querySelectorAll('#heroes button')];
      const hb=buttons.find(b=>b.textContent.trim().toLowerCase().startsWith(heroName.toLowerCase()));
      if(hb){hb.click();return;}
    }catch(_){ }
    if(tries<80)setTimeout(run,75);
  };
  run();
}

function buildUnits(){
  unitLayer.replaceChildren();
  TEAMS[team].forEach(([id,name],i)=>{
    const slot=document.createElement('div');slot.className=`unit-slot s${i+1}`;slot.dataset.hero=id;
    const frame=document.createElement('iframe');
    frame.src=`lastwar-auth-renderer.html?embed=1&t=${team}&hero=${id}&v=${Date.now()}-${i}`;
    frame.setAttribute('title',name);frame.setAttribute('scrolling','no');frame.tabIndex=-1;
    frame.addEventListener('load',()=>selectInFrame(frame,team,name));
    slot.appendChild(frame);unitLayer.appendChild(slot);
  });
}

function stars(){return Array.from({length:5},()=>'<img src="master-assets-v1/ui/star-full.png" alt="">').join('');}
function buildCards(){
  heroStrip.replaceChildren();
  TEAMS[team].forEach(([id,name])=>{
    const b=document.createElement('button');b.type='button';b.className='hero-card'+(id===selected?' selected':'');b.dataset.hero=id;b.title=name;
    b.innerHTML=`<img class="portrait" src="master-assets-v1/heroes/${id}.png" alt="${name}"><img class="type-icon" src="${TYPE_ICON[team]}" alt=""><span class="level">Niv.150</span><span class="stars">${stars()}</span><img class="selected-check" src="master-assets-v1/ui/selected-check.png" alt="">`;
    b.addEventListener('click',()=>{selected=id;document.querySelectorAll('.hero-card').forEach(x=>x.classList.toggle('selected',x.dataset.hero===selected));document.querySelectorAll('.unit-slot').forEach(x=>x.style.filter=x.dataset.hero===selected?'drop-shadow(0 0 8px rgba(255,219,75,.95)) drop-shadow(0 9px 8px rgba(0,0,0,.42))':'drop-shadow(0 9px 8px rgba(0,0,0,.42))');});
    heroStrip.appendChild(b);
  });
}
function setTeam(n){
  team=n;selected=TEAMS[n][0][0];
  teamSwitcher.querySelectorAll('[data-team]').forEach(b=>b.classList.toggle('active',Number(b.dataset.team)===n));
  buildUnits();buildCards();
}
teamSwitcher.addEventListener('click',e=>{const b=e.target.closest('[data-team]');if(b)setTeam(Number(b.dataset.team));});
document.querySelector('.back-button')?.addEventListener('click',()=>history.back());
setTeam(1);
})();
