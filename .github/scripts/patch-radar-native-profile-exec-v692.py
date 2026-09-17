#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT = Path('/tmp/wfgg-radar')
BRIDGE = ROOT / 'connector-go/internal/protocol/profile_scan_v69.go'
PROFILE = ROOT / 'connector-go/native-template/profile_scan_v69.go'
PROFILE_TEST = ROOT / 'connector-go/native-template/profile_scan_v69_test.go'
EXEC = ROOT / 'connector-go/internal/protocol/profile_exec_v692.go'
EXEC_TEST = ROOT / 'connector-go/internal/protocol/profile_exec_v692_test.go'
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


def patch_profile_encode_v696() -> None:
    text = PROFILE.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_PROFILE_ENCODE_TYPE_PRESERVE_V696'
    if marker not in text:
        old = '''\tif lk == "allservers" {\n\t\treturn sfs.SFSValue{Type: v.Type, Val: true}, 0\n\t}\n'''
        new = '''\tif lk == "allservers" {\n\t\t// WFGG_RADAR_PROFILE_ENCODE_TYPE_PRESERVE_V696\n\t\t// Preserve the concrete value shape implied by the captured SFS tag.\n\t\t// Forcing bool while retaining an integer tag makes EncodeObject panic.\n\t\tswitch v.Val.(type) {\n\t\tcase bool:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: true}, 0\n\t\tcase byte:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: byte(1)}, 0\n\t\tcase int16:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: int16(1)}, 0\n\t\tcase int32:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: int32(1)}, 0\n\t\tcase int64:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: int64(1)}, 0\n\t\tcase float32:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: float32(1)}, 0\n\t\tcase float64:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: float64(1)}, 0\n\t\tcase string:\n\t\t\treturn sfs.SFSValue{Type: v.Type, Val: "true"}, 0\n\t\tdefault:\n\t\t\treturn v, 0\n\t\t}\n\t}\n'''
        count = text.count(old)
        if count != 1:
            raise SystemExit(f'V696_ALLSERVERS_ANCHOR_COUNT={count}')
        PROFILE.write_text(text.replace(old, new, 1), encoding='utf-8')
        print('RADAR_V696_ALLSERVERS_TYPE=PATCHED')
    else:
        print('RADAR_V696_ALLSERVERS_TYPE=ALREADY_PRESENT')

    test_text = PROFILE_TEST.read_text(encoding='utf-8')
    test_marker = 'TestProfileCloneAllServersNumericEncodesV696'
    if test_marker not in test_text:
        test_text += '''\nfunc TestProfileCloneAllServersNumericEncodesV696(t *testing.T) {\n\ttemplate := sfs.NewSFSObject()\n\ttemplate.PutInt("allServers", 0)\n\ttemplate.PutUtfString("uids", "old")\n\ttemplate.PutInt("_id", 7)\n\n\tcloned, replaced := cloneProfileBatchObjectV69(template, []string{"101", "202"}, 42)\n\tif cloned == nil || replaced != 1 {\n\t\tt.Fatalf("unexpected clone result: cloned=%v replaced=%d", cloned != nil, replaced)\n\t}\n\tv, ok := cloned.Get("allServers")\n\tif !ok {\n\t\tt.Fatal("allServers missing after clone")\n\t}\n\tn, ok := v.Val.(int32)\n\tif !ok || n != 1 {\n\t\tt.Fatalf("allServers type/value changed incorrectly: %#v", v.Val)\n\t}\n\tif _, err := sfs.EncodeObject(cloned); err != nil {\n\t\tt.Fatalf("profile clone must encode: %v", err)\n\t}\n}\n'''
        PROFILE_TEST.write_text(test_text, encoding='utf-8')
        print('RADAR_V696_PROFILE_ENCODE_TEST=ADDED')
    else:
        print('RADAR_V696_PROFILE_ENCODE_TEST=ALREADY_PRESENT')


def patch_panic_precedence_v696() -> None:
    text = EXEC.read_text(encoding='utf-8')
    marker = 'WFGG_RADAR_PROFILE_PANIC_PRECEDENCE_V696'
    if marker not in text:
        anchor = 'func profilePanicCodeV695(stderrText string) string {\n'
        precise = '''func profilePanicCodeV695(stderrText string) string {\n\t// WFGG_RADAR_PROFILE_PANIC_PRECEDENCE_V696\n\t// Specific safe evidence must win over broad stack-family matches.\n\tif strings.Contains(stderrText, "unsupported encode type") {\n\t\treturn "LASTWAR_PLAYER_PROFILE_PANIC_SFS_UNSUPPORTED_ENCODE_TYPE"\n\t}\n\tif code := profilePanicSourceLineV695(stderrText); code != "" {\n\t\treturn code\n\t}\n'''
        count = text.count(anchor)
        if count != 1:
            raise SystemExit(f'V696_PANIC_PRECEDENCE_ANCHOR_COUNT={count}')
        EXEC.write_text(text.replace(anchor, precise, 1), encoding='utf-8')
        print('RADAR_V696_PANIC_PRECEDENCE=PATCHED')
    else:
        print('RADAR_V696_PANIC_PRECEDENCE=ALREADY_PRESENT')

    test_text = EXEC_TEST.read_text(encoding='utf-8')
    test_marker = 'TestProfilePanicSpecificPrecedenceV696'
    if test_marker not in test_text:
        test_text += '''\nfunc TestProfilePanicSpecificPrecedenceV696(t *testing.T) {\n\tcases := []struct {\n\t\tname   string\n\t\tstderr string\n\t\twant   string\n\t}{\n\t\t{\n\t\t\tname: "unsupported encode beats generic encode",\n\t\t\tstderr: "panic: sfsobject: unsupported encode type 21\\n" +\n\t\t\t\t"lastwar-client/internal/sfs.writeValuePayload(...)\\n" +\n\t\t\t\t"\\tlastwar-client/internal/sfs/sfsobject.go:823 +0x2\\n",\n\t\t\twant: "LASTWAR_PLAYER_PROFILE_PANIC_SFS_UNSUPPORTED_ENCODE_TYPE",\n\t\t},\n\t\t{\n\t\t\tname: "source line beats generic encode",\n\t\t\tstderr: "panic: interface conversion\\n" +\n\t\t\t\t"lastwar-client/internal/sfs.writeValuePayload(...)\\n" +\n\t\t\t\t"\\tlastwar-client/internal/sfs/sfsobject.go:812 +0x2\\n",\n\t\t\twant: "LASTWAR_PLAYER_PROFILE_PANIC_SFS_SFSOBJECT_L812",\n\t\t},\n\t}\n\tfor _, tc := range cases {\n\t\tt.Run(tc.name, func(t *testing.T) {\n\t\t\tgot := profileExecutionFailureV692(errors.New("exit status 2"), nil, []byte(tc.stderr)).Error()\n\t\t\tif got != tc.want {\n\t\t\t\tt.Fatalf("got %q, want %q", got, tc.want)\n\t\t\t}\n\t\t})\n\t}\n}\n'''
        EXEC_TEST.write_text(test_text, encoding='utf-8')
        print('RADAR_V696_PANIC_PRECEDENCE_TEST=ADDED')
    else:
        print('RADAR_V696_PANIC_PRECEDENCE_TEST=ALREADY_PRESENT')


install_sources()
patch_bridge()
patch_profile_encode_v696()
patch_panic_precedence_v696()
print('RADAR_NATIVE_PROFILE_EXEC_V692=READY')
print('RADAR_PROFILE_ENCODE_V696=READY')
