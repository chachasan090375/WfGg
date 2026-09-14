#!/usr/bin/env python3
from pathlib import Path

MAIN = Path('/tmp/wfgg-radar/connector-go/native-template/main.go')


def once(s, old, new, label):
    n = s.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, got {n}')
    return s.replace(old, new, 1)

s = MAIN.read_text(encoding='utf-8')
marker = 'SERVER_EXPLORER_REDIRECT_V5'
if marker not in s:
    if '"lastwar-client/internal/gsl"' not in s:
        s = once(s,
            '\t"lastwar-client/internal/auth"\n',
            '\t"lastwar-client/internal/auth"\n\t"lastwar-client/internal/gsl"\n',
            'gsl import')

    helper_anchor = 'var dynamicKeys = map[string]bool{\n'
    helper = r'''// SERVER_EXPLORER_REDIRECT_V5
func serverExplorerRedirectInfo(loginResp *sfs.SFSObject) (string, int, string, bool) {
	if loginResp == nil {
		return "", 0, "", false
	}
	var content *sfs.SFSObject
	if v, ok := loginResp.Get("p"); ok {
		content, _ = v.Val.(*sfs.SFSObject)
	}
	var si *sfs.SFSObject
	if content != nil {
		if v, ok := content.Get("serverInfo"); ok {
			si, _ = v.Val.(*sfs.SFSObject)
		}
	}
	if si == nil {
		if v, ok := loginResp.Get("serverInfo"); ok {
			si, _ = v.Val.(*sfs.SFSObject)
		}
	}
	if si == nil {
		return "", 0, "", false
	}
	host := strings.TrimSpace(gsl.FirstHost(strings.TrimSpace(si.GetString("ip"))))
	port := int(si.GetInt("port"))
	if port <= 0 {
		if n, err := strconv.Atoi(strings.TrimSpace(si.GetString("port"))); err == nil {
			port = n
		}
	}
	zone := strings.TrimSpace(si.GetString("zone"))
	return host, port, zone, host != "" && port > 0
}

'''
    s = once(s, helper_anchor, helper + helper_anchor, 'redirect helper')

    s = once(s,
        '\tpostLoginOtherExtMarked := false\n',
        '\tpostLoginOtherExtMarked := false\n\tredirectHops := 0\n',
        'redirect state')

    login_anchor = '''\t\t\tif ec, ok := p.Get("ec"); ok {\n\t\t\t\tbase.LoginResponse = "REJECTED"\n\t\t\t\tbase.ErrorCode = scalarNumber(ec.Val)\n\t\t\t\temit(base)\n\t\t\t\tos.Exit(2)\n\t\t\t}\n\t\t\tbase.LoginResponse = "OK"\n'''
    redirect_block = '''\t\t\tif ec, ok := p.Get("ec"); ok {\n\t\t\t\tbase.LoginResponse = "REJECTED"\n\t\t\t\tbase.ErrorCode = scalarNumber(ec.Val)\n\t\t\t\temit(base)\n\t\t\t\tos.Exit(2)\n\t\t\t}\n\t\t\tif host, port, zone, hasRedirect := serverExplorerRedirectInfo(p); hasRedirect {\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_PRESENT")\n\t\t\t\tif redirectHops >= 3 {\n\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_LIMIT")\n\t\t\t\t\tfailWith(base, "LOGIN_SERVERINFO_REDIRECT_LIMIT", nil)\n\t\t\t\t}\n\t\t\t\taddr := net.JoinHostPort(host, strconv.Itoa(port))\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_DIAL")\n\t\t\t\t_ = conn.Close()\n\t\t\t\tnewConn, err := net.DialTimeout("tcp", addr, 10*time.Second)\n\t\t\t\tif err != nil {\n\t\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_DIAL_FAILED")\n\t\t\t\t\tfailWith(base, "LOGIN_SERVERINFO_REDIRECT_DIAL_FAILED", err)\n\t\t\t\t}\n\t\t\t\tconn = newConn\n\t\t\t\tdefer conn.Close()\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_DIAL_OK")\n\t\t\t\tif zone == "" {\n\t\t\t\t\tzone = base.Zone\n\t\t\t\t}\n\t\t\t\tnewServerID := strings.TrimPrefix(zone, "APS")\n\t\t\t\tredirectGenerated := auth.BuildLoginParams(auth.LoginParamsInput{\n\t\t\t\t\tFutureID: 1, DeviceID: cfg.DeviceID, AirKey: "lwDid_" + base64Std(cfg.DeviceID),\n\t\t\t\t\tGameUid: cfg.GameUID, AccessTok: cfg.AccessToken, ServerID: newServerID,\n\t\t\t\t\tShumeiBoxId: cfg.ShumeiBoxID, IOSMode: cfg.IOSMode,\n\t\t\t\t})\n\t\t\t\tfor _, key := range nativeParams.Keys() {\n\t\t\t\t\tif dynamicKeys[key] || key == "serverId" {\n\t\t\t\t\t\tif gv, ok := redirectGenerated.Get(key); ok {\n\t\t\t\t\t\t\tfinalParams.PutValue(key, gv)\n\t\t\t\t\t\t}\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t\tfinalLogin.PutUtfString("zn", zone)\n\t\t\t\tbody2, err := sfs.EncodeObject(finalRoot)\n\t\t\t\tif err != nil { failWith(base, "LOGIN_REDIRECT_ENCODE_FAILED", err) }\n\t\t\t\tframe2, err := sfs.EncodePacket(body2)\n\t\t\t\tif err != nil { failWith(base, "LOGIN_REDIRECT_FRAME_FAILED", err) }\n\t\t\t\t_ = conn.SetDeadline(time.Now().Add(25 * time.Second))\n\t\t\t\tif _, err := conn.Write(frame2); err != nil { failWith(base, "LOGIN_REDIRECT_WRITE_FAILED", err) }\n\t\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_LOGIN_SENT")\n\t\t\t\tredirectHops++\n\t\t\t\tbase.Zone = zone\n\t\t\t\tbase.ServerID = newServerID\n\t\t\t\tbase.ResolvedAddress = addr\n\t\t\t\tloginOK = false\n\t\t\t\tloginInitPullSent = false\n\t\t\t\tloginInitPullAt = time.Time{}\n\t\t\t\tloginInitDeadline = time.Time{}\n\t\t\t\tpostLoginReadMarked = false\n\t\t\t\tpostLoginPacketMarked = false\n\t\t\t\tpostLoginDecodeMarked = false\n\t\t\t\tpostLoginDecodeFailMarked = false\n\t\t\t\tpostLoginOtherExtMarked = false\n\t\t\t\tcontinue\n\t\t\t}\n\t\t\tserverExplorerNativeSentinel("LOGIN_SERVERINFO_REDIRECT_ABSENT")\n\t\t\tbase.LoginResponse = "OK"\n'''
    s = once(s, login_anchor, redirect_block, 'redirect login block')

    MAIN.write_text(s, encoding='utf-8')

print('SERVER_EXPLORER_REDIRECT_V5=PATCHED')
print('SERVER_EXPLORER_REDIRECT_MAX_HOPS=3')
print('SERVER_EXPLORER_REDIRECT_SENTINEL=READY')
