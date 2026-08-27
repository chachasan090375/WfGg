from pathlib import Path
import json
from PIL import Image

ROOTS=[Path('simulator'),Path('frontend/simulator')]
manifest=json.loads((ROOTS[0]/'data/hero-native-animations.v17.json').read_text(encoding='utf-8'))
animated=manifest['animated']

# Generate a still from frame 0 of the exact same GIF. Switching still<->GIF is visually seamless.
for hid,a in animated.items():
    src=ROOTS[0]/a['src']
    im=Image.open(src); im.seek(0); frame=im.convert('RGB')
    rel=f'assets/heroes/animated-still/{hid}.webp'
    for root in ROOTS:
        out=root/rel; out.parent.mkdir(parents=True,exist_ok=True); frame.save(out,'WEBP',quality=92,method=6)
    a['still']=rel
manifest['version']='17.1.0-staged-native-gifs'
manifest['staged']=True
manifest['simultaneous']=6
manifest['syntheticMotion']=False
for root in ROOTS:
    (root/'data/hero-native-animations.v17.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

js=r"""(() => {
  'use strict';
  const MANIFEST='data/hero-native-animations.v17.json';
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live'];
  const ACTIVE_MS=3900, REST_MS=850;
  const CROP={monica:{x:'0%',y:'-9%',zoom:1.03},murphy:{x:'1%',y:'-20%',zoom:1.55},schuyler:{x:'0%',y:'5%',zoom:.94},sarah:{x:'0%',y:'1%',zoom:1.04},gump:{x:'0%',y:'2%',zoom:1.00},loki:{x:'0%',y:'0%',zoom:1.00}};
  let manifest={animated:{}}; let queue=[]; let active=[]; let timer=0; let stopped=false; let queued=false;
  window.WfGgHeroMotionOwner='native-v17b';
  window.WfGgHeroNativeAnimationV17B={version:'17.1.0'};
  document.documentElement.dataset.wfggRosterMotion='staged-native-gifs-v17b';
  const cards=()=>[...document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]')].filter(c=>c.offsetParent!==null);
  const shuf=a=>{a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[a[i],a[j]]=[a[j],a[i]]}return a};
  const info=id=>manifest.animated?.[id]||null;
  function neutralize(card){SYNTH.forEach(c=>card.classList.remove(c));card.style.removeProperty('--wfgg-v15-delay')}
  function imgFor(card){return card.querySelector('.wfgg-v15-motion-layer > img')||card.querySelector('.hero-card-portrait img')}
  function crop(card){const c=CROP[card.dataset.heroId];if(!c)return;card.style.setProperty('--wfgg-v15-x',c.x);card.style.setProperty('--wfgg-v15-y',c.y);card.style.setProperty('--wfgg-v15-zoom',String(c.zoom));card.dataset.wfggV17bCrop=`${c.x},${c.y},${c.zoom}`}
  function toStill(card){
    neutralize(card); const a=info(card.dataset.heroId), img=imgFor(card); if(!img)return;
    card.classList.remove('wfgg-native-gif-active-v17b','wfgg-native-animated-monica');
    if(a?.still){if(img.getAttribute('src')!==a.still)img.src=a.still;card.classList.add('wfgg-native-gif-capable-v17b');card.dataset.wfggNativeAnimation='native-gif-ready-v17b';crop(card)}
    else {card.classList.remove('wfgg-native-gif-capable-v17b');card.dataset.wfggNativeAnimation='static-v17b'}
  }
  function allStill(){active=[];cards().forEach(toStill);document.documentElement.dataset.wfggV17bActive='0'}
  function refill(){queue=shuf(cards().filter(c=>info(c.dataset.heroId)));document.documentElement.dataset.wfggV17bCycle=String(queue.length)}
  function takeGroup(){if(!queue.length)refill();const n=Math.min(queue.length,5+Math.floor(Math.random()*2));return queue.splice(0,n)}
  function preload(url){return new Promise(resolve=>{const i=new Image();let done=false;const finish=()=>{if(done)return;done=true;resolve()};i.onload=finish;i.onerror=finish;i.src=url;if(i.complete)finish();setTimeout(finish,3500)})}
  async function activate(group){
    if(stopped)return;
    await Promise.all(group.map(c=>preload(info(c.dataset.heroId)?.src||'')));
    if(stopped)return;
    active=group.filter(c=>c.isConnected&&c.offsetParent!==null);
    active.forEach(card=>{neutralize(card);crop(card);const a=info(card.dataset.heroId),img=imgFor(card);if(a?.src&&img){img.src=a.src;card.classList.add('wfgg-native-gif-active-v17b');card.dataset.wfggNativeAnimation='native-gif-playing-v17b'}});
    document.documentElement.dataset.wfggV17bPhase='active';document.documentElement.dataset.wfggV17bActive=String(active.length);document.documentElement.dataset.wfggV17bBatch=active.map(c=>c.dataset.heroId).join(',');
    clearTimeout(timer);timer=setTimeout(rest,ACTIVE_MS);
  }
  function rest(){
    allStill();document.documentElement.dataset.wfggV17bPhase='rest';clearTimeout(timer);timer=setTimeout(next,REST_MS)
  }
  function next(){if(stopped||document.hidden){document.documentElement.dataset.wfggV17bPhase='idle';return}activate(takeGroup())}
  function apply(){cards().forEach(c=>{neutralize(c);if(!c.classList.contains('wfgg-native-gif-active-v17b'))toStill(c)})}
  function queueApply(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;apply()})}
  async function init(){
    try{const r=await fetch(MANIFEST,{cache:'no-store'});if(r.ok)manifest=await r.json()}catch(_){}
    stopped=false;allStill();refill();
    const mo=new MutationObserver(ms=>{for(const m of ms){if(m.type==='attributes'&&m.target?.matches?.('.game-hero-card'))neutralize(m.target)}queueApply()});
    mo.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(document.hidden){stopped=true;allStill();document.documentElement.dataset.wfggV17bPhase='idle'}else{stopped=false;refill();timer=setTimeout(next,300)}});
    timer=setTimeout(next,700);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
"""
css=r"""/* WFGG V17B — staged authentic GIFs only; synthetic animation fully disabled. */
.game-hero-card.wfgg-v15-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-live-card .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v10-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v12-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v13-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v14-live .wfgg-v15-motion-layer,
.game-hero-card .wfgg-v15-motion-layer{animation:none!important;transition:none!important;will-change:auto!important}
.game-hero-card .wfgg-v15-motion-layer>img{animation:none!important;transition:none!important;image-rendering:auto!important}
.game-hero-card.wfgg-native-gif-active-v17b,.game-hero-card.wfgg-native-gif-capable-v17b{animation:none!important;transition:none!important}
.game-hero-card[data-hero-id="monica"] .wfgg-v15-motion-layer{transform:translate3d(0%,-9%,0) scale(1.03)!important}
"""
for root in ROOTS:
    (root/'hero-native-animation-v17b.js').write_text(js,encoding='utf-8')
    (root/'hero-native-animation-v17b.css').write_text(css,encoding='utf-8')
    p=root/'index.html'; s=p.read_text(encoding='utf-8')
    # Remove V16/V17 runtime layers so V17B is the sole animation owner.
    s=s.replace('  <link rel="stylesheet" href="hero-native-animation-v16.css?v=016-monica-original-gif" />\n','')
    s=s.replace('  <link rel="stylesheet" href="hero-native-animation-v17.css?v=017-native-gifs-only" />\n','')
    s=s.replace('  <script src="hero-native-animation-v16.js?v=016-monica-original-gif"></script>\n','')
    s=s.replace('  <script src="hero-native-animation-v17.js?v=017-native-gifs-only"></script>\n','')
    cssline='  <link rel="stylesheet" href="hero-native-animation-v17b.css?v=017b-staged-native-gifs" />\n'
    jsline='  <script src="hero-native-animation-v17b.js?v=017b-staged-native-gifs"></script>\n'
    if 'hero-native-animation-v17b.css' not in s:
        marker='  <link rel="stylesheet" href="hero-roster-v15.css?v=015c-dedicated-portrait-motion" />\n';s=s.replace(marker,marker+cssline,1)
    if 'hero-native-animation-v17b.js' not in s:
        marker='  <script src="hero-roster-v15.js?v=015c-dedicated-portrait-motion"></script>\n';s=s.replace(marker,marker+jsline,1)
    p.write_text(s,encoding='utf-8')
    (root/'UI_VERSION.txt').write_text(f'HERO_NATIVE_GIF_V17B\nStaged authentic GIFs, 5-6 at a time; synthetic motion disabled; Loki restored\nAnimated heroes: {len(animated)}\n',encoding='utf-8')
print('STAGED_NATIVE_GIFS',len(animated))
