#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
BRIDGE = ROOT / 'connector-go/internal/protocol/profile_scan_v69.go'
SRC = Path('.radar-release-src/v692-source/connector-go/internal/protocol')


def install_sources() -> None:
    for name in ('profile_exec_v692.go', 'profile_exec_v692_test.go'):
        src = SRC / name
        dst = ROOT / 'connector-go/internal/protocol' / name
        if not src.is_file():
            raise SystemExit(f'V692_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_bridge() -> None:
    text = BRIDGE.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_NATIVE_PROFILE_EXEC_BRIDGE_V692'
    if marker in text:
        print('RADAR_V692_EXEC_BRIDGE=ALREADY_PRESENT')
        return

    old = '''\tvar rep nativeProfileReportV69\n\tif err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {\n\t\tif runErr != nil {\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_PROFILE_FAILED")\n\t\t}\n\t\treturn nil, errors.New("LASTWAR_PLAYER_PROFILE_REPORT_INVALID")\n\t}\n'''
    new = '''\tvar rep nativeProfileReportV69\n\t// WFGG_RADAR_NATIVE_PROFILE_EXEC_BRIDGE_V692\n\tif err := json.Unmarshal(stdout.Bytes(), &rep); err != nil {\n\t\treturn nil, profileExecutionFailureV692(runErr, stdout.Bytes(), stderr.Bytes())\n\t}\n'''
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'profile execution fallback anchor count={count}')
    BRIDGE.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V692_EXEC_BRIDGE=PATCHED')


install_sources()
patch_bridge()
print('RADAR_NATIVE_PROFILE_EXEC_V692=READY')
