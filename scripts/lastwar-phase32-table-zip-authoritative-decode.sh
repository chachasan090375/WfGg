#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 32
# OFFLINE ONLY. Opens the authoritative nested table container discovered in Phase 28
# as the ZIP archive it actually is, then inspects the real LW_Hero / appearance /
# Drone / Dominator members. No Last War network connection. No gameplay automation.

PKG="com.fun.lastwar.gp"
DOWNLOADS="${HOME}/storage/downloads"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE32_TABLE_ZIP_AUTHORITATIVE_DECODE_REDACTED.txt"
PY="${TMPDIR:-${HOME}/.cache}/wfgg-phase32-table-zip.py"

mkdir -p "$(dirname "$PY")"
command -v python >/dev/null 2>&1 || { echo "ERREUR: python Termux absent" >&2; exit 1; }
command -v pm >/dev/null 2>&1 || { echo "ERREUR: commande Android pm absente" >&2; exit 1; }

mapfile -t APK_PATHS < <(pm path "$PKG" 2>/dev/null | sed -n 's/^package://p')
if [[ ${#APK_PATHS[@]} -eq 0 ]]; then
  mapfile -t APK_PATHS < <(cmd package path "$PKG" 2>/dev/null | sed -n 's/^package://p')
fi
[[ ${#APK_PATHS[@]} -gt 0 ]] || { echo "ERREUR: installation Last War introuvable ($PKG)" >&2; exit 1; }

cat > "$PY" <<'PYEOF'
import gzip, hashlib, io, json, os, re, struct, sys, zipfile, zlib
from collections import Counter

out_path,*apk_paths=sys.argv[1:]
TABLE_RX=re.compile(r'^assets/table/table_[^/]+\.data$',re.I)
KNOWN={
 30002:'Loki',30003:'Kane',30004:'Ambolt',30005:'Gump',40007:'Elsa',40008:'Farhad',40009:'Richard',40013:'Braz',40015:'Cage',40016:'Maxwell',40020:'Monica',
 50006:'Murphy',50007:'Williams',50008:'Marshall',50009:'Kimberly',50010:'Stetmann',50013:'McGregor',50014:'Fiona',50015:'Swift',50018:'Schuyler',50019:'Carlie',50020:'Morrison',50021:'Lucius',50022:'Adam'
}
TARGETS=list(KNOWN)+[50016,50017]

# Find the 19,270,680-byte container seen in Phase 28, but keep discovery generic.
container=None
source=None
for apk in apk_paths:
    try:
        with zipfile.ZipFile(apk) as z:
            cands=[zi for zi in z.infolist() if TABLE_RX.match(zi.filename)]
            cands.sort(key=lambda zi:(abs(zi.file_size-19270680),-zi.file_size))
            for zi in cands:
                try:data=z.read(zi)
                except Exception:continue
                if data.startswith(b'PK\x03\x04'):
                    container=data;source=(os.path.basename(apk),zi.filename,zi.file_size);break
            if container is not None:break
    except Exception:
        pass
if container is None:
    raise SystemExit('nested ZIP table container introuvable')

inner=zipfile.ZipFile(io.BytesIO(container))
infos=inner.infolist()

# Inner table names are the authoritative table catalogue.
def norm(s):return re.sub(r'[^a-z0-9]+','_',s.lower()).strip('_')
def interesting_name(name):
    n=norm(name)
    terms=('lw_hero','heroappearance','hero_appearance','dominator','drone','uav','skill_chip','tactical_chip')
    return any(t in n for t in terms)

interesting=[zi for zi in infos if interesting_name(zi.filename)]
# Prioritize exact primary tables first.
def pri(zi):
    n=norm(zi.filename)
    exact=['lw_hero','heroappearance','hero_appearance','lw_hero_appearance_opt','lw_drone_skill','dominator_main','dominator']
    for i,x in enumerate(exact):
        if n==x:return (i,zi.filename)
    return (100,zi.filename)
interesting.sort(key=pri)

# Low-level helpers for opaque table payloads.
def printable_ratio(b):
    if not b:return 0.0
    return sum(1 for x in b if x in (9,10,13) or 32<=x<127)/len(b)

def ascii_strings(b,minlen=4):
    return [m.group().decode('ascii','ignore') for m in re.finditer(rb'[ -~]{%d,}'%minlen,b)]

def varint(n):
    out=[]
    while True:
        x=n&0x7f;n>>=7
        if n:out.append(x|0x80)
        else:out.append(x);return bytes(out)

def positions(blob,pat,limit=30):
    out=[];p=0
    while len(out)<limit:
        p=blob.find(pat,p)
        if p<0:break
        out.append(p);p+=1
    return out

def context_strings(blob,pos,radius=180):
    a=max(0,pos-radius);b=min(len(blob),pos+radius)
    vals=ascii_strings(blob[a:b],3)
    clean=[]
    for s in vals:
        s=s.strip()
        if s and s not in clean:clean.append(s)
    return clean[:18]

def hex_window(blob,pos,radius=32):
    a=max(0,pos-radius);b=min(len(blob),pos+radius)
    return blob[a:b].hex()

def maybe_unwrap(data):
    layers=[];cur=data
    for _ in range(3):
        nxt=None;kind=None
        try:
            if cur.startswith(b'\x1f\x8b'):
                nxt=gzip.decompress(cur);kind='gzip'
            elif cur.startswith(b'PK\x03\x04'):
                # Do not recursively explode arbitrary archives; just flag.
                kind='zip';break
            else:
                for wbits,label in ((zlib.MAX_WBITS,'zlib'),(-zlib.MAX_WBITS,'deflate')):
                    try:
                        x=zlib.decompress(cur,wbits)
                        if len(x)>len(cur)//2:
                            nxt=x;kind=label;break
                    except Exception:pass
        except Exception:pass
        if nxt is None:break
        layers.append((kind,len(cur),len(nxt)));cur=nxt
    return cur,layers

def json_probe(blob):
    t=blob.lstrip()
    if not t.startswith((b'{',b'[')):return None
    try:
        obj=json.loads(blob.decode('utf-8'))
        return type(obj).__name__
    except Exception:return None

# Generic protobuf-wire probe: enough to recognize repeated records without claiming schema.
def read_varint(buf,p):
    v=0;shift=0;start=p
    while p<len(buf) and shift<70:
        x=buf[p];p+=1;v|=(x&0x7f)<<shift
        if not x&0x80:return v,p
        shift+=7
    raise ValueError

def protobuf_probe(buf,max_fields=20000):
    p=0;fields=Counter();steps=0
    try:
        while p<len(buf) and steps<max_fields:
            key,p2=read_varint(buf,p)
            fn=key>>3;wt=key&7
            if fn<=0 or fn>100000 or wt not in (0,1,2,5):return None
            p=p2;fields[(fn,wt)]+=1;steps+=1
            if wt==0:_,p=read_varint(buf,p)
            elif wt==1:p+=8
            elif wt==5:p+=4
            else:
                n,p=read_varint(buf,p)
                if n<0 or p+n>len(buf):return None
                p+=n
            if p>len(buf):return None
        if p==len(buf) and steps>=3:return fields
    except Exception:return None
    return None

# Attempt text row extraction only when the payload genuinely looks textual.
def text_rows(blob):
    if printable_ratio(blob)<0.75:return []
    try:t=blob.decode('utf-8','replace')
    except Exception:return []
    rows=[]
    for line in t.splitlines():
        if re.search(r'(?<!\d)(?:50006|50007|50008|50009|50010|50016|50017)(?!\d)',line):
            rows.append(line[:1200])
    return rows[:40]

with open(out_path,'w',encoding='utf-8') as o:
    o.write('WfGg Last War LAB — PHASE 32 TABLE ZIP AUTHORITATIVE DECODE\n')
    o.write('OFFLINE ONLY · nested static table archive · no private account identifiers\n\n')
    o.write('SOURCE\n')
    o.write(f'  apk={source[0]}\n  entry={source[1]}\n  bytes={source[2]}\n')
    o.write(f'  containerSha256={hashlib.sha256(container).hexdigest()}\n')
    o.write(f'  outerSignature={container[:4].hex()} nestedZipConfirmed={str(container.startswith(b"PK\\x03\\x04")).lower()}\n')
    o.write(f'  innerMembers={len(infos)}\n\n')

    o.write('AUTHORITATIVE_MEMBER_CATALOG\n')
    for zi in interesting[:300]:
        o.write(f'  name={zi.filename} compressed={zi.compress_size} uncompressed={zi.file_size} method={zi.compress_type}\n')
    o.write('\n')

    # Detect strongest candidates by exact normalized table name.
    primaries=[]
    for zi in interesting:
        n=norm(zi.filename)
        if n in ('lw_hero','heroappearance','hero_appearance','lw_hero_appearance_opt','lw_drone_skill','dominator_main','dominator'):
            primaries.append(zi)
    if not primaries:
        primaries=interesting[:40]

    o.write('PRIMARY_MEMBER_FORENSICS\n')
    for zi in primaries[:80]:
        raw=inner.read(zi)
        blob,layers=maybe_unwrap(raw)
        ss=ascii_strings(blob,4)
        pb=protobuf_probe(blob)
        o.write(f'  member={zi.filename}\n')
        o.write(f'    rawBytes={len(raw)} decodedBytes={len(blob)} sha256={hashlib.sha256(blob).hexdigest()} printableRatio={printable_ratio(blob):.4f}\n')
        o.write(f'    first32Hex={blob[:32].hex()} jsonProbe={json_probe(blob) or "none"} protobufWireProbe={"yes" if pb else "no"}\n')
        if layers:o.write('    unwrap='+';'.join(f'{k}:{a}->{b}' for k,a,b in layers)+'\n')
        if pb:o.write('    protobufTopFields='+','.join(f'{fn}/{wt}:{cnt}' for (fn,wt),cnt in pb.most_common(15))+'\n')
        o.write('    strings='+' | '.join(ss[:35])+'\n')
        rows=text_rows(blob)
        for r in rows:o.write(f'    textRow={r}\n')

        # Numeric calibration. Counts and nearby strings are evidence; never assign identity from proximity.
        for hid in TARGETS:
            pats=[('ascii',str(hid).encode()),('le32',struct.pack('<I',hid)),('be32',struct.pack('>I',hid)),('varint',varint(hid))]
            hits=[]
            for enc,pat in pats:
                ps=positions(blob,pat,8)
                if ps:hits.append((enc,ps))
            if hits:
                label=KNOWN.get(hid,'UNKNOWN')
                o.write(f'    heroId={hid} label={label} hits='+';'.join(f'{enc}:{len(ps)}@{",".join(map(str,ps))}' for enc,ps in hits)+'\n')
                # Show contexts only for the unknowns and two calibration rows to keep report compact.
                if hid in (50006,50010,50016,50017):
                    for enc,ps in hits[:2]:
                        for p in ps[:3]:
                            o.write(f'      context encoding={enc} offset={p} strings='+' | '.join(context_strings(blob,p))+'\n')
                            o.write(f'      hex={hex_window(blob,p)}\n')
        o.write('\n')

    o.write('INTERPRETATION_GUARDRAILS\n')
    o.write('  nested_table_container_is_real_zip=true\n')
    o.write('  member_name_is_authoritative_table_catalogue=true\n')
    o.write('  numeric_occurrence_alone_is_not_identity_mapping=true\n')
    o.write('  unknown_50016_50017_are_not_named_without_decoded_LW_Hero_record=true\n')
    o.write('  asset_token_proximity_is_not_identity_mapping=true\n')
    o.write('  next=decode_exact_LW_Hero_member_schema_then_join_appearance_to_icon_resource\n')

print(f'PHASE32_DONE members={len(infos)} interesting={len(interesting)} primary={len(primaries)} output={out_path}')
PYEOF

python "$PY" "$OUT" "${APK_PATHS[@]}"
chmod 600 "$OUT" 2>/dev/null || true
rm -f "$PY"

echo '=== PHASE 32 TERMINEE ==='
echo 'Aucune connexion Last War n’a été effectuée.'
echo 'Fichier à partager : Téléchargements/WFGG_LASTWAR_PHASE32_TABLE_ZIP_AUTHORITATIVE_DECODE_REDACTED.txt'
