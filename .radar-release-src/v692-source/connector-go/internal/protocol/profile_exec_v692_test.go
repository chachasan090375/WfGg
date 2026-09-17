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
			name:   "panic",
			runErr: errors.New("exit status 2"),
			stderr: "panic: runtime error: index out of range",
			want:   "LASTWAR_PLAYER_PROFILE_HELPER_PANIC",
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
