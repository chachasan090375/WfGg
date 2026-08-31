#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
OUT="$ROOT/frontend/lab/master-assets-v2/runtime-lua"
META="$ROOT/frontend/lab/master-assets-v2/meta/lua-runtime-materialize-v1.json"
REPORT="$HOME/storage/downloads/WFGG_LASTWAR_LUA_RUNTIME_MATERIALIZE_V1.txt"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
command -v python >/dev/null 2>&1 || fail "python absent"
command -v unzip >/dev/null 2>&1 || fail "unzip absent"
mkdir -p "$OUT/raw" "$OUT/assetbundle-lua" "$OUT/lwscripts-index" "$(dirname "$META")" "$(dirname "$REPORT")"

APK=""
while IFS= read -r line; do
  p="${line#package:}"
  [[ "$p" == *"split_install_time_pack.apk" ]] && APK="$p" && break
done < <(pm path com.fun.lastwar.gp 2>/dev/null || true)
[[ -n "$APK" && -r "$APK" ]] || fail "split_install_time_pack.apk introuvable"

entries=(
  "assets/AssetBundles/lua"
  "assets/AssetBundles/lua.version"
  "assets/lwScripts/LWScripts.data"
  "assets/lwScripts/LWScripts.txt"
)
for e in "${entries[@]}"; do
  name="${e##*/}"
  dst="$OUT/raw/$name"
  if unzip -p "$APK" "$e" > "$dst" 2>/dev/null && [[ -s "$dst" ]]; then
    printf 'MATERIALIZED %s -> %s (%s bytes)\n' "$e" "$dst" "$(wc -c < "$dst")"
  else
    rm -f "$dst"
    printf 'WARN missing entry %s\n' "$e" >&2
  fi
done

python - "$OUT" "$META" "$REPORT" "$APK" <<'PY'
from __future__ import annotations
from pathlib import Path
import hashlib,json,re,sys,zipfile,os
out,meta,report,apk=map(Path,sys.argv[1:])
raw=out/'raw'; abdir=out/'assetbundle-lua'; idxdir=out/'lwscripts-index'
for d in (abdir,idxdir): d.mkdir(parents=True,exist_ok=True)

# Clean only generated decoded/extracted files; preserve raw exact copies.
for d in (abdir,idxdir):
    for p in d.rglob('*'):
        if p.is_file():
            try:p.unlink()
            except:pass

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def sig(data:bytes):
    if data.startswith(b'UnityFS'): return 'UnityFS'
    if data.startswith(b'UnityWeb'): return 'UnityWeb'
    if data.startswith(b'PK\x03\x04') or data.startswith(b'PK\x05\x06') or data.startswith(b'PK\x07\x08'): return 'PKZIP'
    if data[:16].lower().startswith(b'chacha'): return 'CHACHA'
    if data.startswith(b'\x1bLua'): return 'LUAC'
    return 'UNKNOWN'

def text_score(b:bytes):
    if not b:return 0.0
    s=b[:min(len(b),65536)]
    printable=sum((32<=x<127) or x in (9,10,13) or x>=0xC0 for x in s)
    nul=s.count(0)
    return max(0.0, printable/len(s) - min(.8,nul/max(1,len(s))*4))

def safe_name(s):
    s=s.replace('\\','/').strip('/')
    parts=[]
    for x in s.split('/'):
        x=re.sub(r'[^A-Za-z0-9_.@+-]+','_',x).strip('._') or '_'
        parts.append(x[:120])
    return '/'.join(parts)[:500]

files=[]
for p in sorted(raw.glob('*')):
    if not p.is_file():continue
    head=p.read_bytes()[:128]
    files.append({'name':p.name,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p),'signature':sig(head),'headHex':head[:32].hex(),'textScore':round(text_score(p.read_bytes()[:65536]),4)})

extracted=[]; errors=[]
# Exact AssetBundles/lua handling: ZIP or UnityPy only; no broad scans.
lua=raw/'lua'
if lua.exists():
    data=lua.read_bytes()[:16]
    if sig(data)=='PKZIP':
        try:
            with zipfile.ZipFile(lua) as z:
                for zi in z.infolist():
                    if zi.is_dir() or zi.file_size>8*1024*1024:continue
                    low=zi.filename.lower()
                    if not (low.endswith(('.lua','.luac','.txt','.bytes')) or 'lua' in low):continue
                    b=z.read(zi)
                    rel=safe_name(zi.filename) or ('entry_'+str(len(extracted)))
                    ext=Path(rel).suffix.lower()
                    if not ext: rel += '.lua' if text_score(b)>.72 else '.bytes'
                    dst=abdir/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(b)
                    extracted.append({'source':'AssetBundles/lua:zip','name':zi.filename,'path':str(dst),'bytes':len(b),'textScore':round(text_score(b),4)})
        except Exception as e: errors.append('zip:'+type(e).__name__+':'+str(e))
    elif sig(data) in ('UnityFS','UnityWeb'):
        try:
            import UnityPy
            env=UnityPy.load(str(lua))
            for obj in env.objects:
                if getattr(getattr(obj,'type',None),'name','')!='TextAsset': continue
                try:d=obj.read()
                except Exception as e:
                    errors.append('UnityPy.read:'+str(getattr(obj,'path_id','?'))+':'+type(e).__name__);continue
                name=str(getattr(d,'m_Name',None) or getattr(d,'name',None) or ('TextAsset_'+str(getattr(obj,'path_id','unknown'))))
                payload=getattr(d,'m_Script',None)
                if payload is None: payload=getattr(d,'script',None)
                if payload is None:
                    try:
                        tree=obj.read_typetree();payload=tree.get('m_Script') or tree.get('script') or b''
                    except:payload=b''
                if isinstance(payload,str): b=payload.encode('utf-8','replace')
                elif isinstance(payload,(bytes,bytearray)): b=bytes(payload)
                else:b=str(payload).encode('utf-8','replace') if payload else b''
                if not b:continue
                rel=safe_name(name)
                if not Path(rel).suffix: rel += '.lua' if text_score(b)>.72 else '.bytes'
                dst=abdir/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                if dst.exists(): dst=dst.with_name(dst.stem+'_'+str(getattr(obj,'path_id','x'))+dst.suffix)
                dst.write_bytes(b)
                extracted.append({'source':'AssetBundles/lua:UnityPy','name':name,'pathID':getattr(obj,'path_id',None),'path':str(dst),'bytes':len(b),'textScore':round(text_score(b),4)})
        except Exception as e: errors.append('UnityPy:'+type(e).__name__+':'+str(e))

# Copy readable exact metadata/index into viewer source root.
for nm in ('lua.version','LWScripts.txt'):
    p=raw/nm
    if p.exists():
        dst=out/nm
        dst.write_bytes(p.read_bytes())

# Heuristic but evidence-preserving LWScripts.txt -> LWScripts.data carving.
# We only materialize a row when a filename + numeric offset/size pair is self-consistent
# and the candidate slice has a plausible payload signature/text score.
idx=raw/'LWScripts.txt'; dat=raw/'LWScripts.data'; carved=[]
if idx.exists() and dat.exists() and idx.stat().st_size<32*1024*1024:
    ib=idx.read_bytes(); dsize=dat.stat().st_size
    try: text=ib.decode('utf-8')
    except: text=ib.decode('utf-8','replace')
    with dat.open('rb') as df:
        for line_no,line in enumerate(text.splitlines(),1):
            if not line.strip():continue
            # Capture a path/name and all decimal integers on the row.
            m=re.search(r'([A-Za-z0-9_./\\-]{3,}(?:\.lua|\.luac|\.bytes|\.txt)?)',line,re.I)
            nums=[int(x) for x in re.findall(r'(?<![A-Fa-f0-9])\d{1,12}(?![A-Fa-f0-9])',line)]
            if not m or len(nums)<2:continue
            name=m.group(1)
            candidates=[]
            # Try ordered integer pairs as offset,size; rank by payload plausibility.
            for i,a in enumerate(nums[:6]):
                for j,b in enumerate(nums[:6]):
                    if i==j or a<0 or b<=0 or b>16*1024*1024 or a+b>dsize:continue
                    try:
                        df.seek(a); chunk=df.read(min(b,65536))
                    except:continue
                    sc=text_score(chunk); sg=sig(chunk[:16])
                    bonus=.35 if sg in ('PKZIP','UnityFS','LUAC','CHACHA') else 0
                    if name.lower().endswith('.lua') and sc>.55: bonus+=.2
                    candidates.append((sc+bonus,a,b,sg,sc))
            if not candidates:continue
            candidates.sort(reverse=True); score,off,size,sg,ts=candidates[0]
            if score<.68:continue
            df.seek(off); payload=df.read(size)
            rel=safe_name(name)
            if not rel or rel in ('LWScripts.data','LWScripts.txt'):continue
            if not Path(rel).suffix: rel += '.lua' if text_score(payload)>.72 else '.bytes'
            dst=idxdir/rel;dst.parent.mkdir(parents=True,exist_ok=True)
            if dst.exists(): dst=dst.with_name(dst.stem+f'_L{line_no}'+dst.suffix)
            dst.write_bytes(payload)
            row={'line':line_no,'name':name,'offset':off,'size':size,'signature':sg,'textScore':round(ts,4),'path':str(dst),'indexLine':line[:400]}
            carved.append(row); extracted.append({'source':'LWScripts.data:index','name':name,'path':str(dst),'bytes':size,'textScore':round(ts,4),'indexLine':line_no})

anchors=['UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','A_Hero_Audie_01','RenderTexture','targetTexture','RawImage']
hits=[]
for r in extracted:
    p=Path(r['path'])
    if not p.exists() or p.stat().st_size>8*1024*1024:continue
    b=p.read_bytes()
    if text_score(b)<.5:continue
    text=b.decode('utf-8','replace')
    for a in anchors:
        if a.lower() in text.lower():
            lines=text.splitlines()
            for i,l in enumerate(lines,1):
                if a.lower() in l.lower():
                    hits.append({'file':str(p),'name':r.get('name'),'anchor':a,'line':i,'text':l[:400]})
                    break

result={'format':'WFGG_LASTWAR_LUA_RUNTIME_MATERIALIZE_V1','apk':str(apk),'rawFiles':files,'extracted':extracted,'carvedIndexRows':carved,'anchorHits':hits,'errors':errors,'counts':{'rawFiles':len(files),'extracted':len(extracted),'carved':len(carved),'anchorHits':len(hits)},'guardrails':{'exactApkEntriesOnly':True,'noBroadBundleScan':True,'mainUntouched':True}}
meta.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['LUA_RUNTIME_MATERIALIZE_V1_READY',f"raw={len(files)} extracted={len(extracted)} carved={len(carved)} anchorHits={len(hits)} errors={len(errors)}",'--- RAW CONTAINERS ---']
for r in files: lines.append(f"{r['name']} bytes={r['bytes']} sig={r['signature']} textScore={r['textScore']} sha256={r['sha256'][:16]}…")
lines.append('--- EXTRACTED SOURCES ---')
for r in extracted[:120]: lines.append(f"{r['source']} name={r.get('name')} bytes={r.get('bytes')} textScore={r.get('textScore')} path={r.get('path')}")
if not extracted: lines.append('NONE')
lines.append('--- FORMATION/MURPHY ANCHOR HITS ---')
for h in hits[:80]: lines.append(f"{h['anchor']} :: {h['name']} L{h['line']} :: {h['text']}")
if not hits: lines.append('NONE')
if errors:
    lines.append('--- ERRORS ---'); lines.extend(errors[:40])
lines.append(f'JSON={meta}')
text='\n'.join(lines)+'\n';report.write_text(text,'utf-8');print(text,end='')
PY
