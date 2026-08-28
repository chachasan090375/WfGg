(() => {
  'use strict';
  const kit=window.WFGG_LASTWAR_GRAPHICS_KIT||null;
  const heroMap=window.WFGG_LASTWAR_HERO_AUTHORITATIVE_MAP||null;
  const companionMap=window.WFGG_LASTWAR_COMPANION_AUTHORITATIVE_MAP||null;
  const $=(id)=>document.getElementById(id);
  const norm=(s)=>String(s||'').trim().toLowerCase();
  const stem=(s)=>norm(String(s||'').split('/').pop()).replace(/\.(png|jpg|jpeg|tga|webp)$/i,'');

  function exactRows(name){
    if(!kit||!name)return[];
    const wanted=stem(name);
    return (kit.extractedAssets||[]).filter(x=>stem(x?.name)===wanted||stem(x?.localPath)===wanted);
  }
  function heroIcon(hero){
    const refs=[hero.queueIcon,hero.halfIcon].filter(Boolean).map(stem);
    const rows=(kit?.extractedAssets||[]).filter(x=>refs.includes(stem(x?.name)));
    const murphy=Number(hero.heroId)===50006;
    return rows.sort((a,b)=>{
      const score=(x)=>{
        let s=(x.objectType==='Sprite'?100:0)+(x.height||0)+(x.width||0);
        if(murphy){
          if(x.width===140&&x.height===140)s+=2000;
          else if(x.width===154&&x.height===154)s+=1200;
          else if(x.width===158&&x.height===201)s+=100;
        }else{
          if(x.width===158&&x.height===201)s+=1200;
          else if(x.width===140&&x.height===140)s+=500;
          else if(x.width===154&&x.height===154)s+=350;
        }
        return s;
      };
      return score(b)-score(a);
    })[0]||null;
  }
  function exactAsset(name){
    return exactRows(name).sort((a,b)=>{
      const sa=(a.objectType==='Sprite'?100:0)+(a.width===a.height?80:0)+(a.width||0)+(a.height||0);
      const sb=(b.objectType==='Sprite'?100:0)+(b.width===b.height?80:0)+(b.width||0)+(b.height||0);
      return sb-sa;
    })[0]||null;
  }
  function heroCard(hero,index){
    const card=document.createElement('article');
    card.className=`hero-card${hero.heroId===50006?' murphy':''}`;
    const visual=document.createElement('div');visual.className='hero-visual';
    const badge=document.createElement('span');badge.className='hero-badge';badge.textContent=String(index+1);visual.appendChild(badge);
    const asset=heroIcon(hero);
    if(asset){
      const img=document.createElement('img');img.src=asset.localPath;img.alt=hero.name;visual.appendChild(img);
    }else{
      const missing=document.createElement('div');missing.className='missing';missing.textContent='PNG absent';visual.appendChild(missing);
    }
    const info=document.createElement('div');info.className='hero-info';
    const name=document.createElement('b');name.textContent=hero.name;
    const id=document.createElement('span');id.textContent=`ID ${hero.heroId} · apparence ${hero.appearance}`;
    const ref=document.createElement('code');ref.textContent=hero.queueIcon;
    info.append(name,id,ref);card.append(visual,info);return card;
  }
  function companionCard(kind,title,subtitle,iconName,detail){
    const card=document.createElement('article');card.className=`companion-card ${kind}`;
    const asset=exactAsset(iconName);
    if(asset){const img=document.createElement('img');img.src=asset.localPath;img.alt=title;card.appendChild(img);}
    const copy=document.createElement('div');copy.className='companion-copy';
    const b=document.createElement('b');b.textContent=title;
    const s1=document.createElement('span');s1.textContent=subtitle;
    const s2=document.createElement('span');s2.textContent=detail;
    const code=document.createElement('code');code.textContent=iconName;
    copy.append(b,s1,s2,code);card.appendChild(copy);return card;
  }

  if(!heroMap||!kit){
    $('catalogStatus').textContent='Catalogue ou kit graphique absent.';
    $('catalogDetail').textContent='Recharge la preview après avoir lancé le serveur LAB depuis le dépôt à jour.';
    return;
  }

  const heroes=heroMap.heroes||[];
  const cards=heroes.map(heroCard);
  $('heroCatalogGrid').append(...cards);
  const exactCount=heroes.filter(h=>Boolean(heroIcon(h))).length;
  $('catalogStatus').textContent=`${exactCount}/${heroes.length} icônes héros officielles disponibles localement`;
  $('catalogDetail').textContent='Aucune correspondance par proximité : chaque carte utilise queueIcon/halfIcon issu de la table d’apparence.';

  const drone=companionMap?.drone?.resolve?.(162);
  const gorilla=companionMap?.dominator?.resolve?.(47);
  const cg=$('companionGrid');
  if(drone)cg.appendChild(companionCard('drone','Drone global · niveau 162',`Apparence ${drone.currentAppearance}`,drone.icon,'Profil sélectionné par la table UAV pour le niveau courant'));
  if(gorilla)cg.appendChild(companionCard('gorilla','Overlord · Gorilla · rang 47',`Apparence ${gorilla.appearance}`,gorilla.icon,`Étoile de rang ${gorilla.starLevel}`));
})();
