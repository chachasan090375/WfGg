#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/cmd/radar-connector/main.go'
NATIVE_MAIN = ROOT / 'connector-go/native-template/main.go'
BRIDGE = ROOT / 'connector-go/internal/protocol/profile_scan_v69.go'
HELPER = ROOT / 'connector-go/native-template/profile_scan_v69.go'
SRC = Path('.radar-release-src/v691-source/connector-go/internal/protocol')


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def install_sources() -> None:
    for name in ('profile_handshake_v691.go', 'profile_handshake_v691_test.go'):
        src = SRC / name
        dst = ROOT / 'connector-go/internal/protocol' / name
        if not src.is_file():
            raise SystemExit(f'V691_SOURCE_MISSING={src}')
        shutil.copyfile(src, dst)


def patch_health() -> None:
    text = MAIN.read_text(encoding='utf-8')
    if 'WFGG_RADAR_NATIVE_PROFILE_HEALTH_V691' in text:
        print('RADAR_V691_HEALTH=ALREADY_PRESENT')
        return
    old = '''func (s *server) health(w http.ResponseWriter, _ *http.Request, _ []byte) {\n\twriteJSON(w, http.StatusOK, map[string]any{"ok": true, "service": "wfgg-radar-connector", "version": "0.5.0-collector-async-email-auth-v1", "protocol": s.game.Mode(), "readonly": true, "collectorAsync": true, "emailAuth": s.emailAuth.available()})\n}\n'''
    new = '''func (s *server) health(w http.ResponseWriter, _ *http.Request, _ []byte) {\n\t// WFGG_RADAR_NATIVE_PROFILE_HEALTH_V691\n\tpayload := map[string]any{"ok": true, "service": "wfgg-radar-connector", "version": "0.5.0-collector-async-email-auth-v1-v691", "protocol": s.game.Mode(), "readonly": true, "collectorAsync": true, "emailAuth": s.emailAuth.available()}\n\tif p, ok := s.game.(interface{ RuntimeDiagnostics() map[string]any }); ok {\n\t\tpayload["nativeHelper"] = p.RuntimeDiagnostics()\n\t}\n\twriteJSON(w, http.StatusOK, payload)\n}\n'''
    if old not in text:
        raise SystemExit('health handler anchor missing')
    MAIN.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V691_HEALTH=PATCHED')


def patch_native_capabilities() -> None:
    text = NATIVE_MAIN.read_text(encoding='utf-8')
    if 'WFGG_RADAR_NATIVE_PROFILE_CAPABILITIES_V691' in text:
        print('RADAR_V691_CAPABILITIES=ALREADY_PRESENT')
        return
    old = 'func main() {\n'
    new = '''func main() {\n\t// WFGG_RADAR_NATIVE_PROFILE_CAPABILITIES_V691\n\tif len(os.Args) == 2 && os.Args[1] == "--capabilities" {\n\t\t_ = json.NewEncoder(os.Stdout).Encode(map[string]any{\n\t\t\t"ok": true,\n\t\t\t"mode": "native-template-readonly-v4",\n\t\t\t"readonly": true,\n\t\t\t"profileHandshake": "v6.9.1",\n\t\t\t"profileCLI": true,\n\t\t\t"profileCommand": "get.user.info.multi",\n\t\t})\n\t\treturn\n\t}\n'''
    if text.count(old) != 1:
        raise SystemExit(f'native main anchor count={text.count(old)}')
    NATIVE_MAIN.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V691_CAPABILITIES=PATCHED')


def patch_bridge() -> None:
    text = BRIDGE.read_text(encoding='utf-8')
    if 'profileFailureV691(rep)' in text:
        print('RADAR_V691_BRIDGE=ALREADY_PRESENT')
        return
    old = 'return nil, profileFailureV69(rep)'
    if text.count(old) != 1:
        raise SystemExit(f'profile failure anchor count={text.count(old)}')
    BRIDGE.write_text(text.replace(old, 'return nil, profileFailureV691(rep)', 1), encoding='utf-8')
    print('RADAR_V691_BRIDGE=PATCHED')


def patch_helper() -> None:
    text = HELPER.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_NATIVE_PROFILE_DECODE_STAGE_V691'
    if marker in text:
        print('RADAR_V691_HELPER=ALREADY_PRESENT')
        return
    old = '''\tif diag.CommandMatches == 0 {\n\t\treturn nil, diag, errors.New("PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")\n\t}\n'''
    new = '''\t// WFGG_RADAR_NATIVE_PROFILE_DECODE_STAGE_V691\n\tif diag.CommandMatches == 0 {\n\t\tif diag.DecodeErrors > 0 {\n\t\t\treturn nil, diag, errors.New("PLAYER_PROFILE_DECODE_FAILED")\n\t\t}\n\t\treturn nil, diag, errors.New("PLAYER_PROFILE_RESPONSE_NOT_OBSERVED")\n\t}\n'''
    if old not in text:
        raise SystemExit('helper response anchor missing')
    HELPER.write_text(text.replace(old, new, 1), encoding='utf-8')
    print('RADAR_V691_HELPER=PATCHED')


install_sources()
patch_health()
patch_native_capabilities()
patch_bridge()
patch_helper()
print('RADAR_NATIVE_PROFILE_HANDSHAKE_V691=READY')
