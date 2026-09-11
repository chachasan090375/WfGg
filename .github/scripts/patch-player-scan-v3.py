#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/native-template/main.go'
PROTO = ROOT / 'connector-go/internal/protocol/native_template.go'
HELPER = Path('.radar-release-src/v3-source/connector-go/native-template/player_scan_v3.go')
DEST_HELPER = ROOT / 'connector-go/native-template/player_scan_v3.go'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text(encoding='utf-8')
    text = replace_once(text, '''\tquery := ""\n\tseed := ""\n\tif scanMode {\n\t\tquery = strings.TrimSpace(os.Args[4])\n\t\tseed = strings.TrimSpace(os.Getenv("LASTWAR_NATIVE_SCAN_SEED"))\n\t\tif seed == "" {\n\t\t\tseed = query\n\t\t}\n\t}\n''', '''\tquery := ""\n\tif scanMode {\n\t\tquery = strings.TrimSpace(os.Args[4])\n\t}\n''', 'scan args')

    text = replace_once(text, '''\tvar scanRoot *sfs.SFSObject\n\tscanCommand := ""\n\tunsafeCommand := ""\n\tif scanMode {\n\t\tscanRoot, scanCommand, unsafeCommand = findScanTemplate(convs, server, seed)\n\t}\n''', '''\tvar mapTemplates []*sfs.SFSObject\n\tvar profileTemplate *sfs.SFSObject\n\tscanCommand := ""\n\tif scanMode {\n\t\tmapTemplates, profileTemplate = findPlayerScanV3Templates(convs, server)\n\t\tif len(mapTemplates) > 0 {\n\t\t\tscanCommand = v3MapCommand\n\t\t\tif profileTemplate != nil {\n\t\t\t\tscanCommand += "+" + v3ProfileCommand\n\t\t\t}\n\t\t}\n\t}\n''', 'template discovery')

    text = replace_once(text, '''\tif scanMode && scanRoot != nil {\n\t\tbase.ScanTemplateFound = true\n\t}\n\tif scanMode && scanRoot == nil && unsafeCommand != "" {\n\t\tbase.ScanCommand = unsafeCommand\n\t\tbase.LoginResponse = "PLAYER_SCAN_TEMPLATE_UNSAFE"\n\t\temit(base)\n\t\tos.Exit(5)\n\t}\n\tif scanMode && scanRoot == nil {\n\t\tbase.LoginResponse = "PLAYER_SCAN_TEMPLATE_NOT_FOUND"\n\t\temit(base)\n\t\tos.Exit(5)\n\t}\n''', '''\tif scanMode && len(mapTemplates) > 0 {\n\t\tbase.ScanTemplateFound = true\n\t}\n\tif scanMode && !base.ScanTemplateFound {\n\t\tbase.LoginResponse = "PLAYER_SCAN_TEMPLATE_NOT_FOUND"\n\t\temit(base)\n\t\tos.Exit(5)\n\t}\n''', 'template gate')

    text = replace_once(text,
        '\tplayers, err := runPlayerScan(conn, scanRoot, seed, query, serverID)\n',
        '\tplayers, err := runPlayerScanV3(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n',
        'scan call')

    text = text.replace('native-template-readonly-v2', 'native-template-readonly-v3')
    MAIN.write_text(text, encoding='utf-8')


def patch_protocol() -> None:
    text = PROTO.read_text(encoding='utf-8')
    text = text.replace('native-template-readonly-v2', 'native-template-readonly-v3')
    # Keep the existing snapshot provenance string: regression tests and stored
    # observations rely on it. V3 changes player scanning, not snapshot provenance.
    text = replace_once(text,
        '\tcmd.Env = append(childEnv(dir), "LASTWAR_NATIVE_SCAN_SEED="+c.ScanSeed)\n',
        '\tcmd.Env = childEnv(dir)\n',
        'connector scan seed env')
    PROTO.write_text(text, encoding='utf-8')


def copy_helper() -> None:
    if not HELPER.is_file():
        raise SystemExit(f'helper missing: {HELPER}')
    text = HELPER.read_text(encoding='utf-8')
    # Repair the source snapshot's missing brace around the []byte map-tile case.
    text = replace_once(text,
        '''\t\t\tif !seen[key] {\n\t\t\t\tseen[key] = true\n\t\t\t\t*out = append(*out, p)\n\t\t\t}\n\t}\n}\n\nfunc playerFromMapBlobV3''',
        '''\t\t\tif !seen[key] {\n\t\t\t\tseen[key] = true\n\t\t\t\t*out = append(*out, p)\n\t\t\t}\n\t\t}\n\t}\n}\n\nfunc playerFromMapBlobV3''',
        'map collector brace')
    DEST_HELPER.write_text(text, encoding='utf-8')


patch_main()
patch_protocol()
copy_helper()
print('PLAYER_SCAN_V3_PATCH=OK')
print('PLAYER_SCAN_V3_MODE=native-template-readonly-v3')
print('PLAYER_SCAN_V3_STRATEGY=world.get.block+get.user.info.multi')
