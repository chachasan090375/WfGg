#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 32
# OFFLINE ONLY. Opens the installed assets/table/*.data container as the ZIP archive
# it actually is, extracts the exact LW_Hero member, and analyzes only static game
# configuration. No Last War connection. No gameplay automation. No account data.

PKG="com.fun.lastwar.gp"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE32_TABLE_ZIP_EXTRACTION_REDACTED.txt"
CACHE_DIR="${ROOT}/frontend/lab/local-assets/lastwar-kit-v1/config-cache"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase32-table-zip-extraction.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")" "$CACHE_DIR"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import csv, gzip, hashlib, io, json, os, re, struct, sys, zipfile, zlib
from collections import Counter

out_path, cache_dir, *apk_paths = sys.argv[1:]
KNOWN = {
 30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",40020:"Monica",
 50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam",
 50016:"UNKNOWN_50016",50017:"UNKNOWN_50017"
}
ALIAS_TOKENS=[
 "Audie_Murphy","Murphy","Williams","Marshall","Kimberly","Katyusha","Stetmann","Stettmann","Tesla","McGregor","Ewan_McGregor","Fiona","Swift","Schuyler","DVA","Carlie","Morrison","Lucius","Adam","Nimitz","Rick","Mason","Hager","Monica","Farhad","Maxwell"
]

# --- helpers ---
def varint(n):
    b=bytearray()
    while True:
        x=n&0x7f;n>>=7
        if n:b.append(x|0x80)
        else:b.append(x);return bytes(b)

def positions(blob,needle,limit=10000):
    out=[];p=0
    while len(out)<limit:
        p=blob.find(needle,p)
        if p<0:break
        out.append(p);p+=max(1,len(needle))
    return out

def ascii_boundary_positions(blob,n):
    s=str(n).encode();out=[]
    for p in positions(blob,s):
        l=blob[p-1:p] if p else b'';r=blob[p+len(s):p+len(s)+1]
        if not (l and 48<=l[0]<=57) and not (r and 48<=r[0]<=57):out.append(p)
    return out

def printable_ratio(b):
    if not b:return 0.0
    return sum(1 for x in b if x in (9,10,13) or 32<=x<127)/len(b)

def strings_near(b,pos,radius=180):
    lo=max(0,pos-radius);hi=min(len(b),pos+radius)
    s=b[lo:hi]
    vals=[]
    for m in re.finditer(rb'[ -~]{3,}',s):
        v=m.group().decode('utf-8','ignore').strip()
        if v and v not in vals:vals.append(v)
    return vals[:18]

def hex_window(b,pos,radius=40):
    lo=max(0,pos-radius);hi=min(len(b),pos+radius)
    return b[lo:hi].hex()

def unwrap_member(data):
    layers=[]
    cur=data
    for _ in range(4):
        if cur[:2]==b'\x1f\x8b':
            try:cur=gzip.decompress(cur);layers.append('gzip');continue
            except Exception:pass
        if len(cur)>2 and cur[0]==0x78:
            try:cur=zlib.decompress(cur);layers.append('zlib');continue
            except Exception:pass
        break
    return cur,layers

def safe_scalar(v):
    return v is None or isinstance(v,(str,int,float,bool))

def walk_json(obj,path='root',rows=None):
    if rows is None:rows=[]
    if isinstance(obj,dict):
        idv=None
        for k,v in obj.items():
            nk=str(k).lower().replace('_','')
            if nk in ('id','heroid','configid','cfgid') and isinstance(v,(int,str)):
                try:
                    iv=int(v)
                    if iv in KNOWN:idv=iv;break
                except Exception:pass
        if idv is not None:
            allow={}
            for k,v in obj.items():
                lk=str(k).lower()
                if safe_scalar(v) and any(t in lk for t in ('id','name','appear','icon','quality','type','camp','skill','model','path','rare','rarity','profession','weapon')):
                    sv=str(v)
                    if len(sv)<=300:allow[str(k)]=v
            rows.append((path,idv,allow))
        for k,v in obj.items():walk_json(v,f'{path}.{k}',rows)
    elif isinstance(obj,list):
        for i,v in enumerate(obj):walk_json(v,f'{path}[{i}]',rows)
    return rows

# Find the table .data entry that is itself a ZIP and has exact member lw_hero.
found=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as az:
            for zi in az.infolist():
                q=zi.filename.lower()
                if not (q.startswith('assets/table/') and q.endswith('.data')):continue
                try:container=az.read(zi)
                except Exception:continue
                if not zipfile.is_zipfile(io.BytesIO(container)):continue
                try:
                    with zipfile.ZipFile(io.BytesIO(container)) as tz:
                        names=tz.namelist();lower={n.lower():n for n in names}
                        if 'lw_hero' in lower:
                            found=(apk,zi.filename,container,names,lower);break
                except Exception:continue
            if found:break
    except Exception:pass
if not found:raise SystemExit('conteneur ZIP assets/table/*.data avec membre exact lw_hero introuvable')

apk,entry,container,names,lower=found
related=[]
for n in names:
    q=n.lower()
    if any(t in q for t in ('lw_hero','heroappearance','hero_appearance','dominator','drone','uav','tactical','lw_equip','weapon')):
        related.append(n)

primary_name=lower['lw_hero']
with zipfile.ZipFile(io.BytesIO(container)) as tz:
    info=tz.getinfo(primary_name)
    primary_zip=tz.read(primary_name)
    primary,layers=unwrap_member(primary_zip)
    # Cache only static config locally; local-assets is git-ignored.
    with open(os.path.join(cache_dir,'lw_hero.bin'),'wb') as f:f.write(primary)
    cached=[]
    for n in related:
        q=n.lower()
        if q in ('lw_hero','lw_hero_appearance_opt','lw_equip','lw_drone_skill','lw_hero_unique_weapon') or 'dominator' in q:
            try:
                d,_=unwrap_member(tz.read(n))
                base=re.sub(r'[^A-Za-z0-9_.-]+','_',n)[:100] or 'table_member'
                p=os.path.join(cache_dir,base+'.bin')
                with open(p,'wb') as f:f.write(d)
                cached.append((n,len(d),os.path.basename(p)))
            except Exception:pass

# Structural probes on exact decompressed lw_hero member.
enc_counts={}
enc_pos={}
for hid,label in KNOWN.items():
    forms={
      'ascii':ascii_boundary_positions(primary,hid),
      'le32':positions(primary,struct.pack('<I',hid)),
      'be32':positions(primary,struct.pack('>I',hid)),
      'varint':positions(primary,varint(hid)),
    }
    enc_counts[hid]={k:len(v) for k,v in forms.items()}
    enc_pos[hid]=forms

alias_hits={}
low=primary.lower()
for tok in ALIAS_TOKENS:
    ps=positions(low,tok.lower().encode())
    if ps:alias_hits[tok]=ps[:20]

# Try direct text/JSON/CSV interpretations without guessing.
text=None
try:
    t=primary.decode('utf-8')
    if sum(1 for c in t[:200000] if c.isprintable() or c in '\r\n\t')/max(1,min(len(t),200000))>0.85:text=t
except Exception:pass
json_rows=[];json_error=None
if text:
    st=text.lstrip('\ufeff\x00 \r\n\t')
    if st[:1] in ('{','['):
        try:json_rows=walk_json(json.loads(st))
        except Exception as e:json_error=f'{type(e).__name__}: {e}'

line_candidates=[]
if text:
    for i,line in enumerate(text.splitlines(),1):
        if any(re.search(rf'(?<!\d){hid}(?!\d)',line) for hid in KNOWN):
            line_candidates.append((i,line[:1000]))
            if len(line_candidates)>=120:break

# Detect common binary-ish record clues near IDs; only report, never assign identity.
target_contexts=[]
for hid in (50016,50017,50006,50009,50010,50020):
    for enc,ps in enc_pos[hid].items():
        for p in ps[:8]:
            target_contexts.append((hid,enc,p,strings_near(primary,p),hex_window(primary,p)))

with open(out_path,'w',encoding='utf-8') as o:
    o.write('WfGg Last War LAB — PHASE 32 DIRECT TABLE ZIP EXTRACTION\n')
    o.write('OFFLINE ONLY · exact static table member extraction · no account/private data\n\n')
    o.write('CONTAINER_PROOF\n')
    o.write(f'  apk={os.path.basename(apk)}\n')
    o.write(f'  entry={entry}\n')
    o.write(f'  containerBytes={len(container)}\n')
    o.write(f'  containerMagic={container[:4].hex()}\n')
    o.write(f'  zipMembers={len(names)}\n')
    o.write(f'  exactPrimaryMember={primary_name}\n')
    o.write(f'  primaryCompressedBytes={info.compress_size}\n')
    o.write(f'  primaryZipUncompressedBytes={info.file_size}\n')
    o.write(f'  primaryPostUnwrapBytes={len(primary)}\n')
    o.write(f'  primaryNestedLayers={";".join(layers) if layers else "none"}\n')
    o.write(f'  primarySha256={hashlib.sha256(primary).hexdigest()}\n')
    o.write(f'  primaryFirst32Hex={primary[:32].hex()}\n')
    o.write(f'  primaryPrintableRatio={printable_ratio(primary):.4f}\n')
    o.write(f'  primaryUtf8Text={str(text is not None).lower()}\n')
    o.write(f'  cachedLocal={os.path.join(cache_dir,"lw_hero.bin")}\n')

    o.write('\nRELATED_TABLE_MEMBERS\n')
    for n in related[:300]:
        try:zi=zipfile.ZipFile(io.BytesIO(container)).getinfo(n);o.write(f'  {n} compressed={zi.compress_size} raw={zi.file_size}\n')
        except Exception:o.write(f'  {n}\n')
    o.write('\nCACHED_RELATED_MEMBERS\n')
    for n,size,b in cached:o.write(f'  member={n} bytes={size} cache={b}\n')

    o.write('\nEXACT_LW_HERO_ID_ENCODING_COUNTS\n')
    for hid,label in KNOWN.items():
        c=enc_counts[hid]
        o.write(f'  heroId={hid} label={label} ascii={c["ascii"]} le32={c["le32"]} be32={c["be32"]} varint={c["varint"]}\n')

    o.write('\nALIAS_TOKEN_HITS_IN_EXACT_LW_HERO\n')
    if not alias_hits:o.write('  (none)\n')
    for tok,ps in alias_hits.items():o.write(f'  token={tok} count={len(ps)} positions={",".join(map(str,ps[:12]))}\n')

    o.write('\nJSON_ROW_EXTRACTION\n')
    o.write(f'  parsedRows={len(json_rows)}\n')
    if json_error:o.write(f'  jsonError={json_error}\n')
    for path,hid,row in json_rows[:120]:
        o.write(f'  path={path} heroId={hid} fields={json.dumps(row,ensure_ascii=False,separators=(",",":"))}\n')

    o.write('\nTEXT_LINE_CANDIDATES\n')
    o.write(f'  count={len(line_candidates)}\n')
    for n,line in line_candidates:o.write(f'  line={n} text={line}\n')

    o.write('\nTARGET_AND_CALIBRATION_CONTEXTS\n')
    for hid,enc,p,ss,hx in target_contexts:
        o.write(f'  heroId={hid} encoding={enc} offset={p}\n')
        o.write(f'    strings={" | ".join(ss)}\n')
        o.write(f'    hex={hx}\n')

    o.write('\nINTERPRETATION_GUARDRAILS\n')
    o.write('  analysis_scope=exact_decompressed_lw_hero_member_not_whole_container\n')
    o.write('  compressed_container_false_negatives_eliminated=true\n')
    o.write('  numeric_occurrence_alone_is_not_identity_mapping=true\n')
    o.write('  internal_alias_alone_is_not_heroId_mapping=true\n')
    o.write('  unknown_50016_50017_remain_unresolved_until_same_record_or_decoded_schema=true\n')
    o.write('  next=decode_exact_lw_hero_member_schema_then_bridge_heroId_to_appearance_and_icon\n')

print(f'PHASE32_DONE members={len(names)} lwHeroBytes={len(primary)} target50016={enc_counts[50016]} target50017={enc_counts[50017]} output={out_path}')
PYEOF

python "$PY" "$OUT" "$CACHE_DIR" "${APK_PATHS[@]}"
chmod 600 "$OUT" 2>/dev/null || true
rm -f "$PY"

printf '=== PHASE 32 TERMINEE ===\n'
printf 'Le membre exact LW_Hero du conteneur ZIP a été extrait hors ligne.\n'
printf 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE32_TABLE_ZIP_EXTRACTION_REDACTED.txt\n'
