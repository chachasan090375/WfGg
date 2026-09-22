package mailer

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strconv"
	"testing"
	"time"
)

const testMailerKeyV626 = "0123456789abcdef0123456789abcdef"

func signedQueueRequestV626(t *testing.T, body []byte, ts int64, nonce string) *http.Request {
	t.Helper()
	req := httptest.NewRequest(http.MethodPost, "/v1/outbox/queue", bytes.NewReader(body))
	sum := sha256.Sum256(body)
	canonical := http.MethodPost + "\n/v1/outbox/queue\n" + strconv.FormatInt(ts, 10) + "\n" + nonce + "\n" + hex.EncodeToString(sum[:])
	mac := hmac.New(sha256.New, []byte(testMailerKeyV626))
	_, _ = mac.Write([]byte(canonical))
	req.Header.Set("content-type", "application/json")
	req.Header.Set("X-Radar-Timestamp", strconv.FormatInt(ts, 10))
	req.Header.Set("X-Radar-Nonce", nonce)
	req.Header.Set("X-Radar-Signature", hex.EncodeToString(mac.Sum(nil)))
	return req
}

func TestV626HealthProvesDryRunBoundary(t *testing.T) {
	h, err := NewHTTPHandler(&Store{Path: filepath.Join(t.TempDir(), "outbox.jsonl")}, testMailerKeyV626)
	if err != nil {
		t.Fatal(err)
	}
	res := httptest.NewRecorder()
	h.ServeHTTP(res, httptest.NewRequest(http.MethodGet, "/v1/health", nil))
	if res.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", res.Code, res.Body.String())
	}
	var got map[string]any
	if err := json.Unmarshal(res.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if got["mode"] != "OUTBOX_DRY_RUN" || got["lastwarWrite"] != false || got["lastwarMutation"] != false || got["mailSendExecuted"] != false || got["tokenPersistence"] != false {
		t.Fatalf("unsafe health response: %#v", got)
	}
}

func TestV626SignedQueuePersistsWithoutSending(t *testing.T) {
	path := filepath.Join(t.TempDir(), "outbox.jsonl")
	h, err := NewHTTPHandler(&Store{Path: path}, testMailerKeyV626)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Unix(1770000000, 0)
	s := h.(*http.ServeMux)
	_ = s
	// Build a server directly so the test clock is deterministic.
	server := &HTTPServer{store: &Store{Path: path}, secret: []byte(testMailerKeyV626), now: func() time.Time { return now }, nonces: map[string]int64{}}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", server.health)
	mux.HandleFunc("POST /v1/outbox/queue", server.queue)

	body, _ := json.Marshal(validDraft())
	req := signedQueueRequestV626(t, body, now.Unix(), "nonce-v626-00000001")
	res := httptest.NewRecorder()
	mux.ServeHTTP(res, req)
	if res.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", res.Code, res.Body.String())
	}
	var got struct {
		OK               bool         `json:"ok"`
		Duplicate        bool         `json:"duplicate"`
		Record           OutboxRecord `json:"record"`
		LastWarWrite     bool         `json:"lastwarWrite"`
		LastWarMutation  bool         `json:"lastwarMutation"`
		MailSendExecuted bool         `json:"mailSendExecuted"`
	}
	if err := json.Unmarshal(res.Body.Bytes(), &got); err != nil {
		t.Fatal(err)
	}
	if !got.OK || got.Duplicate || got.LastWarWrite || got.LastWarMutation || got.MailSendExecuted {
		t.Fatalf("unexpected queue response: %#v", got)
	}
	if got.Record.State != "DRY_RUN_READY" || got.Record.WireTemplate.SendLocalTime != 0 || !got.Record.RequiresServerTime {
		t.Fatalf("outbox record violates dry-run contract: %#v", got.Record)
	}
}

func TestV626ReplayAndBadSignatureAreRejected(t *testing.T) {
	path := filepath.Join(t.TempDir(), "outbox.jsonl")
	now := time.Unix(1770000000, 0)
	server := &HTTPServer{store: &Store{Path: path}, secret: []byte(testMailerKeyV626), now: func() time.Time { return now }, nonces: map[string]int64{}}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/outbox/queue", server.queue)
	body, _ := json.Marshal(validDraft())

	req := signedQueueRequestV626(t, body, now.Unix(), "nonce-v626-00000002")
	first := httptest.NewRecorder()
	mux.ServeHTTP(first, req)
	if first.Code != http.StatusAccepted {
		t.Fatalf("first status=%d body=%s", first.Code, first.Body.String())
	}

	replay := signedQueueRequestV626(t, body, now.Unix(), "nonce-v626-00000002")
	second := httptest.NewRecorder()
	mux.ServeHTTP(second, replay)
	if second.Code != http.StatusUnauthorized {
		t.Fatalf("replay status=%d body=%s", second.Code, second.Body.String())
	}

	bad := signedQueueRequestV626(t, body, now.Unix(), "nonce-v626-00000003")
	bad.Header.Set("X-Radar-Signature", "00"+bad.Header.Get("X-Radar-Signature")[2:])
	third := httptest.NewRecorder()
	mux.ServeHTTP(third, bad)
	if third.Code != http.StatusUnauthorized {
		t.Fatalf("bad signature status=%d body=%s", third.Code, third.Body.String())
	}
}
