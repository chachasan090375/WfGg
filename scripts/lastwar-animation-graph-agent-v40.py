#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40 — deterministic Unity animation graph agent.

Purpose
-------
Build, on demand, an evidence graph from a catalogue asset to the runtime Unity objects that make it
move. The agent deliberately separates *proof* from interpretation:

- exact catalogue/Unity relations come from the V39 scanners and SoftReferencePrefab resolver;
- Assembly-CSharp.mdl is recovered read-only from the installed APK and parsed as a .NET assembly;
- method bodies are inspected for validated metadata tokens (calls/fields/user strings);
- motion recipes are inferred only from explicit API calls / serialized fields and carry confidence;
- no visual-similarity edge is ever promoted to an exact runtime dependency.

The cache lives outside the repository under ~/.cache/wfgg-lastwar-v40 and does not touch the V33
catalogue, visual audit or image-indexation state.
"""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import struct
import subprocess
import threading
import time
import zipfile

PKG = 'com.fun.lastwar.gp'
CACHE_ROOT = Path.home() / '.cache/wfgg-lastwar-v40'
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
CACHE_DB = CACHE_ROOT / 'animation-agent-v40.sqlite3'
ASSEMBLY_CACHE = CACHE_ROOT / 'Assembly-CSharp.recovered.dll'

_LOCK = threading.RLock()
_CLR_INDEX = None

ANIM_CALL_PATTERNS = [
    (re.compile(r'(^|\.)Transform\.(Rotate|RotateAround)$', re.I), 'continuous-rotation', 0.99),
    (re.compile(r'(^|\.)(Transform|RectTransform)\.set_(localRotation|localEulerAngles|rotation|eulerAngles)$', re.I), 'rotation-assignment', 0.98),
    (re.compile(r'(^|\.)Quaternion\.(Euler|AngleAxis|Slerp|Lerp)$', re.I), 'rotation-math', 0.92),
    (re.compile(r'(^|\.)Animator\.(Play|CrossFade|CrossFadeInFixedTime|SetTrigger|SetBool|SetFloat|SetInteger)$', re.I), 'animator-state', 0.98),
    (re.compile(r'(^|\.)Animation\.(Play|CrossFade|Blend)$', re.I), 'legacy-animation', 0.98),
    (re.compile(r'(^|\.)(GameObject|Component)\.SetActive$', re.I), 'state-switch', 0.90),
    (re.compile(r'(^|\.)(Object|UnityEngine\.Object)\.Instantiate$', re.I), 'runtime-instantiation', 0.90),
    (re.compile(r'(LoadAsset|LoadPrefab|Addressable|AssetBundle\.Load)', re.I), 'runtime-asset-load', 0.88),
    (re.compile(r'(^|\.)(DOTween|ShortcutExtensions|TweenSettingsExtensions)\.', re.I), 'tween', 0.95),
]


def _db():
    con = sqlite3.connect(CACHE_DB)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS graph_cache(
        stable_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        assembly_sha256 TEXT,
        payload_json TEXT NOT NULL
    )''')
    return con


def _now():
    return datetime.now(timezone.utc).isoformat()


def _apk_paths():
    out = []
    for cmd in (['cmd','package','path',PKG], ['pm','path',PKG]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            for line in p.stdout.splitlines():
                if line.startswith('package:'):
                    x = line.split(':',1)[1].strip()
                    if x and x not in out:
                        out.append(x)
        except Exception:
            pass
    return out


def recover_assembly_csharp():
    """Recover Assembly-CSharp.mdl read-only from the installed APK.

    The observed game build protects the canonical DOS header with XOR 0x13. We only restore bytes
    that exactly match that transform and cache the recovered DLL outside the repo.
    """
    entry = 'assets/Assemblies/Assembly-CSharp.mdl'
    data = None
    source = None
    for apk in _apk_paths():
        try:
            with zipfile.ZipFile(apk) as z:
                if entry in z.namelist():
                    data = bytearray(z.read(entry)); source = {'apk':apk,'entry':entry,'bytes':len(data)}; break
        except Exception:
            continue
    if data is None:
        raise RuntimeError('Assembly-CSharp.mdl introuvable dans les APK installés')
    original_sha = hashlib.sha256(data).hexdigest()
    canonical = bytes.fromhex('4d5a90000300000004000000ffff0000b80000')
    patched = []
    for i,b in enumerate(canonical):
        if i < len(data) and data[i] == (b ^ 0x13):
            data[i] = b; patched.append(i)
    if len(data) >= 2:
        data[0:2] = b'MZ'
    if data[:2] != b'MZ':
        raise RuntimeError('en-tête MZ non restaurable')
    ASSEMBLY_CACHE.write_bytes(data)
    return bytes(data), {'source':source,'originalSha256':original_sha,'patchedHeaderOffsets':patched,'cachePath':str(ASSEMBLY_CACHE)}


def _cidx_size(rows, tagbits, tids):
    limit = 1 << (16-tagbits)
    return 4 if max((rows.get(t,0) for t in tids), default=0) >= limit else 2


class CLRIndex:
    """Minimal .NET metadata + method-body index sufficient for runtime animation evidence."""
    def __init__(self, data: bytes, source_meta: dict):
        self.data = data
        self.source_meta = source_meta
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.sections = []
        self.streams = {}
        self.rows = {}
        self.types = []
        self.types_by_name = {}
        self.methods = [None]
        self.fields = [None]
        self.memberrefs = [None]
        self.type_refs = [None]
        self._parse()

    def u16(self,o): return struct.unpack_from('<H',self.data,o)[0]
    def u32(self,o): return struct.unpack_from('<I',self.data,o)[0]
    def u64(self,o): return struct.unpack_from('<Q',self.data,o)[0]

    def rva_to_off(self, rva):
        for s in self.sections:
            span=max(s['vsize'],s['rawsize'])
            if s['va'] <= rva < s['va']+span:
                return s['raw']+(rva-s['va'])
        if 0 <= rva < len(self.data): return rva
        raise ValueError('RVA hors sections: '+hex(rva))

    def _parse(self):
        d=self.data
        e_lfanew=self.u32(0x3c)
        if d[e_lfanew:e_lfanew+4] != b'PE\0\0': raise RuntimeError('PE absent')
        coff=e_lfanew+4; nsec=self.u16(coff+2); opt_size=self.u16(coff+16); opt=coff+20; magic=self.u16(opt)
        dd=opt+(96 if magic==0x10b else 112 if magic==0x20b else -1)
        if dd<0: raise RuntimeError('optional header PE non supporté')
        sec_off=opt+opt_size
        for i in range(nsec):
            o=sec_off+i*40
            self.sections.append({'name':d[o:o+8].split(b'\0',1)[0].decode('ascii','replace'),'vsize':self.u32(o+8),'va':self.u32(o+12),'rawsize':self.u32(o+16),'raw':self.u32(o+20)})
        clr_rva=self.u32(dd+14*8); clr=self.rva_to_off(clr_rva); meta=self.rva_to_off(self.u32(clr+8))
        if d[meta:meta+4] != b'BSJB': raise RuntimeError('métadonnées CLR BSJB absentes')
        ver_len=self.u32(meta+12); p=(meta+16+ver_len+3)&~3; streams=self.u16(p+2); p+=4
        for _ in range(streams):
            off=self.u32(p); size=self.u32(p+4); p+=8; end=d.find(b'\0',p,p+64)
            if end<0: raise RuntimeError('nom stream CLR invalide')
            name=d[p:end].decode('ascii','replace'); p=(end+1+3)&~3
            self.streams[name]={'offset':meta+off,'size':size}
        strings=self.streams['#Strings']; tables=self.streams.get('#~') or self.streams.get('#-')
        if not tables: raise RuntimeError('stream #~/#- absent')
        self._strings=strings; self._us=self.streams.get('#US')
        t=tables['offset']; heap=self.data[t+6]; valid=self.u64(t+8); q=t+24
        for tid in range(64):
            if (valid>>tid)&1:
                self.rows[tid]=self.u32(q); q+=4
        self._strsz=4 if heap&1 else 2; self._guidsz=4 if heap&2 else 2; self._blobsz=4 if heap&4 else 2
        idx=lambda tid:4 if self.rows.get(tid,0)>=65536 else 2
        c=lambda bits,*tids:_cidx_size(self.rows,bits,tids)
        sizes={
            0:2+self._strsz+self._guidsz*3,
            1:c(2,0,26,35,1)+self._strsz*2,
            2:4+self._strsz*2+c(2,1,2,27)+idx(4)+idx(6),
            3:idx(4),
            4:2+self._strsz+self._blobsz,
            5:idx(6),
            6:4+2+2+self._strsz+self._blobsz+idx(8),
            7:idx(8),
            8:2+2+self._strsz,
            9:idx(2)+c(2,1,2,27),
            10:c(3,2,1,26,6,27)+self._strsz+self._blobsz,
        }
        offs={}; cur=q
        for tid in range(11):
            if (valid>>tid)&1:
                if tid not in sizes: raise RuntimeError('table CLR non gérée avant MemberRef: '+str(tid))
                offs[tid]=cur; cur += sizes[tid]*self.rows.get(tid,0)
        self._sizes=sizes; self._offs=offs

        # TypeRef names.
        for rid in range(1,self.rows.get(1,0)+1):
            o=offs[1]+(rid-1)*sizes[1]; pos=o+c(2,0,26,35,1)
            name=self.str_at(self.read_idx(pos,self._strsz)); pos+=self._strsz
            ns=self.str_at(self.read_idx(pos,self._strsz))
            self.type_refs.append({'rid':rid,'name':name,'namespace':ns,'full':(ns+'.' if ns else '')+name})

        # MethodDefs.
        for rid in range(1,self.rows.get(6,0)+1):
            o=offs[6]+(rid-1)*sizes[6]
            name=self.str_at(self.read_idx(o+8,self._strsz))
            self.methods.append({'rid':rid,'rva':self.u32(o),'name':name,'owner':None})

        # FieldDefs.
        for rid in range(1,self.rows.get(4,0)+1):
            o=offs[4]+(rid-1)*sizes[4]
            name=self.str_at(self.read_idx(o+2,self._strsz))
            self.fields.append({'rid':rid,'name':name,'owner':None})

        # TypeDefs + field/method ranges.
        raw=[]
        for rid in range(1,self.rows.get(2,0)+1):
            o=offs[2]+(rid-1)*sizes[2]; pos=o+4
            name=self.str_at(self.read_idx(pos,self._strsz));pos+=self._strsz
            ns=self.str_at(self.read_idx(pos,self._strsz));pos+=self._strsz
            pos+=c(2,1,2,27)
            fstart=self.read_idx(pos,idx(4));pos+=idx(4);mstart=self.read_idx(pos,idx(6))
            raw.append({'rid':rid,'name':name,'namespace':ns,'full':(ns+'.' if ns else '')+name,'fieldStart':fstart,'methodStart':mstart})
        for i,ty in enumerate(raw):
            fend=(raw[i+1]['fieldStart']-1 if i+1<len(raw) else self.rows.get(4,0)); mend=(raw[i+1]['methodStart']-1 if i+1<len(raw) else self.rows.get(6,0))
            ty['fields']=[];ty['methods']=[]
            if ty['fieldStart']:
                for rid in range(max(1,ty['fieldStart']),min(fend,len(self.fields)-1)+1):
                    self.fields[rid]['owner']=ty['full'];ty['fields'].append(self.fields[rid])
            if ty['methodStart']:
                for rid in range(max(1,ty['methodStart']),min(mend,len(self.methods)-1)+1):
                    self.methods[rid]['owner']=ty['full'];ty['methods'].append(self.methods[rid])
            self.types.append(ty)
            for key in {ty['name'].casefold(),ty['full'].casefold()}:
                self.types_by_name.setdefault(key,[]).append(ty)

        # MemberRefs (method/field references). Parent name is enough for call evidence.
        parent_size=c(3,2,1,26,6,27)
        for rid in range(1,self.rows.get(10,0)+1):
            o=offs[10]+(rid-1)*sizes[10]
            coded=self.read_idx(o,parent_size); pos=o+parent_size
            name=self.str_at(self.read_idx(pos,self._strsz))
            tag=coded & 7; pr=coded >> 3
            owner=''
            if tag==0 and 0<pr<=len(raw): owner=raw[pr-1]['full']
            elif tag==1 and 0<pr<len(self.type_refs): owner=self.type_refs[pr]['full']
            elif tag==3 and 0<pr<len(self.methods): owner=self.methods[pr].get('owner') or ''
            elif tag==2: owner='ModuleRef#'+str(pr)
            elif tag==4: owner='TypeSpec#'+str(pr)
            self.memberrefs.append({'rid':rid,'name':name,'owner':owner,'full':(owner+'.' if owner else '')+name})

    def read_idx(self,o,sz): return self.u16(o) if sz==2 else self.u32(o)

    def str_at(self,idx):
        if not idx:return ''
        o=self._strings['offset']+idx; end=self.data.find(b'\0',o,self._strings['offset']+self._strings['size'])
        if end<0:end=min(len(self.data),o+512)
        return self.data[o:end].decode('utf-8','replace')

    def user_string(self,idx):
        if not self._us or not idx:return ''
        p=self._us['offset']+idx; end=self._us['offset']+self._us['size']
        if p>=end:return ''
        b0=self.data[p];p+=1
        if b0&0x80==0:n=b0
        elif b0&0xC0==0x80:
            if p>=end:return ''
            n=((b0&0x3f)<<8)|self.data[p];p+=1
        elif b0&0xE0==0xC0:
            if p+2>=end:return ''
            n=((b0&0x1f)<<24)|(self.data[p]<<16)|(self.data[p+1]<<8)|self.data[p+2];p+=3
        else:return ''
        raw=self.data[p:min(end,p+n)]
        if raw: raw=raw[:-1]  # terminal special-character flag
        try:return raw.decode('utf-16le','replace')[:500]
        except Exception:return ''

    def find_types(self,name):
        key=str(name or '').strip().casefold()
        if not key:return []
        got=list(self.types_by_name.get(key,[]))
        if got:return got
        return [t for t in self.types if t['name'].casefold().endswith(key) or t['full'].casefold().endswith('.'+key)][:12]

    def resolve_method_token(self,token):
        table=(token>>24)&0xff;rid=token&0x00ffffff
        if table==0x06 and 0<rid<len(self.methods):
            m=self.methods[rid];return {'token':f'0x{token:08x}','table':'MethodDef','owner':m.get('owner') or '','name':m['name'],'full':((m.get('owner')+'.') if m.get('owner') else '')+m['name']}
        if table==0x0A and 0<rid<len(self.memberrefs):
            m=self.memberrefs[rid];return {'token':f'0x{token:08x}','table':'MemberRef','owner':m.get('owner') or '','name':m['name'],'full':m['full']}
        return None

    def resolve_field_token(self,token):
        table=(token>>24)&0xff;rid=token&0x00ffffff
        if table==0x04 and 0<rid<len(self.fields):
            f=self.fields[rid];return {'token':f'0x{token:08x}','owner':f.get('owner') or '','name':f['name'],'full':((f.get('owner')+'.') if f.get('owner') else '')+f['name']}
        if table==0x0A and 0<rid<len(self.memberrefs):
            f=self.memberrefs[rid];return {'token':f'0x{token:08x}','owner':f.get('owner') or '','name':f['name'],'full':f['full']}
        return None

    def method_code(self,m):
        rva=int(m.get('rva') or 0)
        if not rva:return b''
        try:o=self.rva_to_off(rva)
        except Exception:return b''
        if o>=len(self.data):return b''
        b0=self.data[o]
        if b0&3==2:
            size=b0>>2;start=o+1
        elif b0&3==3:
            if o+12>len(self.data):return b''
            flags_size=self.u16(o);hdr=((flags_size>>12)&0xF)*4;size=self.u32(o+4);start=o+hdr
        else:return b''
        if size<0 or size>4*1024*1024:return b''
        return self.data[start:min(len(self.data),start+size)]

    def analyze_method(self,m):
        code=self.method_code(m);calls=[];fields=[];strings=[];seen=set()
        # Metadata-token validation makes this permissive byte scan useful even when uncommon IL
        # opcodes are present; invalid apparent tokens are discarded.
        for i in range(0,max(0,len(code)-4)):
            op=code[i]
            if op in (0x28,0x6f,0x73):  # call/callvirt/newobj
                tok=int.from_bytes(code[i+1:i+5],'little'); rec=self.resolve_method_token(tok)
                if rec:
                    k=('c',rec['token'])
                    if k not in seen:
                        seen.add(k);rec['opcode']={0x28:'call',0x6f:'callvirt',0x73:'newobj'}[op];rec['offset']=i;calls.append(rec)
            elif op in (0x7b,0x7c,0x7d,0x7e,0x7f,0x80):
                tok=int.from_bytes(code[i+1:i+5],'little');rec=self.resolve_field_token(tok)
                if rec:
                    k=('f',rec['token'],op)
                    if k not in seen:
                        seen.add(k);rec['opcode']=hex(op);rec['offset']=i;fields.append(rec)
            elif op==0x72:
                tok=int.from_bytes(code[i+1:i+5],'little')
                if (tok>>24)==0x70:
                    s=self.user_string(tok&0x00ffffff)
                    if s and s not in strings:strings.append(s)
        return {'rid':m['rid'],'name':m['name'],'owner':m.get('owner'),'rva':m.get('rva'),'codeBytes':len(code),'calls':calls[:160],'fields':fields[:120],'strings':strings[:80]}


def clr_index(force=False):
    global _CLR_INDEX
    with _LOCK:
        if _CLR_INDEX is not None and not force:return _CLR_INDEX
        data,meta=recover_assembly_csharp();_CLR_INDEX=CLRIndex(data,meta);return _CLR_INDEX


def _diag(v39,sid):
    a=v39._asset(sid)
    if not a:raise KeyError('asset-not-found:'+sid)
    with v39.ptr_fast.ASSEMBLY_LOCK:
        return v39.anim.scan_animation(a,v39.core,v39.ptr,v39.dependency_rows,v39.CACHE_ROOT)


def _is_2d(a):
    p=str(a.get('asset_path') or '').lower();dim=str(a.get('dimension_class') or '').lower()
    return dim=='2d' or '/sprites/' in p or '/icons/' in p or p.endswith(('.png','.jpg','.jpeg','.webp'))


def _choose_prefab(v39,sid,a):
    if not _is_2d(a):return sid,[],None
    targets=v39._animation_targets(sid);tested=[];best=None
    for cand in (targets.get('candidates') or [])[:5]:
        csid=str(cand.get('stable_id') or '')
        try:d=_diag(v39,csid);err=None
        except Exception as exc:d=None;err=str(exc)
        tested.append({'stable_id':csid,'asset_path':cand.get('asset_path'),'resolver_score':cand.get('resolver_score'),'resolver_reasons':cand.get('resolver_reasons'),'classification':(d or {}).get('classification'),'error':err})
        code=(d or {}).get('classification',{}).get('code')
        if best is None and d:best=(csid,d)
        if code and code!='static-or-undetected':best=(csid,d);break
    return (best[0] if best else (tested[0]['stable_id'] if tested else sid)),tested,targets


def _signal_from_call(full):
    for rx,kind,conf in ANIM_CALL_PATTERNS:
        if rx.search(str(full or '')):return kind,conf
    return None,None


def _serialized_summary(script):
    fields=script.get('serializedFields') or {}; hints=script.get('stringHints') or []
    useful={}
    for k,v in fields.items():
        lk=str(k).lower()
        if any(x in lk for x in ('speed','axis','angle','rotate','rotation','target','anim','clip','state','loop','duration','time','prefab','asset','path','name')):
            useful[k]=v
        if len(useful)>=30:break
    return {'fields':useful,'stringHints':hints[:32]}


def _script_code_evidence(index,script):
    cls=str(script.get('className') or script.get('scriptName') or '').strip()
    out={'className':cls,'gameObject':script.get('nodePath') or script.get('gameObject'),'animationHint':bool(script.get('animationHint')),'serialized':_serialized_summary(script),'types':[],'signals':[]}
    if not cls:return out
    for ty in index.find_types(cls)[:6]:
        trec={'name':ty['name'],'namespace':ty['namespace'],'full':ty['full'],'fields':[f['name'] for f in ty.get('fields',[])[:120]],'methods':[]}
        for m in ty.get('methods',[])[:180]:
            ma=index.analyze_method(m)
            interesting=[]
            for c in ma['calls']:
                kind,conf=_signal_from_call(c['full'])
                if kind:
                    interesting.append({'kind':kind,'confidence':conf,'method':m['name'],'call':c})
                    out['signals'].append({'kind':kind,'confidence':conf,'method':m['name'],'call':c['full'],'token':c['token']})
            # Keep method if it has animation evidence, useful strings, or is a lifecycle/control method.
            lifecycle=bool(re.search(r'^(Awake|Start|OnEnable|Update|LateUpdate|FixedUpdate|Play|Stop|Init|Refresh|Set|Switch|Change)',m['name'],re.I))
            if interesting or ma['strings'] or lifecycle:
                ma['animationSignals']=interesting;trec['methods'].append(ma)
        out['types'].append(trec)
    # deterministic dedupe
    uniq=[];seen=set()
    for s in sorted(out['signals'],key=lambda x:x['confidence'],reverse=True):
        k=(s['kind'],s['method'],s['call'])
        if k not in seen:seen.add(k);uniq.append(s)
    out['signals']=uniq[:80]
    return out


def _graph_nodes_edges(source,root_sid,root_diag,soft,script_evidence,child_diags):
    nodes=[];edges=[];seen=set()
    def node(nid,kind,label,**extra):
        if nid in seen:return
        seen.add(nid);nodes.append({'id':nid,'kind':kind,'label':label,**extra})
    srcid=str(source.get('stable_id'));node(srcid,'asset',source.get('asset_path') or srcid,dimension=source.get('dimension_class'))
    if root_sid!=srcid:
        node(root_sid,'prefab',root_sid);edges.append({'from':srcid,'to':root_sid,'kind':'icon-to-prefab','proof':'V39 exact target resolver + animation scan'})
    else:node(root_sid,'prefab',source.get('asset_path') or root_sid)
    for s in script_evidence:
        sid='script:'+root_sid+':'+str(s.get('gameObject'))+':'+str(s.get('className'))
        node(sid,'script',s.get('className') or 'MonoBehaviour',gameObject=s.get('gameObject'));edges.append({'from':root_sid,'to':sid,'kind':'component','proof':'MonoBehaviour serialized on exact prefab'})
        for sig in s.get('signals',[]):
            mid=sid+':method:'+sig['method'];node(mid,'method',sig['method']);edges.append({'from':sid,'to':mid,'kind':'declares','proof':'Assembly-CSharp TypeDef/MethodDef'})
            aid='api:'+sig['call'];node(aid,'api',sig['call']);edges.append({'from':mid,'to':aid,'kind':'calls','proof':'validated CLR metadata token','confidence':sig['confidence']})
    for item in soft.get('items') or []:
        b=item.get('best') or {};csid=b.get('stable_id')
        if not csid:continue
        node(csid,'runtime-prefab',b.get('asset_path') or csid,variant=item.get('variant'),availability=b.get('render_availability'))
        edges.append({'from':root_sid,'to':csid,'kind':'soft-reference','slot':item.get('nodePath'),'variant':item.get('variant'),'proof':'exact serialized/name/path evidence' if (b.get('exactName') or b.get('exactPath')) else 'candidate'})
    for csid,diag in child_diags.items():
        for sc in (diag.get('components',{}).get('scripts') or []):
            cn=str(sc.get('className') or sc.get('scriptName') or '')
            if cn:
                nid='script:'+csid+':'+str(sc.get('nodePath'))+':'+cn;node(nid,'script',cn,gameObject=sc.get('nodePath'));edges.append({'from':csid,'to':nid,'kind':'component','proof':'child prefab animation scan'})
    return nodes,edges


def build_graph(stable_id, v3915, force=False, max_children=8):
    """Build the V40 graph for one source asset. v3915 is the imported V39.15 server module."""
    sid=str(stable_id or '').strip().upper()
    if not re.fullmatch(r'LWGA-[A-Z0-9]+',sid):raise ValueError('invalid-stable-id')
    v3914=v3915.v3914;v3912=v3914.v3912;v398=v3912.v398;v397=v398.v397;v39=v397.v39
    if not force:
        con=_db();row=con.execute('SELECT payload_json FROM graph_cache WHERE stable_id=?',(sid,)).fetchone();con.close()
        if row:
            try:
                d=json.loads(row[0]);d['cacheHit']=True;return d
            except Exception:pass
    started=time.perf_counter();source=v39._asset(sid)
    if not source:raise KeyError('asset-not-found')
    root_sid,tested,targets=_choose_prefab(v39,sid,source)
    root_diag=_diag(v39,root_sid)
    soft,status=v3912.resolve_soft_prefabs(root_sid,materialize=True)
    if status!=200:soft={'items':[],'assemblyReady':False,'error':soft}
    child_diags={}
    for item in (soft.get('items') or [])[:max_children]:
        b=item.get('best') or {};csid=str(b.get('stable_id') or '')
        exact=bool(b.get('exactName') or b.get('exactPath'));local=str(b.get('render_availability') or '').startswith('local-')
        if not csid or not exact or not local:continue
        try:child_diags[csid]=_diag(v39,csid)
        except Exception as exc:child_diags[csid]={'error':str(exc)}
    idx=clr_index(False)
    scripts=root_diag.get('components',{}).get('scripts') or []
    evid=[_script_code_evidence(idx,s) for s in scripts]
    signals=[]
    for e in evid:signals.extend(e.get('signals') or [])
    signals.sort(key=lambda x:x['confidence'],reverse=True)
    # Serialized-only fallback remains explicitly lower confidence.
    if not signals:
        for e in evid:
            if e.get('animationHint'):
                signals.append({'kind':'script-runtime-unknown','confidence':0.68,'method':None,'call':None,'className':e.get('className')})
    recipe=[];seen=set()
    for s in signals:
        k=s['kind']
        if k in seen:continue
        seen.add(k);recipe.append({'type':k,'confidence':s['confidence'],'evidence':s})
    nodes,edges=_graph_nodes_edges(source,root_sid,root_diag,soft,evid,child_diags)
    payload={
        'version':'40.0','stableId':sid,'sourceAsset':{'stable_id':sid,'asset_path':source.get('asset_path'),'dimension_class':source.get('dimension_class')},
        'rootPrefab':root_sid,'targetCandidatesTested':tested,'rootDiagnostic':{
            'classification':root_diag.get('classification'),'rootGameObject':root_diag.get('rootGameObject'),
            'nodeCount':root_diag.get('hierarchy',{}).get('nodeCount',0),'animatorOrAnimationCount':root_diag.get('components',{}).get('animatorOrAnimationCount',0),
            'directLinkedClipCount':root_diag.get('clips',{}).get('directLinkedCount',0),'particleSystemCount':root_diag.get('components',{}).get('particleSystemCount',0),
            'monoBehaviourCount':root_diag.get('components',{}).get('monoBehaviourCount',0),
        },
        'runtimePrefabs':soft,'childDiagnostics':child_diags,'scriptCodeEvidence':evid,'motionRecipe':recipe,
        'graph':{'nodes':nodes,'edges':edges},
        'summary':{
            'status':'motion-evidence-found' if recipe else 'runtime-graph-built-no-motion-api-yet',
            'bestMotion':recipe[0] if recipe else None,
            'exactRuntimeChildren':sum(1 for x in (soft.get('items') or []) if (x.get('best') or {}).get('exactName') or (x.get('best') or {}).get('exactPath')),
            'localRuntimeChildren':soft.get('localResolvedCount',0),'assemblyReady':soft.get('assemblyReady',False),
            'assemblyCSharpTypesMatched':sum(len(x.get('types') or []) for x in evid),
        },
        'assembly':{'sha256':idx.sha256,'source':idx.source_meta,'typeCount':len(idx.types),'methodCount':len(idx.methods)-1,'memberRefCount':len(idx.memberrefs)-1},
        'policy':'Exact runtime relations only. CLR calls are accepted only when metadata tokens resolve. Interpretation is confidence-labelled. No synthetic geometry, motion or visual-similarity dependency.',
        'createdAt':_now(),'scanSeconds':round(time.perf_counter()-started,3),'cacheHit':False,
    }
    con=_db();con.execute('INSERT OR REPLACE INTO graph_cache(stable_id,created_at,assembly_sha256,payload_json) VALUES(?,?,?,?)',(sid,payload['createdAt'],idx.sha256,json.dumps(payload,ensure_ascii=False,separators=(',',':'))));con.commit();con.close()
    return payload


def cache_status():
    con=_db();n=con.execute('SELECT count(*) FROM graph_cache').fetchone()[0];con.close()
    return {'cacheDb':str(CACHE_DB),'graphsCached':n,'assemblyCached':ASSEMBLY_CACHE.exists(),'version':'40.0'}
