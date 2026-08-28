#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 27
# OFFLINE ONLY. Classifies the exact LW_Hero UnityFS bundles found by Phase 26
# and traces the runtime config-loader API used by HeroTemplateManager/DataConfig.
# No Last War network connection. No gameplay automation.
# Privacy: static installed assets only; no credentials, account UUID/GUID/UID,
# player names, resource balances or private formation references.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
P26="${DOWNLOADS}/WFGG_LASTWAR_PHASE26_DECODED_PAYLOAD_INDEX_REDACTED.txt"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE27_CONFIG_LOADER_DISCOVERY_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase27-config-loader-discovery.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$P26" ]] || die "Phase 26 absente: $P26"
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import os,re,struct,sys,zipfile,lzma
from collections import Counter,defaultdict

p26_path,out_path,*apk_paths=sys.argv[1:]
ENTRY="assets/AssetBundles/BundleFragment0.bytes"
LWS="assets/lwScripts/LWScripts.data"

# The Phase 26 output is the source of the exact LW_Hero bundle offsets. This
# avoids ranking arbitrary int32 hits as identities.
with open(p26_path,"r",encoding="utf-8",errors="ignore") as f:
    p26=f.read()
hero_bundle_offsets=[]
for m in re.finditer(r"bundleOffset=(\d+) bundleSize=(\d+) decodedBytes=(\d+) nodes=(\d+)\n\s+tokens=([^\n]*LW_Hero[^\n]*)",p26):
    hero_bundle_offsets.append((int(m.group(1)),int(m.group(2)),m.group(5).strip()))
hero_bundle_offsets=sorted(set(hero_bundle_offsets))

found_fragment=None; found_lws=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            try: found_fragment=(apk,z.getinfo(ENTRY))
            except KeyError: pass
            try: found_lws=(apk,z.getinfo(LWS))
            except KeyError: pass
    except Exception: pass
if not found_fragment: raise SystemExit("BundleFragment0.bytes introuvable")
if not found_lws: raise SystemExit("LWScripts.data introuvable")

# --- UnityFS helpers -----------------------------------------------------------
def read_cstr(f,maxlen=16384):
    b=bytearray()
    while len(b)<maxlen:
        c=f.read(1)
        if not c: raise EOFError("cstr eof")
        if c==b"\0": return bytes(b)
        b+=c
    raise ValueError("cstr too long")

def align16(n): return (n+15)&~15

def lz4_block(src,expected=None):
    src=memoryview(src); i=0; out=bytearray()
    while i<len(src):
        token=src[i]; i+=1; lit=token>>4
        if lit==15:
            while True:
                if i>=len(src): raise ValueError("lz4 literal overflow")
                x=src[i]; i+=1; lit+=x
                if x!=255: break
        if i+lit>len(src): raise ValueError("lz4 literal range")
        out+=src[i:i+lit]; i+=lit
        if i>=len(src): break
        if i+2>len(src): raise ValueError("lz4 offset eof")
        off=src[i]|(src[i+1]<<8); i+=2
        if off<=0 or off>len(out): raise ValueError("lz4 bad offset")
        ml=(token&15)+4
        if (token&15)==15:
            while True:
                if i>=len(src): raise ValueError("lz4 match overflow")
                x=src[i]; i+=1; ml+=x
                if x!=255: break
        pos=len(out)-off
        for _ in range(ml): out.append(out[pos]); pos+=1
    return bytes(out)

def decomp(blob,typ,expected=None):
    typ &= 0x3f
    if typ==0:return blob
    if typ in (2,3):return lz4_block(blob,expected)
    if typ==1:
        for fmt in (lzma.FORMAT_AUTO,lzma.FORMAT_ALONE):
            try:return lzma.decompress(blob,format=fmt)
            except Exception:pass
        raise ValueError("lzma decode failed")
    raise ValueError(f"unknown compression {typ}")

def parse_block_info(raw):
    if len(raw)<20: raise ValueError("short blockinfo")
    p=16; bc=struct.unpack_from(">I",raw,p)[0]; p+=4
    if bc>200000: raise ValueError("bad block count")
    blocks=[]
    for _ in range(bc):
        if p+10>len(raw): raise ValueError("truncated blocks")
        blocks.append(struct.unpack_from(">IIH",raw,p)); p+=10
    if p+4>len(raw): raise ValueError("missing node count")
    nc=struct.unpack_from(">I",raw,p)[0]; p+=4
    if nc>200000: raise ValueError("bad node count")
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw): raise ValueError("truncated node")
        off,size,fl=struct.unpack_from(">qqI",raw,p); p+=20
        e=raw.find(b"\0",p)
        if e<0: raise ValueError("unterminated node")
        path=raw[p:e].decode("utf-8","ignore"); p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

def decode_bundle_at(f,start):
    f.seek(start)
    if read_cstr(f)!=b"UnityFS": raise ValueError("bad signature")
    fmt=struct.unpack(">I",f.read(4))[0]
    unity=read_cstr(f).decode("ascii","ignore")
    rev=read_cstr(f).decode("ascii","ignore")
    size=struct.unpack(">Q",f.read(8))[0]
    cs=struct.unpack(">I",f.read(4))[0]
    us=struct.unpack(">I",f.read(4))[0]
    flags=struct.unpack(">I",f.read(4))[0]
    hend=f.tell(); aligned=start+align16(hend-start) if fmt>=7 else hend
    meta_pos=start+size-cs if flags&0x80 else aligned
    f.seek(meta_pos); meta=decomp(f.read(cs),flags&0x3f,us)
    blocks,nodes=parse_block_info(meta)
    data_pos=aligned if flags&0x80 else meta_pos+cs
    if not (flags&0x80) and (flags&0x200): data_pos=start+align16(data_pos-start)
    f.seek(data_pos); parts=[]
    for u,cc,bfl in blocks:
        raw=f.read(cc)
        if len(raw)!=cc: raise ValueError("data block truncated")
        parts.append(decomp(raw,bfl&0x3f,u))
    return {"start":start,"size":size,"fmt":fmt,"unity":unity,"rev":rev,"flags":flags,"blocks":blocks,"nodes":nodes,"data":b"".join(parts)}

def node_for(nodes,pos):
    for off,size,fl,path in nodes:
        if off<=pos<off+size:return (off,size,fl,path)
    return None

PRINTABLE=re.compile(rb"[\x20-\x7e]{3,}")
def printable_strings(data,lo=0,hi=None,limit=120):
    if hi is None:hi=len(data)
    vals=[]
    for m in PRINTABLE.finditer(data[max(0,lo):min(len(data),hi)]):
        s=m.group().decode("ascii","ignore").strip()
        if not s or s in vals: continue
        vals.append(s[:260])
        if len(vals)>=limit: break
    return vals

def positions(data,needle,limit=50):
    out=[];p=0
    while len(out)<limit:
        p=data.find(needle,p)
        if p<0:break
        out.append(p);p+=1
    return out

def ascii_numeric_positions(data,n,limit=20):
    # Exact decimal token boundary: 50016 must NOT match icon_item_650016.
    rx=re.compile(rb"(?<![0-9])"+str(n).encode()+rb"(?![0-9])")
    return [m.start() for m in rx.finditer(data)][:limit]

KNOWN={30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",40020:"Monica",50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam"}
HYPOTHESIS_NAMES=("Tesla","DVA")

# --- Decode only the four Phase-26 LW_Hero token bundles -----------------------
bundle_reports=[]
apk,info=found_fragment
with zipfile.ZipFile(apk) as z,z.open(info) as f:
    for start,reported_size,p26tokens in hero_bundle_offsets:
        try:
            b=decode_bundle_at(f,start); data=b["data"]; low=data.lower()
            lwpos=positions(data,b"LW_Hero",20)
            contexts=[]
            for p in lwpos:
                contexts.append((p,node_for(b["nodes"],p),printable_strings(data,p-1800,p+3200,80)))
            known_ids=[n for n in KNOWN if struct.pack("<I",n) in data]
            known_names=[(n,name) for n,name in KNOWN.items() if name.lower().encode() in low]
            hypotheses=[name for name in HYPOTHESIS_NAMES if name.lower().encode() in low]
            unknown={}
            for n in (50016,50017):
                unknown[n]={"ascii":ascii_numeric_positions(data,n),"le32":positions(data,struct.pack("<I",n),20)}
            semantic_strings=[]
            for s in printable_strings(data,0,len(data),5000):
                sl=s.lower()
                if any(k in sl for k in ("lw_hero","heroappearance","herotemplate","hero_icon","heroicons","a_hero_","assetbundle","atlas","sprite","texture","prefab","material","sound_hero")):
                    if s not in semantic_strings:semantic_strings.append(s)
                    if len(semantic_strings)>=100:break
            bundle_reports.append((b,p26tokens,lwpos,contexts,known_ids,known_names,hypotheses,unknown,semantic_strings,None))
        except Exception as e:
            bundle_reports.append((None,p26tokens,[],[],[],[],[],{},[],str(e)[:180]))

# --- Trace runtime config API from LWScripts -----------------------------------
apk_lws,info_lws=found_lws
with zipfile.ZipFile(apk_lws) as z:
    lws=z.read(info_lws)
lows=lws.lower()

anchors=[
    ("HeroTemplateManager",b"HeroTemplateManager"),
    ("LW_Hero",b"LW_Hero"),
    ("HeroAppearance",b"HeroAppearance"),
    ("DataConfig",b"DataConfig"),
    ("InitAllTemplate",b"InitAllTemplate"),
    ("TryGetStr",b"TryGetStr"),
    ("GetHeroNameByConfigId",b"GetHeroNameByConfigId"),
]
anchor_contexts=defaultdict(list)
for label,needle in anchors:
    p=0
    while len(anchor_contexts[label])<30:
        p=lows.find(needle.lower(),p)
        if p<0:break
        vals=printable_strings(lws,p-5000,p+9000,220)
        anchor_contexts[label].append((p,vals));p+=1

api_rx=re.compile(r"^(?:Try|Get|Load|Read|Init|Parse|Find|Open|Create|Update|Set|Has|Is)[A-Za-z0-9_]{2,80}$")
field_rx=re.compile(r"(?i)(rowData|tableName|tableDict|templateDict|dataConfig|configData|lineData|GetString|GetInt|GetLong|GetFloat|GetBool|GetRow|GetTable|TryGet|LuaEntry|DataConfig|TableName|InitAllTemplate)")
api_tokens=Counter()
for label in ("DataConfig","InitAllTemplate","HeroTemplateManager","LW_Hero"):
    for _,vals in anchor_contexts.get(label,[]):
        for s in vals:
            if api_rx.fullmatch(s) or field_rx.search(s):api_tokens[s]+=1

# Nearby module/source identifiers around the generic loader anchors.
module_rx=re.compile(r"(?:DataCenter/[A-Za-z0-9_./-]+\.luac|Assets/Main/LuaScripts/[A-Za-z0-9_./-]+\.lua|[A-Za-z0-9_.]+TemplateManager|[A-Za-z0-9_.]+DataConfig[A-Za-z0-9_.]*)")
loader_modules=Counter()
for label in ("DataConfig","InitAllTemplate"):
    for _,vals in anchor_contexts.get(label,[]):
        for s in vals:
            for m in module_rx.findall(s):loader_modules[m]+=1

# --- Scan other APK entries for exact config tokens ----------------------------
# Phase 26 established UnityFS payload coverage. Here we only ask whether an exact
# table/loader token also lives in a separate static container outside LWScripts.
source_tokens=(b"LW_Hero",b"HeroAppearance",b"HeroTemplateManager",b"DataConfig",b"GetHeroNameByConfigId")
source_hits=[]; scanned_files=0; scanned_bytes=0
for apkx in apk_paths:
    try:z=zipfile.ZipFile(apkx)
    except Exception:continue
    for zi in z.infolist():
        if zi.filename in (ENTRY,LWS):continue
        if zi.file_size<=0 or zi.file_size>32*1024*1024:continue
        try:raw=z.read(zi)
        except Exception:continue
        scanned_files+=1;scanned_bytes+=len(raw); low=raw.lower()
        hits=[]
        for t in source_tokens:
            c=low.count(t.lower())
            if c:hits.append((t.decode("ascii"),c))
        if hits:
            source_hits.append((os.path.basename(apkx),zi.filename,zi.file_size,hits,printable_strings(raw,0,len(raw),60)))
    z.close()

# --- Write redacted report -----------------------------------------------------
with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 27 CONFIG LOADER DISCOVERY\n")
    o.write("OFFLINE ONLY · static installed assets · no private account identifiers\n\n")
    o.write("PHASE26_PIVOT\n")
    o.write(f"  phase26_lwHeroTokenBundles={len(hero_bundle_offsets)}\n")
    o.write("  heroDenseBundles=0\n")
    o.write("  global_int32_hits_are_not_identity_mapping=true\n")
    o.write("  exact_ascii_numeric_boundary_enabled=true\n")
    o.write("  strategy=classify_exact_LW_Hero_bundles_and_trace_LuaEntry_DataConfig_loader\n")

    o.write("\nLW_HERO_BUNDLE_CLASSIFICATION\n")
    for idx,r in enumerate(bundle_reports,1):
        b,p26tokens,lwpos,contexts,kids,knames,hypotheses,unknown,sem,err=r
        if err:
            o.write(f"  bundle={idx} decodeError={err}\n");continue
        o.write(f"  bundle={idx} offset={b['start']} size={b['size']} decodedBytes={len(b['data'])} nodes={len(b['nodes'])} flags=0x{b['flags']:x} phase26Tokens={p26tokens}\n")
        o.write(f"    lwHeroOccurrences={len(lwpos)} knownHeroIdsLE={','.join(map(str,kids)) or '-'} knownHeroNamesASCII={','.join(name for _,name in knames) or '-'} hypothesisNameTokens={','.join(hypotheses) or '-'}\n")
        for n in (50016,50017):
            u=unknown[n]
            o.write(f"    targetId={n} exactAsciiOccurrences={len(u['ascii'])} le32Occurrences={len(u['le32'])}\n")
        for off,nsize,nfl,path in b["nodes"]:
            o.write(f"    node off={off} size={nsize} flags=0x{nfl:x} path={path}\n")
        for p,nd,vals in contexts:
            o.write(f"    LW_Hero_context logicalOffset={p} node={nd[3] if nd else '-'}\n")
            for s in vals[:55]:o.write(f"      {s}\n")
        if sem:
            o.write("    semanticStrings\n")
            for s in sem[:70]:o.write(f"      {s}\n")

    o.write("\nRUNTIME_CONFIG_LOADER_ANCHORS\n")
    for label,_ in anchors:
        rows=anchor_contexts.get(label,[])
        o.write(f"  anchor={label} hitsShown={len(rows)}\n")
        for p,vals in rows[:8]:
            picked=[]
            for s in vals:
                if field_rx.search(s) or api_rx.fullmatch(s) or any(k in s for k in ("HeroTemplate","AppearanceTemplate","LuaEntry","DataConfig","LW_Hero","HeroAppearance")):
                    if s not in picked:picked.append(s)
                if len(picked)>=45:break
            o.write(f"    offset={p}\n")
            for s in picked:o.write(f"      {s}\n")

    o.write("\nDATACONFIG_API_CANDIDATES\n")
    for s,c in api_tokens.most_common(180):o.write(f"  token={s} contexts={c}\n")

    o.write("\nLOADER_MODULE_CANDIDATES\n")
    for s,c in loader_modules.most_common(120):o.write(f"  module={s} contexts={c}\n")

    o.write("\nOTHER_APK_EXACT_TOKEN_SOURCES\n")
    o.write(f"  scannedFiles={scanned_files} scannedBytes={scanned_bytes} matchingFiles={len(source_hits)}\n")
    for apkname,path,size,hits,vals in source_hits[:120]:
        o.write(f"  source={apkname}:{path} size={size} tokens="+",".join(f"{t}:{c}" for t,c in hits)+"\n")
        picked=[]
        for s in vals:
            if any(t.decode("ascii").lower() in s.lower() for t in source_tokens) or "config" in s.lower() or "hero" in s.lower():
                if s not in picked:picked.append(s)
            if len(picked)>=20:break
        for s in picked:o.write(f"    {s}\n")

    o.write("\nEVIDENCE_RULE\n")
    o.write("  accepted_hero_mapping_requires=authoritative_LW_Hero_row_or_equivalent_runtime_config_record_with_explicit_heroId_and_name_or_localization_key\n")
    o.write("  exact_ascii_50016_does_not_match_650016=true\n")
    o.write("  little_endian_int32_occurrence_alone_is_not_mapping=true\n")
    o.write("  asset_name_Tesla_or_DVA_alone_is_not_heroId_mapping=true\n")
    o.write("  unknown_hero_ids_are_not_guessed=true\n")
    o.write("  next=use_discovered_DataConfig_API_or_identified_config_container_to_extract_LW_Hero_rows_50016_50017_then_follow_HeroAppearance_icon_chain\n")

print(f"OUTPUT={out_path} LW_HERO_BUNDLES={len(hero_bundle_offsets)} DATACONFIG_CONTEXTS={len(anchor_contexts.get('DataConfig',[]))} OTHER_SOURCES={len(source_hits)}")
PYEOF

python "$PY" "$P26" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"
printf '%s\n' "=== PHASE 27 TERMINEE ===" "Aucune connexion Last War n'a été effectuée." "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE27_CONFIG_LOADER_DISCOVERY_REDACTED.txt"
