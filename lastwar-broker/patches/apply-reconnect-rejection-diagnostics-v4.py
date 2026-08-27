#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = '''\tif err != nil {
\t\tif errors.Is(err, session.ErrAuthRejected) {
\t\t\tif state.Version < 3 || strings.TrimSpace(state.AccessTok) == "" || strings.TrimSpace(state.RoleIP) == "" || state.RolePort <= 0 || strings.TrimSpace(state.RoleZone) == "" {
\t\t\t\twriteError(w, 409, "LASTWAR_RELINK_REQUIRED")
\t\t\t} else {
\t\t\t\twriteError(w, 401, "LASTWAR_RECONNECT_AUTH_REJECTED")
\t\t\t}
\t\t\treturn
\t\t}
\t\tlog.Printf("read-only role reconnect failed: %T", err)
\t\twriteError(w, 503, "LASTWAR_RECONNECT_FAILED")
\t\treturn
\t}'''

new = '''\tif err != nil {
\t\tif errors.Is(err, session.ErrAuthRejected) {
\t\t\tif state.Version < 3 || strings.TrimSpace(state.AccessTok) == "" || strings.TrimSpace(state.RoleIP) == "" || state.RolePort <= 0 || strings.TrimSpace(state.RoleZone) == "" {
\t\t\t\twriteError(w, 409, "LASTWAR_RELINK_REQUIRED")
\t\t\t} else {
\t\t\t\t// Keep credentials and the redacted server payload out of the browser, but expose
\t\t\t\t// the protocol's stable rejection class so staging can distinguish an identity/
\t\t\t\t// field mismatch (E005) from the alternate auth rejection (E011).  The upstream
\t\t\t\t// client includes these markers in the wrapped, already-redacted error string.
\t\t\t\tmsg := err.Error()
\t\t\t\tswitch {
\t\t\t\tcase strings.Contains(msg, "E005"):
\t\t\t\t\twriteError(w, 401, "LASTWAR_RECONNECT_AUTH_E005")
\t\t\t\tcase strings.Contains(msg, "E011"):
\t\t\t\t\twriteError(w, 401, "LASTWAR_RECONNECT_AUTH_E011")
\t\t\t\tdefault:
\t\t\t\t\twriteError(w, 401, "LASTWAR_RECONNECT_AUTH_REJECTED")
\t\t\t\t}
\t\t\t}
\t\t\treturn
\t\t}
\t\tlog.Printf("read-only role reconnect failed: %T", err)
\t\twriteError(w, 503, "LASTWAR_RECONNECT_FAILED")
\t\treturn
\t}'''

count = text.count(old)
if count != 1:
    raise SystemExit(f"auth rejection marker: expected exactly 1 match, found {count}")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("patched broker with safe E005/E011 reconnect diagnostics")
