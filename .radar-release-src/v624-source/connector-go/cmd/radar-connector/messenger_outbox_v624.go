package main

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

const messengerOutboxVersionV624 = "v6.24.0-dry-run"

var messengerOutboxIDV624 = regexp.MustCompile(`^[a-f0-9]{24}$`)

func messengerOutboxBinV624() string {
	p := strings.TrimSpace(os.Getenv("WFGG_MESSENGER_OUTBOX_BIN"))
	if p == "" {
		p = "/opt/wfgg-messenger/bin/wfgg-messenger-outbox"
	}
	return p
}

func messengerOutboxLedgerV624() string {
	p := strings.TrimSpace(os.Getenv("WFGG_MESSENGER_OUTBOX_LEDGER"))
	if p == "" {
		p = "/opt/wfgg-messenger/data/outbox.jsonl"
	}
	return p
}

func messengerOutboxAvailableV624() bool {
	bin := messengerOutboxBinV624()
	if !filepath.IsAbs(bin) {
		return false
	}
	info, err := os.Stat(bin)
	return err == nil && !info.IsDir() && info.Mode()&0111 != 0
}

func messengerOutboxRunV624(ctx context.Context, stdin []byte, args ...string) (any, error) {
	bin := messengerOutboxBinV624()
	if !filepath.IsAbs(bin) {
		return nil, errors.New("MESSENGER_OUTBOX_BIN_MUST_BE_ABSOLUTE_V624")
	}
	if !messengerOutboxAvailableV624() {
		return nil, errors.New("MESSENGER_OUTBOX_BIN_UNAVAILABLE_V624")
	}
	ledger := messengerOutboxLedgerV624()
	if !filepath.IsAbs(ledger) {
		return nil, errors.New("MESSENGER_OUTBOX_LEDGER_MUST_BE_ABSOLUTE_V624")
	}
	allArgs := []string{"-ledger", ledger}
	allArgs = append(allArgs, args...)
	cmd := exec.CommandContext(ctx, bin, allArgs...)
	if len(stdin) > 0 {
		cmd.Stdin = strings.NewReader(string(stdin))
	}
	out, err := cmd.CombinedOutput()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return nil, errors.New("MESSENGER_OUTBOX_TIMEOUT_V624")
		}
		msg := strings.TrimSpace(string(out))
		if len(msg) > 180 {
			msg = msg[:180]
		}
		if msg == "" {
			msg = "MESSENGER_OUTBOX_HELPER_FAILED_V624"
		}
		return nil, errors.New(msg)
	}
	var payload any
	if err := json.Unmarshal(out, &payload); err != nil {
		return nil, errors.New("MESSENGER_OUTBOX_RESPONSE_INVALID_V624")
	}
	return payload, nil
}

func (s *server) messengerOutboxCreateV624(w http.ResponseWriter, r *http.Request, body []byte) {
	if len(body) == 0 || len(body) > 64*1024 || !json.Valid(body) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "MESSENGER_OUTBOX_DRAFT_INVALID_V624"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	payload, err := messengerOutboxRunV624(ctx, body, "create")
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "mode": "DRY_RUN_ONLY", "version": messengerOutboxVersionV624,
		"lastwarMutation": false, "networkSend": false, "outbox": payload,
	})
}

func (s *server) messengerOutboxQueueV624(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("id")))
	if !messengerOutboxIDV624.MatchString(id) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "MESSENGER_OUTBOX_ID_INVALID_V624"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	payload, err := messengerOutboxRunV624(ctx, nil, "queue", id)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "mode": "DRY_RUN_ONLY", "lastwarMutation": false, "networkSend": false, "outbox": payload,
	})
}

func (s *server) messengerOutboxCancelV624(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("id")))
	if !messengerOutboxIDV624.MatchString(id) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "MESSENGER_OUTBOX_ID_INVALID_V624"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	payload, err := messengerOutboxRunV624(ctx, nil, "cancel", id)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "mode": "DRY_RUN_ONLY", "lastwarMutation": false, "networkSend": false, "outbox": payload,
	})
}

func (s *server) messengerOutboxStatusV624(w http.ResponseWriter, r *http.Request, _ []byte) {
	id := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("id")))
	if !messengerOutboxIDV624.MatchString(id) {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "MESSENGER_OUTBOX_ID_INVALID_V624"})
		return
	}
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	payload, err := messengerOutboxRunV624(ctx, nil, "show", id)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "mode": "DRY_RUN_ONLY", "lastwarMutation": false, "networkSend": false, "outbox": payload,
	})
}

func (s *server) messengerOutboxListV624(w http.ResponseWriter, r *http.Request, _ []byte) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Second)
	defer cancel()
	payload, err := messengerOutboxRunV624(ctx, nil, "list")
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok": true, "mode": "DRY_RUN_ONLY", "lastwarMutation": false, "networkSend": false, "outbox": payload,
	})
}
