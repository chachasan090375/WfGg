#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 25
# OFFLINE ONLY. Repairs UnityFS v7+ metadata alignment used by Phase 24,
# then isolates semantic bundle/node candidates for Hero/Dominator/Drone catalogs.
# No Last War network connection. No gameplay automation.
# Privacy: no credentials, account UUID/GUID/UID, player names or balances.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE25_UNITYFS_METADATA_REPAIR_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase25-unityfs-metadata-repair.py"

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
import io, os, re, struct, sys, zipfile, lzma
from collections import Counter

out_path,*apk_paths=sys.argv[1:]
ENTRY="assets/AssetBundles/BundleFragment0.bytes"
found=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            try: info=z.getinfo(ENTRY)
            except KeyError: continue
            found=(apk,info)
            break
    except Exception:
        pass
if not found:
    raise SystemExit("BundleFragment0.bytes introuvable")
apk,info=found

# UnityFS helpers ---------------------------------------------------------------
def read_cstr(f, maxlen=16384):
    b=bytearray()
    while len(b)<maxlen:
        c=f.read(1)
        if not c: raise EOFError("cstr eof")
        if c==b"\0": return bytes(b)
        b += c
    raise ValueError("cstr too long")

def align16(n):
    return (n+15)&~15

def lz4_block(src, expected=None):
    src=memoryview(src); i=0; out=bytearray()
    while i < len(src):
        token=src[i]; i+=1
        lit=token>>4
        if lit==15:
            while True:
                if i>=len(src): raise ValueError("lz4 literal overflow")
                x=src[i]; i+=1; lit+=x
                if x!=255: break
        if i+lit>len(src): raise ValueError("lz4 literal out of range")
        out += src[i:i+lit]; i+=lit
        if i>=len(src): break
        if i+2>len(src): raise ValueError("lz4 offset eof")
        off=src[i] | (src[i+1]<<8); i+=2
        if off<=0 or off>len(out): raise ValueError("lz4 bad offset")
        ml=(token&0x0f)+4
        if (token&0x0f)==15:
            while True:
                if i>=len(src): raise ValueError("lz4 match overflow")
                x=src[i]; i+=1; ml+=x
                if x!=255: break
        pos=len(out)-off
        for _ in range(ml):
            out.append(out[pos]); pos+=1
    if expected is not None and len(out)!=expected:
        # Unity bundles should match exactly; keep data but expose mismatch upstream.
        pass
    return bytes(out)

def decomp(blob, typ, expected=None):
    typ &= 0x3f
    if typ==0: return blob
    if typ in (2,3): return lz4_block(blob, expected)
    if typ==1:
        # UnityFS LZMA is normally a complete LZMA stream. Try common decoders.
        for fmt in (lzma.FORMAT_AUTO, lzma.FORMAT_ALONE):
            try: return lzma.decompress(blob, format=fmt)
            except Exception: pass
        raise ValueError("lzma decode failed")
    raise ValueError(f"unknown compression {typ}")

def parse_block_info(raw):
    if raw is None or len(raw)<20: raise ValueError("blockinfo too short")
    p=16 # 128-bit uncompressed data hash
    bc=struct.unpack_from(">I",raw,p)[0]; p+=4
    if bc>200000: raise ValueError(f"bad block count {bc}")
    blocks=[]
    for _ in range(bc):
        if p+10>len(raw): raise ValueError("block list truncated")
        u,c,fl=struct.unpack_from(">IIH",raw,p); p+=10
        blocks.append((u,c,fl))
    if p+4>len(raw): raise ValueError("node count missing")
    nc=struct.unpack_from(">I",raw,p)[0]; p+=4
    if nc>200000: raise ValueError(f"bad node count {nc}")
    nodes=[]
    for _ in range(nc):
        if p+20>len(raw): raise ValueError("node record truncated")
        off,size,fl=struct.unpack_from(">qqI",raw,p); p+=20
        e=raw.find(b"\0",p)
        if e<0: raise ValueError("node path unterminated")
        path=raw[p:e].decode("utf-8","ignore"); p=e+1
        nodes.append((off,size,fl,path))
    return blocks,nodes

SEMANTIC=("hero","dominator","tactical","chip","uav","drone","weapon","config","template","appearance")
STRONG=("lw_hero","heroappearance","lw_drone_skill","dominator","tacticalchip","tacticalweapon","lwdronbattlesystem","lwdron", "drone")
ASCII_TARGETS=(b"LW_Hero",b"HeroAppearance",b"LW_Drone_Skill",b"DominatorMainTemplate",b"dominator_id",b"TacticalChipManager",b"TWSkillChipTemplate",b"50016",b"50017",b"1000000")

stats=Counter(); errors=Counter(); candidates=[]; headers=[]

# We scan sequentially. Correct UnityFS rule: format >= 7 aligns header end to 16.
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    total=info.file_size
    while f.tell()<total:
        start=f.tell()
        sig=f.read(8)
        if not sig: break
        if not sig.startswith(b"UnityFS"):
            # Find next signature inside a bounded forward window.
            buf=sig+f.read(min(2*1024*1024,total-f.tell()))
            q=buf.find(b"UnityFS\0")
            if q<0:
                continue
            start=start+q; f.seek(start)
        try:
            if read_cstr(f)!=b"UnityFS":
                f.seek(start+1); continue
            fmt=struct.unpack(">I",f.read(4))[0]
            unity=read_cstr(f).decode("ascii","ignore")
            rev=read_cstr(f).decode("ascii","ignore")
            size=struct.unpack(">Q",f.read(8))[0]
            cs=struct.unpack(">I",f.read(4))[0]
            us=struct.unpack(">I",f.read(4))[0]
            flags=struct.unpack(">I",f.read(4))[0]
            hend=f.tell()
            if not (1 <= fmt <= 20): raise ValueError(f"fmt {fmt}")
            if size<=0 or start+size>total+16: raise ValueError(f"size {size}")
            if cs<=0 or cs>128*1024*1024 or us<=0 or us>256*1024*1024:
                raise ValueError(f"meta sizes {cs}/{us}")
            stats["headers_ok"]+=1
            if len(headers)<30: headers.append((start,size,fmt,flags,cs,us,unity,rev,hend-start))

            # UnityFS v7+ aligns after the header before blocks-info.
            aligned_header = start + align16(hend-start) if fmt>=7 else hend
            if flags & 0x80:
                stats["metadata_at_end"]+=1
                meta_pos=start+size-cs
            else:
                meta_pos=aligned_header
            if not (start <= meta_pos <= start+size-cs): raise ValueError("meta pos")
            f.seek(meta_pos)
            comp=f.read(cs)
            if len(comp)!=cs: raise ValueError("meta compressed truncated")
            typ=flags&0x3f
            try:
                meta=decomp(comp,typ,us)
            except Exception as e:
                errors["metadata_decompress"]+=1
                if len(candidates)<20:
                    candidates.append({"kind":"meta_error","start":start,"size":size,"fmt":fmt,"flags":flags,"detail":str(e)[:180]})
                f.seek(start+size); continue
            if len(meta)!=us:
                errors["metadata_size_mismatch"]+=1
            try:
                blocks,nodes=parse_block_info(meta)
            except Exception as e:
                errors["metadata_parse"]+=1
                if len(candidates)<20:
                    candidates.append({"kind":"parse_error","start":start,"size":size,"fmt":fmt,"flags":flags,"detail":str(e)[:180],"metaPrefix":meta[:32].hex()})
                f.seek(start+size); continue
            stats["metadata_ok"]+=1
            stats["nodes_total"]+=len(nodes)
            stats["blocks_total"]+=len(blocks)

            sem=[n for n in nodes if any(k in n[3].lower() for k in SEMANTIC)]
            strong=[n for n in nodes if any(k in n[3].lower() for k in STRONG)]
            if sem:
                stats["semantic_bundles"]+=1
                candidates.append({"kind":"semantic","start":start,"size":size,"fmt":fmt,"flags":flags,"compression":typ,"blocks":blocks,"nodes":nodes,"semantic":sem,"strong":strong,"headerEnd":hend,"alignedHeader":aligned_header,"metaPos":meta_pos})
            f.seek(start+size)
        except Exception as e:
            errors[type(e).__name__]+=1
            stats["header_or_bundle_fail"]+=1
            try: f.seek(start+1)
            except Exception: break

# Second pass: only semantic candidates; decompress bundle data and look for strong
# catalog tokens. This does not interpret numeric proximity as an identity mapping.
strong_hits=[]
with zipfile.ZipFile(apk) as z, z.open(info) as f:
    for c in [x for x in candidates if x.get("kind")=="semantic"][:350]:
        try:
            start=c["start"]; size=c["size"]; flags=c["flags"]; blocks=c["blocks"]
            if flags & 0x80:
                data_pos=c["alignedHeader"]
            else:
                data_pos=c["metaPos"] + struct.unpack(">I", b"\x00\x00\x00\x00")[0] # placeholder 0
                # Actual data starts after compressed metadata.
                # Re-read cs from cached header tuple is not stored; derive from first pass header table below is unsafe.
                # Use metadata location plus compressed size by reparsing header now.
                f.seek(start)
                read_cstr(f); fmt=struct.unpack(">I",f.read(4))[0]; read_cstr(f); read_cstr(f)
                f.read(8); cs=struct.unpack(">I",f.read(4))[0]; f.read(4); f.read(4)
                data_pos=c["metaPos"]+cs
                if flags & 0x200: data_pos=start+align16(data_pos-start)
            f.seek(data_pos)
            parts=[]; total_u=0
            # Cap candidate expansion to 96 MiB to protect the phone.
            if sum(u for u,_,_ in blocks)>96*1024*1024:
                continue
            for u,csz,bfl in blocks:
                blob=f.read(csz)
                if len(blob)!=csz: raise ValueError("data block truncated")
                parts.append(decomp(blob,bfl&0x3f,u)); total_u+=u
            data=b"".join(parts)
            hits=[]
            low=data.lower()
            for t in ASCII_TARGETS:
                count=low.count(t.lower())
                if count: hits.append((t.decode("ascii","ignore"),count))
            # Also exact little-endian integer occurrences, but only as forensic hits.
            ints=[]
            for n in (50016,50017,1000000):
                cnt=data.count(struct.pack("<I",n))
                if cnt: ints.append((n,cnt))
            if hits or ints or c.get("strong"):
                strong_hits.append((c,hits,ints,len(data)))
        except Exception as e:
            errors["candidate_data_decode"]+=1

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 25 UNITYFS METADATA REPAIR\n")
    o.write("OFFLINE ONLY · corrected UnityFS v7+ alignment · no private account identifiers\n\n")
    o.write("PHASE24_ROOT_CAUSE_TEST\n")
    o.write("  phase24_used_header_alignment_only_when_flag_0x200=true\n")
    o.write("  corrected_rule=format_version_ge_7_align_header_to_16_before_blocks_info\n")
    o.write("  identity_mapping_from_numeric_proximity=false\n")

    o.write("\nUNITYFS_STATS\n")
    for k in ("headers_ok","metadata_ok","metadata_at_end","semantic_bundles","nodes_total","blocks_total","header_or_bundle_fail"):
        o.write(f"  {k}={stats[k]}\n")
    o.write(f"  fragmentSize={info.file_size}\n")
    o.write(f"  source={os.path.basename(apk)}:{ENTRY}\n")

    o.write("\nERROR_COUNTS\n")
    for k,v in errors.most_common(): o.write(f"  {k}={v}\n")

    o.write("\nHEADER_SAMPLES\n")
    for start,size,fmt,flags,cs,us,unity,rev,hlen in headers:
        o.write(f"  offset={start} size={size} format={fmt} flags=0x{flags:x} compressedMeta={cs} uncompressedMeta={us} rawHeaderLen={hlen} unity={unity}/{rev}\n")

    semc=[x for x in candidates if x.get("kind")=="semantic"]
    o.write("\nSEMANTIC_NODE_CANDIDATES\n")
    o.write(f"  candidateBundles={len(semc)}\n")
    for c in semc[:220]:
        o.write(f"  bundleOffset={c['start']} bundleSize={c['size']} format={c['fmt']} flags=0x{c['flags']:x} nodes={len(c['nodes'])} semanticNodes={len(c['semantic'])} strongNodes={len(c['strong'])}\n")
        for off,nsize,nfl,path in c["semantic"][:35]:
            o.write(f"    nodeOffset={off} nodeSize={nsize} nodeFlags=0x{nfl:x} path={path}\n")

    o.write("\nTARGET_TOKEN_HITS_IN_SEMANTIC_BUNDLES\n")
    o.write(f"  bundlesWithHits={len(strong_hits)}\n")
    for c,hits,ints,dlen in strong_hits[:220]:
        o.write(f"  bundleOffset={c['start']} bundleSize={c['size']} decodedBytes={dlen}\n")
        if hits: o.write("    ascii="+",".join(f"{t}:{n}" for t,n in hits)+"\n")
        if ints: o.write("    littleEndianInt32_forensic_only="+",".join(f"{n}:{cnt}" for n,cnt in ints)+"\n")
        for off,nsize,nfl,path in c.get("strong",[])[:20]:
            o.write(f"    strongNode path={path} nodeOffset={off} nodeSize={nsize}\n")

    o.write("\nEVIDENCE_RULE\n")
    o.write("  accepted_mapping_requires=decoded_template_row_with_explicit_id_and_name_or_localization_key\n")
    o.write("  numeric_substring_or_nearby_asset_is_not_mapping=true\n")
    o.write("  unknown_hero_ids_are_not_guessed=true\n")
    o.write("  next=decode_exact_serialized_nodes_from_target_token_bundles_then_extract_LW_Hero_rows_50016_50017_and_dominator_1000000\n")

print(f"OUTPUT={out_path} META_OK={stats['metadata_ok']} SEMANTIC={stats['semantic_bundles']} HITS={len(strong_hits)}")
PYEOF

python "$PY" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT"
rm -f "$PY"
printf '%s\n' "=== PHASE 25 TERMINEE ===" "Aucune connexion Last War n'a été effectuée." "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE25_UNITYFS_METADATA_REPAIR_REDACTED.txt"
