#!/usr/bin/env python3
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
SRC = Path('.radar-release-src/v693-source/connector-go/cmd/radar-connector')
DST = ROOT / 'connector-go/cmd/radar-connector'


def install_sources() -> None:
    for name in ('runtime_fingerprint_v693.go', 'runtime_fingerprint_v693_test.go'):
        src = SRC / name
        dst = DST / name
        if not src.is_file():
            raise SystemExit(f'V693_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_health() -> None:
    text = MAIN.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_CONNECTOR_RUNTIME_HEALTH_V693'
    if marker in text:
        print('RADAR_V693_HEALTH=ALREADY_PRESENT')
        return
    old = '''\tif p, ok := s.game.(interface{ RuntimeDiagnostics() map[string]any }); ok {\n\t\tpayload["nativeHelper"] = p.RuntimeDiagnostics()\n\t}\n\twriteJSON(w, http.StatusOK, payload)\n'''
    new = '''\tif p, ok := s.game.(interface{ RuntimeDiagnostics() map[string]any }); ok {\n\t\tpayload["nativeHelper"] = p.RuntimeDiagnostics()\n\t}\n\t// WFGG_RADAR_CONNECTOR_RUNTIME_HEALTH_V693\n\tpayload["connectorRuntime"] = connectorRuntimeDiagnosticsV693()\n\tpayload["version"] = "0.5.0-collector-async-email-auth-v1-v693"\n\twriteJSON(w, http.StatusOK, payload)\n'''
    if text.count(old) != 1:
        raise SystemExit(f'V693_HEALTH_ANCHOR_COUNT={text.count(old)}')
    MAIN.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V693_HEALTH=PATCHED')


def run_patch(path: str, ready: str) -> None:
    script = Path(path)
    if not script.is_file():
        raise SystemExit(f'PATCH_MISSING={script}')
    subprocess.run([sys.executable, str(script)], check=True)
    print(ready)


install_sources()
patch_health()
run_patch('.github/scripts/patch-radar-full-profile-universe-v697.py', 'RADAR_FULL_PROFILE_UNIVERSE_V697=CHAINED')
run_patch('.github/scripts/patch-radar-collector-live-audit-v699.py', 'RADAR_COLLECTOR_LIVE_AUDIT_V699=CHAINED')
run_patch('.github/scripts/patch-radar-collector-index-v610.py', 'RADAR_COLLECTOR_INDEX_V610=CHAINED')
run_patch('.github/scripts/patch-radar-collector-fast-lookup-v611.py', 'RADAR_FAST_IDENTITY_LOOKUP_V611=CHAINED')
run_patch('.github/scripts/patch-radar-server-census-v612.py', 'RADAR_SERVER_CENSUS_V612=CHAINED')
print('RADAR_CONNECTOR_RUNTIME_V693=READY')
