package main

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"lastwar-client/internal/auth"
	"lastwar-client/internal/session"
	"lastwar-client/internal/sfs"
)

const (
	listenAddr      = ":8080"
	transactionTTL  = 10 * time.Minute
	sendCodeTimeout = 70 * time.Second
	verifyTimeout   = 60 * time.Second
	maxRequestBytes = 32 << 10
	stateAAD        = "wfgg-lastwar-state:v1"
)

var (
	txMu = sync.Mutex{}
	txs  = map[string]*authTransaction{}
)

var (
	errTransactionExpired   = errors.New("transaction expired")
	errTransactionCancelled = errors.New("transaction cancelled")
)

type authTransaction struct {
	id       string
	uid      string
	email    string
	expires  time.Time
	codeCh   chan string
	cancelCh chan struct{}
	sentCh   chan struct{}
	resultCh chan loginOutcome

	mu            sync.Mutex
	codeSubmitted bool
	sentOnce      sync.Once
	cancelOnce    sync.Once
}

type loginOutcome struct {
	result *auth.LoginResult
	err    error
}

type roleInfo struct {
	PlayerName string `json:"player_name,omitempty"`
	ServerID   string `json:"server_id,omitempty"`
}

type sealedState struct {
	Version    int       `json:"version"`
	LinkedUID  string    `json:"linked_uid"`
	PlayerName string    `json:"player_name,omitempty"`
	ServerID   string    `json:"server_id,omitempty"`
	DeviceID   string    `json:"device_id"`
	Username   string    `json:"username,omitempty"`
	GameUID    string    `json:"game_uid,omitempty"`
	LoginKey   string    `json:"login_key"`
	CreatedAt  time.Time `json:"created_at"`
}

type identityRequest struct {
	UserID string `json:"user_id"`
	UID    string `json:"uid"`
	Email  string `json:"email,omitempty"`
	Locale string `json:"locale,omitempty"`
}

type verifyRequest struct {
	UserID          string `json:"user_id"`
	UID             string `json:"uid"`
	Code            string `json:"code"`
	AuthTransaction string `json:"auth_transaction"`
	Locale          string `json:"locale,omitempty"`
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("/ping", ping)
	mux.HandleFunc("/v1/identity/resolve", internalOnly(resolveIdentity))
	mux.HandleFunc("/v1/identity/send-code", internalOnly(sendCode))
	mux.HandleFunc("/v1/identity/verify-code", internalOnly(verifyCode))
	mux.HandleFunc("/v1/profile/sync", internalOnly(syncSession))

	server := &http.Server{
		Addr:              listenAddr,
		Handler:           securityHeaders(mux),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       90 * time.Second,
		WriteTimeout:      90 * time.Second,
		IdleTimeout:       90 * time.Second,
	}
	log.Printf("wfgg-lastwar-broker listening on %s", listenAddr)
	log.Fatal(server.ListenAndServe())
}

func ping(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, 200, map[string]any{"ok": true, "service": "wfgg-lastwar-go-broker", "mode": "read-only"})
}

func internalOnly(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, 405, "METHOD_NOT_ALLOWED")
			return
		}
		if r.Header.Get("X-WfGg-Container-Auth") != "1" {
			writeError(w, 403, "FORBIDDEN")
			return
		}
		cleanupTransactions()
		next(w, r)
	}
}

func resolveIdentity(w http.ResponseWriter, r *http.Request) {
	var req identityRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, 400, "INVALID_JSON")
		return
	}
	uid := normalizeUID(req.UID)
	if uid == "" {
		writeError(w, 400, "LASTWAR_UID_INVALID")
		return
	}

	// If this user was linked previously, the Durable Object gives us only the sealed blob.
	// We can recognize the already-linked UID without exposing any reconnect secret.
	if sealed := strings.TrimSpace(r.Header.Get("X-WfGg-Sealed-State")); sealed != "" {
		if state, err := unsealState(sealed, stateSecret(r)); err == nil && state.LinkedUID == uid {
			writeJSON(w, 200, map[string]any{
				"uid":          uid,
				"contact_hint": nil,
				"player_name":  emptyToNil(state.PlayerName),
				"server_id":    emptyToNil(state.ServerID),
				"already_linked": true,
			})
			return
		}
	}

	// Public UID lookup is intentionally conservative here. Until an official Last War endpoint
	// is confirmed to return a masked bound contact, we never invent one.
	writeJSON(w, 200, map[string]any{
		"uid":          uid,
		"contact_hint": nil,
		"player_name":  nil,
		"server_id":    nil,
	})
}

func sendCode(w http.ResponseWriter, r *http.Request) {
	var req identityRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, 400, "INVALID_JSON")
		return
	}
	uid := normalizeUID(req.UID)
	email := normalizeEmail(req.Email)
	if uid == "" {
		writeError(w, 400, "LASTWAR_UID_INVALID")
		return
	}
	if email == "" {
		writeError(w, 400, "LASTWAR_EMAIL_REQUIRED")
		return
	}

	// New linking attempt must not accidentally reuse a previous account's remembered loginKey.
	resetIdentityState()
	cancelAllTransactions()

	tx := &authTransaction{
		id:       randomToken(24),
		uid:      uid,
		email:    email,
		expires:  time.Now().Add(transactionTTL),
		codeCh:   make(chan string, 1),
		cancelCh: make(chan struct{}),
		sentCh:   make(chan struct{}),
		resultCh: make(chan loginOutcome, 1),
	}
	storeTransaction(tx)

	go runEmailLogin(tx)

	select {
	case <-tx.sentCh:
		writeJSON(w, 200, map[string]any{
			"auth_transaction": tx.id,
			"contact_hint":     maskEmail(email),
			"expires_in":       int(time.Until(tx.expires).Seconds()),
		})
	case out := <-tx.resultCh:
		deleteTransaction(tx.id)
		writeLoginError(w, out.err, false)
	case <-time.After(sendCodeTimeout):
		tx.cancel()
		deleteTransaction(tx.id)
		writeError(w, 504, "LASTWAR_UPSTREAM_TIMEOUT")
	}
}

func verifyCode(w http.ResponseWriter, r *http.Request) {
	var req verifyRequest
	if err := readJSON(r, &req); err != nil {
		writeError(w, 400, "INVALID_JSON")
		return
	}
	uid := normalizeUID(req.UID)
	code := normalizeCode(req.Code)
	if uid == "" || code == "" || strings.TrimSpace(req.AuthTransaction) == "" {
		writeError(w, 400, "LASTWAR_VERIFY_CODE_INVALID")
		return
	}

	tx := getTransaction(req.AuthTransaction)
	if tx == nil || tx.uid != uid || time.Now().After(tx.expires) {
		writeError(w, 401, "LASTWAR_VERIFY_CODE_EXPIRED")
		return
	}
	if !tx.submitCode(code) {
		writeError(w, 409, "LASTWAR_VERIFY_CODE_ALREADY_SUBMITTED")
		return
	}

	select {
	case out := <-tx.resultCh:
		deleteTransaction(tx.id)
		if out.err != nil {
			writeLoginError(w, out.err, true)
			return
		}
		if out.result == nil || out.result.Account == nil {
			writeError(w, 502, "LASTWAR_ACCOUNT_DATA_MISSING")
			return
		}
		defer closeLoginResult(out.result)

		role, roleCount, matched := findRequestedRole(out.result.Account, uid)
		if !matched {
			// Email ownership alone is not enough: the requested public UID must actually occur in
			// the roles returned by Last War for the authenticated account.
			resetIdentityState()
			writeError(w, 409, "LASTWAR_UID_LINK_NOT_CONFIRMED")
			return
		}

		state, err := snapshotIdentityState(uid, role)
		if err != nil {
			writeError(w, 502, "LASTWAR_RECONNECT_STATE_MISSING")
			return
		}
		sealed, err := sealState(state, stateSecret(r))
		if err != nil {
			writeError(w, 500, "BROKER_STATE_ENCRYPTION_FAILED")
			return
		}

		writeJSON(w, 200, map[string]any{
			"uid":                    uid,
			"player_name":            emptyToNil(role.PlayerName),
			"server_id":              emptyToNil(role.ServerID),
			"role_count":              roleCount,
			"initial_sync_available": true,
			"_wfgg_sealed_state":      sealed,
		})
	case <-time.After(verifyTimeout):
		tx.cancel()
		deleteTransaction(tx.id)
		writeError(w, 504, "LASTWAR_UPSTREAM_TIMEOUT")
	}
}

func syncSession(w http.ResponseWriter, r *http.Request) {
	sealed := strings.TrimSpace(r.Header.Get("X-WfGg-Sealed-State"))
	if sealed == "" {
		writeError(w, 401, "LASTWAR_RECONNECT_STATE_REQUIRED")
		return
	}
	state, err := unsealState(sealed, stateSecret(r))
	if err != nil {
		writeError(w, 401, "LASTWAR_RECONNECT_STATE_INVALID")
		return
	}
	if err := restoreIdentityState(state); err != nil {
		writeError(w, 500, "LASTWAR_RECONNECT_STATE_RESTORE_FAILED")
		return
	}

	result, err := auth.Login(auth.LoginOptions{})
	if err != nil {
		writeLoginError(w, err, false)
		return
	}
	defer closeLoginResult(result)

	freshState, err := snapshotIdentityState(state.LinkedUID, roleInfo{PlayerName: state.PlayerName, ServerID: state.ServerID})
	if err != nil {
		writeError(w, 502, "LASTWAR_RECONNECT_STATE_MISSING")
		return
	}
	freshSealed, err := sealState(freshState, stateSecret(r))
	if err != nil {
		writeError(w, 500, "BROKER_STATE_ENCRYPTION_FAILED")
		return
	}

	// This endpoint intentionally proves only that the read-only session can be restored. Hero,
	// equipment, research and drone pulls will be added one-by-one to an explicit read allowlist.
	writeJSON(w, 200, map[string]any{
		"uid":                 state.LinkedUID,
		"session_valid":       true,
		"profile_sync_version": "session-only-v1",
		"_wfgg_sealed_state":  freshSealed,
	})
}

func runEmailLogin(tx *authTransaction) {
	result, err := auth.Login(auth.LoginOptions{
		Email: tx.email,
		OnVerificationCodeSent: func() {
			tx.sentOnce.Do(func() { close(tx.sentCh) })
		},
		VerificationCodeProvider: func() (string, error) {
			remaining := time.Until(tx.expires)
			if remaining <= 0 {
				return "", errTransactionExpired
			}
			timer := time.NewTimer(remaining)
			defer timer.Stop()
			select {
			case code := <-tx.codeCh:
				return code, nil
			case <-tx.cancelCh:
				return "", errTransactionCancelled
			case <-timer.C:
				return "", errTransactionExpired
			}
		},
	})
	tx.resultCh <- loginOutcome{result: result, err: err}
}

func findRequestedRole(account *sfs.SFSObject, requestedUID string) (roleInfo, int, bool) {
	if account == nil {
		return roleInfo{}, 0, false
	}

	roles := []*sfs.SFSObject{}
	if raw, ok := account.Get("accountArr"); ok {
		if arr, ok := raw.Val.(*sfs.SFSArray); ok && arr != nil {
			for _, item := range arr.Items() {
				if obj, ok := item.Val.(*sfs.SFSObject); ok && obj != nil {
					roles = append(roles, obj)
				}
			}
		}
	}
	roleCount := len(roles)
	if roleCount == 0 {
		roles = append(roles, account)
		roleCount = 1
	}

	for _, role := range roles {
		if objectContainsUID(role, requestedUID) {
			return roleMetadata(role, account), roleCount, true
		}
	}
	// Some response variants carry the selected role's UID at top level while accountArr carries
	// only server-routing fields. Accept that only when the top-level UID itself matches exactly.
	if objectContainsUID(account, requestedUID) {
		return roleMetadata(account, account), roleCount, true
	}
	return roleInfo{}, roleCount, false
}

func objectContainsUID(obj *sfs.SFSObject, requestedUID string) bool {
	for _, key := range obj.Keys() {
		normalizedKey := strings.ToLower(strings.NewReplacer("_", "", "-", "").Replace(key))
		if !(normalizedKey == "uid" || strings.HasSuffix(normalizedKey, "uid") || normalizedKey == "playerid" || normalizedKey == "roleid" || normalizedKey == "characterid") {
			continue
		}
		value, ok := obj.Get(key)
		if !ok {
			continue
		}
		if digitsOnly(scalarString(value.Val)) == requestedUID {
			return true
		}
	}
	return false
}

func roleMetadata(role, account *sfs.SFSObject) roleInfo {
	player := firstString(role, "playerName", "gameUserName", "roleName", "nickname", "nickName", "name")
	if player == "" {
		player = firstString(account, "playerName", "gameUserName", "roleName", "nickname", "nickName", "name")
	}
	server := firstString(role, "serverId", "server_id", "zone", "server")
	if server == "" {
		server = firstString(account, "serverId", "server_id", "zone", "server")
	}
	if strings.HasPrefix(strings.ToUpper(server), "APS") {
		server = digitsOnly(server)
	}
	return roleInfo{PlayerName: player, ServerID: server}
}

func firstString(obj *sfs.SFSObject, keys ...string) string {
	if obj == nil {
		return ""
	}
	for _, key := range keys {
		if v, ok := obj.Get(key); ok {
			if s := strings.TrimSpace(scalarString(v.Val)); s != "" {
				return s
			}
		}
	}
	return ""
}

func scalarString(value any) string {
	switch v := value.(type) {
	case string:
		return v
	case int64:
		return fmt.Sprintf("%d", v)
	case int32:
		return fmt.Sprintf("%d", v)
	case int16:
		return fmt.Sprintf("%d", v)
	case byte:
		return fmt.Sprintf("%d", v)
	default:
		return ""
	}
}

func snapshotIdentityState(linkedUID string, role roleInfo) (sealedState, error) {
	deviceID, err := readStateFile(".lastwar_goclient_device_id")
	if err != nil || deviceID == "" {
		return sealedState{}, fmt.Errorf("device identity missing")
	}
	loginKey, err := readStateFile(".lastwar_goclient_loginkey")
	if err != nil || loginKey == "" {
		return sealedState{}, fmt.Errorf("login key missing")
	}
	username, _ := readStateFile(".lastwar_goclient_username")
	gameUID, _ := readStateFile(".lastwar_goclient_gameuid")
	return sealedState{
		Version:    1,
		LinkedUID:  linkedUID,
		PlayerName: role.PlayerName,
		ServerID:   role.ServerID,
		DeviceID:   deviceID,
		Username:   username,
		GameUID:    gameUID,
		LoginKey:   loginKey,
		CreatedAt:  time.Now().UTC(),
	}, nil
}

func restoreIdentityState(state sealedState) error {
	if state.Version != 1 || state.DeviceID == "" || state.LoginKey == "" || normalizeUID(state.LinkedUID) == "" {
		return fmt.Errorf("invalid sealed state")
	}
	pairs := map[string]string{
		".lastwar_goclient_device_id": state.DeviceID,
		".lastwar_goclient_username":  state.Username,
		".lastwar_goclient_gameuid":   state.GameUID,
		".lastwar_goclient_loginkey":  state.LoginKey,
	}
	for name, value := range pairs {
		if value == "" && name != ".lastwar_goclient_username" && name != ".lastwar_goclient_gameuid" {
			return fmt.Errorf("required state missing")
		}
		if err := os.WriteFile(auth.StateFilePath(name), []byte(value), 0o600); err != nil {
			return err
		}
	}
	return nil
}

func resetIdentityState() {
	for _, name := range []string{
		".lastwar_goclient_device_id",
		".lastwar_goclient_username",
		".lastwar_goclient_gameuid",
		".lastwar_goclient_loginkey",
	} {
		_ = os.Remove(auth.StateFilePath(name))
	}
}

func readStateFile(name string) (string, error) {
	data, err := os.ReadFile(auth.StateFilePath(name))
	if err != nil {
		return "", err
	}
	return strings.TrimSpace(string(data)), nil
}

func stateSecret(r *http.Request) string {
	if r != nil {
		if secret := strings.TrimSpace(r.Header.Get("X-WfGg-State-Key")); len(secret) >= 16 {
			return secret
		}
	}
	return os.Getenv("WFGG_STATE_KEY")
}

func sealState(state sealedState, secret string) (string, error) {
	if len(secret) < 16 {
		return "", fmt.Errorf("state key missing or too short")
	}
	plain, err := json.Marshal(state)
	if err != nil {
		return "", err
	}
	key := sha256.Sum256([]byte(secret))
	block, err := aes.NewCipher(key[:])
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}
	ciphertext := gcm.Seal(nil, nonce, plain, []byte(stateAAD))
	payload := append(nonce, ciphertext...)
	return "wfgs1." + base64.RawURLEncoding.EncodeToString(payload), nil
}

func unsealState(sealed string, secret string) (sealedState, error) {
	var state sealedState
	if len(secret) < 16 || !strings.HasPrefix(sealed, "wfgs1.") {
		return state, fmt.Errorf("invalid sealed state")
	}
	payload, err := base64.RawURLEncoding.DecodeString(strings.TrimPrefix(sealed, "wfgs1."))
	if err != nil {
		return state, err
	}
	key := sha256.Sum256([]byte(secret))
	block, err := aes.NewCipher(key[:])
	if err != nil {
		return state, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return state, err
	}
	if len(payload) <= gcm.NonceSize() {
		return state, fmt.Errorf("sealed state too short")
	}
	nonce, ciphertext := payload[:gcm.NonceSize()], payload[gcm.NonceSize():]
	plain, err := gcm.Open(nil, nonce, ciphertext, []byte(stateAAD))
	if err != nil {
		return state, err
	}
	if err := json.Unmarshal(plain, &state); err != nil {
		return state, err
	}
	return state, nil
}

func writeLoginError(w http.ResponseWriter, err error, afterCode bool) {
	if err == nil {
		writeError(w, 502, "LASTWAR_UPSTREAM_ERROR")
		return
	}
	if errors.Is(err, errTransactionExpired) || errors.Is(err, errTransactionCancelled) {
		writeError(w, 401, "LASTWAR_VERIFY_CODE_EXPIRED")
		return
	}
	if errors.Is(err, session.ErrAuthRejected) {
		if afterCode {
			writeError(w, 401, "LASTWAR_VERIFY_CODE_INVALID")
		} else {
			writeError(w, 401, "LASTWAR_EMAIL_MISMATCH")
		}
		return
	}
	writeError(w, 503, "LASTWAR_UPSTREAM_UNAVAILABLE")
}

func closeLoginResult(result *auth.LoginResult) {
	if result != nil && result.Conn != nil {
		_ = result.Conn.Close()
	}
}

func (tx *authTransaction) submitCode(code string) bool {
	tx.mu.Lock()
	defer tx.mu.Unlock()
	if tx.codeSubmitted {
		return false
	}
	tx.codeSubmitted = true
	tx.codeCh <- code
	return true
}

func (tx *authTransaction) cancel() {
	tx.cancelOnce.Do(func() { close(tx.cancelCh) })
}

func storeTransaction(tx *authTransaction) {
	txMu.Lock()
	defer txMu.Unlock()
	txs[tx.id] = tx
}

func getTransaction(id string) *authTransaction {
	txMu.Lock()
	defer txMu.Unlock()
	return txs[strings.TrimSpace(id)]
}

func deleteTransaction(id string) {
	txMu.Lock()
	defer txMu.Unlock()
	delete(txs, id)
}

func cleanupTransactions() {
	now := time.Now()
	txMu.Lock()
	defer txMu.Unlock()
	for id, tx := range txs {
		if now.After(tx.expires) {
			tx.cancel()
			delete(txs, id)
		}
	}
}

func cancelAllTransactions() {
	txMu.Lock()
	defer txMu.Unlock()
	for id, tx := range txs {
		tx.cancel()
		delete(txs, id)
	}
}

func randomToken(n int) string {
	buf := make([]byte, n)
	if _, err := io.ReadFull(rand.Reader, buf); err != nil {
		panic(err)
	}
	return base64.RawURLEncoding.EncodeToString(buf)
}

func normalizeUID(value string) string {
	value = digitsOnly(value)
	if len(value) < 8 || len(value) > 24 {
		return ""
	}
	return value
}

func normalizeCode(value string) string {
	value = digitsOnly(value)
	if len(value) != 6 {
		return ""
	}
	return value
}

func digitsOnly(value string) string {
	var b strings.Builder
	for _, r := range value {
		if r >= '0' && r <= '9' {
			b.WriteRune(r)
		}
	}
	return b.String()
}

func normalizeEmail(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if len(value) < 3 || len(value) > 254 || strings.Count(value, "@") != 1 {
		return ""
	}
	parts := strings.SplitN(value, "@", 2)
	if parts[0] == "" || !strings.Contains(parts[1], ".") || strings.ContainsAny(value, " \t\r\n") {
		return ""
	}
	return value
}

func maskEmail(email string) string {
	parts := strings.SplitN(email, "@", 2)
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return "***"
	}
	local := string([]rune(parts[0])[0]) + "***"
	domainParts := strings.Split(parts[1], ".")
	domain := "***"
	if len(domainParts) > 0 && domainParts[0] != "" {
		domain = string([]rune(domainParts[0])[0]) + "***"
	}
	if len(domainParts) > 1 {
		domain += "." + domainParts[len(domainParts)-1]
	}
	return local + "@" + domain
}

func readJSON(r *http.Request, dst any) error {
	defer r.Body.Close()
	dec := json.NewDecoder(io.LimitReader(r.Body, maxRequestBytes+1))
	return dec.Decode(dst)
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(w, r)
	})
}

func writeError(w http.ResponseWriter, status int, code string) {
	writeJSON(w, status, map[string]any{"error": code})
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func emptyToNil(s string) any {
	if strings.TrimSpace(s) == "" {
		return nil
	}
	return s
}
