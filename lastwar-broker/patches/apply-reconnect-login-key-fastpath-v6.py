#!/usr/bin/env python3
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

# V6: a later cloud sync is NOT the role-picker transition that immediately
# follows account.login.new. Once the selected role's loginKey/gameUid have
# been sealed, the reference client reconnects through its normal Login()
# fast-path: GSL opt=login, then the base-zone SFS Login with un/gameUid empty.
# Re-running DoCrossServerLogin on every refresh incorrectly repeats the
# one-time role-picker path and can surface ec=28/E005.
sync_impl = r'''func syncSession(w http.ResponseWriter, r *http.Request) {
	sealed := strings.TrimSpace(r.Header.Get("X-WfGg-Sealed-State"))
	if sealed == "" {
		writeError(w, 401, "LASTWAR_RECONNECT_STATE_REQUIRED")
		return
	}
	state, err := unsealState(sealed, stateSecret(r))
	if err != nil {
		writeError(w, 401, "LASTWAR_RECONNECT_STATE_INVALID")
		return
	}
	if state.Version < 3 || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {
		writeError(w, 409, "LASTWAR_RELINK_REQUIRED")
		return
	}

	// Restore the role-specific durable identity captured from accountArr. Login()
	// then follows the reference returning-session path: GSL opt=login and a
	// base-zone Login with un/gameUid intentionally empty. That is materially
	// different from the one-time CrossServerLogin role-picker transition.
	if err := restoreIdentityState(state); err != nil {
		writeError(w, 500, "LASTWAR_RECONNECT_STATE_RESTORE_FAILED")
		return
	}

	result, err := auth.Login(auth.LoginOptions{})
	if err != nil {
		if errors.Is(err, session.ErrAuthRejected) {
			msg := err.Error()
			switch {
			case strings.Contains(msg, "E005"):
				writeError(w, 401, "LASTWAR_RECONNECT_AUTH_E005")
			case strings.Contains(msg, "E011"):
				writeError(w, 401, "LASTWAR_RECONNECT_AUTH_E011")
			default:
				writeError(w, 401, "LASTWAR_RECONNECT_AUTH_REJECTED")
			}
			return
		}
		log.Printf("read-only login-key fastpath failed: %T", err)
		writeError(w, 503, "LASTWAR_RECONNECT_FAILED")
		return
	}
	defer closeLoginResult(result)

	// Login() may refresh the persisted gameUid/username while resolving the
	// account. Fold those durable values back into the encrypted state without
	// exposing them to the Worker/browser. Keep the saved role route as a
	// diagnostic/fallback artifact, but future V6 syncs no longer depend on it.
	if v, readErr := readStateFile(".lastwar_goclient_device_id"); readErr == nil && strings.TrimSpace(v) != "" {
		state.DeviceID = strings.TrimSpace(v)
	}
	if v, readErr := readStateFile(".lastwar_goclient_username"); readErr == nil {
		state.Username = strings.TrimSpace(v)
	}
	if v, readErr := readStateFile(".lastwar_goclient_gameuid"); readErr == nil && strings.TrimSpace(v) != "" {
		state.GameUID = strings.TrimSpace(v)
	}
	if v, readErr := readStateFile(".lastwar_goclient_loginkey"); readErr == nil && strings.TrimSpace(v) != "" {
		state.LoginKey = strings.TrimSpace(v)
	}
	if result != nil && strings.TrimSpace(result.AccessTok) != "" {
		state.AccessTok = strings.TrimSpace(result.AccessTok)
	}
	state.Version = 4
	state.CreatedAt = time.Now().UTC()

	freshSealed, err := sealState(state, stateSecret(r))
	if err != nil {
		writeError(w, 500, "BROKER_STATE_ENCRYPTION_FAILED")
		return
	}

	writeJSON(w, 200, map[string]any{
		"uid":                  state.LinkedUID,
		"session_valid":        true,
		"profile_sync_version": "login-key-fastpath-v6",
		"_wfgg_sealed_state":   freshSealed,
	})
}'''

pattern = re.compile(
    r'func syncSession\(w http\.ResponseWriter, r \*http\.Request\) \{.*?\n\}\n\nfunc reconnectRole',
    re.S,
)
patched, count = pattern.subn(sync_impl + '\n\nfunc reconnectRole', text, count=1)
if count != 1:
    raise SystemExit(f"v6 syncSession marker: expected exactly 1 match, found {count}")

path.write_text(patched, encoding="utf-8")
print("patched broker with loginKey fast-path reconnect v6")
