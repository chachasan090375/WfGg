#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V40 — deterministic Unity animation graph agent.

Purpose
-------
Build a reusable, evidence-first graph from a WfGg asset to its controller prefab,
runtime child prefabs, MonoBehaviours and the relevant Assembly-CSharp methods.

The agent does NOT execute game code and does NOT invent motion.  It combines:
- catalogue/path evidence from the V33 SQLite index;
- exact V39 hierarchy / serialized MonoBehaviour evidence;
- exact V39.12 SoftReferencePrefab resolution;
- read-only CLR metadata + bounded IL call-token inspection from the installed
  assets/Assemblies/Assembly-CSharp.mdl.

The first validation target is the research building/laboratory chain:
LWGA-C37A0F67197299 -> building_10123000.prefab -> SimpleAnimation -> runtime children.
"""

from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import struct
import subprocess
import time
import zipfile

SCHEMA = 4001
PKG = "com.fun.lastwar.gp"
SID_RE = re.compile(r"^LWGA-[A-Z0-9]+$")
NUM_TOKEN_RE = re.compile(r"(?<!\d)(\d{6,})(?!\d)")
CACHE_ROOT = Path.home() / ".cache" / "wfgg-lastwar-v40"
CACHE_ROOT.mkdir(parents=True, exist_ok=True)
TRACE_DB = CACHE_ROOT / "animation-graph.sqlite3"
ASM_CACHE = CACHE_ROOT / "assembly-csharp-code-map.json"

ANIM_CALL_PATTERNS = (
    ("continuous_rotation", re.compile(r"(?:^|\.)Transform::(?:Rotate|set_localRotation|set_localEulerAngles)$", re.I), 0.98),
    ("rotation_math", re.compile(r"Quaternion::(?:Euler|AngleAxis|Slerp|Lerp)$", re.I), 0.92),
    ("animator_state", re.compile(r"Animator::(?:Play|CrossFade|CrossFadeInFixedTime|SetTrigger|SetBool|SetFloat|SetInteger)$", re.I), 0.96),
    ("legacy_animation", re.compile(r"Animation::(?:Play|CrossFade|Blend|Rewind)$", re.I), 0.96),
    ("state_switch", re.compile(r"GameObject::SetActive$", re.I), 0.90),
    ("runtime_instantiate", re.compile(r"(?:Object|GameObject)::Instantiate$", re.I), 0.88),
    ("runtime_load", re.compile(r"(?:LoadAsset|LoadPrefab|Addressables|Resources::Load)", re.I), 0.84),
)


def _utc():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _trace_con():
    con = sqlite3.connect(TRACE_DB)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("""
      CREATE TABLE IF NOT EXISTS traces(
        stable_id TEXT PRIMARY KEY,
        schema_version INTEGER NOT NULL,
        generated_at TEXT NOT NULL,
        generated_epoch INTEGER NOT NULL,
        signature TEXT NOT NULL,
        payload_json TEXT NOT NULL
      )
    """)
    con.execute("""
      CREATE TABLE IF NOT EXISTS graph_edges(
        source_id TEXT NOT NULL,
        target_id TEXT NOT NULL,
        relation TEXT NOT NULL,
        evidence TEXT,
        confidence REAL,
        trace_root TEXT NOT NULL,
        PRIMARY KEY(source_id,target_id,relation,trace_root)
      )
    """)
    return con


def _cmd_package_paths():
    out = []
    for cmd in (["cmd", "package", "path", PKG], ["pm", "path", PKG]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        except Exception:
            continue
        for line in p.stdout.splitlines():
            if line.startswith("package:"):
                path = line.split(":", 1)[1].strip()
                if path and path not in out:
                    out.append(path)
    return out


def _find_assembly_payload():
    wanted = "assets/Assemblies/Assembly-CSharp.mdl"
    for apk in _cmd_package_paths():
        try:
            with zipfile.ZipFile(apk) as z:
                if wanted in z.namelist():
                    info = z.getinfo(wanted)
                    return {
                        "apk": apk,
                        "entry": wanted,
                        "bytes": info.file_size,
                        "crc": info.CRC,
                        "data": z.read(wanted),
                    }
        except Exception:
            continue
    raise RuntimeError("V40_ASSEMBLY_CSHARP_MDL_NOT_FOUND")


def _restore_mdl_header(raw: bytes) -> bytearray:
    data = bytearray(raw)
    canonical = bytes.fromhex("4d5a90000300000004000000ffff0000b80000")
    for i, b in enumerate(canonical):
        if i < len(data) and data[i] == (b ^ 0x13):
            data[i] = b
    if len(data) >= 2:
        data[0:2] = b"MZ"
    return data


def _parse_assembly_map(force=False):
    source = _find_assembly_payload()
    signature = f"{source['bytes']}:{source['crc']}"
    if not force and ASM_CACHE.is_file():
        try:
            cached = json.loads(ASM_CACHE.read_text("utf-8"))
            if cached.get("sourceSignature") == signature and cached.get("schemaVersion") == SCHEMA:
                return cached
        except Exception:
            pass

    data = _restore_mdl_header(source.pop("data"))
    u16 = lambda o: struct.unpack_from("<H", data, o)[0]
    u32 = lambda o: struct.unpack_from("<I", data, o)[0]
    u64 = lambda o: struct.unpack_from("<Q", data, o)[0]
    if data[:2] != b"MZ":
        raise RuntimeError("V40_ASSEMBLY_MZ_RESTORE_FAILED")
    e_lfanew = u32(0x3C)
    if data[e_lfanew:e_lfanew+4] != b"PE\0\0":
        raise RuntimeError("V40_ASSEMBLY_PE_NOT_FOUND")
    coff = e_lfanew + 4
    sections = u16(coff+2); opt_size = u16(coff+16); opt = coff + 20; magic = u16(opt)
    dd = opt + (96 if magic == 0x10B else 112 if magic == 0x20B else -1)
    if dd < opt:
        raise RuntimeError(f"V40_ASSEMBLY_OPTIONAL_MAGIC_{magic:#x}")
    clr_rva = u32(dd + 14*8)
    sec_off = opt + opt_size
    secs = []
    for i in range(sections):
        o = sec_off + i*40
        name = bytes(data[o:o+8]).split(b"\0", 1)[0].decode("ascii", "replace")
        secs.append({"name":name,"vsize":u32(o+8),"va":u32(o+12),"rawsize":u32(o+16),"raw":u32(o+20)})

    def rva_to_off(rva):
        for s in secs:
            span = max(s["vsize"], s["rawsize"])
            if s["va"] <= rva < s["va"] + span:
                return s["raw"] + (rva - s["va"])
        if 0 <= rva < len(data):
            return rva
        raise ValueError(f"RVA_OUTSIDE_SECTIONS:{rva:#x}")

    clr_off = rva_to_off(clr_rva)
    metadata_rva = u32(clr_off+8)
    meta = rva_to_off(metadata_rva)
    if bytes(data[meta:meta+4]) != b"BSJB":
        raise RuntimeError("V40_ASSEMBLY_BSJB_NOT_FOUND")
    ver_len = u32(meta+12); p = (meta + 16 + ver_len + 3) & ~3
    streams = u16(p+2); p += 4
    stream_map = {}
    for _ in range(streams):
        off = u32(p); size = u32(p+4); p += 8
        end = data.find(0, p, p+96)
        if end < 0:
            raise RuntimeError("V40_ASSEMBLY_BAD_STREAM_NAME")
        name = bytes(data[p:end]).decode("ascii", "replace"); p = (end+1+3) & ~3
        stream_map[name] = {"offset":meta+off,"size":size}
    strings = stream_map.get("#Strings")
    tables = stream_map.get("#~") or stream_map.get("#-")
    if not strings or not tables:
        raise RuntimeError("V40_ASSEMBLY_METADATA_STREAMS_INCOMPLETE")

    def str_at(idx):
        if not idx:
            return ""
        o = strings["offset"] + idx
        e = data.find(0, o, strings["offset"] + strings["size"])
        if e < 0:
            e = min(len(data), o+512)
        return bytes(data[o:e]).decode("utf-8", "replace")

    t = tables["offset"]; heap_sizes = data[t+6]; valid = u64(t+8); q = t+24
    rows = {}
    for tid in range(64):
        if (valid >> tid) & 1:
            rows[tid] = u32(q); q += 4
    rowdata = q
    strsz = 4 if heap_sizes & 1 else 2
    guidsz = 4 if heap_sizes & 2 else 2
    blobsz = 4 if heap_sizes & 4 else 2
    idxsz = lambda tid: 4 if rows.get(tid, 0) >= 65536 else 2
    cidx = lambda tagbits, *tids: 4 if max((rows.get(x,0) for x in tids), default=0) >= (1 << (16-tagbits)) else 2
    resolution_scope = cidx(2, 0, 26, 35, 1)
    typedef_or_ref = cidx(2, 2, 1, 27)
    memberref_parent = cidx(3, 2, 1, 26, 6, 27)
    row_size = {
        0: 2 + strsz + guidsz*3,
        1: resolution_scope + strsz*2,
        2: 4 + strsz*2 + typedef_or_ref + idxsz(4) + idxsz(6),
        3: idxsz(4),
        4: 2 + strsz + blobsz,
        5: idxsz(6),
        6: 4 + 2 + 2 + strsz + blobsz + idxsz(8),
        7: idxsz(8),
        8: 2 + 2 + strsz,
        9: idxsz(2) + typedef_or_ref,
        10: memberref_parent + strsz + blobsz,
    }
    offs = {}; cur = rowdata
    for tid in range(11):
        if (valid >> tid) & 1:
            if tid not in row_size:
                raise RuntimeError(f"V40_ASSEMBLY_UNSUPPORTED_TABLE_BEFORE_MEMBERREF:{tid}")
            offs[tid] = cur; cur += row_size[tid] * rows.get(tid,0)
    read_idx = lambda o, sz: u16(o) if sz == 2 else u32(o)

    typerefs = [None]
    base = offs.get(1, 0)
    for rid in range(1, rows.get(1,0)+1):
        o = base + (rid-1)*row_size[1]
        pos = o + resolution_scope
        name_i = read_idx(pos, strsz); pos += strsz
        ns_i = read_idx(pos, strsz)
        typerefs.append({"rid":rid,"name":str_at(name_i),"namespace":str_at(ns_i)})

    methods = [None]
    base = offs.get(6, 0)
    for rid in range(1, rows.get(6,0)+1):
        o = base + (rid-1)*row_size[6]
        rva = u32(o); name_i = read_idx(o+8, strsz)
        methods.append({"rid":rid,"rva":rva,"name":str_at(name_i)})

    raw_types = []; base = offs.get(2, 0)
    for rid in range(1, rows.get(2,0)+1):
        o = base + (rid-1)*row_size[2]
        pos = o+4; name_i = read_idx(pos,strsz); pos += strsz; ns_i = read_idx(pos,strsz); pos += strsz
        pos += typedef_or_ref; pos += idxsz(4); method_start = read_idx(pos, idxsz(6))
        raw_types.append({"rid":rid,"name":str_at(name_i),"namespace":str_at(ns_i),"methodStart":method_start})
    method_owner = {}
    for i, ty in enumerate(raw_types):
        start = ty["methodStart"] or 1
        end = (raw_types[i+1]["methodStart"]-1 if i+1 < len(raw_types) else rows.get(6,0))
        ids = list(range(max(1,start), min(end, rows.get(6,0))+1)) if end >= start else []
        ty["methodRids"] = ids
        for rid in ids:
            method_owner[rid] = ty

    memberrefs = [None]; base = offs.get(10,0)
    for rid in range(1, rows.get(10,0)+1):
        o = base + (rid-1)*row_size[10]
        coded = read_idx(o, memberref_parent); pos = o + memberref_parent
        name_i = read_idx(pos, strsz); name = str_at(name_i)
        tag = coded & 0x7; prid = coded >> 3
        owner = ""
        if tag == 0 and 1 <= prid <= len(raw_types):
            ty = raw_types[prid-1]; owner = (ty["namespace"] + "." if ty["namespace"] else "") + ty["name"]
        elif tag == 1 and 1 <= prid < len(typerefs):
            ty = typerefs[prid]; owner = (ty["namespace"] + "." if ty["namespace"] else "") + ty["name"]
        elif tag == 3 and 1 <= prid < len(methods):
            ty = method_owner.get(prid) or {}; owner = (ty.get("namespace","") + "." if ty.get("namespace") else "") + ty.get("name","")
        memberrefs.append({"rid":rid,"name":name,"owner":owner})

    def method_full(rid):
        if not (1 <= rid < len(methods)):
            return ""
        m = methods[rid]; ty = method_owner.get(rid) or {}
        owner = (ty.get("namespace","") + "." if ty.get("namespace") else "") + ty.get("name","")
        return f"{owner}::{m['name']}" if owner else m["name"]

    def body_bounds(rva):
        if not rva:
            return None
        try:
            o = rva_to_off(rva); b0 = data[o]
            if (b0 & 0x3) == 0x2:
                size = b0 >> 2; return o+1, min(len(data), o+1+size)
            if (b0 & 0x3) == 0x3:
                flags = u16(o); hsz = ((flags >> 12) & 0xF) * 4; size = u32(o+4)
                return o+hsz, min(len(data), o+hsz+size)
        except Exception:
            return None
        return None

    def calls_for(rid):
        m = methods[rid] if 1 <= rid < len(methods) else None
        if not m:
            return []
        b = body_bounds(m["rva"])
        if not b:
            return []
        start, end = b; code = data[start:end]; found = []
        # Conservative token scan: accepted only when the following 4 bytes decode to an
        # existing MethodDef or MemberRef RID.  This catches call/callvirt/newobj without
        # requiring a full CIL interpreter and is safe for classification because each hit
        # remains labelled as IL evidence, not executed behavior.
        for i in range(0, max(0, len(code)-4)):
            op = code[i]
            if op not in (0x28, 0x6F, 0x73):
                continue
            tok = struct.unpack_from("<I", code, i+1)[0]
            table = (tok >> 24) & 0xFF; rr = tok & 0x00FFFFFF
            text = ""
            if table == 0x0A and 1 <= rr < len(memberrefs):
                mr = memberrefs[rr]; text = f"{mr['owner']}::{mr['name']}" if mr.get("owner") else mr.get("name","")
            elif table == 0x06 and 1 <= rr < len(methods):
                text = method_full(rr)
            if text and text not in found:
                found.append(text)
            if len(found) >= 120:
                break
        return found

    types_out = []
    for ty in raw_types:
        fq = (ty["namespace"] + "." if ty["namespace"] else "") + ty["name"]
        meth = []
        for rid in ty["methodRids"]:
            m = methods[rid]
            meth.append({"rid":rid,"rva":m["rva"],"name":m["name"],"calls":calls_for(rid)})
        types_out.append({"rid":ty["rid"],"namespace":ty["namespace"],"name":ty["name"],"fullName":fq,"methods":meth})

    payload = {
        "schemaVersion":SCHEMA,
        "generatedAt":_utc(),
        "sourceSignature":signature,
        "source":source,
        "typeCount":len(types_out),
        "methodCount":rows.get(6,0),
        "memberRefCount":rows.get(10,0),
        "types":types_out,
    }
    ASM_CACHE.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    return payload


def _script_code_evidence(class_name, namespace="", assembly_map=None):
    class_name = str(class_name or "").strip()
    namespace = str(namespace or "").strip()
    if not class_name:
        return None
    amap = assembly_map or _parse_assembly_map()
    exact = []
    for ty in amap.get("types") or []:
        if ty.get("name") != class_name:
            continue
        if namespace and ty.get("namespace") and ty.get("namespace") != namespace:
            continue
        exact.append(ty)
    if not exact:
        return {"className":class_name,"namespace":namespace,"found":False,"signals":[],"methods":[]}
    ty = exact[0]
    signals = []
    methods_out = []
    for m in ty.get("methods") or []:
        calls = m.get("calls") or []
        matched = []
        for call in calls:
            compact = call.replace("UnityEngine.", "")
            for kind, rx, confidence in ANIM_CALL_PATTERNS:
                if rx.search(compact) or rx.search(call):
                    hit = {"kind":kind,"call":call,"method":m.get("name"),"confidence":confidence}
                    matched.append(hit); signals.append(hit)
        if matched or re.search(r"update|lateupdate|fixedupdate|play|anim|rotate|work|idle", str(m.get("name") or ""), re.I):
            methods_out.append({"name":m.get("name"),"rid":m.get("rid"),"rva":m.get("rva"),"calls":calls[:80],"animationSignals":matched})
    uniq = []
    seen = set()
    for s in sorted(signals, key=lambda x:x["confidence"], reverse=True):
        key = (s["kind"], s["call"], s["method"])
        if key not in seen:
            seen.add(key); uniq.append(s)
    return {"className":class_name,"namespace":namespace,"found":True,"type":ty.get("fullName"),"signals":uniq[:80],"methods":methods_out[:80]}


def _asset(v3912, sid):
    return v3912._asset(sid)


def _prefab_candidates(v3912, a):
    path = str(a.get("asset_path") or "").replace("\\", "/")
    base = path.rsplit("/",1)[-1]
    stem = base.rsplit(".",1)[0]
    nums = NUM_TOKEN_RE.findall(path)
    exact_names = set()
    if stem.lower().startswith("ui_building_"):
        exact_names.add(stem[len("UI_"):] + ".prefab")
    for n in nums:
        exact_names.add("building_" + n + ".prefab")
    con = v3912.core.dbcon(); rows = []
    try:
        for name in exact_names:
            got = con.execute("SELECT * FROM assets WHERE lower(asset_path) LIKE ? ORDER BY CASE WHEN lower(asset_path) LIKE '%/prefabs/building/%' THEN 0 ELSE 1 END, stable_id LIMIT 12", ("%/"+name.lower(),)).fetchall()
            rows.extend(v3912.core.rowdict(r) for r in got)
        if not rows:
            for n in nums[:3]:
                got = con.execute("SELECT * FROM assets WHERE lower(asset_path) LIKE ? AND lower(asset_path) LIKE '%.prefab' ORDER BY stable_id LIMIT 20", ("%"+n+"%",)).fetchall()
                rows.extend(v3912.core.rowdict(r) for r in got)
    finally:
        con.close()
    dedup = {}; out = []
    for r in rows:
        sid = r.get("stable_id")
        if not sid or sid in dedup:
            continue
        low = str(r.get("asset_path") or "").lower(); score = 0; evidence = []
        if low.endswith("/" + ("building_" + nums[0] + ".prefab").lower()) if nums else False:
            score += 500; evidence.append("exact-building-basename")
        if "/prefabs/building/" in low:
            score += 120; evidence.append("building-prefab-folder")
        if str(r.get("render_availability") or "").startswith("local-"):
            score += 40; evidence.append("local-source")
        out.append({"asset":r,"score":score,"evidence":evidence})
        dedup[sid] = True
    out.sort(key=lambda x:x["score"], reverse=True)
    return out[:8]


def _signal_recipe(code_evidence, diag, soft):
    signals = []
    for ev in code_evidence:
        signals.extend(ev.get("signals") or [])
    signals.sort(key=lambda x:x.get("confidence",0), reverse=True)
    if signals:
        top = signals[0]
        return {
            "kind":top["kind"],
            "confidence":top["confidence"],
            "basis":"Assembly-CSharp IL call evidence",
            "controller":top.get("call"),
            "method":top.get("method"),
            "synthetic":False,
        }
    comp = (diag or {}).get("classification") or {}
    if comp.get("hasDirectLinkedClip"):
        return {"kind":"animation_clip","confidence":0.97,"basis":"direct AnimationClip PPtr","synthetic":False}
    if comp.get("hasAnimationHintScript"):
        return {"kind":"runtime_script_unresolved","confidence":0.72,"basis":"MonoBehaviour serialized/script-name evidence","synthetic":False}
    if soft and soft.get("resolvedCount"):
        return {"kind":"runtime_state_prefabs","confidence":0.78,"basis":"exact SoftReferencePrefab graph","synthetic":False}
    return {"kind":"static_or_unresolved","confidence":0.35,"basis":"no exact animation behavior resolved","synthetic":False}


class AnimationGraphAgent:
    def __init__(self, v3912):
        self.v3912 = v3912

    def _signature(self, sid):
        a = _asset(self.v3912, sid) or {}
        raw = json.dumps({
            "schema":SCHEMA,"sid":sid,"bundle":a.get("bundle_id"),"path":a.get("asset_path"),
            "availability":a.get("render_availability"),"reason":a.get("render_source_reason")
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def cached(self, sid, max_age=86400):
        sig = self._signature(sid)
        con = _trace_con()
        try:
            row = con.execute("SELECT * FROM traces WHERE stable_id=?", (sid,)).fetchone()
        finally:
            con.close()
        if not row:
            return None
        _, schema, _, epoch, oldsig, payload = row
        if schema != SCHEMA or oldsig != sig or int(time.time())-int(epoch) > max_age:
            return None
        try:
            d = json.loads(payload); d["cacheHit"] = True; return d
        except Exception:
            return None

    def trace(self, sid, refresh=False, deep=True):
        sid = str(sid or "").strip().upper()
        if not SID_RE.fullmatch(sid):
            raise ValueError("V40_INVALID_STABLE_ID")
        if not refresh:
            old = self.cached(sid)
            if old:
                return old
        started = time.time(); root = _asset(self.v3912, sid)
        if not root:
            raise KeyError("V40_ASSET_NOT_FOUND")
        nodes = {}; edges = []
        def node(nid, kind, label, **extra):
            rec = {"id":nid,"kind":kind,"label":label}; rec.update(extra); nodes[nid] = rec; return rec
        def edge(src, dst, relation, evidence, confidence=1.0):
            edges.append({"source":src,"target":dst,"relation":relation,"evidence":evidence,"confidence":confidence})
        node(sid, "asset", root.get("asset_path") or sid, stable_id=sid, availability=root.get("render_availability"), dimension=root.get("dimension_class"))

        controller = root
        if str(root.get("dimension_class") or "").upper() == "2D" or str(root.get("asset_path") or "").lower().endswith((".png",".jpg",".webp")):
            candidates = _prefab_candidates(self.v3912, root)
            if candidates:
                controller = candidates[0]["asset"]
                csid = controller.get("stable_id")
                node(csid, "prefab", controller.get("asset_path") or csid, stable_id=csid, availability=controller.get("render_availability"))
                edge(sid, csid, "controller-prefab", ",".join(candidates[0]["evidence"]), min(1.0, 0.70 + candidates[0]["score"]/1000.0))

        controller_sid = controller.get("stable_id")
        diag = self.v3912._diag(controller_sid)
        root_name = diag.get("rootGameObject") or controller_sid
        node("go:"+controller_sid, "gameobject-root", root_name, stable_id=controller_sid)
        edge(controller_sid, "go:"+controller_sid, "root-gameobject", str(diag.get("rootAnchor") or "exact V39 anchor"), 1.0)

        scripts = (diag.get("components") or {}).get("scripts") or []
        script_keys = []
        for i, s in enumerate(scripts):
            cname = s.get("className") or s.get("scriptName") or "MonoBehaviour"
            sk = f"script:{controller_sid}:{i}:{cname}"
            node(sk, "script", cname, className=cname, namespace=s.get("namespace"), assembly=s.get("assembly"), nodePath=s.get("nodePath"), animationHint=bool(s.get("animationHint")), serializedFields=s.get("serializedFields"), stringHints=s.get("stringHints"))
            edge("go:"+controller_sid, sk, "component-script", str(s.get("nodePath") or root_name), 1.0)
            script_keys.append((sk,s))

        soft = self.v3912.resolve_soft_prefabs(controller_sid, materialize=True)[0]
        for i, item in enumerate(soft.get("items") or []):
            best = item.get("best") or {}
            child = best.get("stable_id")
            if not child:
                continue
            node(child, "runtime-prefab", best.get("asset_path") or child, stable_id=child, availability=best.get("render_availability"), variant=item.get("variant"))
            edge(controller_sid, child, "soft-reference-prefab", f"{item.get('nodePath')} | {'; '.join(best.get('reasons') or [])}", 0.99 if best.get("exactName") or best.get("exactPath") else 0.75)

        asm = _parse_assembly_map()
        code = []
        for sk, s in script_keys:
            ev = _script_code_evidence(s.get("className") or s.get("scriptName"), s.get("namespace"), asm)
            if not ev:
                continue
            code.append(ev)
            if ev.get("found"):
                tid = "code:" + str(ev.get("type"))
                node(tid, "assembly-type", ev.get("type"), className=ev.get("className"), methods=ev.get("methods"), signals=ev.get("signals"))
                edge(sk, tid, "implemented-by", "Assembly-CSharp CLR TypeDef + bounded IL call-token scan", 0.99)
                for j, sig in enumerate(ev.get("signals") or []):
                    cid = f"call:{tid}:{j}:{sig.get('kind')}"
                    node(cid, "code-signal", sig.get("call"), signalKind=sig.get("kind"), method=sig.get("method"), confidence=sig.get("confidence"))
                    edge(tid, cid, "calls", f"method {sig.get('method')}", sig.get("confidence",0.8))

        # Optional one-level child diagnostics: enough to expose geometry/animation-bearing runtime states
        child_diags = []
        if deep:
            for item in (soft.get("items") or [])[:8]:
                best = item.get("best") or {}
                csid = best.get("stable_id")
                if not csid or not str(best.get("render_availability") or "").startswith("local-"):
                    continue
                try:
                    cd = self.v3912._diag(csid)
                except Exception as exc:
                    child_diags.append({"stable_id":csid,"error":str(exc)}); continue
                child_diags.append({
                    "stable_id":csid,"variant":item.get("variant"),"rootGameObject":cd.get("rootGameObject"),
                    "classification":cd.get("classification"),"nodeCount":((cd.get("hierarchy") or {}).get("nodeCount")),
                    "scripts":[{"className":x.get("className"),"nodePath":x.get("nodePath"),"animationHint":x.get("animationHint")} for x in ((cd.get("components") or {}).get("scripts") or [])[:40]],
                })

        recipe = _signal_recipe(code, diag, soft)
        payload = {
            "schemaVersion":SCHEMA,"version":"40.0","generatedAt":_utc(),"cacheHit":False,
            "stableId":sid,"controllerStableId":controller_sid,"controllerPath":controller.get("asset_path"),
            "scanSeconds":round(time.time()-started,3),
            "summary":{
                "nodeCount":len(nodes),"edgeCount":len(edges),"scriptCount":len(scripts),
                "softPrefabCount":soft.get("resolvedCount",0),"localSoftPrefabCount":soft.get("localResolvedCount",0),
                "assemblyTypesMatched":sum(1 for x in code if x.get("found")),
            },
            "recipe":recipe,"animationDiagnostic":{
                "classification":diag.get("classification"),"playback":diag.get("playback"),"rootGameObject":diag.get("rootGameObject")
            },
            "softPrefabs":soft,"scriptCode":code,"childDiagnostics":child_diags,
            "graph":{"nodes":list(nodes.values()),"edges":edges},
            "policy":"Evidence-first only: exact catalogue/path, V39 PPtr/serialized data, exact SoftReferencePrefab resolver and read-only Assembly-CSharp CLR/IL call-token evidence. No game code execution, no synthetic movement, no visual substitution.",
        }
        sig = self._signature(sid); epoch = int(time.time())
        con = _trace_con()
        try:
            con.execute("INSERT OR REPLACE INTO traces VALUES(?,?,?,?,?,?)", (sid,SCHEMA,payload["generatedAt"],epoch,sig,json.dumps(payload,ensure_ascii=False)))
            con.execute("DELETE FROM graph_edges WHERE trace_root=?", (sid,))
            con.executemany("INSERT OR REPLACE INTO graph_edges VALUES(?,?,?,?,?,?)", [(e["source"],e["target"],e["relation"],e["evidence"],float(e.get("confidence",0)),sid) for e in edges])
            con.commit()
        finally:
            con.close()
        return payload


def agent_status():
    con = _trace_con()
    try:
        traces = con.execute("SELECT count(*) FROM traces").fetchone()[0]
        edges = con.execute("SELECT count(*) FROM graph_edges").fetchone()[0]
    finally:
        con.close()
    asm = None
    if ASM_CACHE.is_file():
        try:
            d = json.loads(ASM_CACHE.read_text("utf-8")); asm = {"ready":True,"generatedAt":d.get("generatedAt"),"typeCount":d.get("typeCount"),"methodCount":d.get("methodCount"),"memberRefCount":d.get("memberRefCount")}
        except Exception:
            asm = {"ready":False}
    return {"version":"40.0","schemaVersion":SCHEMA,"traceCache":str(TRACE_DB),"traces":traces,"edges":edges,"assembly":asm or {"ready":False},"deterministic":True,"syntheticAnimation":False}
