#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = MAIN.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_INIT_WINDOW_V4'
if marker not in s:
    if '"errors"' not in s:
        s = replace_once(s, 'import (\n', 'import (\n\t"errors"\n', 'errors import')

    s = replace_once(
        s,
        '\tloginOK := false\n\tloginInitPullSent := false\n',
        '\tloginOK := false\n\tloginInitPullSent := false\n'
        '\t// SERVER_EXPLORER_INIT_WINDOW_V4\n'
        '\tvar loginInitPullAt time.Time\n'
        '\tvar loginInitDeadline time.Time\n'
        '\tpostLoginReadMarked := false\n'
        '\tpostLoginPacketMarked := false\n'
        '\tpostLoginDecodeMarked := false\n'
        '\tpostLoginDecodeFailMarked := false\n'
        '\tpostLoginOtherExtMarked := false\n',
        'v4 state')

    old_loop = '''readLoginLoop:\n\tfor i := 0; i < 240; i++ {\n\t\trb, err := sfs.ReadPacket(conn)\n\t\tif err != nil {\n\t\t\tif ne, ok := err.(net.Error); ok && ne.Timeout() {\n\t\t\t\tbreak\n\t\t\t}\n\t\t\tfailWith(base, "READ_FAILED", err)\n\t\t}\n\t\tobj, err := sfs.DecodeObject(rb)\n\t\tif err != nil {\n\t\t\tcontinue\n\t\t}\n'''
    new_loop = '''readLoginLoop:\n\tfor i := 0; i < 240; i++ {\n\t\tif loginOK && !postLoginReadMarked {\n\t\t\tserverExplorerNativeSentinel("POST_LOGIN_READ_WAIT")\n\t\t\tpostLoginReadMarked = true\n\t\t}\n\t\tif loginOK && !loginInitPullSent && !loginInitPullAt.IsZero() && !time.Now().Before(loginInitPullAt) {\n\t\t\tif err := sendServerExplorerLoginInit(conn); err != nil {\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_WRITE_FAILED")\n\t\t\t\tfailWith(base, "LOGIN_INIT_PULL_WRITE_FAILED", err)\n\t\t\t}\n\t\t\tloginInitPullSent = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_SENT")\n\t\t\t_ = conn.SetReadDeadline(loginInitDeadline)\n\t\t}\n\t\trb, err := sfs.ReadPacket(conn)\n\t\tif err != nil {\n\t\t\tvar ne net.Error\n\t\t\tif errors.As(err, &ne) && ne.Timeout() {\n\t\t\t\tif loginOK && !loginInitPullSent && !loginInitDeadline.IsZero() && time.Now().Before(loginInitDeadline) {\n\t\t\t\t\tif err := sendServerExplorerLoginInit(conn); err != nil {\n\t\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_WRITE_FAILED")\n\t\t\t\t\t\tfailWith(base, "LOGIN_INIT_PULL_WRITE_FAILED", err)\n\t\t\t\t\t}\n\t\t\t\t\tloginInitPullSent = true\n\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_SENT")\n\t\t\t\t\t_ = conn.SetReadDeadline(loginInitDeadline)\n\t\t\t\t\tcontinue\n\t\t\t\t}\n\t\t\t\tif loginOK {\n\t\t\t\t\tserverExplorerNativeSentinel("POST_LOGIN_READ_TIMEOUT")\n\t\t\t\t}\n\t\t\t\tbreak\n\t\t\t}\n\t\t\tif loginOK {\n\t\t\t\tserverExplorerNativeSentinel("POST_LOGIN_READ_ERROR")\n\t\t\t}\n\t\t\tfailWith(base, "READ_FAILED", err)\n\t\t}\n\t\tif loginOK && !postLoginPacketMarked {\n\t\t\tserverExplorerNativeSentinel("POST_LOGIN_PACKET_RX")\n\t\t\tpostLoginPacketMarked = true\n\t\t}\n\t\tobj, err := sfs.DecodeObject(rb)\n\t\tif err != nil {\n\t\t\tif loginOK && !postLoginDecodeFailMarked {\n\t\t\t\tserverExplorerNativeSentinel("POST_LOGIN_DECODE_FAIL")\n\t\t\t\tpostLoginDecodeFailMarked = true\n\t\t\t}\n\t\t\tcontinue\n\t\t}\n\t\tif loginOK && !postLoginDecodeMarked {\n\t\t\tserverExplorerNativeSentinel("POST_LOGIN_DECODE_OK")\n\t\t\tpostLoginDecodeMarked = true\n\t\t}\n'''
    s = replace_once(s, old_loop, new_loop, 'read loop')

    old_login = '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_OK")\n\t\t\tif strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1" && !loginInitPullSent {\n\t\t\t\tif err := sendServerExplorerLoginInit(conn); err != nil {\n\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_WRITE_FAILED")\n\t\t\t\t\tfailWith(base, "LOGIN_INIT_PULL_WRITE_FAILED", err)\n\t\t\t\t}\n\t\t\t\tloginInitPullSent = true\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_SENT")\n\t\t\t}\n\t\t\tcontinue\n'''
    new_login = '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_OK")\n\t\t\tif strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1" {\n\t\t\t\t// Match the reference client: a fresh 45s init window, with login.init\n\t\t\t\t// sent halfway through only if the bare init push has not arrived.\n\t\t\t\tnow := time.Now()\n\t\t\t\tloginInitDeadline = now.Add(45 * time.Second)\n\t\t\t\tloginInitPullAt = now.Add(22500 * time.Millisecond)\n\t\t\t\t_ = conn.SetReadDeadline(loginInitPullAt)\n\t\t\t\t_ = conn.SetWriteDeadline(loginInitDeadline)\n\t\t\t\tserverExplorerNativeSentinel("INIT_WAIT_PHASE1")\n\t\t\t}\n\t\t\tcontinue\n'''
    s = replace_once(s, old_login, new_login, 'reference init window')

    old_ext = '''\t\t\text, ok := pv.Val.(*sfs.SFSObject)\n\t\t\tif !ok || ext == nil || ext.GetString("c") != "init" {\n\t\t\t\tcontinue\n\t\t\t}\n'''
    new_ext = '''\t\t\text, ok := pv.Val.(*sfs.SFSObject)\n\t\t\tif !ok || ext == nil {\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tpostCmd := strings.TrimSpace(ext.GetString("c"))\n\t\t\tif postCmd == "login.init" {\n\t\t\t\tserverExplorerNativeSentinel("POST_LOGIN_CMD_LOGIN_INIT")\n\t\t\t}\n\t\t\tif postCmd != "init" {\n\t\t\t\tif !postLoginOtherExtMarked {\n\t\t\t\t\tserverExplorerNativeSentinel("POST_LOGIN_EXTENSION_OTHER")\n\t\t\t\t\tpostLoginOtherExtMarked = true\n\t\t\t\t}\n\t\t\t\tcontinue\n\t\t\t}\n'''
    s = replace_once(s, old_ext, new_ext, 'post-login extension classification')

    MAIN.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_INIT_WINDOW_V4=PATCHED')
print('SERVER_EXPLORER_INIT_WINDOW_SECONDS=45')
print('SERVER_EXPLORER_LOGIN_INIT_HALF_SECONDS=22.5')
print('SERVER_EXPLORER_POST_LOGIN_SENTINEL=READY')
