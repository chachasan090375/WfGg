#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 26
# OFFLINE ONLY. Decodes UnityFS payload blocks sequentially and indexes exact
# Hero/Dominator/Drone table tokens plus target IDs. No Last War network connection.
# Privacy: static installed assets only; no credentials, account UUID/GUID/UID,
# player names, resource balances or gameplay automation.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE26_DECODED_PAYLOAD_INDEX_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase26-decoded-payload-index.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
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

out_path,*apk_paths=sys.argv[1:]
ENTRY="assets/AssetBundles/BundleFragment0.bytes"
found=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            try: info=z.getinfo(ENTRY)
            except KeyError: continue
            found=(apk,info); break
    except Exception: pass
if not found: raise SystemExit("BundleFragment0.bytes introuvable")
apk,info=found

KNOWN_HERO_NAMES={
 30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",
 40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",
 40020:"Monica",50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",
 50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",
 50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam"
}
UNKNOWN_IDS=(50016,50017)
DOMINATOR_ID=1000000
DRONE_CFG_IDS=(1408,1501,1502,1503,1508,1608,2501,2502,2503,3501,3502,3503,4501,4502,4503)
TABLE_TOKENS=(
 b"LW_Hero",b"HeroAppearance",b"HeroTemplate",b"HeroTemplateManager",b"heroId",
 b"DominatorMainTemplate",b"dominator_id",b"default_name",b"small_pic_path",
 b"LW_Drone_Skill",b"TWSkillChipTemplate",b"TacticalChipManager",
 b"battlesystem_chip_set_name",b"item_uav_equip_"
)
PRINTABLE=re.compile(rb"[\x20-\x7e]{3,}")

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
    typ&=0x3f
    if typ==0:return blob
    if typ in (2,3):return lz4_block(blob,expected)
    if typ==1:
        for fmt in (lzma.FORMAT_AUTO,lzma.FORMAT_ALONE):
            try:return lzma.decompress(blob,format=fmt)
            except Exception:pass
        raise ValueError("lzma decode failed")
    raise ValueError(f"unknown compression {typ}")

def parse_block_info(raw):
    p=16
    if len(raw)<20: raise ValueError("short blockinfo")
    bc=struct.unpack_from(">I",raw,p)[0]; p+=4
    if bc>200000:raise ValueError("bad block count")
    blocks=[]
    for _ in range(bc):
        if p+10>len(raw):raise ValueError("truncated blocks")
        blocks.append(struct.unpack_from(">IIH",raw,p));p+=10
    if p+4>len(raw):raise ValueError("missing node count")
    nc=struct.unpack_from(">I",raw,p)[0];p+=4
    if nc>200000:raise ValueError("bad node count")
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw):raise ValueError("truncated node")
        off,size,fl=struct.unpack_from(">qqI",raw,p);p+=20
        e=raw.find(b"\0",p)
        if e<0:raise ValueError("unterminated node")
        path=raw[p:e].decode("utf-8","ignore");p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

def all_positions(data,needle,limit=80):
    out=[]; p=0
    while len(out)<limit:
        p=data.find(needle,p)
        if p<0:break
        out.append(p);p+=1
    return out

def node_for(nodes,pos):
    for off,size,fl,path in nodes:
        if off<=pos<off+size:return (off,size,fl,path)
    return None

def nearby_strings(data,pos,radius=1100,limit=32):
    lo=max(0,pos-radius);hi=min(len(data),pos+radius)
    vals=[]
    for m in PRINTABLE.finditer(data[lo:hi]):
        s=m.group().decode("ascii","ignore").strip()
        if not s or s in vals:continue
        # Suppress giant opaque hashes while keeping paths/keys/names.
        if len(s)>220:s=s[:220]
        vals.append(s)
        if len(vals)>=limit:break
    return vals

stats=Counter(); errors=Counter(); interesting=[]; target_contexts=defaultdict(list)
hero_dense=[]; token_bundles=[]; decoded_total=0

# Sequential scan: metadata and payload are processed in one pass, avoiding random
# seeks through the APK. For the installed version Phase 25 observed metadata-at-end=0,
# but the branch below still handles it conservatively.
with zipfile.ZipFile(apk) as z,z.open(info) as f:
    total=info.file_size
    while f.tell()<total:
        start=f.tell();sig=f.read(8)
        if not sig:break
        if not sig.startswith(b"UnityFS"):
            buf=sig+f.read(min(2*1024*1024,total-f.tell()))
            q=buf.find(b"UnityFS\0")
            if q<0:continue
            start+=q;f.seek(start)
        try:
            if read_cstr(f)!=b"UnityFS":f.seek(start+1);continue
            fmt=struct.unpack(">I",f.read(4))[0];unity=read_cstr(f).decode("ascii","ignore");rev=read_cstr(f).decode("ascii","ignore")
            size=struct.unpack(">Q",f.read(8))[0];cs=struct.unpack(">I",f.read(4))[0];us=struct.unpack(">I",f.read(4))[0];flags=struct.unpack(">I",f.read(4))[0]
            hend=f.tell()
            if not (1<=fmt<=20) or size<=0 or start+size>total+16:raise ValueError("bad header")
            aligned=start+align16(hend-start) if fmt>=7 else hend
            meta_pos=start+size-cs if flags&0x80 else aligned
            f.seek(meta_pos);meta=decomp(f.read(cs),flags&0x3f,us);blocks,nodes=parse_block_info(meta)
            stats["metadata_ok"]+=1
            total_u=sum(u for u,_,_ in blocks)
            if total_u>192*1024*1024:
                stats["oversize_skipped"]+=1;f.seek(start+size);continue
            data_pos=aligned if flags&0x80 else meta_pos+cs
            if not (flags&0x80) and (flags&0x200):data_pos=start+align16(data_pos-start)
            f.seek(data_pos)
            parts=[]
            for u,cc,bfl in blocks:
                raw=f.read(cc)
                if len(raw)!=cc:raise ValueError("data block truncated")
                parts.append(decomp(raw,bfl&0x3f,u))
            data=b"".join(parts);decoded_total+=len(data);stats["payloads_decoded"]+=1

            low=data.lower()
            ascii_hits=[]
            for tok in TABLE_TOKENS:
                cnt=low.count(tok.lower())
                if cnt:ascii_hits.append((tok.decode("ascii","ignore"),cnt))

            known_ids=[]
            for hid in KNOWN_HERO_NAMES:
                if struct.pack("<I",hid) in data:known_ids.append(hid)
            known_names=[]
            for hid,name in KNOWN_HERO_NAMES.items():
                if name.lower().encode() in low:known_names.append((hid,name))

            unknown_hits={}
            for n in UNKNOWN_IDS:
                le=all_positions(data,struct.pack("<I",n),50)
                asc=all_positions(data,str(n).encode(),50)
                if le or asc:unknown_hits[n]=(le,asc)
            dom_le=all_positions(data,struct.pack("<I",DOMINATOR_ID),40)
            dom_asc=all_positions(data,str(DOMINATOR_ID).encode(),40)

            # Drone calibration by exact config IDs and semantic UAV token.
            drone_ids=[n for n in DRONE_CFG_IDS if struct.pack("<I",n) in data]

            dense=(len(known_ids)>=6 and (len(known_names)>=1 or any(t[0] in ("LW_Hero","HeroTemplate","HeroAppearance") for t in ascii_hits)))
            if dense:
                hero_dense.append((start,size,len(data),nodes,known_ids,known_names,ascii_hits,unknown_hits))
            if ascii_hits:
                token_bundles.append((start,size,len(data),nodes,ascii_hits,known_ids,known_names,drone_ids))

            if ascii_hits or unknown_hits or dom_le or dom_asc or dense or len(drone_ids)>=5:
                interesting.append((start,size,len(data),len(nodes),ascii_hits,known_ids,known_names,drone_ids,unknown_hits,len(dom_le),len(dom_asc)))

            for n,(le,asc) in unknown_hits.items():
                for mode,poss in (("le32",le),("ascii",asc)):
                    for p in poss[:24]:
                        nd=node_for(nodes,p)
                        target_contexts[n].append((start,size,len(data),mode,p,nd,nearby_strings(data,p)))
            # Dominator context only when the same bundle has a dominator token, to
            # avoid exporting unrelated integer 1000000 occurrences.
            if dom_le or dom_asc:
                has_dom_token=any("dominator" in t.lower() for t,_ in ascii_hits)
                if has_dom_token:
                    for mode,poss in (("le32",dom_le),("ascii",dom_asc)):
                        for p in poss[:16]:
                            target_contexts[DOMINATOR_ID].append((start,size,len(data),mode,p,node_for(nodes,p),nearby_strings(data,p)))

            f.seek(start+size)
        except Exception as e:
            errors[type(e).__name__]+=1;stats["bundle_fail"]+=1
            try:f.seek(start+1)
            except Exception:break

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 26 DECODED PAYLOAD INDEX\n")
    o.write("OFFLINE ONLY · static installed UnityFS payloads · no private account identifiers\n\n")
    o.write("PHASE25_INTERPRETATION\n")
    o.write("  metadata_decoder_fixed=true\n")
    o.write("  semantic_node_paths_absent_does_not_mean_semantic_payload_absent=true\n")
    o.write("  strategy=scan_decoded_payload_content_not_node_filename\n")
    o.write("  numeric_proximity_is_not_identity_mapping=true\n\n")

    o.write("DECODE_STATS\n")
    for k in ("metadata_ok","payloads_decoded","oversize_skipped","bundle_fail"):
        o.write(f"  {k}={stats[k]}\n")
    o.write(f"  decodedBytes={decoded_total}\n")
    o.write(f"  tokenBundles={len(token_bundles)}\n")
    o.write(f"  heroDenseBundles={len(hero_dense)}\n")
    o.write(f"  interestingBundles={len(interesting)}\n")
    if errors:
        o.write("  errors="+",".join(f"{k}:{v}" for k,v in errors.most_common())+"\n")

    o.write("\nEXACT_TABLE_TOKEN_BUNDLES\n")
    for start,size,dlen,nodes,toks,kids,knames,dids in token_bundles[:180]:
        o.write(f"  bundleOffset={start} bundleSize={size} decodedBytes={dlen} nodes={len(nodes)}\n")
        o.write("    tokens="+",".join(f"{t}:{c}" for t,c in toks)+"\n")
        if kids:o.write("    knownHeroIdsLE="+",".join(map(str,kids))+"\n")
        if knames:o.write("    knownHeroNamesASCII="+",".join(f"{i}:{n}" for i,n in knames)+"\n")
        if dids:o.write("    droneCfgIdsLE="+",".join(map(str,dids))+"\n")
        for off,nsize,nfl,path in nodes[:12]:o.write(f"    node off={off} size={nsize} flags=0x{nfl:x} path={path}\n")

    o.write("\nHERO_DENSE_BUNDLES\n")
    for start,size,dlen,nodes,kids,knames,toks,uh in hero_dense[:100]:
        o.write(f"  bundleOffset={start} bundleSize={size} decodedBytes={dlen}\n")
        o.write("    knownHeroIdsLE="+",".join(map(str,kids))+"\n")
        if knames:o.write("    knownHeroNamesASCII="+",".join(f"{i}:{n}" for i,n in knames)+"\n")
        if toks:o.write("    tokens="+",".join(f"{t}:{c}" for t,c in toks)+"\n")
        if uh:o.write("    unknownIdsPresent="+",".join(map(str,sorted(uh)))+"\n")
        for off,nsize,nfl,path in nodes[:12]:o.write(f"    node off={off} size={nsize} flags=0x{nfl:x} path={path}\n")

    o.write("\nTARGET_ID_CONTEXTS\n")
    for n in (*UNKNOWN_IDS,DOMINATOR_ID):
        rows=target_contexts.get(n,[])
        o.write(f"  targetId={n} contexts={len(rows)}\n")
        for start,size,dlen,mode,p,nd,vals in rows[:60]:
            o.write(f"    bundleOffset={start} bundleSize={size} decodedBytes={dlen} encoding={mode} logicalOffset={p}\n")
            if nd:
                o.write(f"      node off={nd[0]} size={nd[1]} flags=0x{nd[2]:x} path={nd[3]}\n")
            else:o.write("      node=unmapped\n")
            if vals:o.write("      nearbyStrings="+" | ".join(vals[:28])+"\n")

    o.write("\nDRONE_PAYLOAD_CANDIDATES\n")
    shown=0
    for start,size,dlen,nc,toks,kids,knames,dids,uh,dle,dasc in interesting:
        if len(dids)<5 and not any(("drone" in t.lower() or "uav" in t.lower() or "tacticalchip" in t.lower() or "lw_drone_skill" in t.lower()) for t,_ in toks):continue
        o.write(f"  bundleOffset={start} bundleSize={size} decodedBytes={dlen} droneCfgIdsLE={','.join(map(str,dids)) if dids else '-'}\n")
        if toks:o.write("    tokens="+",".join(f"{t}:{c}" for t,c in toks)+"\n")
        shown+=1
        if shown>=100:break

    o.write("\nEVIDENCE_RULE\n")
    o.write("  accepted_mapping_requires=decoded_template_row_with_explicit_id_plus_name_or_localization_key_and_calibration_consistency\n")
    o.write("  nearbyStrings_are_forensic_context_only=true\n")
    o.write("  unknown_hero_ids_are_not_guessed=true\n")
    o.write("  next=extract_serialized_node_from_best_hero_dense_or_LW_Hero_token_bundle_and_parse_row_boundaries\n")

print(f"OUTPUT={out_path} META={stats['metadata_ok']} PAYLOADS={stats['payloads_decoded']} TOKENS={len(token_bundles)} DENSE={len(hero_dense)}")
PYEOF

python "$PY" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"
printf '%s\n' "=== PHASE 26 TERMINEE ===" "Aucune connexion Last War n'a été effectuée." "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE26_DECODED_PAYLOAD_INDEX_REDACTED.txt"
