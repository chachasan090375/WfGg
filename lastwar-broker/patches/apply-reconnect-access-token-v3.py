#!/usr/bin/env python3
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

sealed_struct = '''type sealedState struct {
\tVersion    int       `json:"version"`
\tLinkedUID  string    `json:"linked_uid"`
\tPlayerName string    `json:"player_name,omitempty"`
\tServerID   string    `json:"server_id,omitempty"`
\tDeviceID   string    `json:"device_id"`
\tUsername   string    `json:"username,omitempty"`
\tGameUID    string    `json:"game_uid,omitempty"`
\tLoginKey   string    `json:"login_key"`
\tAccessTok  string    `json:"access_token"`
\tRoleIP     string    `json:"role_ip,omitempty"`
\tRolePort   int       `json:"role_port,omitempty"`
\tRoleZone   string    `json:"role_zone,omitempty"`
\tCreatedAt  time.Time `json:"created_at"`
}'''
text, n = re.subn(r'type sealedState struct \{.*?\n\}', sealed_struct, text, count=1, flags=re.S)
if n != 1:
    raise SystemExit("sealedState struct marker not found")

old_verify = '''\t\tstate, err := snapshotIdentityState(uid, role)
\t\tif err != nil {
\t\t\twriteError(w, 502, "LASTWAR_RECONNECT_STATE_MISSING")
\t\t\treturn
\t\t}
\t\tsealed, err := sealState(state, stateSecret(r))'''
new_verify = '''\t\tstate, err := snapshotIdentityState(uid, role)
\t\tif err != nil {
\t\t\twriteError(w, 502, "LASTWAR_RECONNECT_STATE_MISSING")
\t\t\treturn
\t\t}
\t\t// Preserve the exact access token that authenticated the successful base-zone
\t\t// session. The selected role is opened by the real client from accountArr using
\t\t// this same live session material; manufacturing a different GSL token here can
\t\t// produce a token/route mismatch and an immediate ec=28/E011 rejection.
\t\tstate.AccessTok = strings.TrimSpace(out.result.AccessTok)
\t\tif state.AccessTok == "" {
\t\t\twriteError(w, 502, "LASTWAR_RECONNECT_STATE_MISSING")
\t\t\treturn
\t\t}
\t\tstate.Version = 3
\t\tsealed, err := sealState(state, stateSecret(r))'''
if text.count(old_verify) != 1:
    raise SystemExit(f"verify state marker: expected 1 match, found {text.count(old_verify)}")
text = text.replace(old_verify, new_verify, 1)

reconnect_impl = r'''func reconnectRole(state sealedState) (*auth.CrossServerLoginResult, sealedState, error) {
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

\tip := strings.TrimSpace(state.RoleIP)
\tport := state.RolePort
\tzone := strings.TrimSpace(state.RoleZone)
\tgameUID := strings.TrimSpace(state.GameUID)
\taccessTok := strings.TrimSpace(state.AccessTok)

\t// Version 3 preserves the exact access token from the successful email-code
\t// session and reuses it with the accountArr-selected role, matching the real
\t// client's role-picker flow. Older sealed states never stored that token and
\t// are rejected by syncSession's relink guard before this function is reached.
\tif accessTok == "" {
\t\treturn nil, state, fmt.Errorf("reconnect access token missing")
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

\tstate.Version = 3
\tstate.AccessTok = accessTok
\tif strings.TrimSpace(result.AccessTok) != "" {
\t\tstate.AccessTok = strings.TrimSpace(result.AccessTok)
\t}
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
}'''
text, n = re.subn(
    r'func reconnectRole\(state sealedState\) \(\*auth\.CrossServerLoginResult, sealedState, error\) \{.*?\n\}\n\nfunc airKeyForDevice',
    reconnect_impl + '\n\nfunc airKeyForDevice',
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("reconnectRole block marker not found")

# New links carry the exact session token, so any pre-v3 sealed state must be
# linked one last time instead of retrying the known-bad synthetic-token path.
old_guard = 'if state.Version < 2 || strings.TrimSpace(state.RoleIP) == "" || state.RolePort <= 0 || strings.TrimSpace(state.RoleZone) == "" {'
new_guard = 'if state.Version < 3 || strings.TrimSpace(state.AccessTok) == "" || strings.TrimSpace(state.RoleIP) == "" || state.RolePort <= 0 || strings.TrimSpace(state.RoleZone) == "" {'
if text.count(old_guard) != 1:
    raise SystemExit(f"legacy relink guard marker: expected 1 match, found {text.count(old_guard)}")
text = text.replace(old_guard, new_guard, 1)

text = text.replace(
    'Version:    2,',
    'Version:    3,',
    1,
)
text = text.replace(
    'if (state.Version != 1 && state.Version != 2) || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {',
    'if (state.Version != 1 && state.Version != 2 && state.Version != 3) || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {',
    1,
)

path.write_text(text, encoding="utf-8")
print("patched broker with v3 sealed access-token reconnect")
