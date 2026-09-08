#!/usr/bin/env python3
from __future__ import annotations

"""V39.7 physical bundle recovery wrapper.

When the icon resolver reaches the correct 3D prefab but its catalogue row is INDEX ONLY, this
wrapper performs a conservative source refresh. The underlying sourcefixed materializer now also
supports shifted UnityFS offsets inside the SAME BundleFragment and validates the exact indexed
asset before accepting a relocated bundle. Original sources are never modified.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, json, os, re, shutil, sys, time

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v39-animated.py'

spec = importlib.util.spec_from_file_location('wfgg_v39_base_for_recovery', BASE)
v39 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v39)

core = v39.core
v31 = v39.v33.v31
sf = v39.v33.sf

PRUNE = {'.git', 'node_modules', '__pycache__', 'renders'}
MAX_FILES = 140000
MAX_SECONDS = 18.0


def _asset(sid):
    return v39._asset(sid)


def _bundle_names(a):
    names = []
    for key in ('asset_path', 'logical_name', 'alias_name', 'subject'):
        raw = str(a.get(key) or '').replace('\\', '/')
        tail = raw.rsplit('/', 1)[-1].strip()
        if tail.lower().endswith('.bundle') and tail not in names:
            names.append(tail)
    return names


def _roots():
    home = Path.home()
    candidates = [
        ROOT / 'frontend/lab/local_assets',
        ROOT / 'frontend/lab/master-assets-v2',
        v31.BUNDLE_CACHE,
        home / '.cache/wfgg-lastwar-v31',
        home / 'storage/downloads',
        home / 'storage/shared/Download',
        Path('/sdcard/Download'),
        Path('/storage/emulated/0/Download'),
    ]
    out, seen = [], set()
    for p in candidates:
        try:
            if not p.exists():
                continue
            k = str(p.resolve())
        except Exception:
            continue
        if k in seen:
            continue
        seen.add(k); out.append(p)
    return out


def _good_exact_bundle(path: Path, span: int):
    try:
        if not path.is_file(): return False, 'not-file'
        size = path.stat().st_size
        if span > 0 and size != span: return False, f'size:{size}!={span}'
        with path.open('rb') as fh: head = fh.read(16)
        if not head.startswith((b'UnityFS', b'UnityWeb', b'UnityRaw')):
            return False, 'bad-header:' + head[:12].hex()
        return True, 'unity-bundle-exact-size'
    except Exception as exc:
        return False, 'io:' + str(exc)[:160]


def _search_exact_names(names, span):
    if not names: return [], {'roots': [], 'filesScanned': 0, 'timedOut': False}
    wanted = {x.casefold() for x in names}
    found = []
    roots = _roots(); scanned = 0; started = time.monotonic(); timed_out = False
    for base in roots:
        try:
            for dp, dirs, files in os.walk(base):
                dirs[:] = [d for d in dirs if d not in PRUNE]
                for fn in files:
                    scanned += 1
                    if scanned >= MAX_FILES or time.monotonic() - started > MAX_SECONDS:
                        timed_out = True; break
                    if fn.casefold() not in wanted:
                        continue
                    p = Path(dp) / fn
                    ok, reason = _good_exact_bundle(p, span)
                    found.append({'path': str(p), 'ok': ok, 'reason': reason})
                if timed_out: break
        except (OSError, PermissionError):
            pass
        if timed_out: break
    return found, {'roots': [str(x) for x in roots], 'filesScanned': scanned, 'timedOut': timed_out, 'seconds': round(time.monotonic()-started, 3)}


def _refresh_source_indexes():
    # Existing sourcefixed indexes are intentionally cached for speed. A recovery request means
    # "look again now", so invalidate only discovery indexes, never catalogue/audit data.
    try: v31._fragment_index = None
    except Exception: pass
    try: v31._apk_index = None
    except Exception: pass
    try: sf._apk_entries = None
    except Exception: pass


def _mark_local(sid, reason):
    con = core.dbcon()
    try:
        con.execute("UPDATE assets SET render_availability='local-exact', render_source_reason=? WHERE stable_id=?", (reason[:500], sid))
        con.commit()
    finally:
        con.close()


def recover_source(sid):
    sid = str(sid or '').strip().upper()
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
        return {'error': 'invalid-id', 'id': sid}, 400
    a = _asset(sid)
    if not a:
        return {'error': 'asset-not-found', 'id': sid}, 404
    try: bid = int(a.get('bundle_id') if a.get('bundle_id') is not None else -1)
    except Exception: bid = -1
    try: span = int(a.get('span_bytes') if a.get('span_bytes') is not None else -1)
    except Exception: span = -1

    result = {
        'stableId': sid,
        'assetPath': a.get('asset_path'),
        'bundleId': bid,
        'offsetBytes': a.get('offset_bytes'),
        'spanBytes': span,
        'fragmentEntry': a.get('fragment_entry'),
        'tableFragment': a.get('table_fragment'),
        'logicalBundleNames': _bundle_names(a),
        'beforeAvailability': a.get('render_availability'),
        'beforeReason': a.get('render_source_reason'),
        'recovered': False,
        'method': None,
        'source': None,
    }

    # 1. Refresh authoritative fragment/APK discovery and retry the enhanced materializer.
    # V39.7 sourcefixed can relocate a stale offset inside the same BundleFragment, but it must
    # prove the exact indexed asset path/object inside the candidate UnityFS before accepting it.
    _refresh_source_indexes()
    normal_error = None
    try:
        p, source = v31.materialize_bundle(a)
        if p and Path(p).is_file():
            method = 'shifted-offset-exact-validated' if 'shifted-offset' in str(source) else 'existing-materializer-refresh'
            result.update({'recovered': True, 'method': method, 'source': str(source), 'cachePath': str(p)})
            _mark_local(sid, 'v39.7-source-recovery:' + str(source))
    except Exception as exc:
        normal_error = str(exc)
    result['normalMaterializerError'] = normal_error

    # 2. Legacy fallback for exact standalone .bundle copies from previous WfGg extraction runs.
    if not result['recovered']:
        matches, stats = _search_exact_names(result['logicalBundleNames'], span)
        result['standaloneSearch'] = stats
        result['standaloneMatches'] = matches
        exact = next((m for m in matches if m.get('ok')), None)
        if exact and bid >= 0:
            src = Path(exact['path'])
            out = v31.BUNDLE_CACHE / f'bundle-{bid}.bundle'
            try:
                if src.resolve() != out.resolve(): shutil.copyfile(src, out)
                ok, reason = _good_exact_bundle(out, span)
                if ok:
                    try:
                        v31.BUNDLE_LRU[bid] = str(out)
                        v31.BUNDLE_LRU.move_to_end(bid)
                    except Exception: pass
                    _mark_local(sid, 'v39.7-exact-standalone:' + str(src))
                    result.update({'recovered': True, 'method': 'exact-standalone-bundle', 'source': str(src), 'cachePath': str(out), 'verification': reason})
            except Exception as exc:
                result['copyError'] = str(exc)

    after = _asset(sid)
    result['afterAvailability'] = after.get('render_availability') if after else None
    result['afterReason'] = after.get('render_source_reason') if after else None
    return result, 200


def _auto_recover_if_runtime_demoted(sid):
    sid = str(sid or '').strip().upper()
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
        return None
    a = _asset(sid)
    if not a:
        return None
    availability = str(a.get('render_availability') or '')
    reason = str(a.get('render_source_reason') or '')
    if availability != 'global-index-only':
        return None
    if not ('source-not-materializable' in reason or 'runtime-fragment-source-absent' in reason or reason.startswith('runtime:')):
        return None
    payload, _ = recover_source(sid)
    print(
        'V39_7_AUTO_SOURCE_RECOVERY', sid,
        'recovered=' + str(payload.get('recovered')),
        'method=' + str(payload.get('method')),
        'before=' + str(payload.get('beforeAvailability')),
        'after=' + str(payload.get('afterAvailability')),
        flush=True,
    )
    return payload


class RecoveryHandler(v39.AnimatedHandler):
    def do_GET(self):
        u = urlparse(self.path); qs = parse_qs(u.query)
        if u.path == '/api/v39/recover-source':
            try:
                payload, status = recover_source(str((qs.get('id') or [''])[0]))
                print('V39_7_SOURCE_RECOVERY', payload.get('stableId'), 'recovered='+str(payload.get('recovered')), 'method='+str(payload.get('method')), 'source='+str(payload.get('source'))[:300], flush=True)
                return self.send_json(payload, status)
            except Exception as exc:
                print('V39_7_SOURCE_RECOVERY_ERROR', type(exc).__name__, str(exc)[:700], flush=True)
                return self.send_json({'error':'v39-source-recovery-failed','message':str(exc)},500)

        # Automatic recovery before the parent handler returns an INDEX SEULEMENT asset or starts
        # animation analysis. This is what makes "Ouvrir le prefab 3D" retry the now-proven source.
        try:
            sid = ''
            if u.path == '/api/v33/search':
                sid = str((qs.get('stable_id') or [''])[0]).strip().upper()
            elif u.path in {'/api/v39/animation', '/api/v39/animation-bindings'}:
                sid = str((qs.get('id') or [''])[0]).strip().upper()
            if sid:
                _auto_recover_if_runtime_demoted(sid)
        except Exception as exc:
            print('V39_7_AUTO_SOURCE_RECOVERY_ERROR', type(exc).__name__, str(exc)[:700], flush=True)

        if u.path == '/api/v39/status':
            return self.send_json({
                'version':'39.7','animationDiagnostics':True,'exactStableIdLookup':True,
                'iconToPrefabResolver':True,'physicalSourceRecovery':True,
                'shiftedOffsetRecovery':True,'sameFragmentOnly':True,'exactAssetValidationRequired':True,
                'recoveryPolicy':'same BundleFragment; stale UnityFS offset scan ±8 MiB; exact Unity asset path/object validation required; standalone exact bundle fallback',
                'syntheticAnimation':False,'referenceAsset':'LWGA-C37A0F67197299',
                'referencePrefab':'LWGA-0D0CA2A747F7DF'
            })
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.7 — SHIFTED SOURCE RECOVERY ===', flush=True)
    print('V39_7_SOURCE_RECOVERY fragment-apk-refresh=ON shifted-offset=ON exact-asset-validation=REQUIRED approximate-substitution=OFF', flush=True)
    print('V39_7_REFERENCE_PREFAB LWGA-0D0CA2A747F7DF building_10123000.prefab', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), RecoveryHandler).serve_forever()
