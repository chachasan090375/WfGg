package mailer

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"
	"sync"
	"time"
)

const (
	BridgeVersion     = "v6.26.0"
	MaxQueueBodyBytes = 8192
	MaxClockSkew      = 90 * time.Second
)

type HTTPServer struct {
	store  *Store
	secret []byte
	now    func() time.Time

	mu     sync.Mutex
	nonces map[string]int64
}

func NewHTTPHandler(store *Store, sharedKey string) (http.Handler, error) {
	if store == nil {
		return nil, errors.New("MAIL_OUTBOX_STORE_REQUIRED_V626")
	}
	if len(sharedKey) < 32 {
		return nil, errors.New("MAILER_SHARED_KEY_WEAK_V626")
	}
	s := &HTTPServer{
		store:  store,
		secret: []byte(sharedKey),
		now:    time.Now,
		nonces: map[string]int64{},
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", s.health)
	mux.HandleFunc("POST /v1/outbox/queue", s.queue)
	mux.HandleFunc("POST /v1/outbox/queue-batch", s.queueBatchV627)
	return mux, nil
}

func writeHTTPJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("content-type", "application/json; charset=utf-8")
	w.Header().Set("cache-control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func (s *HTTPServer) health(w http.ResponseWriter, _ *http.Request) {
	writeHTTPJSON(w, http.StatusOK, map[string]any{
		"ok":               true,
		"version":          BridgeVersion,
		"mode":             "OUTBOX_DRY_RUN",
		"lastwarWrite":     false,
		"lastwarMutation":  false,
		"mailSendExecuted": false,
		"tokenPersistence": false,
	})
}

func (s *HTTPServer) queue(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(io.LimitReader(r.Body, MaxQueueBodyBytes+1))
	if err != nil {
		writeHTTPJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": "MAIL_OUTBOX_BODY_READ_FAILED_V626"})
		return
	}
	if len(body) > MaxQueueBodyBytes {
		writeHTTPJSON(w, http.StatusRequestEntityTooLarge, map[string]any{"ok": false, "error": "MAIL_OUTBOX_BODY_TOO_LARGE_V626"})
		return
	}
	if err := s.verifySignedRequest(r, body); err != nil {
		writeHTTPJSON(w, http.StatusUnauthorized, map[string]any{"ok": false, "error": err.Error()})
		return
	}

	var input DraftRequest
	dec := json.NewDecoder(bytes.NewReader(body))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&input); err != nil {
		writeHTTPJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": "MAIL_OUTBOX_REQUEST_INVALID_V626"})
		return
	}
	if err := ValidateDraft(input); err != nil {
		writeHTTPJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	result, err := s.store.Queue(input)
	if err != nil {
		writeHTTPJSON(w, http.StatusInternalServerError, map[string]any{"ok": false, "error": "MAIL_OUTBOX_QUEUE_FAILED_V626"})
		return
	}
	writeHTTPJSON(w, http.StatusAccepted, map[string]any{
		"ok":               true,
		"version":          BridgeVersion,
		"mode":             "OUTBOX_DRY_RUN",
		"duplicate":        result.Duplicate,
		"record":           result.Record,
		"lastwarWrite":     false,
		"lastwarMutation":  false,
		"mailSendExecuted": false,
		"tokenPersistence": false,
	})
}

func (s *HTTPServer) verifySignedRequest(r *http.Request, body []byte) error {
	tsRaw := strings.TrimSpace(r.Header.Get("X-Radar-Timestamp"))
	nonce := strings.TrimSpace(r.Header.Get("X-Radar-Nonce"))
	sigRaw := strings.TrimSpace(r.Header.Get("X-Radar-Signature"))
	if tsRaw == "" || len(nonce) < 16 || len(nonce) > 128 || len(sigRaw) != 64 {
		return errors.New("MAILER_SIGNATURE_REQUIRED_V626")
	}
	for _, c := range nonce {
		if !(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') && !(c >= '0' && c <= '9') && c != '-' && c != '_' {
			return errors.New("MAILER_NONCE_INVALID_V626")
		}
	}
	ts, err := strconv.ParseInt(tsRaw, 10, 64)
	if err != nil {
		return errors.New("MAILER_TIMESTAMP_INVALID_V626")
	}
	now := s.now().Unix()
	if delta := now - ts; delta > int64(MaxClockSkew/time.Second) || delta < -int64(MaxClockSkew/time.Second) {
		return errors.New("MAILER_TIMESTAMP_STALE_V626")
	}
	bodyHash := sha256.Sum256(body)
	canonical := strings.Join([]string{
		r.Method,
		r.URL.Path,
		tsRaw,
		nonce,
		hex.EncodeToString(bodyHash[:]),
	}, "\n")
	mac := hmac.New(sha256.New, s.secret)
	_, _ = mac.Write([]byte(canonical))
	expected := mac.Sum(nil)
	provided, err := hex.DecodeString(sigRaw)
	if err != nil || !hmac.Equal(expected, provided) {
		return errors.New("MAILER_SIGNATURE_INVALID_V626")
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	cutoff := now - int64(MaxClockSkew/time.Second)
	for n, seen := range s.nonces {
		if seen < cutoff {
			delete(s.nonces, n)
		}
	}
	if _, exists := s.nonces[nonce]; exists {
		return errors.New("MAILER_NONCE_REPLAY_V626")
	}
	s.nonces[nonce] = now
	return nil
}
