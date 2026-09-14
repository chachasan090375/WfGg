#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')
s = MAIN.read_text(encoding='utf-8')
marker = 'FEDERATED_COLLECTOR_V632_LOGIN_TARGET'
if marker in s:
    print('FEDERATED_COLLECTOR_V632_LOGIN_TARGET=ALREADY_PRESENT')
    raise SystemExit(0)


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old, new, 1)

old = '''\tserverID := strings.TrimPrefix(cfg.Zone, "APS")\n\tgenerated := auth.BuildLoginParams(auth.LoginParamsInput{\n'''
new = '''\tserverID := strings.TrimPrefix(cfg.Zone, "APS")\n\t// FEDERATED_COLLECTOR_V632_LOGIN_TARGET\n\t// Server Explorer V1 only overrides world.get.block. Federated V6.3.2 can\n\t// instead ask the login layer for a real target zone, allowing the existing\n\t// serverInfo redirect machinery to move the TCP session to the target shard.\n\tloginTarget := strings.TrimSpace(os.Getenv("WFGG_LOGIN_SERVER_ID_OVERRIDE"))\n\tif loginTarget != "" {\n\t\tloginTarget = strings.TrimPrefix(loginTarget, "APS")\n\t\tn, err := strconv.Atoi(loginTarget)\n\t\tif err != nil || n <= 0 || n > 999999 {\n\t\t\tfail("FEDERATED_LOGIN_SERVER_ID_INVALID", err)\n\t\t}\n\t\tserverID = strconv.Itoa(n)\n\t\tserverExplorerNativeSentinel("FEDERATED_LOGIN_TARGET_OVERRIDE")\n\t}\n\ttargetZone := cfg.Zone\n\tif loginTarget != "" {\n\t\ttargetZone = "APS" + serverID\n\t}\n\tgenerated := auth.BuildLoginParams(auth.LoginParamsInput{\n'''
s = once(s, old, new, 'login target selection')

old = '''\tfor _, key := range nativeParams.Keys() {\n\t\tnv, _ := nativeParams.Get(key)\n\t\tif dynamicKeys[key] {\n\t\t\tif gv, ok := generated.Get(key); ok {\n\t\t\t\tfinalParams.PutValue(key, gv)\n\t\t\t\tfreshDynamic++\n\t\t\t\tcontinue\n\t\t\t}\n\t\t}\n\t\tfinalParams.PutValue(key, nv)\n\t\tcopiedNative++\n\t}\n\n\tfinalLogin := sfs.NewSFSObject()\n'''
new = '''\tfor _, key := range nativeParams.Keys() {\n\t\tnv, _ := nativeParams.Get(key)\n\t\tif dynamicKeys[key] {\n\t\t\tif gv, ok := generated.Get(key); ok {\n\t\t\t\tfinalParams.PutValue(key, gv)\n\t\t\t\tfreshDynamic++\n\t\t\t\tcontinue\n\t\t\t}\n\t\t}\n\t\tfinalParams.PutValue(key, nv)\n\t\tcopiedNative++\n\t}\n\tif loginTarget != "" {\n\t\tif gv, ok := generated.Get("serverId"); ok {\n\t\t\tfinalParams.PutValue("serverId", gv)\n\t\t}\n\t}\n\n\tfinalLogin := sfs.NewSFSObject()\n'''
s = once(s, old, new, 'login target serverId param')

old = '''\tfor _, key := range nativeLogin.Keys() {\n\t\tif key == "p" {\n\t\t\tfinalLogin.PutSFSObject("p", finalParams)\n\t\t\tcontinue\n\t\t}\n\t\tv, _ := nativeLogin.Get(key)\n\t\tfinalLogin.PutValue(key, v)\n\t}\n\n\tfinalRoot := sfs.NewSFSObject()\n'''
new = '''\tfor _, key := range nativeLogin.Keys() {\n\t\tif key == "p" {\n\t\t\tfinalLogin.PutSFSObject("p", finalParams)\n\t\t\tcontinue\n\t\t}\n\t\tv, _ := nativeLogin.Get(key)\n\t\tfinalLogin.PutValue(key, v)\n\t}\n\tif loginTarget != "" {\n\t\tfinalLogin.PutUtfString("zn", targetZone)\n\t}\n\n\tfinalRoot := sfs.NewSFSObject()\n'''
s = once(s, old, new, 'login target zone')

old = '''\t\tZone:            cfg.Zone,\n\t\tServerID:        serverID,\n'''
new = '''\t\tZone:            targetZone,\n\t\tServerID:        serverID,\n'''
s = once(s, old, new, 'login target report')

MAIN.write_text(s, encoding='utf-8')
print('FEDERATED_COLLECTOR_V632_LOGIN_TARGET=PATCHED')
print('FEDERATED_COLLECTOR_V632_LOGIN_ENV=WFGG_LOGIN_SERVER_ID_OVERRIDE')
print('FEDERATED_COLLECTOR_V632_REDIRECT_PATH=ENABLED')
