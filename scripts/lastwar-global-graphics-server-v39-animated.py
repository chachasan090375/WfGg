#!/usr/bin/env python3
from __future__ import annotations

"""WfGg Last War graphics LAB V39: exact animated-prefab diagnostics.

This is a non-destructive wrapper around the current V33/V34/V35/V38 explorer. It adds exact
Unity animation diagnostics plus V39.2 relation resolution when the selected catalogue entry is
only a 2D UI/build icon while the runtime animation lives on a separate prefab.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v33-explorer.py'
SCANNER = ROOT / 'scripts/lastwar-global-graphics-animation-v39.py'
BINDINGS = ROOT / 'scripts/lastwar-global-graphics-animation-bindings-v39.py'
V39_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-viewer-v39.js'
V391_RUNTIME_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-runtime-v39.js'
V392_RESOLVER_JS = ROOT / 'frontend/lab/global-graphics-v33/animation-resolver-v392.js'
VIEWER = ROOT / 'frontend/lab/lastwar-global-graphics-viewer-v33.html'
CACHE_ROOT = Path.home() / '.cache/wfgg-lastwar-v31'

spec = importlib.util.spec_from_file_location('wfgg_v33_explorer_for_v39', BASE)
v33 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v33)

aspec = importlib.util.spec_from_file_location('wfgg_animation_v39', SCANNER)
anim = importlib.util.module_from_spec(aspec)
aspec.loader.exec_module(anim)

bspec = importlib.util.spec_from_file_location('wfgg_animation_bindings_v39', BINDINGS)
bindings = importlib.util.module_from_spec(bspec)
bspec.loader.exec_module(bindings)

base = v33.base
core = v33.core
ptr_fast = base.ptr3d
ptr = ptr_fast.p
dependency_rows = v33.mobile.ORIGINAL_DEPENDENCY_ROWS


def _send_js(handler, path):
    raw = path.read_bytes()
    handler.send_response(200)
    handler.send_header('Content-Type', 'application/javascript; charset=utf-8')
    handler.send_header('Content-Length', str(len(raw)))
    handler.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
    handler.send_header('Pragma', 'no-cache')
    handler.send_header('Expires', '0')
    handler.end_headers()
    handler.wfile.write(raw)


def _asset(sid):
    if hasattr(core, 'get_asset'):
        try:
            a = core.get_asset(sid)
            if a:
                return a
        except Exception:
            pass
    con = core.dbcon()
    try:
        row = con.execute('SELECT * FROM assets WHERE stable_id=?', (sid,)).fetchone()
        return core.rowdict(row) if row else None
    finally:
        con.close()


def _relation_tokens(a):
    text = ' '.join(str(a.get(k) or '') for k in (
        'asset_path', 'logical_name', 'alias_name', 'subject', 'family', 'subfamily', 'context', 'search_text'
    ))
    # Runtime/building identifiers are usually long numeric IDs. They are much safer than generic
    # words such as "building" or "ui", which would create thousands of false relations.
    nums = []
    for tok in re.findall(r'(?<!\d)(\d{5,12})(?!\d)', text):
        if tok not in nums:
            nums.append(tok)
    # Keep a few long alphanumeric identity stems only as a secondary signal.
    words = []
    for tok in re.findall(r'[A-Za-z][A-Za-z0-9_-]{6,40}', text):
        low = tok.lower().strip('_-')
        if low in {'assets', 'sprites', 'building', 'buildiconoutcity', 'unknown', 'current', 'default'}:
            continue
        if low not in words:
            words.append(low)
    return nums[:8], words[:8]


def _score_target(src, cand, nums, words):
    p = str(cand.get('asset_path') or cand.get('logical_name') or cand.get('alias_name') or '').replace('\\', '/').lower()
    text = ' '.join(str(cand.get(k) or '') for k in ('asset_path', 'logical_name', 'alias_name', 'subject', 'search_text')).lower()
    dim = str(cand.get('dimension_class') or '').lower()
    role = str(cand.get('model_role') or '').lower()
    tech = str(cand.get('tech_kind') or '').lower()
    availability = str(cand.get('render_availability') or '').lower()
    score = 0
    reasons = []
    matched_nums = [x for x in nums if x in text]
    matched_words = [x for x in words if x in text]
    if matched_nums:
        score += 125 + 20 * min(3, len(matched_nums)); reasons.append('identifiant '+','.join(matched_nums[:3]))
    if matched_words:
        score += 8 * min(3, len(matched_words)); reasons.append('nom '+','.join(matched_words[:3]))
    if dim in {'3d', 'composant 3d', 'mixte 2d/3d'} or '3d' in dim:
        score += 95; reasons.append('asset 3D')
    if role == 'prefab' or p.endswith('.prefab'):
        score += 95; reasons.append('prefab')
    elif role in {'geometry', 'geometry-candidate', 'model'} or p.endswith(('.fbx', '.obj', '.mesh')):
        score += 55; reasons.append('géométrie')
    if any(x in tech for x in ('animator', 'animation', 'gameobject', 'prefab')):
        score += 25; reasons.append('type runtime')
    if availability.startswith('local-'):
        score += 18; reasons.append('bundle local')
    if '/prefab' in p or '/model' in p or '/building' in p:
        score += 18
    if '/sprites/' in p or '/icons/' in p or '/ui/' in p or p.endswith(('.png', '.jpg', '.jpeg', '.webp')):
        score -= 110
    if dim == '2d':
        score -= 80
    if role in {'texture', 'material'}:
        score -= 65
    if str(cand.get('stable_id') or '') == str(src.get('stable_id') or ''):
        score -= 1000
    return score, reasons


def _animation_targets(sid):
    src = _asset(sid)
    if not src:
        return {'source': None, 'tokens': [], 'candidates': []}
    nums, words = _relation_tokens(src)
    if not nums and not words:
        return {'source': src, 'tokens': [], 'candidates': []}
    con = core.dbcon()
    rows = []
    seen = set()
    try:
        # Prefer numeric identities. search_text is the catalogue's denormalized searchable corpus
        # and already includes path/name metadata, so this remains independent of any one column.
        for tok in nums:
            try:
                part = con.execute('SELECT * FROM assets WHERE stable_id<>? AND lower(search_text) LIKE ? LIMIT 260', (sid, '%'+tok.lower()+'%')).fetchall()
            except Exception:
                part = []
            for r in part:
                d = core.rowdict(r)
                if d['stable_id'] not in seen:
                    seen.add(d['stable_id']); rows.append(d)
        # If no numeric relation exists in the corpus, cautiously try the strongest long stem.
        if not rows and words:
            for tok in words[:2]:
                try:
                    part = con.execute('SELECT * FROM assets WHERE stable_id<>? AND lower(search_text) LIKE ? LIMIT 180', (sid, '%'+tok+'%')).fetchall()
                except Exception:
                    part = []
                for r in part:
                    d = core.rowdict(r)
                    if d['stable_id'] not in seen:
                        seen.add(d['stable_id']); rows.append(d)
    finally:
        con.close()
    out = []
    for d in rows:
        score, reasons = _score_target(src, d, nums, words)
        if score < 70:
            continue
        rec = dict(d)
        rec['resolver_score'] = score
        rec['resolver_reasons'] = reasons
        out.append(rec)
    out.sort(key=lambda x: (x.get('resolver_score', 0), float(x.get('confidence') or 0)), reverse=True)
    return {
        'source': src,
        'tokens': nums,
        'fallbackWords': words,
        'candidates': out[:24],
        'policy': 'Shared long identity tokens first; 3D/prefab/local evidence increases rank; UI/raster/texture candidates are penalized. Animation is asserted only after the exact V39 scanner validates the candidate.'
    }


class AnimatedHandler(v33.ExplorerHandler):
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        try:
            if u.path == '/lab/global-graphics-v33/animation-viewer-v39.js':
                return _send_js(self, V39_JS)
            if u.path == '/lab/global-graphics-v33/animation-runtime-v39.js':
                return _send_js(self, V391_RUNTIME_JS)
            if u.path == '/lab/global-graphics-v33/animation-resolver-v392.js':
                return _send_js(self, V392_RESOLVER_JS)

            if u.path == '/api/v39/animation-targets':
                sid = str((qs.get('id') or [''])[0])
                if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
                    return self.send_json({'error': 'invalid-id'}, 400)
                payload = _animation_targets(sid)
                if not payload.get('source'):
                    return self.send_json({'error': 'asset-not-found', 'id': sid}, 404)
                print('V39_2_ANIMATION_TARGETS', sid, 'tokens='+','.join(payload.get('tokens') or []), 'candidates='+str(len(payload.get('candidates') or [])), flush=True)
                return self.send_json(payload)

            if u.path == '/api/v39/animation':
                sid = str((qs.get('id') or [''])[0])
                if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
                    return self.send_json({'error': 'invalid-id'}, 400)
                a = _asset(sid)
                if not a:
                    return self.send_json({'error': 'asset-not-found', 'id': sid}, 404)
                with ptr_fast.ASSEMBLY_LOCK:
                    payload = anim.scan_animation(a, core, ptr, dependency_rows, CACHE_ROOT)
                print(
                    'V39_ANIMATION_SCAN', sid,
                    payload.get('classification', {}).get('status', ''),
                    'clips=' + str(payload.get('clips', {}).get('directLinkedCount', 0)),
                    'nodes=' + str(payload.get('hierarchy', {}).get('nodeCount', 0)),
                    'cache=' + ('HIT' if payload.get('cacheHit') else 'MISS'),
                    flush=True,
                )
                return self.send_json(payload)

            if u.path == '/api/v39/animation-bindings':
                sid = str((qs.get('id') or [''])[0])
                if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
                    return self.send_json({'error': 'invalid-id'}, 400)
                a = _asset(sid)
                if not a:
                    return self.send_json({'error': 'asset-not-found', 'id': sid}, 404)
                with ptr_fast.ASSEMBLY_LOCK:
                    payload = bindings.build_bindings(a, core, ptr, dependency_rows, CACHE_ROOT)
                print('V39_ANIMATION_BINDINGS', sid, 'nodes='+str(payload.get('nodeCount', 0)), 'meshes='+str(payload.get('meshBindingCount', 0)), 'cache='+('HIT' if payload.get('cacheHit') else 'MISS'), flush=True)
                return self.send_json(payload)

            if u.path == '/api/v39/status':
                return self.send_json({
                    'version': '39.2',
                    'animationDiagnostics': True,
                    'exactBundlePtrEvidence': True,
                    'syntheticAnimation': False,
                    'playbackRuntime': 'reconstructed-simple-transform-curves',
                    'exactMeshTransformBindings': True,
                    'iconToPrefabResolver': True,
                    'referenceAsset': 'LWGA-C37A0F67197299',
                })

            if u.path == '/lab/lastwar-global-graphics-viewer-v33.html':
                raw = VIEWER.read_text('utf-8')
                corr = '<script src="./global-graphics-v33/search-correlation-v33.js"></script>'
                exp = '<script src="./global-graphics-v33/explorer-v33.js"></script>'
                v39 = '<script src="./global-graphics-v33/animation-viewer-v39.js?v=3901"></script>'
                v391 = '<script src="./global-graphics-v33/animation-runtime-v39.js?v=3911"></script>'
                v392 = '<script src="./global-graphics-v33/animation-resolver-v392.js?v=3921"></script>'
                if 'search-correlation-v33.js' not in raw:
                    raw = raw.replace('</body>', corr + '</body>')
                if 'explorer-v33.js' not in raw:
                    raw = raw.replace('</body>', exp + '</body>')
                if 'animation-viewer-v39.js' not in raw:
                    raw = raw.replace('</body>', v39 + '</body>')
                if 'animation-runtime-v39.js' not in raw:
                    raw = raw.replace('</body>', v391 + '</body>')
                if 'animation-resolver-v392.js' not in raw:
                    raw = raw.replace('</body>', v392 + '</body>')
                data = raw.encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(data)
                return
        except Exception as exc:
            print('V39_ANIMATION_ERROR', type(exc).__name__, str(exc)[:900], flush=True)
            return self.send_json({'error': 'v39-animation-failed', 'message': str(exc)}, 500)
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.2 — ANIMATED PREFAB + ICON RESOLVER ===', flush=True)
    print('V39_ANIMATION exact-bundle-ptr=ON transform-curves=INSPECT synthetic-motion=OFF', flush=True)
    print('V39_PLAYBACK simple-transform-curves=RECONSTRUCTABLE exact-mesh-bindings=ON', flush=True)
    print('V39_2_ICON_RESOLVER shared-runtime-id=ON ui-icon-to-prefab=ON animation-validation=EXACT_SCAN', flush=True)
    print('V39_PARTICLES detection=ON playback=NOT_YET', flush=True)
    print('V39_SCRIPTS animation-hints=CONSERVATIVE execution=OFF', flush=True)
    print('V39_REFERENCE_ASSET LWGA-C37A0F67197299', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), AnimatedHandler).serve_forever()
