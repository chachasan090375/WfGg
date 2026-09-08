#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V39.12 — runtime SoftReferencePrefab resolver.

This wrapper keeps every V39.7/V39.8 guardrail and adds a conservative resolver for child prefabs
referenced by serialized MonoBehaviours such as SoftReferencePrefab. It never substitutes a child
by visual similarity or by a vague name. Exact basename/path evidence is ranked first; physical
source recovery is attempted only for high-confidence exact prefab-name matches.

The browser add-on also keeps the linked-animation badge on the same top row as the normal render
badge and exposes resolved idle/work child prefabs in the V39 diagnostic modal.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, json, re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v398-hotfix.py'
ADDON_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-softprefab-v3912.js'

spec = importlib.util.spec_from_file_location('wfgg_v398_for_v3912', BASE)
v398 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v398)

v397 = v398.v397
v39 = v397.v39
core = v39.core
ptr_fast = v39.ptr_fast
ptr = v39.ptr
dependency_rows = v39.dependency_rows
CACHE_ROOT = v39.CACHE_ROOT

EXACT_ID = re.compile(r'^LWGA-[A-Z0-9]+$')
PREFAB_TOKEN = re.compile(r'(?i)(?:assets/[^\s"\']+?\.prefab|[A-Za-z][A-Za-z0-9_\-]{7,80})')
GENERIC = {
    'assets','main','prefab','prefabs','building','modelgo','normal','upgrade','idle','work',
    'softreferenceprefab','assembly','csharp','script','gameobject','unknown','default'
}


def _asset(sid):
    return v39._asset(sid)


def _diag(sid):
    a = _asset(sid)
    if not a:
        raise KeyError('asset-not-found')
    with ptr_fast.ASSEMBLY_LOCK:
        return v39.anim.scan_animation(a, core, ptr, dependency_rows, CACHE_ROOT)


def _clean_token(raw):
    s = str(raw or '').strip().replace('\\', '/')
    if not s:
        return ''
    s = s.split('?', 1)[0].split('#', 1)[0]
    tail = s.rsplit('/', 1)[-1]
    if tail.lower().endswith('.prefab'):
        tail = tail[:-7]
    return tail.strip()


def _tokens_for_script(script):
    out = []
    seen = set()

    def add(value, evidence):
        raw = str(value or '').strip()
        if not raw:
            return
        # Preserve full Assets/...prefab strings as strongest evidence.
        if raw.lower().startswith('assets/') and '.prefab' in raw.lower():
            full = raw[: raw.lower().find('.prefab') + 7].replace('\\', '/')
            key = ('path', full.casefold())
            if key not in seen:
                seen.add(key); out.append({'kind':'path','value':full,'evidence':evidence})
        # Also extract the prefab-like leaf/token.
        for m in PREFAB_TOKEN.finditer(raw):
            val = m.group(0).replace('\\', '/')
            leaf = _clean_token(val)
            if len(leaf) < 8 or leaf.casefold() in GENERIC:
                continue
            key = ('name', leaf.casefold())
            if key not in seen:
                seen.add(key); out.append({'kind':'name','value':leaf,'evidence':evidence})

    node = str(script.get('nodePath') or script.get('gameObject') or '')
    if node:
        add(node.rsplit('/', 1)[-1], 'node-path')
    for hint in script.get('stringHints') or []:
        add(hint.get('value'), 'serialized:' + str(hint.get('field') or '?'))
    return out[:32]


def _candidate_rows(tokens, source_sid):
    con = core.dbcon()
    rows = {}
    try:
        for t in tokens:
            value = str(t.get('value') or '').strip()
            if not value:
                continue
            if t.get('kind') == 'path':
                norm = value.replace('\\', '/').lower()
                part = con.execute(
                    "SELECT * FROM assets WHERE stable_id<>? AND lower(replace(asset_path,'\\\\','/'))=? LIMIT 40",
                    (source_sid, norm)
                ).fetchall()
            else:
                low = value.lower()
                patterns = [
                    '%/' + low + '.prefab',
                    '%/' + low,
                    '%' + low + '%',
                ]
                part = []
                for pat in patterns:
                    got = con.execute(
                        "SELECT * FROM assets WHERE stable_id<>? AND (lower(asset_path) LIKE ? OR lower(search_text) LIKE ?) LIMIT 90",
                        (source_sid, pat, pat)
                    ).fetchall()
                    part.extend(got)
                    if got and pat.endswith('.prefab'):
                        break
            for r in part:
                d = core.rowdict(r)
                rows[d.get('stable_id')] = d
    finally:
        con.close()
    return list(rows.values())


def _score_candidate(c, tokens):
    path = str(c.get('asset_path') or c.get('logical_name') or c.get('alias_name') or '').replace('\\', '/')
    low = path.lower()
    base = path.rsplit('/', 1)[-1]
    stem = base[:-7] if base.lower().endswith('.prefab') else base.rsplit('.', 1)[0]
    score = 0
    reasons = []
    exact_name = False
    exact_path = False
    for t in tokens:
        val = str(t.get('value') or '').replace('\\', '/')
        if t.get('kind') == 'path' and low == val.lower():
            score += 500; exact_path = True; reasons.append('chemin prefab exact')
        elif t.get('kind') == 'name' and stem.casefold() == val.casefold():
            score += 360; exact_name = True; reasons.append('nom prefab exact ' + val)
        elif t.get('kind') == 'name' and val.casefold() in low:
            score += 120; reasons.append('nom présent ' + val)
    role = str(c.get('model_role') or '').lower()
    dim = str(c.get('dimension_class') or '').lower()
    avail = str(c.get('render_availability') or '').lower()
    tech = str(c.get('tech_kind') or '').lower()
    if low.endswith('.prefab') or role == 'prefab':
        score += 90; reasons.append('asset prefab')
    if '3d' in dim or role in {'prefab','model','geometry','geometry-candidate'}:
        score += 45; reasons.append('candidat 3D')
    if avail.startswith('local-'):
        score += 35; reasons.append('source locale')
    if '/prefab' in low:
        score += 20
    if dim == '2d' or '/sprites/' in low or '/icons/' in low:
        score -= 240
    if role in {'texture','material'} or 'texture' in tech:
        score -= 160
    return score, reasons, exact_name, exact_path


def _variant(node_path):
    p = str(node_path or '').lower()
    if '/idle/' in '/' + p: return 'idle'
    if '/work/' in '/' + p: return 'work'
    if '/upgrade/' in '/' + p: return 'upgrade'
    if 'leveltip' in p: return 'level-tip'
    return 'runtime'


def resolve_soft_prefabs(sid, materialize=True):
    sid = str(sid or '').strip().upper()
    if not EXACT_ID.fullmatch(sid):
        return {'error':'invalid-id','id':sid}, 400
    try:
        diag = _diag(sid)
    except KeyError:
        return {'error':'asset-not-found','id':sid}, 404
    except Exception as exc:
        return {'error':'diagnostic-failed','id':sid,'message':str(exc)}, 500

    scripts = diag.get('components', {}).get('scripts') or []
    soft = [s for s in scripts if (str(s.get('className') or s.get('scriptName') or '').casefold() == 'softreferenceprefab')]
    refs = []
    for s in soft:
        tokens = _tokens_for_script(s)
        rows = _candidate_rows(tokens, sid) if tokens else []
        ranked = []
        for c in rows:
            score, reasons, exact_name, exact_path = _score_candidate(c, tokens)
            if score < 120:
                continue
            ranked.append({
                'stable_id': c.get('stable_id'),
                'asset_path': c.get('asset_path'),
                'dimension_class': c.get('dimension_class'),
                'model_role': c.get('model_role'),
                'render_availability': c.get('render_availability'),
                'render_source_reason': c.get('render_source_reason'),
                'bundle_id': c.get('bundle_id'),
                'score': score,
                'reasons': reasons,
                'exactName': exact_name,
                'exactPath': exact_path,
            })
        ranked.sort(key=lambda x: (x['score'], str(x.get('render_availability') or '').startswith('local-')), reverse=True)
        ranked = ranked[:6]

        recovery = None
        top = ranked[0] if ranked else None
        if materialize and top and (top.get('exactName') or top.get('exactPath')) and not str(top.get('render_availability') or '').startswith('local-'):
            try:
                recovery, status = v397.recover_source(top['stable_id'])
                if status == 200 and recovery.get('recovered'):
                    fresh = _asset(top['stable_id']) or {}
                    top['render_availability'] = fresh.get('render_availability')
                    top['render_source_reason'] = fresh.get('render_source_reason')
            except Exception as exc:
                recovery = {'recovered':False,'error':str(exc)}

        refs.append({
            'nodePath': s.get('nodePath'),
            'gameObject': s.get('gameObject'),
            'variant': _variant(s.get('nodePath')),
            'scriptPathId': s.get('pathId'),
            'tokens': tokens,
            'candidates': ranked,
            'best': top,
            'recovery': recovery,
        })

    resolved = [r for r in refs if r.get('best')]
    local = [r for r in resolved if str((r.get('best') or {}).get('render_availability') or '').startswith('local-')]
    return {
        'version':'39.12',
        'stableId':sid,
        'rootGameObject':diag.get('rootGameObject'),
        'softReferenceCount':len(soft),
        'resolvedCount':len(resolved),
        'localResolvedCount':len(local),
        'items':refs,
        'assemblyPlan':[
            {
                'slot':r.get('nodePath'),
                'variant':r.get('variant'),
                'stable_id':(r.get('best') or {}).get('stable_id'),
                'asset_path':(r.get('best') or {}).get('asset_path'),
                'availability':(r.get('best') or {}).get('render_availability'),
                'exact':bool((r.get('best') or {}).get('exactName') or (r.get('best') or {}).get('exactPath')),
            }
            for r in resolved
        ],
        'assemblyReady': bool(resolved) and all(
            bool((r.get('best') or {}).get('exactName') or (r.get('best') or {}).get('exactPath')) and
            str((r.get('best') or {}).get('render_availability') or '').startswith('local-')
            for r in resolved
        ),
        'policy':'SoftReferencePrefab only. Exact serialized/name/path evidence is required for automatic physical recovery. No visual-similarity substitution. Parent+child merged rendering stays disabled until every chosen slot is exact and local.'
    }, 200


def _send_js(handler, text):
    raw = text.encode('utf-8')
    handler.send_response(200)
    handler.send_header('Content-Type','application/javascript; charset=utf-8')
    handler.send_header('Content-Length',str(len(raw)))
    handler.send_header('Cache-Control','no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma','no-cache')
    handler.send_header('Expires','0')
    handler.end_headers(); handler.wfile.write(raw)


class V3912Handler(v398.HotfixHandler):
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == '/lab/global-graphics-v33/animation-viewer-v39.js':
            try:
                text = v398.ORIGINAL_JS.read_text('utf-8')
                count = text.count(v398.BAD)
                if count != 1:
                    raise RuntimeError('V39_12_EXPECTED_GETTER_ASSIGNMENT_COUNT_' + str(count))
                text = text.replace(v398.BAD, v398.GOOD)
                text += "\n;(()=>{if(!document.querySelector('script[data-wfgg-v3912-softprefab]')){const s=document.createElement('script');s.src='/lab/global-graphics-v33/animation-softprefab-v3912.js?v=3912';s.dataset.wfggV3912Softprefab='1';document.head.appendChild(s);}})();\n"
                return _send_js(self, text)
            except Exception as exc:
                return self.send_json({'error':'v39.12-viewer-loader-failed','message':str(exc)},500)
        if u.path == '/lab/global-graphics-v33/animation-softprefab-v3912.js':
            try:
                return _send_js(self, ADDON_JS.read_text('utf-8'))
            except Exception as exc:
                return self.send_json({'error':'v39.12-addon-failed','message':str(exc)},500)
        if u.path == '/api/v39/soft-prefabs':
            sid = str((qs.get('id') or [''])[0])
            materialize = str((qs.get('materialize') or ['1'])[0]).lower() not in {'0','false','no'}
            payload, status = resolve_soft_prefabs(sid, materialize=materialize)
            print('V39_12_SOFTPREFAB', sid, 'resolved='+str(payload.get('resolvedCount',0)), 'local='+str(payload.get('localResolvedCount',0)), 'ready='+str(payload.get('assemblyReady',False)), flush=True)
            return self.send_json(payload, status)
        if u.path == '/api/v39/status':
            return self.send_json({
                'version':'39.12',
                'animationDiagnostics':True,
                'getterOnlyLastHotfix':True,
                'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,
                'exactAssetValidationRequired':True,
                'softReferencePrefabResolver':True,
                'softReferencePhysicalRecovery':True,
                'softReferenceAssemblyPlan':True,
                'mergedAssemblyEnabled':False,
                'syntheticAnimation':False,
                'referenceAsset':'LWGA-C37A0F67197299',
                'referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.12 — SOFT PREFAB TRACE ===', flush=True)
    print('V39_12_BADGE same-row-render-badge=ON viewport-clamp=ON', flush=True)
    print('V39_12_SOFTPREFAB serialized-evidence=ON exact-name-path=REQUIRED physical-recovery=ON', flush=True)
    print('V39_12_ASSEMBLY plan=ON merged-render=GUARDED_UNTIL_ALL_EXACT_LOCAL', flush=True)
    print('V39_7_SOURCE_RECOVERY inherited=ON shifted-offset=ON exact-asset-validation=REQUIRED', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), V3912Handler).serve_forever()
