package main

import (
	"context"
	"crypto/rand"
	"encoding/base64"
	"errors"
	"io"
	"net/mail"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

const emailAuthReadyMarker = "verification code should now be arriving"

var sixDigitCode = regexp.MustCompile(`^[0-9]{6}$`)

type emailAuthStartRequest struct {
	GameUID string `json:"gameUid"`
	Email   string `json:"email"`
}

type emailAuthFinishRequest struct {
	ChallengeID string `json:"challengeId"`
	Code        string `json:"code"`
}

type emailChallenge struct {
	id          string
	expectedUID string
	home        string
	stdin       io.WriteCloser
	cmd         *exec.Cmd
	done        chan error
	expiresAt   time.Time
}

type emailAuthBroker struct {
	bin        string
	mu         sync.Mutex
	challenges map[string]*emailChallenge
}

func newEmailAuthBroker() *emailAuthBroker {
	bin := strings.TrimSpace(os.Getenv("LASTWAR_AUTH_CLIENT_BIN"))
	if bin == "" {
		bin = "/opt/wfgg-radar/bin/radar-lastwar-auth-client"
	}
	return &emailAuthBroker{bin: bin, challenges: map[string]*emailChallenge{}}
}

func (b *emailAuthBroker) available() bool {
	st, err := os.Stat(b.bin)
	return err == nil && !st.IsDir() && st.Mode()&0111 != 0
}

func (b *emailAuthBroker) cleanupExpired(now time.Time) {
	b.mu.Lock()
	defer b.mu.Unlock()
	for id, ch := range b.challenges {
		if now.After(ch.expiresAt) {
			_ = ch.cmd.Process.Kill()
			_ = ch.stdin.Close()
			_ = os.RemoveAll(ch.home)
			delete(b.challenges, id)
		}
	}
}

func newChallengeID() (string, error) {
	buf := make([]byte, 18)
	if _, err := rand.Read(buf); err != nil {
		return "", err
	}
	return base64.RawURLEncoding.EncodeToString(buf), nil
}

type readyWriter struct {
	mu    sync.Mutex
	tail  string
	ready chan struct{}
	once  sync.Once
}

func newReadyWriter() *readyWriter { return &readyWriter{ready: make(chan struct{})} }

func (w *readyWriter) Write(p []byte) (int, error) {
	w.mu.Lock()
	combined := w.tail + string(p)
	if strings.Contains(combined, emailAuthReadyMarker) {
		w.once.Do(func() { close(w.ready) })
	}
	if len(combined) > 1024 {
		combined = combined[len(combined)-1024:]
	}
	w.tail = combined
	w.mu.Unlock()
	return len(p), nil
}

func authChildEnv(home string) []string {
	out := make([]string, 0, len(os.Environ())+1)
	for _, item := range os.Environ() {
		key := item
		if i := strings.IndexByte(item, '='); i >= 0 {
			key = item[:i]
		}
		upper := strings.ToUpper(key)
		if upper == "HOME" || strings.HasPrefix(upper, "RADAR_") || strings.HasPrefix(upper, "LASTWAR_") || strings.HasPrefix(upper, "LWDEBUG_") {
			continue
		}
		out = append(out, item)
	}
	return append(out, "HOME="+home)
}

func (b *emailAuthBroker) start(expectedUID, email string) (string, error) {
	b.cleanupExpired(time.Now())
	if !b.available() {
		return "", errors.New("LASTWAR_EMAIL_AUTH_CLIENT_UNAVAILABLE")
	}
	expectedUID = strings.TrimSpace(expectedUID)
	if len(expectedUID) < 6 || len(expectedUID) > 64 {
		return "", errors.New("LASTWAR_GAME_UID_REQUIRED")
	}
	email = strings.TrimSpace(email)
	if len(email) > 320 {
		return "", errors.New("LASTWAR_EMAIL_INVALID")
	}
	parsed, err := mail.ParseAddress(email)
	if err != nil || !strings.EqualFold(parsed.Address, email) {
		return "", errors.New("LASTWAR_EMAIL_INVALID")
	}

	id, err := newChallengeID()
	if err != nil {
		return "", errors.New("LASTWAR_EMAIL_CHALLENGE_ID_FAILED")
	}
	home, err := os.MkdirTemp("", "wfgg-radar-email-auth-*")
	if err != nil {
		return "", errors.New("LASTWAR_EMAIL_CHALLENGE_TEMP_FAILED")
	}
	if err := os.Chmod(home, 0700); err != nil {
		_ = os.RemoveAll(home)
		return "", errors.New("LASTWAR_EMAIL_CHALLENGE_TEMP_FAILED")
	}

	ctx, cancel := context.WithCancel(context.Background())
	cmd := exec.CommandContext(ctx, b.bin, "-no-config", "-email", email, "-list-buildings", "-log-level", "info")
	cmd.Env = authChildEnv(home)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		cancel()
		_ = os.RemoveAll(home)
		return "", errors.New("LASTWAR_EMAIL_CHALLENGE_START_FAILED")
	}
	watch := newReadyWriter()
	cmd.Stdout = watch
	cmd.Stderr = watch
	if err := cmd.Start(); err != nil {
		cancel()
		_ = stdin.Close()
		_ = os.RemoveAll(home)
		return "", errors.New("LASTWAR_EMAIL_CHALLENGE_START_FAILED")
	}
	done := make(chan error, 1)
	go func() {
		done <- cmd.Wait()
		cancel()
	}()

	select {
	case <-watch.ready:
		ch := &emailChallenge{id: id, expectedUID: expectedUID, home: home, stdin: stdin, cmd: cmd, done: done, expiresAt: time.Now().Add(10 * time.Minute)}
		b.mu.Lock()
		b.challenges[id] = ch
		b.mu.Unlock()
		return id, nil
	case <-done:
		_ = stdin.Close()
		_ = os.RemoveAll(home)
		return "", errors.New("LASTWAR_EMAIL_CODE_REQUEST_REJECTED")
	case <-time.After(30 * time.Second):
		_ = cmd.Process.Kill()
		_ = stdin.Close()
		_ = os.RemoveAll(home)
		return "", errors.New("LASTWAR_EMAIL_CODE_REQUEST_TIMEOUT")
	}
}

func readPrivateTrimmed(path string) (string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

func (b *emailAuthBroker) finish(id, code string) (map[string]any, error) {
	b.cleanupExpired(time.Now())
	id = strings.TrimSpace(id)
	code = strings.TrimSpace(code)
	if id == "" || !sixDigitCode.MatchString(code) {
		return nil, errors.New("LASTWAR_EMAIL_CODE_INVALID")
	}

	b.mu.Lock()
	ch, ok := b.challenges[id]
	if ok {
		delete(b.challenges, id)
	}
	b.mu.Unlock()
	if !ok {
		return nil, errors.New("LASTWAR_EMAIL_CHALLENGE_NOT_FOUND")
	}
	defer os.RemoveAll(ch.home)

	if _, err := io.WriteString(ch.stdin, code+"\n"); err != nil {
		_ = ch.cmd.Process.Kill()
		_ = ch.stdin.Close()
		return nil, errors.New("LASTWAR_EMAIL_CODE_DELIVERY_FAILED")
	}
	_ = ch.stdin.Close()

	select {
	case err := <-ch.done:
		if err != nil {
			return nil, errors.New("LASTWAR_EMAIL_CODE_REJECTED")
		}
	case <-time.After(60 * time.Second):
		_ = ch.cmd.Process.Kill()
		return nil, errors.New("LASTWAR_EMAIL_LOGIN_TIMEOUT")
	}

	loginKey, err := readPrivateTrimmed(filepath.Join(ch.home, ".lastwar_goclient_loginkey"))
	if err != nil || len(loginKey) < 8 {
		return nil, errors.New("LASTWAR_EMAIL_LOGINKEY_MISSING")
	}
	gameUID, err := readPrivateTrimmed(filepath.Join(ch.home, ".lastwar_goclient_gameuid"))
	if err != nil || gameUID == "" {
		return nil, errors.New("LASTWAR_EMAIL_GAME_UID_MISSING")
	}
	if gameUID != ch.expectedUID {
		return nil, errors.New("LASTWAR_EMAIL_UID_MISMATCH")
	}
	pseudo, _ := readPrivateTrimmed(filepath.Join(ch.home, ".lastwar_goclient_username"))

	return map[string]any{
		"credential": loginKey,
		"identity": map[string]any{
			"gameUid": gameUID,
			"pseudo":  pseudo,
		},
	}, nil
}

func (s *server) emailAuthStart(w http.ResponseWriter, _ *http.Request, body []byte) {
	var input emailAuthStartRequest
	if err := decodeJSON(body, &input); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "INVALID_JSON"})
		return
	}
	id, err := s.emailAuth.start(input.GameUID, input.Email)
	if err != nil {
		writeJSON(w, emailAuthStatus(err), map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"ok": true, "challengeId": id, "expiresIn": 600})
}

func (s *server) emailAuthFinish(w http.ResponseWriter, _ *http.Request, body []byte) {
	var input emailAuthFinishRequest
	if err := decodeJSON(body, &input); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]any{"error": "INVALID_JSON"})
		return
	}
	result, err := s.emailAuth.finish(input.ChallengeID, input.Code)
	if err != nil {
		writeJSON(w, emailAuthStatus(err), map[string]any{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true, "auth": result})
}

func emailAuthStatus(err error) int {
	switch err.Error() {
	case "LASTWAR_GAME_UID_REQUIRED", "LASTWAR_EMAIL_INVALID", "LASTWAR_EMAIL_CODE_INVALID":
		return http.StatusBadRequest
	case "LASTWAR_EMAIL_CHALLENGE_NOT_FOUND":
		return http.StatusGone
	case "LASTWAR_EMAIL_UID_MISMATCH":
		return http.StatusForbidden
	case "LASTWAR_EMAIL_CODE_REJECTED", "LASTWAR_EMAIL_CODE_REQUEST_REJECTED":
		return http.StatusUnauthorized
	case "LASTWAR_EMAIL_AUTH_CLIENT_UNAVAILABLE":
		return http.StatusServiceUnavailable
	default:
		return http.StatusBadGateway
	}
}
