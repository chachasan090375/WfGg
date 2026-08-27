#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old_struct = '''type LoginResult struct {
\tConn      *session.GameConn
\tIdent     *deviceIdentity
\tAccount   *sfs.SFSObject  // push.account.login.new params, if the email path ran (nil on loginKey fast-path)
\tBuildings []game.Building // populated if the `init` bootstrap push arrived during login (see waitForInitPush)
\tVisitors  []game.Visitor  // populated alongside Buildings, from the same `init` push (see waitForInitPush)
}'''
new_struct = '''type LoginResult struct {
\tConn      *session.GameConn
\tIdent     *deviceIdentity
\tAccount   *sfs.SFSObject  // push.account.login.new params, if the email path ran (nil on loginKey fast-path)
\tBuildings []game.Building // populated if the `init` bootstrap push arrived during login (see waitForInitPush)
\tVisitors  []game.Visitor  // populated alongside Buildings, from the same `init` push (see waitForInitPush)

\t// WfGg read-only broker extension: preserve the exact GSL access token used by
\t// the successful base-zone session so the selected role can be reconnected with
\t// the same authenticated session material after account.login.new.
\tAccessTok string
}'''
if text.count(old_struct) != 1:
    raise SystemExit(f"LoginResult marker: expected 1 match, found {text.count(old_struct)}")
text = text.replace(old_struct, new_struct, 1)

old_result = '''\tresult := &LoginResult{Conn: conn, Ident: ident, Buildings: buildings, Visitors: visitors}'''
new_result = '''\tresult := &LoginResult{Conn: conn, Ident: ident, Buildings: buildings, Visitors: visitors, AccessTok: accessTok}'''
if text.count(old_result) != 1:
    raise SystemExit(f"LoginResult init marker: expected 1 match, found {text.count(old_result)}")
text = text.replace(old_result, new_result, 1)

path.write_text(text, encoding="utf-8")
print("patched LoginResult to expose the successful GSL access token")
