package protocol

import (
	"errors"
	"testing"
)

func TestProfileExecutionFailureV692(t *testing.T) {
	cases := []struct {
		name   string
		runErr error
		stdout string
		stderr string
		want   string
	}{
		{
			name:   "panic clone",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error: index out of range\nmain.cloneProfileBatchValueV69(...)\nmain.runProfileScanV69(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_CLONE",
		},
		{
			name:   "panic encode",
			runErr: errors.New("exit status 2"),
			stderr: "panic: interface conversion\nlastwar-client/internal/sfs.EncodeObject(...)\nmain.runProfileScanV69(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_ENCODE",
		},
		{
			name:   "panic frame",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error\nlastwar-client/internal/sfs.EncodePacket(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_FRAME",
		},
		{
			name:   "panic read",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error\nlastwar-client/internal/sfs.ReadPacket(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_READ",
		},
		{
			name:   "panic decode",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error\nlastwar-client/internal/sfs.DecodeObject(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_DECODE",
		},
		{
			name:   "panic profile parse",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error\nmain.findProfileV3(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_PROFILE_PARSE",
		},
		{
			name:   "panic template discovery",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error\nmain.findPlayerScanV3Templates(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_TEMPLATE_DISCOVERY",
		},
		{
			name:   "panic unsupported SFS encode type",
			runErr: errors.New("exit status 2"),
			stderr: "panic: sfsobject: unsupported encode type 21\nlastwar-client/internal/sfs.someEncoder(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_SFS_UNSUPPORTED_ENCODE_TYPE",
		},
		{
			name:   "panic native source line",
			runErr: errors.New("exit status 2"),
			stderr: "panic: exotic helper failure\nruntime.gopanic(...)\n\t/usr/local/go/src/runtime/panic.go:783 +0x1\nmain.unknownProfilePath(...)\n\tlastwar-client/cmd/wfgg-radar-native-template/profile_scan_v69.go:141 +0x2\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_NATIVE_PROFILE_SCAN_V69_L141",
		},
		{
			name:   "panic SFS source line",
			runErr: errors.New("exit status 2"),
			stderr: "panic: exotic helper failure\nruntime.gopanic(...)\n\t/usr/local/go/src/runtime/panic.go:783 +0x1\nsfs.unknownEncoder(...)\n\tlastwar-client/internal/sfs/sfsobject.go:823 +0x2\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_SFS_SFSOBJECT_L823",
		},
		{
			name:   "panic auth source line",
			runErr: errors.New("exit status 2"),
			stderr: "panic: exotic helper failure\nauth.unknown(...)\n\tlastwar-client/internal/auth/login.go:77 +0x2\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_AUTH_LOGIN_L77",
		},
		{
			name:   "panic nil fallback",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error: invalid memory address or nil pointer dereference\nmain.unknownFunction(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_NIL",
		},
		{
			name:   "panic type fallback",
			runErr: errors.New("exit status 2"),
			stderr: "panic: interface conversion: interface {} is string, not int64\nmain.unknownFunction(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_TYPE",
		},
		{
			name:   "panic bounds fallback",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error: index out of range [4] with length 2\nmain.unknownFunction(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_BOUNDS",
		},
		{
			name:   "panic map fallback",
			runErr: errors.New("exit status 2"),
			stderr: "panic: assignment to entry in nil map\nmain.unknownFunction(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_MAP",
		},
		{
			name:   "panic unknown fallback",
			runErr: errors.New("exit status 2"),
			stderr: "panic: unexpected runtime failure\nmain.unknownFunction(...)\n",
			want:   "LASTWAR_PLAYER_PROFILE_PANIC_UNKNOWN_V695",
		},
		{
			name:   "signal crash",
			runErr: errors.New("signal: segmentation fault"),
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_CRASH",
		},
		{
			name:   "exec failure",
			runErr: errors.New("fork/exec /missing/helper: no such file or directory"),
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_EXEC_FAILED",
		},
		{
			name:   "normal error exit without report",
			runErr: errors.New("exit status 1"),
			stdout: "  \n",
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_NO_REPORT",
		},
		{
			name:   "normal error exit malformed report",
			runErr: errors.New("exit status 1"),
			stdout: "{broken-json",
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_REPORT_INVALID",
		},
		{
			name:   "successful exit without report",
			stdout: "",
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_NO_REPORT",
		},
		{
			name:   "successful exit malformed report",
			stdout: "not-json",
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_REPORT_INVALID",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := profileExecutionFailureV692(tc.runErr, []byte(tc.stdout), []byte(tc.stderr)).Error()
			if got != tc.want {
				t.Fatalf("got %q, want %q", got, tc.want)
			}
		})
	}
}
