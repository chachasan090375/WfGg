package authsig

import (
    "crypto/hmac"
    "crypto/sha256"
    "encoding/hex"
    "errors"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "strings"
    "sync"
    "time"
)

const maxBody = 1 << 20

type ReplayGuard struct {
    mu sync.Mutex
    seen map[string]time.Time
    TTL time.Duration
}

func NewReplayGuard(ttl time.Duration) *ReplayGuard {
    return &ReplayGuard{seen: map[string]time.Time{}, TTL: ttl}
}

func (g *ReplayGuard) Use(nonce string, now time.Time) bool {
    g.mu.Lock()
    defer g.mu.Unlock()
    for k, t := range g.seen {
        if now.Sub(t) > g.TTL { delete(g.seen, k) }
    }
    if _, exists := g.seen[nonce]; exists { return false }
    g.seen[nonce] = now
    return true
}

func Signature(method, path, timestamp, nonce string, body []byte, secret string) string {
    bodyHash := sha256.Sum256(body)
    canonical := strings.ToUpper(method) + "\n" + path + "\n" + timestamp + "\n" + nonce + "\n" + hex.EncodeToString(bodyHash[:])
    mac := hmac.New(sha256.New, []byte(secret))
    _, _ = mac.Write([]byte(canonical))
    return hex.EncodeToString(mac.Sum(nil))
}

func VerifyRequest(r *http.Request, secret string, guard *ReplayGuard, now time.Time) ([]byte, error) {
    if len(secret) < 32 { return nil, errors.New("shared key missing or weak") }
    tsRaw := r.Header.Get("X-Radar-Timestamp")
    nonce := r.Header.Get("X-Radar-Nonce")
    supplied := r.Header.Get("X-Radar-Signature")
    if tsRaw == "" || nonce == "" || supplied == "" { return nil, errors.New("signature headers missing") }
    ts, err := strconv.ParseInt(tsRaw, 10, 64)
    if err != nil { return nil, errors.New("invalid timestamp") }
    delta := now.Sub(time.Unix(ts, 0))
    if delta < -60*time.Second || delta > 60*time.Second { return nil, errors.New("timestamp outside allowed window") }
    if len(nonce) < 16 || len(nonce) > 128 { return nil, errors.New("invalid nonce") }
    body, err := io.ReadAll(io.LimitReader(r.Body, maxBody+1))
    if err != nil { return nil, err }
    if len(body) > maxBody { return nil, fmt.Errorf("body too large") }
    expected := Signature(r.Method, r.URL.Path, tsRaw, nonce, body, secret)
    suppliedBytes, e1 := hex.DecodeString(supplied)
    expectedBytes, e2 := hex.DecodeString(expected)
    if e1 != nil || e2 != nil || !hmac.Equal(suppliedBytes, expectedBytes) { return nil, errors.New("invalid signature") }
    if guard != nil && !guard.Use(nonce, now) { return nil, errors.New("replayed nonce") }
    return body, nil
}
