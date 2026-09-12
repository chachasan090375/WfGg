package authsig

import "testing"

func TestSignatureMatchesRadarWorkerVector(t *testing.T) {
    got := Signature("POST", "/v1/authenticate", "1789020000", "00112233445566778899aabbccddeeff", []byte(`{"token":"FAKE-NOT-A-REAL-TOKEN"}`), "0123456789abcdef0123456789abcdef")
    want := "fe1184b9e9dedb9521bb9f48f2fe21bd42ca5e2d677680f7ba620c4fd70af6e5"
    if got != want { t.Fatalf("signature mismatch: got %s want %s", got, want) }
}
