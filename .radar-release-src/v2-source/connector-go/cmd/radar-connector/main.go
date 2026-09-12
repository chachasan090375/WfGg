package main

import (
	"encoding/json"
	"errors"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strings"
	"time"

	"wfgg-radar-connector/internal/authsig"
	"wfgg-radar-connector/internal/protocol"
)

type server struct {
	secret    string
	replay    *authsig.ReplayGuard
	game      protocol.Client
	emailAuth *emailAuthBroker
}

type authRequest struct {
	Token string `json:"token"`
}
type scanRequest struct {
	Token string `json:"token"`
	Query string `json:"query"`
}

func main() {
	secret := os.Getenv("RADAR_CONNECTOR_SHARED_KEY")
	if len(secret) < 32 {
		panic("RADAR_CONNECTOR_SHARED_KEY must contain at least 32 characters")
	}
	addr := os.Getenv("RADAR_CONNECTOR_ADDR")
	if addr == "" {
		addr = ":8788"
	}

	game := protocol.NewFromEnv()
	s := &server{secret: secret, replay: authsig.NewReplayGuard(2 * time.Minute), game: game, emailAuth: newEmailAuthBroker()}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /v1/health", s.signed(s.health))
	mux.HandleFunc("POST /v1/authenticate", s.signed(s.authenticate))
	mux.HandleFunc("POST /v1/auth/email/start", s.signed(s.emailAuthStart))
	mux.HandleFunc("POST /v1/auth/email/finish", s.signed(s.emailAuthFinish))
	mux.HandleFunc("POST /v1/snapshot", s.signed(s.snapshot))
	mux.HandleFunc("POST /v1/scan/player", s.signed(s.scanPlayer))
	mux.HandleFunc("POST /v1/collector/search/start", s.signed(s.collectorSearchStart))
	mux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))

	httpServer := &http.Server{Addr: addr, Handler: securityHeaders(mux), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 15 * time.Second, WriteTimeout: 75 * time.Second, IdleTimeout: 30 * time.Second}
	slog.Info("radar connector listening", "addr", addr, "protocol", game.Mode(), "readonly", true, "emailAuth", s.emailAuth.available())
	if err := httpServer.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		panic(err)
	}
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		next.ServeHTTP(w, r)
	})
}

func (s *server) signed(next func(http.ResponseWriter, *http.Request, []byte)) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		body, err := authsig.VerifyRequest(r, s.secret, s.replay, time.Now())
		if err != nil {
			writeJSON(w, http.StatusUnauthorized, map[string]any{"error": "CONNECTOR_AUTH_FAILED"})
			return
		}
		next(w, r, body)
	}
}

func (s *server) health(w http.ResponseWriter, _ *http.Request, _ []byte) {
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "service": "wfgg-radar-connector", "version": "0.5.0-collector-async-email-auth-v1", "protocol": s.game.Mode(), "readonly": true, "collectorAsync": true, "emailAuth": s.emailAuth.available()})
}

func (s *server) authenticate(w http.ResponseWriter, r *http.Request, body []byte) {
	var input authRequest
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "GAME_TOKEN_REQUIRED"})
		return
	}
	identity, err := s.game.Authenticate(r.Context(), input.Token)
	if err != nil {
		writeGameError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"identity": identity})
}

func (s *server) snapshot(w http.ResponseWriter, r *http.Request, body []byte) {
	var input authRequest
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "GAME_TOKEN_REQUIRED"})
		return
	}
	snapshot, err := s.game.Snapshot(r.Context(), input.Token)
	if err != nil {
		writeGameError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"snapshot": snapshot})
}

func (s *server) scanPlayer(w http.ResponseWriter, r *http.Request, body []byte) {
	var input scanRequest
	if err := decodeJSON(body, &input); err != nil || len(strings.TrimSpace(input.Token)) < 8 || strings.TrimSpace(input.Query) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "TOKEN_AND_QUERY_REQUIRED"})
		return
	}
	players, err := s.game.ScanPlayer(r.Context(), input.Token, input.Query)
	if err != nil {
		writeGameError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"players": players})
}

func writeGameError(w http.ResponseWriter, err error) {
	code := err.Error()
	status := http.StatusBadGateway
	switch code {
	case "LASTWAR_PROTOCOL_NOT_CONFIGURED", "LASTWAR_SESSION_CONTEXT_INCOMPLETE", "LASTWAR_SESSION_CONTEXT_INVALID", "LASTWAR_SESSION_CONTEXT_MUST_NOT_CONTAIN_ACCESS_TOKEN", "LASTWAR_NATIVE_TEMPLATE_BIN_REQUIRED", "LASTWAR_NATIVE_CAPTURE_REQUIRED", "LASTWAR_NATIVE_CAPTURE_UNREADABLE":
		status = http.StatusServiceUnavailable
	case "LASTWAR_AUTH_REJECTED":
		status = http.StatusUnauthorized
	case "LASTWAR_PSEUDO_NOT_OBSERVED_YET":
		status = http.StatusUnprocessableEntity
	case "LASTWAR_MAP_SCAN_NOT_IMPLEMENTED":
		status = http.StatusNotImplemented
	}
	// Deliberately do not log request bodies/tokens.
	writeJSON(w, status, map[string]any{"error": code})
}

func decodeJSON(body []byte, target any) error {
	dec := json.NewDecoder(strings.NewReader(string(body)))
	dec.DisallowUnknownFields()
	if err := dec.Decode(target); err != nil {
		return err
	}
	if err := dec.Decode(&struct{}{}); err != io.EOF {
		return errors.New("trailing JSON")
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
