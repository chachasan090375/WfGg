#!/usr/bin/env python3
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

# The email-code flow proves account ownership and returns accountArr, but the real
# client then reconnects to the selected role. Persist enough role routing material
# to reproduce that reconnect instead of treating a later sync as another base login.
text = text.replace(
    '\t"lastwar-client/internal/auth"\n',
    '\t"lastwar-client/internal/auth"\n\tlwcrypto "lastwar-client/internal/crypto"\n\t"lastwar-client/internal/gsl"\n',
    1,
)
text = text.replace(
    '\t"log"\n\t"net/http"\n',
    '\t"log"\n\t"net"\n\t"net/http"\n\t"strconv"\n',
    1,
)

role_struct = '''type roleInfo struct {
\tPlayerName string `json:"player_name,omitempty"`
\tServerID   string `json:"server_id,omitempty"`
\tIP         string
\tPort       int
\tZone       string
\tGameUID    string
\tLoginKey   string
}'''
text, n = re.subn(r'type roleInfo struct \{.*?\n\}', role_struct, text, count=1, flags=re.S)
if n != 1:
    raise SystemExit('roleInfo struct marker not found')

sealed_struct = '''type sealedState struct {
\tVersion    int       `json:"version"`
\tLinkedUID  string    `json:"linked_uid"`
\tPlayerName string    `json:"player_name,omitempty"`
\tServerID   string    `json:"server_id,omitempty"`
\tDeviceID   string    `json:"device_id"`
\tUsername   string    `json:"username,omitempty"`
\tGameUID    string    `json:"game_uid,omitempty"`
\tLoginKey   string    `json:"login_key"`
\tRoleIP     string    `json:"role_ip,omitempty"`
\tRolePort   int       `json:"role_port,omitempty"`
\tRoleZone   string    `json:"role_zone,omitempty"`
\tCreatedAt  time.Time `json:"created_at"`
}'''
text, n = re.subn(r'type sealedState struct \{.*?\n\}', sealed_struct, text, count=1, flags=re.S)
if n != 1:
    raise SystemExit('sealedState struct marker not found')

sync_impl = r'''func syncSession(w http.ResponseWriter, r *http.Request) {
\tsealed := strings.TrimSpace(r.Header.Get("X-WfGg-Sealed-State"))
\tif sealed == "" {
\t\twriteError(w, 401, "LASTWAR_RECONNECT_STATE_REQUIRED")
\t\treturn
\t}
\tstate, err := unsealState(sealed, stateSecret(r))
\tif err != nil {
\t\twriteError(w, 401, "LASTWAR_RECONNECT_STATE_INVALID")
\t\treturn
\t}

\tresult, refreshed, err := reconnectRole(state)
\tif err != nil {
\t\tif errors.Is(err, session.ErrAuthRejected) {
\t\t\tif state.Version < 2 || state.RoleIP == "" || state.RolePort <= 0 || state.RoleZone == "" {
\t\t\t\twriteError(w, 409, "LASTWAR_RELINK_REQUIRED")
\t\t\t} else {
\t\t\t\twriteError(w, 401, "LASTWAR_RECONNECT_AUTH_REJECTED")
\t\t\t}
\t\t\treturn
\t\t}
\t\tlog.Printf("read-only role reconnect failed: %T", err)
\t\twriteError(w, 503, "LASTWAR_RECONNECT_FAILED")
\t\treturn
\t}
\tdefer func() {
\t\tif result != nil && result.Conn != nil {
\t\t\t_ = result.Conn.Close()
\t\t}
\t}()

\tfreshSealed, err := sealState(refreshed, stateSecret(r))
\tif err != nil {
\t\twriteError(w, 500, "BROKER_STATE_ENCRYPTION_FAILED")
\t\treturn
\t}

\t// For now this endpoint proves the selected role can be reconnected read-only.
\t// Hero/equipment/research pulls are layered on this live role session next.
\twriteJSON(w, 200, map[string]any{
\t\t"uid":                  refreshed.LinkedUID,
\t\t"session_valid":        true,
\t\t"profile_sync_version": "role-session-v2",
\t\t"_wfgg_sealed_state":   freshSealed,
\t})
}

func reconnectRole(state sealedState) (*auth.CrossServerLoginResult, sealedState, error) {
\tif state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {
\t\treturn nil, state, fmt.Errorf("reconnect state incomplete")
\t}

\thttpClient := gsl.DefaultHTTPClient()
\tcv, gateHost, err := gsl.CheckVersion(httpClient)
\tif err != nil {
\t\treturn nil, state, fmt.Errorf("check-version: %w", err)
\t}
\tpub, err := lwcrypto.ParseRSAPubKeyFromDER(cv.ResMsg.String())
\tif err != nil {
\t\treturn nil, state, fmt.Errorf("parse RSA key: %w", err)
\t}
\tlsr, err := gsl.GetServerList(
\t\thttpClient,
\t\tgateHost,
\t\tpub,
\t\tstate.DeviceID,
\t\tgsl.GSLOpt{Opt: "login", LoginKey: state.LoginKey},
\t\t"",
\t\tstate.GameUID,
\t)
\tif err != nil {
\t\treturn nil, state, fmt.Errorf("refresh access token: %w", err)
\t}
\taccessTok := ""
\tif lsr.At != nil {
\t\taccessTok = strings.TrimSpace(lsr.At.Token.String())
\t}
\tif accessTok == "" {
\t\treturn nil, state, fmt.Errorf("refresh access token: empty token")
\t}

\tip := strings.TrimSpace(state.RoleIP)
\tport := state.RolePort
\tzone := strings.TrimSpace(state.RoleZone)
\tgameUID := strings.TrimSpace(state.GameUID)

\t// Version-1 links did not persist accountArr routing. Give them one safe
\t// upgrade attempt using the GSL-resolved route before requiring a one-time relink.
\tif len(lsr.ServerList) > 0 {
\t\tsrv := lsr.ServerList[0]
\t\tif ip == "" {
\t\t\tip = strings.TrimSpace(srv.IP.String())
\t\t}
\t\tif port <= 0 {
\t\t\tport = srv.Port.Int("port")
\t\t}
\t\tif zone == "" {
\t\t\tzone = strings.TrimSpace(srv.Zone.String())
\t\t}
\t\tif gameUID == "" {
\t\t\tgameUID = strings.TrimSpace(srv.GameUid.String())
\t\t}
\t}
\tif ip == "" || port <= 0 || zone == "" || gameUID == "" {
\t\treturn nil, state, fmt.Errorf("selected role route missing")
\t}

\tresult, err := auth.DoCrossServerLogin(auth.CrossServerLoginParams{
\t\tIP:         ip,
\t\tPort:       port,
\t\tZone:       zone,
\t\tGameUid:    gameUID,
\t\tDeviceID:   state.DeviceID,
\t\tAirKey:     airKeyForDevice(state.DeviceID),
\t\tAccessTok:  accessTok,
\t\tHTTPClient: httpClient,
\t\tRSAPub:     pub,
\t\tGateHost:   gateHost,
\t})
\tif err != nil {
\t\treturn nil, state, err
\t}

\tstate.Version = 2
\tstate.GameUID = gameUID
\tstate.RoleIP = ip
\tstate.RolePort = port
\tstate.RoleZone = zone
\tif result.GameUid != "" {
\t\tstate.GameUID = result.GameUid
\t}
\tif result.Zone != "" {
\t\tstate.RoleZone = result.Zone
\t}
\tif host, portText, splitErr := net.SplitHostPort(result.Addr); splitErr == nil {
\t\tif parsed, convErr := strconv.Atoi(portText); convErr == nil && parsed > 0 {
\t\t\tstate.RoleIP = host
\t\t\tstate.RolePort = parsed
\t\t}
\t}
\tstate.CreatedAt = time.Now().UTC()
\treturn result, state, nil
}

func airKeyForDevice(deviceID string) string {
\treturn "lwDid_" + base64.StdEncoding.EncodeToString([]byte(deviceID))
}'''
text, n = re.subn(
    r'func syncSession\(w http\.ResponseWriter, r \*http\.Request\) \{.*?\n\}\n\nfunc runEmailLogin',
    sync_impl + '\n\nfunc runEmailLogin',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('syncSession block marker not found')

role_metadata = r'''func roleMetadata(role, account *sfs.SFSObject) roleInfo {
\tplayer := firstString(role, "playerName", "gameUserName", "roleName", "nickname", "nickName", "name")
\tif player == "" {
\t\tplayer = firstString(account, "playerName", "gameUserName", "roleName", "nickname", "nickName", "name")
\t}
\tzone := firstString(role, "zone")
\tif zone == "" {
\t\tzone = firstString(account, "zone")
\t}
\tserver := firstString(role, "serverId", "server_id", "server")
\tif server == "" {
\t\tserver = firstString(account, "serverId", "server_id", "server")
\t}
\tif server == "" && zone != "" {
\t\tserver = digitsOnly(zone)
\t}
\tif strings.HasPrefix(strings.ToUpper(server), "APS") {
\t\tserver = digitsOnly(server)
\t}
\tip := firstString(role, "ip", "serverIp", "server_ip", "host")
\tif ip == "" {
\t\tip = firstString(account, "ip", "serverIp", "server_ip", "host")
\t}
\tport := firstPort(role)
\tif port <= 0 {
\t\tport = firstPort(account)
\t}
\tgameUID := firstString(role, "gameUid", "game_uid")
\tif gameUID == "" {
\t\tgameUID = firstString(account, "gameUid", "game_uid")
\t}
\tloginKey := firstString(role, "loginKey", "login_key")
\tif loginKey == "" {
\t\tloginKey = firstString(account, "loginKey", "login_key")
\t}
\treturn roleInfo{
\t\tPlayerName: player,
\t\tServerID:   server,
\t\tIP:         ip,
\t\tPort:       port,
\t\tZone:       zone,
\t\tGameUID:    gameUID,
\t\tLoginKey:   loginKey,
\t}
}

func firstPort(obj *sfs.SFSObject) int {
\tvalue := strings.TrimSpace(firstString(obj, "port"))
\tif value == "" {
\t\treturn 0
\t}
\tn, err := strconv.Atoi(value)
\tif err != nil || n <= 0 || n > 65535 {
\t\treturn 0
\t}
\treturn n
}'''
text, n = re.subn(
    r'func roleMetadata\(role, account \*sfs\.SFSObject\) roleInfo \{.*?\n\}\n\nfunc firstString',
    role_metadata + '\n\nfunc firstString',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('roleMetadata block marker not found')

snapshot_impl = r'''func snapshotIdentityState(linkedUID string, role roleInfo) (sealedState, error) {
\tdeviceID, err := readStateFile(".lastwar_goclient_device_id")
\tif err != nil || deviceID == "" {
\t\treturn sealedState{}, fmt.Errorf("device identity missing")
\t}
\tloginKey := strings.TrimSpace(role.LoginKey)
\tif loginKey == "" {
\t\tloginKey, err = readStateFile(".lastwar_goclient_loginkey")
\t\tif err != nil || loginKey == "" {
\t\t\treturn sealedState{}, fmt.Errorf("login key missing")
\t\t}
\t}
\tusername, _ := readStateFile(".lastwar_goclient_username")
\tgameUID := strings.TrimSpace(role.GameUID)
\tif gameUID == "" {
\t\tgameUID, _ = readStateFile(".lastwar_goclient_gameuid")
\t}
\treturn sealedState{
\t\tVersion:    2,
\t\tLinkedUID:  linkedUID,
\t\tPlayerName: role.PlayerName,
\t\tServerID:   role.ServerID,
\t\tDeviceID:   deviceID,
\t\tUsername:   username,
\t\tGameUID:    gameUID,
\t\tLoginKey:   loginKey,
\t\tRoleIP:     strings.TrimSpace(role.IP),
\t\tRolePort:   role.Port,
\t\tRoleZone:   strings.TrimSpace(role.Zone),
\t\tCreatedAt:  time.Now().UTC(),
\t}, nil
}'''
text, n = re.subn(
    r'func snapshotIdentityState\(linkedUID string, role roleInfo\) \(sealedState, error\) \{.*?\n\}\n\nfunc restoreIdentityState',
    snapshot_impl + '\n\nfunc restoreIdentityState',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('snapshotIdentityState block marker not found')

# Keep the legacy helper tolerant because old v1 sealed state may still be restored by
# diagnostics during a rolling deployment, even though syncSession now uses reconnectRole.
text = text.replace(
    'if state.Version != 1 || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {',
    'if (state.Version != 1 && state.Version != 2) || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {',
    1,
)

path.write_text(text, encoding='utf-8')
print('patched broker with role-aware sealed state and reusable cross-server reconnect')
