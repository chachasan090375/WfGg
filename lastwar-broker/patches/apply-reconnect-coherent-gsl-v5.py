#!/usr/bin/env python3
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# The v3 runtime persisted the exact access token from the email-code login. That
# proves the selected role once, but the token is session material and must not be
# treated as a durable credential. For later cloud-sync runs, use the role's durable
# loginKey to obtain a fresh GSL token AND fresh route/gameUid as one coherent bundle.
# Mixing a fresh token with a stale accountArr route is precisely the kind of state
# mismatch that can surface as ec=28/E011.
reconnect_impl = r'''func reconnectRole(state sealedState) (*auth.CrossServerLoginResult, sealedState, error) {
	if state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {
		return nil, state, fmt.Errorf("reconnect state incomplete")
	}

	httpClient := gsl.DefaultHTTPClient()
	cv, gateHost, err := gsl.CheckVersion(httpClient)
	if err != nil {
		return nil, state, fmt.Errorf("check-version: %w", err)
	}
	pub, err := lwcrypto.ParseRSAPubKeyFromDER(cv.ResMsg.String())
	if err != nil {
		return nil, state, fmt.Errorf("parse RSA key: %w", err)
	}

	lsr, err := gsl.GetServerList(
		httpClient,
		gateHost,
		pub,
		state.DeviceID,
		gsl.GSLOpt{Opt: "login", LoginKey: state.LoginKey},
		"",
		state.GameUID,
	)
	if err != nil {
		return nil, state, fmt.Errorf("coherent GSL login: %w", err)
	}

	accessTok := ""
	if lsr.At != nil {
		accessTok = strings.TrimSpace(lsr.At.Token.String())
	}
	if accessTok == "" {
		return nil, state, fmt.Errorf("coherent GSL login returned no access token")
	}
	if len(lsr.ServerList) == 0 {
		return nil, state, fmt.Errorf("coherent GSL login returned no server route")
	}

	// Prefer the server entry for the exact saved role gameUid, then its zone. A
	// single-entry response is unambiguous. Only as a final fallback use entry 0;
	// token and route still come from the SAME GSL response in every case.
	selected := -1
	wantedGameUID := strings.TrimSpace(state.GameUID)
	wantedZone := strings.TrimSpace(state.RoleZone)
	if wantedGameUID != "" {
		for i := range lsr.ServerList {
			if strings.TrimSpace(lsr.ServerList[i].GameUid.String()) == wantedGameUID {
				selected = i
				break
			}
		}
	}
	if selected < 0 && wantedZone != "" {
		for i := range lsr.ServerList {
			if strings.TrimSpace(lsr.ServerList[i].Zone.String()) == wantedZone {
				selected = i
				break
			}
		}
	}
	if selected < 0 && len(lsr.ServerList) == 1 {
		selected = 0
	}
	if selected < 0 {
		selected = 0
	}

	srv := lsr.ServerList[selected]
	ip := strings.TrimSpace(srv.IP.String())
	port := srv.Port.Int("port")
	zone := strings.TrimSpace(srv.Zone.String())
	gameUID := strings.TrimSpace(srv.GameUid.String())
	if ip == "" || port <= 0 || zone == "" || gameUID == "" {
		return nil, state, fmt.Errorf("coherent GSL server route incomplete")
	}

	result, err := auth.DoCrossServerLogin(auth.CrossServerLoginParams{
		IP:         ip,
		Port:       port,
		Zone:       zone,
		GameUid:    gameUID,
		DeviceID:   state.DeviceID,
		AirKey:     airKeyForDevice(state.DeviceID),
		AccessTok:  accessTok,
		HTTPClient: httpClient,
		RSAPub:     pub,
		GateHost:   gateHost,
	})
	if err != nil {
		return nil, state, fmt.Errorf("coherent GSL role reconnect: %w", err)
	}

	// Persist the final server-accepted bundle. DoCrossServerLogin may itself follow
	// a serverInfo migration and refresh the access token, so its result wins.
	state.Version = 3
	state.AccessTok = accessTok
	state.GameUID = gameUID
	state.RoleIP = ip
	state.RolePort = port
	state.RoleZone = zone
	if strings.TrimSpace(result.AccessTok) != "" {
		state.AccessTok = strings.TrimSpace(result.AccessTok)
	}
	if strings.TrimSpace(result.GameUid) != "" {
		state.GameUID = strings.TrimSpace(result.GameUid)
	}
	if strings.TrimSpace(result.Zone) != "" {
		state.RoleZone = strings.TrimSpace(result.Zone)
	}
	if host, portText, splitErr := net.SplitHostPort(result.Addr); splitErr == nil {
		if parsed, convErr := strconv.Atoi(portText); convErr == nil && parsed > 0 {
			state.RoleIP = host
			state.RolePort = parsed
		}
	}
	state.CreatedAt = time.Now().UTC()
	return result, state, nil
}'''

pattern = re.compile(
    r'func reconnectRole\(state sealedState\) \(\*auth\.CrossServerLoginResult, sealedState, error\) \{.*?\n\}\n\nfunc airKeyForDevice',
    re.S,
)
patched, count = pattern.subn(reconnect_impl + '\n\nfunc airKeyForDevice', text, count=1)
if count != 1:
    raise SystemExit(f"v5 reconnectRole marker: expected exactly 1 match, found {count}")

path.write_text(patched, encoding="utf-8")
print("patched broker with coherent fresh GSL token+route role reconnect v5")
