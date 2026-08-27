#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-staged-email-auth.py /path/to/internal/auth/login.go")

    path = pathlib.Path(sys.argv[1])
    text = path.read_text(encoding="utf-8")

    old_options = '''type LoginOptions struct {
\tEmail     string // required unless a LoginKey is already persisted
\tCodePipe  string // FIFO path to read the email verification code from; "" reads stdin
\tHandshake bool   // experimental: send the vanilla SFS2X pre-Login Handshake (see conn.go:DoHandshake)
}'''
    new_options = '''type LoginOptions struct {
\tEmail     string // required unless a LoginKey is already persisted
\tCodePipe  string // FIFO path to read the email verification code from; "" reads stdin
\tHandshake bool   // experimental: send the vanilla SFS2X pre-Login Handshake (see conn.go:DoHandshake)

\t// WfGg staged-web-auth extension. When provided, Login signals once Last War has accepted
\t// the send-code request, then obtains the code from the provider instead of stdin/FIFO.
\t// Neither callback changes the wire protocol; they only replace the CLI interaction boundary.
\tOnVerificationCodeSent   func()
\tVerificationCodeProvider func() (string, error)
}'''
    text = replace_once(text, old_options, new_options, "LoginOptions")

    old_sent = '''\tslog.Info("server accepted", "response", msg.Params.StringRedacted())
\tslog.Info("verification code should now be arriving", "emailLen", len(opts.Email))

\tslog.Info("step 7: waiting for verification code")'''
    new_sent = '''\tslog.Info("server accepted", "response", msg.Params.StringRedacted())
\tslog.Info("verification code should now be arriving", "emailLen", len(opts.Email))
\tif opts.OnVerificationCodeSent != nil {
\t\topts.OnVerificationCodeSent()
\t}

\tslog.Info("step 7: waiting for verification code")'''
    text = replace_once(text, old_sent, new_sent, "verification-code-sent callback")

    old_provider = '''\tvar code string
\tif opts.CodePipe != "" {
\t\tslog.Info("waiting for a writer on code pipe", "codePipe", opts.CodePipe)
\t\tcode = readCodeFromPipe(opts.CodePipe, conn)
\t} else {
\t\tslog.Info("feed the 6-digit code on stdin")
\t\tcode = readCodeFromStdin(conn)
\t}'''
    new_provider = '''\tvar code string
\tif opts.VerificationCodeProvider != nil {
\t\t// The embedding application may abort an expired/cancelled browser transaction without
\t\t// sending an empty or fabricated verification code to Last War.
\t\tprovided, providerErr := opts.VerificationCodeProvider()
\t\tif providerErr != nil {
\t\t\t_ = conn.Close()
\t\t\treturn nil, fmt.Errorf("verification code provider: %w", providerErr)
\t\t}
\t\tcode = strings.TrimSpace(provided)
\t} else if opts.CodePipe != "" {
\t\tslog.Info("waiting for a writer on code pipe", "codePipe", opts.CodePipe)
\t\tcode = readCodeFromPipe(opts.CodePipe, conn)
\t} else {
\t\tslog.Info("feed the 6-digit code on stdin")
\t\tcode = readCodeFromStdin(conn)
\t}'''
    text = replace_once(text, old_provider, new_provider, "verification-code provider")

    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
