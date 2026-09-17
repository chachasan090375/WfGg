package protocol

import "testing"

func TestNormalizeFederatedTargetServerV614(t *testing.T) {
	cases := map[string]string{
		"972":    "972",
		"APS972": "972",
		" 00972 ": "972",
	}
	for in, want := range cases {
		got, err := normalizeFederatedTargetServerV614(in)
		if err != nil {
			t.Fatalf("normalize %q: %v", in, err)
		}
		if got != want {
			t.Fatalf("normalize %q = %q, want %q", in, got, want)
		}
	}
	for _, in := range []string{"", "APS", "abc", "0", "-1", "123456789"} {
		if got, err := normalizeFederatedTargetServerV614(in); err == nil {
			t.Fatalf("normalize %q unexpectedly succeeded as %q", in, got)
		}
	}
}
