#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

old = '''\t\tlog.Printf("read-only login-key fastpath failed: %T", err)
\t\twriteError(w, 503, "LASTWAR_RECONNECT_FAILED")
\t\treturn'''
new = '''\t\tcode := reconnectFailureCode(err)
\t\t// Never log or return err.Error() here: upstream errors can contain account/session
\t\t// material even when most payload formatting is redacted. The browser only receives
\t\t// a static stage category; logs keep the Go type plus that same category.
\t\tlog.Printf("read-only login-key fastpath failed: category=%s type=%T", code, err)
\t\twriteError(w, 503, code)
\t\treturn'''

if text.count(old) != 1:
    raise SystemExit(f"v7 generic reconnect marker: expected exactly 1 match, found {text.count(old)}")
text = text.replace(old, new, 1)

helper = r'''// reconnectFailureCode maps the returning-session Login() failure to a deliberately
// coarse, non-sensitive stage. Classification may inspect the local wrapped error string, but
// that string is never returned to the Worker/browser and is never logged here.
func reconnectFailureCode(err error) string {
	if err == nil {
		return "LASTWAR_RECONNECT_FAILED"
	}
	msg := strings.ToLower(err.Error())

	switch {
	case strings.Contains(msg, "connection failed while waiting for init push"):
		return "LASTWAR_RECONNECT_INIT_CONNECTION_LOST"
	case strings.Contains(msg, "response had no p payload"):
		return "LASTWAR_RECONNECT_LOGIN_RESPONSE_INVALID"
	case strings.Contains(msg, "serverinfo") ||
		strings.Contains(msg, "redirect") ||
		strings.Contains(msg, "redirect target"):
		return "LASTWAR_RECONNECT_REDIRECT_FAILED"
	case strings.Contains(msg, "check-version") ||
		strings.Contains(msg, "getserverlist") ||
		strings.Contains(msg, "no servers returned") ||
		strings.Contains(msg, "parse rsa") ||
		strings.Contains(msg, "gsl"):
		return "LASTWAR_RECONNECT_GSL_FAILED"
	case strings.Contains(msg, "send stage") ||
		strings.Contains(msg, "send envelope") ||
		strings.Contains(msg, "write tcp"):
		return "LASTWAR_RECONNECT_SEND_FAILED"
	case strings.Contains(msg, "i/o timeout") ||
		strings.Contains(msg, "deadline exceeded") ||
		strings.Contains(msg, "timed out") ||
		strings.Contains(msg, "timeout"):
		return "LASTWAR_RECONNECT_NETWORK_TIMEOUT"
	case strings.Contains(msg, "dial tcp") ||
		strings.Contains(msg, "connection refused") ||
		strings.Contains(msg, "network is unreachable") ||
		strings.Contains(msg, "no route to host") ||
		strings.Contains(msg, "connect:"):
		return "LASTWAR_RECONNECT_DIAL_FAILED"
	case strings.Contains(msg, "connection reset") ||
		strings.Contains(msg, "broken pipe") ||
		strings.Contains(msg, "unexpected eof") ||
		strings.Contains(msg, "connection closed"):
		return "LASTWAR_RECONNECT_CONNECTION_LOST"
	default:
		return "LASTWAR_RECONNECT_FAILED"
	}
}
'''

marker = '\nfunc reconnectRole('
if text.count(marker) != 1:
    raise SystemExit(f"v7 reconnectRole insertion marker: expected exactly 1 match, found {text.count(marker)}")
text = text.replace(marker, '\n' + helper + '\nfunc reconnectRole(', 1)

path.write_text(text, encoding="utf-8")
print("patched broker with safe reconnect stage diagnostics v7")
