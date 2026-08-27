from pathlib import Path
import io, json, re, hashlib
import requests
from PIL import Image, ImageOps, ImageChops, ImageStat

ROOTS=[Path('simulator'),Path('frontend/simulator')]
CATALOG=ROOTS[0]/'data/hero-catalog.v2.json'
HEADERS={'User-Agent':'Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/139 Mobile Safari/537.36','Accept':'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'}
s=requests.Session(); s.headers.update(HEADERS)
cat=json.loads(CATALOG.read_text(encoding='utf-8'))
heroes=cat['heroes']

def get(url, timeout=10):
    try:
        r=s.get(url,timeout=timeout,allow_redirects=True)
        if r.status_code==200 and len(r.content)>1500:
            return r
    except Exception:
        pass
    return None

def gif_metrics(raw):
    im=Image.open(io.BytesIO(raw))
    frames=getattr(im,'n_frames',1)
    if frames<2:
        return None
    total=0; diffs=[]; prev=None
    sample_step=max(1,frames//12)
    for i in range(frames):
        im.seek(i)
        total += int(im.info.get('duration',0) or 0)
        if i%sample_step==0 or i==frames-1:
            cur=im.convert('RGB').resize((80,100))
            if prev is not None:
                d=ImageChops.difference(prev,cur)
                diffs.append(sum(ImageStat.Stat(d).mean)/3)
            prev=cur
    return {
        'format':im.format,'width':im.width,'height':im.height,'frames':frames,
        'durationMs':total,'meanSampleDifference':round(sum(diffs)/len(diffs),3) if diffs else 0,
        'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()
    }

found={}; audit=[]
for h in heroes:
    hid=h['id']; name=h['name']; clean=re.sub(r'[^A-Za-z0-9]','',name)
    candidates=[]
    p=h.get('portrait') or ''
    if '.gif' in p.lower(): candidates.append(p)
    # Historical/likely Theria animated portrait locations. Exact catalog URL always wins.
    candidates += [
        f'https://theriagames.com/wp-content/uploads/2025/05/{clean}.gif',
        f'https://theriagames.com/wp-content/uploads/2025/04/{clean}.gif',
    ]
    if hid=='schuyler':
        candidates += ['https://theriagames.com/wp-content/uploads/2025/05/Schuyler.gif','https://theriagames.com/wp-content/uploads/2025/05/Skyler.gif']
    if hid=='sarah': candidates.insert(0,'https://theriagames.com/wp-content/uploads/2025/05/giphy-3-1.gif')
    if hid=='gump': candidates.insert(0,'https://theriagames.com/wp-content/uploads/2025/05/Gump.gif')
    if hid=='murphy': candidates.insert(0,'https://theriagames.com/wp-content/uploads/2025/04/Murphy.gif')
    seen=set()
    for url in candidates:
        if not url or url in seen: continue
        seen.add(url)
        r=get(url,7)
        if not r: continue
        try: m=gif_metrics(r.content)
        except Exception: m=None
        if not m or m['frames']<2 or m['durationMs']<400 or m['meanSampleDifference']<0.5: continue
        rel=f'assets/heroes/animated/{hid}.gif'
        for root in ROOTS:
            out=root/rel; out.parent.mkdir(parents=True,exist_ok=True); out.write_bytes(r.content)
        found[hid]={'id':hid,'name':name,'src':rel,'source':url,**m}
        audit.append(found[hid]); break

# Restore Loki from a real portrait instead of the generated letter fallback.
loki_candidates=[
    'https://theriagames.com/wp-content/uploads/2024/12/Loki.png',
    'https://theriagames.com/wp-content/uploads/2024/12/Loki-1024x1024.png',
    'https://theriagames.com/wp-content/uploads/2024/12/Loki-768x768.png',
]
loki_ok=False; loki_source=''
for url in loki_candidates:
    r=get(url,10)
    if not r: continue
    try:
        im=Image.open(io.BytesIO(r.content)).convert('RGB')
        if im.width<150 or im.height<150: continue
        # Same roster canvas as the other cached portraits, head biased upward.
        im=ImageOps.fit(im,(360,440),method=Image.Resampling.LANCZOS,centering=(0.5,0.24))
        for root in ROOTS:
            out=root/'assets/heroes/loki.webp'; out.parent.mkdir(parents=True,exist_ok=True); im.save(out,'WEBP',quality=92,method=6)
        loki_ok=True; loki_source=url; break
    except Exception:
        continue
if not loki_ok:
    raise SystemExit('Loki real portrait recovery failed')

manifest={
  'version':'17.0.0-native-gifs-only',
  'animatedCount':len(found),
  'animated':found,
  'lokiPortrait':'assets/heroes/loki.webp',
  'lokiSource':loki_source,
  'syntheticMotion':False
}
for root in ROOTS:
    (root/'data/hero-native-animations.v17.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

js=r"""(() => {
  'use strict';
  const MANIFEST='data/hero-native-animations.v17.json';
  const CATALOG='data/hero-catalog.v2.json';
  const SYNTH=['wfgg-live-card','wfgg-v10-live','wfgg-v12-live','wfgg-v13-live','wfgg-v14-live','wfgg-v15-live'];
  const CROP={monica:{x:'0%',y:'-7%',zoom:1.02},murphy:{x:'1%',y:'-20%',zoom:1.55},schuyler:{x:'0%',y:'5%',zoom:.94},sarah:{x:'0%',y:'1%',zoom:1.04},gump:{x:'0%',y:'2%',zoom:1.00}};
  let manifest={animated:{}}; let catalog=[]; let queued=false;
  window.WfGgHeroMotionOwner='native-v17';
  window.WfGgHeroNativeAnimationV17={version:'17.0.0'};
  document.documentElement.dataset.wfggRosterMotion='native-gif-only-v17';
  const byId=id=>catalog.find(h=>h.id===id)||null;
  function neutralize(card){SYNTH.forEach(c=>card.classList.remove(c));card.style.removeProperty('--wfgg-v15-delay')}
  function apply(card){
    const id=card.dataset.heroId;if(!id)return;
    neutralize(card);
    const cat=byId(id); const anim=manifest.animated?.[id];
    const layer=card.querySelector('.wfgg-v15-motion-layer')||card.querySelector('.hero-card-portrait');
    const img=layer?.querySelector('img')||card.querySelector('.hero-card-portrait img'); if(!img)return;
    if(id==='loki'){
      img.src='assets/heroes/loki.webp';
      img.dataset.wfggStaticSrc='assets/heroes/loki.webp';
      card.dataset.wfggLokiPortrait='restored-v17';
    } else if(cat?.localPortrait && !img.dataset.wfggStaticSrc){img.dataset.wfggStaticSrc=cat.localPortrait}
    if(anim?.src){
      if(img.getAttribute('src')!==anim.src)img.src=anim.src;
      card.classList.add('wfgg-native-animated','wfgg-native-gif-v17');
      card.dataset.wfggNativeAnimation=`gif-v17:${id}`;
      const c=CROP[id];if(c){card.style.setProperty('--wfgg-v15-x',c.x);card.style.setProperty('--wfgg-v15-y',c.y);card.style.setProperty('--wfgg-v15-zoom',String(c.zoom));card.dataset.wfggV17Crop=`${c.x},${c.y},${c.zoom}`}
    }else{
      card.classList.remove('wfgg-native-animated','wfgg-native-gif-v17','wfgg-native-animated-monica');
      card.dataset.wfggNativeAnimation='static-v17';
      const fallback=id==='loki'?'assets/heroes/loki.webp':(cat?.localPortrait||img.dataset.wfggStaticSrc||cat?.portrait||'');
      if(fallback&&img.getAttribute('src')!==fallback)img.src=fallback;
    }
  }
  function applyAll(){document.querySelectorAll('#gameHeroGrid .game-hero-card[data-hero-id]').forEach(apply)}
  function queue(){if(queued)return;queued=true;requestAnimationFrame(()=>{queued=false;applyAll()})}
  async function init(){
    try{const [m,c]=await Promise.all([fetch(MANIFEST,{cache:'no-store'}),fetch(CATALOG,{cache:'no-store'})]);if(m.ok)manifest=await m.json();if(c.ok)catalog=(await c.json()).heroes||[]}catch(_){}
    applyAll();
    const mo=new MutationObserver(ms=>{for(const m of ms){if(m.type==='attributes'&&m.target?.matches?.('.game-hero-card'))neutralize(m.target)}queue()});
    mo.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)queue()});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init,{once:true});else init();
})();
"""
css=r"""/* WFGG V17 — only authentic multi-frame GIF portraits animate. No synthetic card/portrait motion. */
.game-hero-card.wfgg-v15-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-live-card .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v10-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v12-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v13-live .wfgg-v15-motion-layer,
.game-hero-card.wfgg-v14-live .wfgg-v15-motion-layer,
.game-hero-card .wfgg-v15-motion-layer{
  animation:none!important;transition:none!important;will-change:auto!important;
}
.game-hero-card.wfgg-native-gif-v17 .wfgg-v15-motion-layer{animation:none!important;transition:none!important;will-change:auto!important}
.game-hero-card.wfgg-native-gif-v17 .wfgg-v15-motion-layer>img{animation:none!important;transition:none!important;object-fit:cover!important;object-position:center top!important;image-rendering:auto!important}
/* Monica source has more empty vertical room than the static crop: lift her to the same visual head line. */
.game-hero-card[data-hero-id="monica"].wfgg-native-gif-v17 .wfgg-v15-motion-layer{transform:translate3d(0%,-7%,0) scale(1.02)!important}
"""
for root in ROOTS:
    (root/'hero-native-animation-v17.js').write_text(js,encoding='utf-8')
    (root/'hero-native-animation-v17.css').write_text(css,encoding='utf-8')
    p=root/'index.html'; text=p.read_text(encoding='utf-8')
    cssline='  <link rel="stylesheet" href="hero-native-animation-v17.css?v=017-native-gifs-only" />\n'
    jsline='  <script src="hero-native-animation-v17.js?v=017-native-gifs-only"></script>\n'
    if 'hero-native-animation-v17.css' not in text:
        marker='  <link rel="stylesheet" href="hero-native-animation-v16.css?v=016-monica-original-gif" />\n'
        text=text.replace(marker,marker+cssline,1)
    if 'hero-native-animation-v17.js' not in text:
        marker='  <script src="hero-native-animation-v16.js?v=016-monica-original-gif"></script>\n'
        text=text.replace(marker,marker+jsline,1)
    p.write_text(text,encoding='utf-8')
    (root/'UI_VERSION.txt').write_text(f'HERO_NATIVE_GIF_V17\nAuthentic GIFs only; synthetic motion disabled; Loki restored\nAnimated heroes: {len(found)}\n',encoding='utf-8')

Path('simulator/research/native-gif-audit.v17.json').write_text(json.dumps({'animated':audit,'count':len(audit),'lokiSource':loki_source},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('NATIVE_GIFS_FOUND',len(found),sorted(found))
print('LOKI_RESTORED',loki_source)
if len(found)<4:
    raise SystemExit(f'Expected at least the known four authentic GIFs, found {len(found)}')
