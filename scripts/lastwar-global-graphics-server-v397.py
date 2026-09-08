#!/usr/bin/env python3
from __future__ import annotations

"""V39.7 runtime wrapper.

Adds on-demand restoration for assets previously demoted to INDEX SEULEMENT when their indexed
UnityFS offset became stale after a Last War update. Recovery is delegated to the V39.7
source-fixed materializer, which searches only the same BundleFragment and accepts a relocated
candidate only after exact Unity asset validation.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import importlib.util, re, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
BASE = ROOT / 'scripts/lastwar-global-graphics-server-v39-animated.py'

spec = importlib.util.spec_from_file_location('wfgg_v39_animated_for_397', BASE)
v39 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v39)

core = v39.core
# explorer -> sourcefixed-debug -> sourcefixed
sourcefixed = v39.v33.base.m


def _maybe_restore(sid: str):
    sid = str(sid or '').strip().upper()
    if not re.fullmatch(r'LWGA-[A-Z0-9]+', sid):
        return False, 'invalid-id'
    a = v39._asset(sid)
    if not a:
        return False, 'asset-not-found'
    availability = str(a.get('render_availability') or '')
    reason = str(a.get('render_source_reason') or '')
    if availability != 'global-index-only':
        return True, 'already-' + availability
    # Only auto-retry rows demoted by runtime materialization or source presence logic.
    if not ('source-not-materializable' in reason or 'runtime-fragment-source-absent' in reason or reason.startswith('runtime:')):
        return False, 'index-only-not-runtime-demoted'
    fn = getattr(sourcefixed, 'try_restore_runtime_asset', None)
    if not callable(fn):
        return False, 'restore-function-unavailable'
    ok, detail = fn(a)
    print('V39_7_ON_DEMAND_RESTORE', sid, 'ok=' + str(bool(ok)), str(detail)[:500], flush=True)
    return bool(ok), str(detail)


class Handler(v39.AnimatedHandler):
    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        try:
            if u.path == '/api/v39/status':
                return self.send_json({
                    'version': '39.7',
                    'animationDiagnostics': True,
                    'exactBundlePtrEvidence': True,
                    'syntheticAnimation': False,
                    'playbackRuntime': 'reconstructed-simple-transform-curves',
                    'exactMeshTransformBindings': True,
                    'iconToPrefabResolver': True,
                    'exactStableIdLookup': True,
                    'exactStableIdFilterBypass': True,
                    'shiftedBundleRecovery': True,
                    'sameFragmentOnly': True,
                    'exactAssetValidationRequired': True,
                    'referenceAsset': 'LWGA-C37A0F67197299',
                    'referencePrefab': 'LWGA-0D0CA2A747F7DF',
                })

            sid = ''
            if u.path == '/api/v33/search':
                sid = str((qs.get('stable_id') or [''])[0]).strip().upper()
            elif u.path in {'/api/v39/animation', '/api/v39/animation-bindings'}:
                sid = str((qs.get('id') or [''])[0]).strip().upper()

            if sid:
                _maybe_restore(sid)
        except Exception as exc:
            print('V39_7_RESTORE_GUARD_ERROR', type(exc).__name__, str(exc)[:600], flush=True)
        return super().do_GET()


if __name__ == '__main__':
    print('=== WFGG LAST WAR GLOBAL GRAPHICS V39.7 — SHIFTED BUNDLE RECOVERY ===', flush=True)
    print('V39_7_OFFSET_RECOVERY same-fragment=ONLY unityfs-scan=±8MiB exact-asset-validation=REQUIRED', flush=True)
    print('V39_7_REFERENCE_PREFAB LWGA-0D0CA2A747F7DF building_10123000.prefab', flush=True)
    print(f'http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1', core.PORT), Handler).serve_forever()
