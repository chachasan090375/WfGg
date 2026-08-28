#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 28
# OFFLINE ONLY. Inspects the installed static table container identified by
# Phase 27 and searches for the authoritative LW_Hero/HeroAppearance row layout.
# No Last War network connection. No gameplay automation.
# Privacy: static installed assets only; no credentials, account UUID/GUID/UID,
# player names, resource balances or private formation references.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
P27="${DOWNLOADS}/WFGG_LASTWAR_PHASE27_CONFIG_LOADER_DISCOVERY_REDACTED.txt"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE28_TABLE_CONTAINER_FORENSICS_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase28-table-container-forensics.py"

die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
[[ -s "$P27" ]] || die "Phase 27 absente: $P27"
command -v python >/dev/null 2>&1 || die "python Termux absent"
command -v pm >/dev/null 2>&1 || die "commande Android pm absente"
mkdir -p "$(dirname "$PY")"

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || die "installation Last War introuvable ($PKG)"

cat > "$PY" <<'PYEOF'
import hashlib, math, os, re, struct, sys, zipfile
from collections import Counter, defaultdict

p27_path,out_path,*apk_paths=sys.argv[1:]
TARGETS=(50016,50017)
KNOWN={
30002:"Loki",30003:"Kane",30004:"Ambolt",30005:"Gump",40007:"Elsa",40008:"Farhad",40009:"Richard",40013:"Braz",40015:"Cage",40016:"Maxwell",40020:"Monica",
50006:"Murphy",50007:"Williams",50008:"Marshall",50009:"Kimberly",50010:"Stetmann",50013:"McGregor",50014:"Fiona",50015:"Swift",50018:"Schuyler",50019:"Carlie",50020:"Morrison",50021:"Lucius",50022:"Adam"
}

with open(p27_path,"r",encoding="utf-8",errors="ignore") as f:
    p27=f.read()
m=re.search(r"source=[^:]+:(assets/table/[^\s]+\.data) size=(\d+) tokens=LW_Hero:(\d+)",p27)
expected_entry=m.group(1) if m else None
expected_size=int(m.group(2)) if m else None

# Locate the exact static table container reported by Phase 27. Phase 27 counted
# semantic tokens case-insensitively, so the container check must do the same.
# If the filename changed with a game update, accept only an assets/table/*.data
# entry that itself contains an LW_Hero token ignoring case.
chosen=None
for apk in apk_paths:
    try:z=zipfile.ZipFile(apk)
    except Exception:continue
    names=z.namelist()
    candidates=[]
    if expected_entry and expected_entry in names:candidates=[expected_entry]
    else:candidates=[n for n in names if n.startswith("assets/table/") and n.endswith(".data")]
    for name in candidates:
        try:raw=z.read(name)
        except Exception:continue
        if b"lw_hero" in raw.lower():
            chosen=(apk,name,raw);break
    z.close()
    if chosen:break
if not chosen:raise SystemExit("conteneur assets/table/*.data avec LW_Hero introuvable")
apk_path,entry,raw=chosen
raw_lower=raw.lower()

PRINTABLE=re.compile(rb"[\x20-\x7e]{4,}")
ASCII_BOUNDARY=lambda n: re.compile(rb"(?<![0-9])"+str(n).encode()+rb"(?![0-9])")

def all_positions(buf,needle,limit=None):
    out=[];p=0
    while True:
        p=buf.find(needle,p)
        if p<0:break
        out.append(p)
        if limit and len(out)>=limit:break
        p+=1
    return out

def varint(n):
    out=bytearray()
    while True:
        b=n&0x7f;n>>=7
        if n:out.append(b|0x80)
        else:out.append(b);break
    return bytes(out)

def printable_records(buf):
    return [(m.start(),m.end(),m.group().decode("ascii","ignore")) for m in PRINTABLE.finditer(buf)]

records=printable_records(raw)
starts=[a for a,_,_ in records]

def string_context(pos,radius=1200,limit=30):
    vals=[]
    lo=max(0,pos-radius);hi=min(len(raw),pos+radius)
    for a,b,s in records:
        if b<lo:continue
        if a>hi:break
        if s not in vals:vals.append(s[:220])
        if len(vals)>=limit:break
    return vals

def hexdump(pos,radius=96):
    lo=max(0,pos-radius);hi=min(len(raw),pos+radius)
    b=raw[lo:hi]
    rows=[]
    for i in range(0,len(b),16):
        chunk=b[i:i+16]
        hx=" ".join(f"{x:02x}" for x in chunk)
        asc="".join(chr(x) if 32<=x<127 else "." for x in chunk)
        rows.append(f"{lo+i:08x}  {hx:<47}  {asc}")
    return rows

def entropy(buf):
    if not buf:return 0.0
    c=Counter(buf);n=len(buf)
    return -sum((v/n)*math.log2(v/n) for v in c.values())

def nearest(pos,arr):
    if not arr:return None
    # arrays are tiny; deterministic and clear.
    x=min(arr,key=lambda p:abs(p-pos))
    return x,pos-x

# Table-name markers are located case-insensitively because the static container
# may normalize names differently from the runtime strings in LWScripts.data.
table_tokens=(b"LW_Hero",b"HeroAppearance",b"LW_Hero_Rank",b"LW_Hero_Para",b"HeroTemplateManager",b"DataConfig")
token_positions={t.decode():all_positions(raw_lower,t.lower()) for t in table_tokens}

# Numeric representations. None of these alone proves identity; they only help
# locate candidate row regions for later structural decoding.
enc_positions=defaultdict(dict)
for n in list(KNOWN)+list(TARGETS):
    enc_positions[n]["ascii"]=[m.start() for m in ASCII_BOUNDARY(n).finditer(raw)]
    enc_positions[n]["le32"]=all_positions(raw,struct.pack("<I",n))
    enc_positions[n]["be32"]=all_positions(raw,struct.pack(">I",n))
    enc_positions[n]["varint"]=all_positions(raw,varint(n))

# Calibration windows around target occurrences: count how many established hero
# IDs use the same encoding within +/- 64 KiB. This is a topology clue only.
cal_windows=[]
for target in TARGETS:
    for enc in ("ascii","le32","varint"):
        for p in enc_positions[target][enc][:80]:
            lo=max(0,p-65536);hi=min(len(raw),p+65536)
            known_here=[]
            for n in KNOWN:
                if any(lo<=q<hi for q in enc_positions[n][enc]):known_here.append(n)
            lw_near=nearest(p,token_positions["LW_Hero"])
            app_near=nearest(p,token_positions["HeroAppearance"])
            cal_windows.append((len(known_here),target,enc,p,known_here,lw_near,app_near))
cal_windows.sort(key=lambda x:(-x[0],x[1],x[2],x[3]))

# Detect text-like rows containing exact IDs. This will immediately expose a CSV,
# TSV, JSON-lines or other delimiter-based table if present.
line_candidates=defaultdict(list)
line_start=0
for line in raw.splitlines(keepends=True):
    if len(line)<=8192:
        for n in list(KNOWN)+list(TARGETS):
            if ASCII_BOUNDARY(n).search(line):
                txt="".join(chr(x) if 32<=x<127 else " " for x in line[:2000])
                txt=re.sub(r"\s+"," ",txt).strip()
                if txt and len(line_candidates[n])<12:line_candidates[n].append((line_start,txt))
    line_start+=len(line)

# Inspect possible string length/index structure around table-name markers.
marker_headers=[]
for label,poses in token_positions.items():
    for p in poses[:20]:
        vals=[]
        for rel in (-16,-12,-8,-4,0,4,8,12,16):
            q=p+rel
            if 0<=q<=len(raw)-4:
                vals.append((rel,struct.unpack_from("<I",raw,q)[0],struct.unpack_from(">I",raw,q)[0]))
        marker_headers.append((label,p,vals,string_context(p,500,12)))

# Common file/container signatures.
signatures={
    "SQLite":b"SQLite format 3\x00","UnityFS":b"UnityFS","gzip":b"\x1f\x8b",
    "zstd":b"\x28\xb5\x2f\xfd","lz4frame":b"\x04\x22\x4d\x18","xz":b"\xfd7zXZ\x00",
    "json_object":b"{","json_array":b"["
}
sig_hits={k:all_positions(raw,v,20) for k,v in signatures.items() if v and v in raw}

with open(out_path,"w",encoding="utf-8") as o:
    o.write("WfGg Last War LAB — PHASE 28 TABLE CONTAINER FORENSICS\n")
    o.write("OFFLINE ONLY · static installed table data · no private account identifiers\n\n")
    o.write("SOURCE\n")
    o.write(f"  apk={os.path.basename(apk_path)}\n")
    o.write(f"  entry={entry}\n")
    o.write(f"  expectedSize={expected_size if expected_size is not None else '-'} actualSize={len(raw)}\n")
    o.write(f"  sha256={hashlib.sha256(raw).hexdigest()}\n")
    sample=raw[:min(len(raw),2*1024*1024)]
    pr=sum(1 for b in sample if b in (9,10,13) or 32<=b<127)/max(1,len(sample))
    o.write(f"  samplePrintableRatio={pr:.4f} sampleEntropy={entropy(sample):.4f}\n")
    o.write(f"  first64Hex={raw[:64].hex()}\n")
    o.write(f"  signatures={';'.join(f'{k}:{v}' for k,v in sig_hits.items()) or '-'}\n")
    o.write("  tableTokenMatching=case_insensitive\n")

    o.write("\nTABLE_TOKEN_POSITIONS\n")
    for label in token_positions:
        ps=token_positions[label]
        o.write(f"  token={label} count={len(ps)} positions={','.join(map(str,ps[:40])) or '-'}\n")

    o.write("\nMARKER_HEADER_PATTERNS\n")
    for label,p,vals,ctx in marker_headers:
        o.write(f"  token={label} offset={p}\n")
        o.write("    u32Around="+";".join(f"rel{rel}:le={le}:be={be}" for rel,le,be in vals)+"\n")
        if ctx:o.write("    strings="+" | ".join(ctx)+"\n")

    o.write("\nNUMERIC_ENCODING_COUNTS\n")
    for n in list(KNOWN)+list(TARGETS):
        label=KNOWN.get(n,"UNKNOWN")
        d=enc_positions[n]
        o.write(f"  heroId={n} label={label} ascii={len(d['ascii'])} le32={len(d['le32'])} be32={len(d['be32'])} varint={len(d['varint'])}\n")

    o.write("\nTARGET_CALIBRATION_WINDOWS\n")
    shown=0
    for score,target,enc,p,known_here,lw_near,app_near in cal_windows:
        if shown>=40:break
        if score==0 and shown>=12:break
        o.write(f"  heroId={target} encoding={enc} offset={p} establishedHeroIdsWithin64KiB={score}\n")
        o.write(f"    known={','.join(map(str,known_here)) or '-'}\n")
        o.write(f"    nearestLW_Hero={lw_near if lw_near else '-'} nearestHeroAppearance={app_near if app_near else '-'}\n")
        o.write("    strings="+" | ".join(string_context(p,900,18))+"\n")
        for row in hexdump(p,64):o.write("    "+row+"\n")
        shown+=1

    o.write("\nTEXT_ROW_CANDIDATES\n")
    for n in list(KNOWN)+list(TARGETS):
        rows=line_candidates.get(n,[])
        if not rows:continue
        o.write(f"  heroId={n} label={KNOWN.get(n,'UNKNOWN')} rows={len(rows)}\n")
        for off,txt in rows:o.write(f"    offset={off} row={txt}\n")

    o.write("\nTARGET_RAW_OCCURRENCE_SUMMARY\n")
    for n in TARGETS:
        for enc in ("ascii","le32","be32","varint"):
            ps=enc_positions[n][enc]
            o.write(f"  heroId={n} encoding={enc} count={len(ps)} positions={','.join(map(str,ps[:60])) or '-'}\n")

    o.write("\nINTERPRETATION_GUARDRAILS\n")
    o.write("  exact_ascii_numeric_boundary_enabled=true\n")
    o.write("  numeric_occurrence_alone_is_not_identity_mapping=true\n")
    o.write("  proximity_to_Tesla_or_DVA_asset_name_is_not_identity_mapping=true\n")
    o.write("  unknown_hero_ids_are_not_guessed=true\n")
    o.write("  accepted_mapping_requires=decoded_LW_Hero_row_or_equivalent_runtime_record_with_explicit_heroId_and_name_or_localization_key\n")
    o.write("  next=derive_container_record_structure_from_marker_headers_and_calibrated_known_hero_rows_then_extract_50016_50017_authoritatively\n")
PYEOF

python "$PY" "$P27" "$OUT" "${APK_PATHS[@]}"
printf 'Phase 28 terminée.\nFichier : %s\n' "$OUT"
