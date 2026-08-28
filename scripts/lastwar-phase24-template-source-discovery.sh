#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 24
# OFFLINE ONLY. Discovers the authoritative Hero/Dominator/Drone template sources
# and inventories semantic UnityFS node metadata. No Last War network connection.
# Privacy: no credentials, no private UUID/GUID/UID.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE24_TEMPLATE_SOURCE_DISCOVERY_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase24-template-source.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")"
mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p'); fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import os,re,struct,sys,zipfile
from collections import defaultdict

out_path,*apk_paths=sys.argv[1:]
wanted={"assets/AssetBundles/BundleFragment0.bytes","assets/lwScripts/LWScripts.data"}
entries={}; all_entries=[]
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    for i in z.infolist():
        all_entries.append((os.path.basename(apk),i.filename,i.file_size,i.compress_size))
        if i.filename in wanted: entries[i.filename]=(apk,i)
    z.close()

def read_entry(name):
    if name not in entries:return None,None
    apk,info=entries[name]
    with zipfile.ZipFile(apk) as z:return z.read(info),os.path.basename(apk)+":"+name

pr=re.compile(rb"[\x20-\x7e]{3,}")
def strings(blob,limit=600):
    out=[]
    for m in pr.finditer(blob):
        s=m.group().decode("ascii","ignore").strip()
        if s and s not in out:
            out.append(s)
            if len(out)>=limit:break
    return out

# Authoritative Lua modules and their embedded constant names.
lws,lws_label=read_entry("assets/lwScripts/LWScripts.data")
mods=[
("HeroTemplateManager",b"DataCenter/HeroData/HeroTemplateManager"),
("AppearanceTemplateManager",b"DataCenter/HeroData/AppearanceTemplateManager"),
("HeroUtils",b"HeroUtils"),
("DominatorMainTemplate",b"DataCenter/Dominator/TemplateManager/DominatorMainTemplate"),
("DominatorManager",b"DataCenter/Dominator/Main/DominatorManager"),
("TacticalChipManager",b"DataCenter/TacticalWeapon/TacticalChipManager/TacticalChipManager"),
("DroneLevelTemplate",b"LwDroneBattlesystemLevelTemplate"),
("DroneTierTemplate",b"LwDroneBattlesystemTierTemplate"),
]
key=re.compile(r"(?i)(hero|appearance|dominator|tactical|chip|uav|drone|config|template|meta|name|icon|quality|skill|weapon|default|localization|resource|path|id)")
hits=defaultdict(list)
if lws:
    low=lws.lower()
    for label,needle in mods:
        p=0
        while len(hits[label])<6:
            p=low.find(needle.lower(),p)
            if p<0:break
            vals=[s for s in strings(lws[max(0,p-6000):min(len(lws),p+14000)],700) if key.search(s)]
            hits[label].append((p,vals[:150]));p+=1

# Dedicated package paths that may contain static config data.
path_re=re.compile(r"(?i)(hero.*(?:config|template|meta|data)|(?:config|template|meta|data).*hero|dominator|tacticalchip|tacticalweapon|uav|drone)")
path_candidates=[x for x in all_entries if path_re.search(x[1])]
path_candidates.sort(key=lambda x:(x[2],x[1]))

# Minimal UnityFS metadata reader. We only decode the block-info table, not game data.
def cstr(f,maxlen=4096):
    b=bytearray()
    while len(b)<maxlen:
        c=f.read(1)
        if not c:raise EOFError
        if c==b"\0":return bytes(b)
        b+=c
    raise ValueError

def lz4(src):
    src=memoryview(src);i=0;o=bytearray()
    while i<len(src):
        t=src[i];i+=1;ln=t>>4
        if ln==15:
            while True:
                x=src[i];i+=1;ln+=x
                if x!=255:break
        o+=src[i:i+ln];i+=ln
        if i>=len(src):break
        off=src[i]|(src[i+1]<<8);i+=2
        if off<=0 or off>len(o):raise ValueError("bad lz4 offset")
        ml=(t&15)+4
        if (t&15)==15:
            while True:
                x=src[i];i+=1;ml+=x
                if x!=255:break
        base=len(o)-off
        for _ in range(ml):o.append(o[base]);base+=1
    return bytes(o)

def dec(blob,typ):
    if typ==0:return blob
    if typ in (2,3):return lz4(blob)
    if typ==1:
        import lzma
        try:return lzma.decompress(blob)
        except Exception:return None
    return None

def parse_meta(raw):
    if not raw or len(raw)<20:return [],[]
    p=16;bc=struct.unpack_from(">I",raw,p)[0];p+=4
    if bc>100000:return [],[]
    blocks=[]
    for _ in range(bc):
        if p+10>len(raw):return [],[]
        blocks.append(struct.unpack_from(">IIH",raw,p));p+=10
    if p+4>len(raw):return blocks,[]
    nc=struct.unpack_from(">I",raw,p)[0];p+=4
    if nc>100000:return blocks,[]
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw):break
        off,size,fl=struct.unpack_from(">qqI",raw,p);p+=20
        e=raw.find(b"\0",p)
        if e<0:break
        path=raw[p:e].decode("utf-8","ignore");p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

stats=defaultdict(int); candidates=[]; frag_label="-"
if "assets/AssetBundles/BundleFragment0.bytes" in entries:
    apk,info=entries["assets/AssetBundles/BundleFragment0.bytes"]
    frag_label=os.path.basename(apk)+":assets/AssetBundles/BundleFragment0.bytes"
    with zipfile.ZipFile(apk) as z,z.open(info) as f:
        total=info.file_size
        while f.tell()<total:
            start=f.tell();head=f.read(8)
            if not head:break
            if not head.startswith(b"UnityFS"):
                buf=head+f.read(min(1024*1024,total-f.tell()));q=buf.find(b"UnityFS\0")
                if q<0:continue
                start=start+q;f.seek(start)
            try:
                if cstr(f)!=b"UnityFS":f.seek(start+1);continue
                fmt=struct.unpack(">I",f.read(4))[0];uver=cstr(f).decode("ascii","ignore");urev=cstr(f).decode("ascii","ignore")
                size=struct.unpack(">Q",f.read(8))[0];cs=struct.unpack(">I",f.read(4))[0];us=struct.unpack(">I",f.read(4))[0];flags=struct.unpack(">I",f.read(4))[0]
                hend=f.tell()
                if size<=0 or start+size>total+16 or cs>67108864 or us>134217728:f.seek(start+1);continue
                stats["bundles"]+=1;typ=flags&0x3f
                if flags&0x80:stats["metadata_at_end"]+=1;ipos=start+size-cs
                else:
                    ipos=hend
                    if flags&0x200:ipos=(ipos+15)&~15
                f.seek(ipos);meta=dec(f.read(cs),typ);blocks,nodes=parse_meta(meta)
                if nodes:
                    stats["metadata_ok"]+=1
                    mm=[n for n in nodes if any(x in n[3].lower() for x in ("hero","dominator","tactical","uav","drone"))]
                    if mm:candidates.append((start,size,fmt,flags,typ,uver,urev,len(blocks),len(nodes),mm[:100]))
                else:stats["metadata_fail"]+=1
                f.seek(start+size)
            except Exception:
                stats["metadata_fail"]+=1
                try:f.seek(start+1)
                except Exception:break

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 24 TEMPLATE SOURCE DISCOVERY\n")
    o.write("OFFLINE ONLY · static installed assets · no private account identifiers\n\n")
    o.write("AUTHORITATIVE_LUA_MODULE_CONSTANTS\n")
    for label,_ in mods:
        o.write(f"  module={label} hits={len(hits.get(label,[]))}\n")
        for p,vals in hits.get(label,[])[:3]:
            o.write(f"    offset={p}\n")
            for s in vals[:70]:o.write(f"      {s}\n")
    o.write("\nAPK_CONFIG_PATH_CANDIDATES\n")
    o.write(f"  count={len(path_candidates)}\n")
    for apk,name,size,csize in path_candidates[:220]:o.write(f"  source={apk} size={size} compressed={csize} path={name}\n")
    o.write("\nUNITYFS_METADATA_STATS\n")
    o.write(f"  source={frag_label}\n")
    for k in ("bundles","metadata_ok","metadata_fail","metadata_at_end"):o.write(f"  {k}={stats[k]}\n")
    o.write("\nUNITYFS_SEMANTIC_NODE_CANDIDATES\n")
    o.write(f"  candidateBundles={len(candidates)}\n")
    for start,size,fmt,flags,typ,uver,urev,bc,nc,mm in candidates[:220]:
        o.write(f"  bundleOffset={start} bundleSize={size} format={fmt} flags=0x{flags:x} compression={typ} blocks={bc} nodes={nc} unity={uver}/{urev}\n")
        for off,nsize,nfl,path in mm[:40]:o.write(f"    nodeOffset={off} nodeSize={nsize} nodeFlags=0x{nfl:x} path={path}\n")
    o.write("\nDISCOVERY_TARGET\n")
    o.write("  hero_chain=HeroTemplateManager -> HeroTemplate row -> appearance/name/icon -> localization/asset\n")
    o.write("  dominator_chain=DominatorMainTemplate -> dominator_id -> linked HeroTemplate/default_name\n")
    o.write("  drone_chain=TacticalChipManager/LwDroneBattlesystem* -> exact UAV item/config rows\n")
    o.write("  unknown_hero_ids_are_not_guessed=true\n")
    o.write("  next=decode_only_semantic_UnityFS_candidate_nodes_and_extract_exact_config_rows_for_50016_50017_and_dominator_1000000\n")
print(f"OUTPUT={out_path} BUNDLES={stats['bundles']} META_OK={stats['metadata_ok']} CANDIDATES={len(candidates)}")
PYEOF

python "$PY" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"
printf '%s\n' "=== PHASE 24 TERMINEE ===" "Aucune connexion Last War n'a été effectuée." "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE24_TEMPLATE_SOURCE_DISCOVERY_REDACTED.txt"
