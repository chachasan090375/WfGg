#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

needle = '''\tstate, err := unsealState(sealed, stateSecret(r))
\tif err != nil {
\t\twriteError(w, 401, "LASTWAR_RECONNECT_STATE_INVALID")
\t\treturn
\t}

\tresult, refreshed, err := reconnectRole(state)
'''
replacement = '''\tstate, err := unsealState(sealed, stateSecret(r))
\tif err != nil {
\t\twriteError(w, 401, "LASTWAR_RECONNECT_STATE_INVALID")
\t\treturn
\t}
\n\t// Links created before role-session-v2 do not contain the selected role route.
\t// Do not guess a route from the account-level GSL response: require a one-time
\t// relink so accountArr can be captured from the already-proven email flow.
\tif state.Version < 2 || strings.TrimSpace(state.RoleIP) == "" || state.RolePort <= 0 || strings.TrimSpace(state.RoleZone) == "" {
\t\twriteError(w, 409, "LASTWAR_RELINK_REQUIRED")
\t\treturn
\t}

\tresult, refreshed, err := reconnectRole(state)
'''
if needle not in text:
    raise SystemExit('syncSession unseal marker not found')
text = text.replace(needle, replacement, 1)

# A v2 state should be complete before reconnectRole is entered. Keep its fallback
# harmless, but change the comment so future maintenance does not re-enable v1 guessing.
text = text.replace(
    '''\t// Version-1 links did not persist accountArr routing. Give them one safe
\t// upgrade attempt using the GSL-resolved route before requiring a one-time relink.
''',
    '''\t// Defensive fallback for an incomplete v2 state only; syncSession rejects v1 links.
''',
    1,
)

path.write_text(text, encoding='utf-8')
print('patched broker to require one-time relink for legacy v1 state')
