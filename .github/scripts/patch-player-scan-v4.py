#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/native-template/main.go'
PROTO = ROOT / 'connector-go/internal/protocol/native_template.go'
V4_SRC = Path('.radar-release-src/v4-source/connector-go/native-template/player_scan_v4.go')
V4_DST = ROOT / 'connector-go/native-template/player_scan_v4.go'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


text = MAIN.read_text(encoding='utf-8')

text = replace_once(text, '''\tif scanMode {\n\t\tmapTemplates, profileTemplate = findPlayerScanV3Templates(convs, server)\n\t\tif len(mapTemplates) > 0 {\n\t\t\tscanCommand = v3MapCommand\n\t\t\tif profileTemplate != nil {\n\t\t\t\tscanCommand += "+" + v3ProfileCommand\n\t\t\t}\n\t\t}\n\t}\n''', '''\tif scanMode {\n\t\tmapTemplates, profileTemplate = findPlayerScanV3Templates(convs, server)\n\t\tscanCommand = v3MapCommand + "(synthetic-v4.1)"\n\t\tif len(mapTemplates) > 0 {\n\t\t\tscanCommand = v3MapCommand + "(captured-v3)"\n\t\t}\n\t\tif profileTemplate != nil {\n\t\t\tscanCommand += "+" + v3ProfileCommand\n\t\t}\n\t}\n''', 'v4 scan discovery')

text = replace_once(text, '''\tif scanMode && len(mapTemplates) > 0 {\n\t\tbase.ScanTemplateFound = true\n\t}\n\tif scanMode && !base.ScanTemplateFound {\n\t\tbase.LoginResponse = "PLAYER_SCAN_TEMPLATE_NOT_FOUND"\n\t\temit(base)\n\t\tos.Exit(5)\n\t}\n''', '''\tif scanMode {\n\t\t// V4 can synthesize world.get.block from the documented wire format, so\n\t\t// absence of a captured map request is no longer a deployment gate.\n\t\tbase.ScanTemplateFound = true\n\t}\n''', 'v4 template gate')

text = replace_once(text,
    '\tplayers, err := runPlayerScanV3(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n',
    '\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n',
    'v4 scan call')

text = text.replace('native-template-readonly-v3', 'native-template-readonly-v4')
MAIN.write_text(text, encoding='utf-8')

ptext = PROTO.read_text(encoding='utf-8')
ptext = ptext.replace('native-template-readonly-v3', 'native-template-readonly-v4')
ptext = replace_once(ptext,
    '''\t\tcase "PLAYER_SCAN_READ_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_READ_FAILED")\n''',
    '''\t\tcase "PLAYER_SCAN_READ_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_READ_FAILED")\n\t\tcase "PLAYER_SCAN_SERVER_ID_INVALID":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SERVER_ID_INVALID")\n\t\tcase "PLAYER_SCAN_SYNTHETIC_ENCODE_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_ENCODE_FAILED")\n\t\tcase "PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_DEADLINE_FAILED")\n\t\tcase "PLAYER_SCAN_SYNTHETIC_WRITE_TIMEOUT":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_WRITE_TIMEOUT")\n\t\tcase "PLAYER_SCAN_SYNTHETIC_WRITE_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_WRITE_FAILED")\n\t\tcase "PLAYER_SCAN_SYNTHETIC_READ_FAILED":\n\t\t\treturn nil, errors.New("LASTWAR_PLAYER_SCAN_SYNTHETIC_READ_FAILED")\n''',
    'v4 connector error mapping')

# V4.1 diagnostic failures carry peer details after a colon, for example
# PLAYER_SCAN_SYNTHETIC_READ_FAILED:*net.OpError:EOF:origin=... . The old exact
# switch therefore collapsed them to LASTWAR_PLAYER_SCAN_FAILED. Inject prefix
# guards immediately before the switch that owns PLAYER_SCAN_READ_FAILED, without
# assuming the local result variable name used by the immutable base release.
case_marker = '\t\tcase "PLAYER_SCAN_READ_FAILED":'
case_pos = ptext.find(case_marker)
if case_pos < 0:
    raise SystemExit('v4 detailed mapping: PLAYER_SCAN_READ_FAILED case missing')
switch_pos = ptext.rfind('\tswitch ', 0, case_pos)
if switch_pos < 0:
    raise SystemExit('v4 detailed mapping: owning switch missing')
switch_end = ptext.find('\n', switch_pos)
if switch_end < 0:
    raise SystemExit('v4 detailed mapping: malformed switch line')
switch_line = ptext[switch_pos:switch_end]
stripped = switch_line.strip()
if not stripped.startswith('switch ') or not stripped.endswith(' {'):
    raise SystemExit(f'v4 detailed mapping: unexpected switch line: {stripped!r}')
expr = stripped[len('switch '):-len(' {')].strip()
if not expr:
    raise SystemExit('v4 detailed mapping: empty switch expression')

guards = ''
for prefix in (
    'PLAYER_SCAN_SYNTHETIC_WRITE_TIMEOUT:',
    'PLAYER_SCAN_SYNTHETIC_WRITE_FAILED:',
    'PLAYER_SCAN_SYNTHETIC_READ_FAILED:',
):
    guards += (
        f'\tif len({expr}) >= len("{prefix}") && '
        f'{expr}[:len("{prefix}")] == "{prefix}" {{\n'
        f'\t\treturn nil, errors.New("LASTWAR_" + {expr})\n'
        f'\t}}\n'
    )
ptext = ptext[:switch_pos] + guards + ptext[switch_pos:]

PROTO.write_text(ptext, encoding='utf-8')

if not V4_SRC.is_file():
    raise SystemExit(f'v4 helper missing: {V4_SRC}')
V4_DST.write_text(V4_SRC.read_text(encoding='utf-8'), encoding='utf-8')

print('PLAYER_SCAN_V4_PATCH=OK')
print('PLAYER_SCAN_V4_MODE=native-template-readonly-v4')
print('PLAYER_SCAN_V4_STRATEGY=synthetic-world.get.block+get.user.info.multi')
print('PLAYER_SCAN_V4_SWEEP=bounded-v4.1')
print('PLAYER_SCAN_V4_DIAGNOSTICS=PREFIX_PRESERVED')
