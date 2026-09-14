#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

s = MAIN.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_LOGIN_INIT_V3'
if marker not in s:
    anchor = 'func main() {\n'
    helper = '''// SERVER_EXPLORER_LOGIN_INIT_V3\nfunc sendServerExplorerLoginInit(conn net.Conn) error {\n\tparams := sfs.NewSFSObject()\n\tparams.PutInt("_id", 2)\n\tparams.PutUtfString("dataConfigMd5", "")\n\text := sfs.NewSFSObject()\n\text.PutUtfString("c", "login.init")\n\text.PutInt("r", -1)\n\text.PutSFSObject("p", params)\n\touter := sfs.NewSFSObject()\n\touter.PutByte("c", 1)\n\touter.PutShort("a", 13)\n\touter.PutSFSObject("p", ext)\n\tbody, err := sfs.EncodeObject(outer)\n\tif err != nil {\n\t\treturn err\n\t}\n\tframe, err := sfs.EncodePacket(body)\n\tif err != nil {\n\t\treturn err\n\t}\n\t_, err = conn.Write(frame)\n\treturn err\n}\n\n'''
    s = replace_once(s, anchor, helper + anchor, 'login.init helper')
    s = replace_once(s, '\tloginOK := false\n', '\tloginOK := false\n\tloginInitPullSent := false\n', 'login.init state')
    old = '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_OK")\n\t\t\tcontinue\n'''
    new = '''\t\t\tbase.LoginResponse = "OK"\n\t\t\tloginOK = true\n\t\t\tserverExplorerNativeSentinel("LOGIN_OK")\n\t\t\tif strings.TrimSpace(os.Getenv("WFGG_SERVER_PROBE")) == "1" && !loginInitPullSent {\n\t\t\t\tif err := sendServerExplorerLoginInit(conn); err != nil {\n\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_WRITE_FAILED")\n\t\t\t\t\tfailWith(base, "LOGIN_INIT_PULL_WRITE_FAILED", err)\n\t\t\t\t}\n\t\t\t\tloginInitPullSent = true\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_INIT_PULL_SENT")\n\t\t\t}\n\t\t\tcontinue\n'''
    s = replace_once(s, old, new, 'login.init send')
    MAIN.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_LOGIN_INIT_V3=PATCHED')
print('SERVER_EXPLORER_LOGIN_INIT_V3_MODE=READONLY_BOOTSTRAP')
