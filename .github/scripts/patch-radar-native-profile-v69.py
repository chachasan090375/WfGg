#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
MAIN = ROOT / 'connector-go/native-template/main.go'
REGION = ROOT / 'connector-go/internal/protocol/region_scan.go'
SRC = Path('.radar-release-src/v69-source/connector-go')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, got {count}')
    return text.replace(old, new, 1)


def install_sources() -> None:
    copies = (
        (SRC / 'native-template/profile_scan_v69.go', ROOT / 'connector-go/native-template/profile_scan_v69.go'),
        (SRC / 'native-template/profile_scan_v69_test.go', ROOT / 'connector-go/native-template/profile_scan_v69_test.go'),
        (SRC / 'internal/protocol/profile_scan_v69.go', ROOT / 'connector-go/internal/protocol/profile_scan_v69.go'),
    )
    for src, dst in copies:
        if not src.is_file():
            raise SystemExit(f'V69_SOURCE_MISSING={src}')
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)


def patch_main() -> None:
    text = MAIN.read_text(encoding='utf-8')
    if 'WFGG_RADAR_NATIVE_PROFILE_MAIN_V69' in text:
        print('RADAR_V69_MAIN=ALREADY_PRESENT')
        return

    text = replace_once(
        text,
        '\tPlayers           []playerReport `json:"players,omitempty"`\n\tErrorCode         any            `json:"errorCode,omitempty"`\n',
        '\tPlayers           []playerReport        `json:"players,omitempty"`\n\tProfileDiagnostics *profileDiagnosticsV69 `json:"profileDiagnostics,omitempty"`\n\tErrorCode         any                   `json:"errorCode,omitempty"`\n',
        'report diagnostics field',
    )

    text = replace_once(
        text,
        '''\tscanMode := len(os.Args) == 5 && os.Args[3] == "--scan-player"\n\tif (!scanMode && len(os.Args) != 3) || (scanMode && strings.TrimSpace(os.Args[4]) == "") {\n\t\temit(report{OK: false, Mode: "native-template-readonly-v4", LoginResponse: "INVALID_ARGS"})\n\t\tos.Exit(2)\n\t}\n\tcapturePath, sessionPath := os.Args[1], os.Args[2]\n\tquery := ""\n\tif scanMode {\n\t\tquery = strings.TrimSpace(os.Args[4])\n\t}\n''',
        '''\t// WFGG_RADAR_NATIVE_PROFILE_MAIN_V69\n\tscanMode := len(os.Args) == 5 && os.Args[3] == "--scan-player"\n\tprofileMode := len(os.Args) == 5 && os.Args[3] == "--scan-profiles"\n\tactiveReadMode := scanMode || profileMode\n\tif (!activeReadMode && len(os.Args) != 3) || (activeReadMode && strings.TrimSpace(os.Args[4]) == "") {\n\t\temit(report{OK: false, Mode: "native-template-readonly-v4", LoginResponse: "INVALID_ARGS"})\n\t\tos.Exit(2)\n\t}\n\tcapturePath, sessionPath := os.Args[1], os.Args[2]\n\tquery := ""\n\tprofileArg := ""\n\tif scanMode {\n\t\tquery = strings.TrimSpace(os.Args[4])\n\t} else if profileMode {\n\t\tprofileArg = strings.TrimSpace(os.Args[4])\n\t}\n''',
        'native profile cli mode',
    )

    text = replace_once(
        text,
        '''\tvar mapTemplates []*sfs.SFSObject\n\tvar profileTemplate *sfs.SFSObject\n\tscanCommand := ""\n\tif scanMode {\n\t\tmapTemplates, profileTemplate = findPlayerScanV3Templates(convs, server)\n\t\tscanCommand = v3MapCommand + "(synthetic-v4.1)"\n\t\tif len(mapTemplates) > 0 {\n\t\t\tscanCommand = v3MapCommand + "(captured-v3)"\n\t\t}\n\t\tif profileTemplate != nil {\n\t\t\tscanCommand += "+" + v3ProfileCommand\n\t\t}\n\t}\n''',
        '''\tvar mapTemplates []*sfs.SFSObject\n\tvar profileTemplate *sfs.SFSObject\n\tscanCommand := ""\n\tif activeReadMode {\n\t\tmapTemplates, profileTemplate = findPlayerScanV3Templates(convs, server)\n\t\tif scanMode {\n\t\t\tscanCommand = v3MapCommand + "(synthetic-v4.1)"\n\t\t\tif len(mapTemplates) > 0 {\n\t\t\t\tscanCommand = v3MapCommand + "(captured-v3)"\n\t\t\t}\n\t\t\tif profileTemplate != nil {\n\t\t\t\tscanCommand += "+" + v3ProfileCommand\n\t\t\t}\n\t\t} else {\n\t\t\tscanCommand = v3ProfileCommand + "(native-v6.9)"\n\t\t}\n\t}\n''',
        'profile template discovery',
    )

    text = replace_once(
        text,
        '''\tif scanMode {\n\t\t// V4 can synthesize world.get.block from the documented wire format, so\n\t\t// absence of a captured map request is no longer a deployment gate.\n\t\tbase.ScanTemplateFound = true\n\t}\n''',
        '''\tif scanMode {\n\t\t// V4 can synthesize world.get.block from the documented wire format, so\n\t\t// absence of a captured map request is no longer a deployment gate.\n\t\tbase.ScanTemplateFound = true\n\t}\n\tif profileMode {\n\t\tbase.ScanTemplateFound = profileTemplate != nil\n\t\tif profileTemplate == nil {\n\t\t\tbase.LoginResponse = "PLAYER_PROFILE_TEMPLATE_NOT_FOUND"\n\t\t\temit(base)\n\t\t\tos.Exit(5)\n\t\t}\n\t}\n''',
        'profile template gate',
    )

    text = replace_once(
        text,
        '\t\t\tif !scanMode {\n',
        '\t\t\tif !scanMode && !profileMode {\n',
        'init snapshot return',
    )
    text = replace_once(
        text,
        '\tif !scanMode {\n',
        '\tif !scanMode && !profileMode {\n',
        'post-login snapshot return',
    )

    text = replace_once(
        text,
        '\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n',
        '''\tif profileMode {\n\t\tplayers, diag, err := runProfileScanV69(conn, profileTemplate, profileArg)\n\t\tbase.ProfileDiagnostics = &diag\n\t\tif err != nil {\n\t\t\tbase.OK = false\n\t\t\tbase.LoginResponse = err.Error()\n\t\t\temit(base)\n\t\t\tos.Exit(7)\n\t\t}\n\t\tbase.OK = true\n\t\tbase.LoginResponse = "OK"\n\t\tbase.ScanPerformed = true\n\t\tbase.Players = players\n\t\temit(base)\n\t\treturn\n\t}\n\n\tplayers, err := runPlayerScanV4(conn, convs, server, mapTemplates, profileTemplate, query, serverID)\n''',
        'native profile execution',
    )

    MAIN.write_text(text, encoding='utf-8')
    print('RADAR_V69_MAIN=PATCHED')


def patch_bridge() -> None:
    text = REGION.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_NATIVE_PROFILE_BRIDGE_V69'
    if marker in text:
        print('RADAR_V69_BRIDGE=ALREADY_PRESENT')
        return
    old = '\treturn c.scanNativeV4(parent, token, "@profile:"+strings.Join(clean, ","), nil)\n'
    new = '\t// WFGG_RADAR_NATIVE_PROFILE_BRIDGE_V69\n\treturn c.scanNativeProfilesV69(parent, token, clean)\n'
    text = replace_once(text, old, new, 'profile bridge call')
    REGION.write_text(text, encoding='utf-8')
    print('RADAR_V69_BRIDGE=PATCHED')


install_sources()
patch_main()
patch_bridge()
print('RADAR_NATIVE_PROFILE_V69=READY')
