#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 5
# Local read-only validation using the successful native Login captured in the
# user's PCAP as a field template. No credential is printed or uploaded.
#
# The helper regenerates only fields that are expected to change per login
# (_id/cmdBaseTime/SecurityCode/OneCode/CoreV/psh). Every other Login parameter,
# including fields the generic upstream client does not know how to reproduce,
# is copied locally from the user's own native capture. It then opens one game
# socket, sends exactly one Login request, and only reads the response/init push.
# No gameplay command and no -collect action is used.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
LAB_HOME="${BASE}/home"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
SESSION="${LAB_HOME}/.lastwar_goclient_session.json"
OUT_PRIVATE="${BASE}/WFGG_LASTWAR_PHASE5_NATIVE_TEMPLATE_REDACTED.txt"
OUT_SHARE="${DOWNLOADS}/WFGG_LASTWAR_PHASE5_NATIVE_TEMPLATE_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-native-template-login"
HELPER="${BASE}/wfgg-native-template-login"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source du probe absente; exécute d'abord la phase 1"
[[ -s "$SESSION" ]] || die "session PCAP privée absente; exécute d'abord la phase 3"
[[ -d "$DOWNLOADS" ]] || die "accès stockage Android absent; exécute termux-setup-storage"

CAPTURE="${1:-}"
if [[ -z "$CAPTURE" ]]; then
  CANDIDATES="$({
    for root in \
      "$DOWNLOADS" \
      "$SHARED/Download" \
      "$SHARED/Documents" \
      "$SHARED/PCAPdroid" \
      "$ANDROID_SHARED/Download" \
      "$ANDROID_SHARED/Documents"; do
      [[ -e "$root" ]] || continue
      find -L "$root" -maxdepth 6 -type f \
        \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) \
        -printf '%T@ %p\n' 2>/dev/null || true
    done
  } | sort -nr)"
  if [[ -z "$CANDIDATES" && -e "$SHARED" ]]; then
    CANDIDATES="$(find -L "$SHARED" -type f \
      \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) \
      -printf '%T@ %p\n' 2>/dev/null | sort -nr || true)"
  fi
  CAPTURE="$(printf '%s\n' "$CANDIDATES" | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 5 ==="
say "Mode: native-template / lecture seule / local-only"
say "Capture: $CAPTURE"
say "Aucune valeur sensible ne sera affichée."

mkdir -p "$TMP_CMD"
cleanup_tmp() { rm -rf "$TMP_CMD" 2>/dev/null || true; }
trap cleanup_tmp EXIT INT TERM

cat > "$TMP_CMD/main.go" <<'GOEOF'
package main

import (
    "bytes"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "lastwar-client/internal/auth"
    "lastwar-client/internal/pcap"
    "lastwar-client/internal/sfs"
    "net"
    "net/netip"
    "os"
    "strings"
    "time"
)

type sessionConfig struct {
    IP          string `json:"ip"`
    Port        int    `json:"port"`
    Zone        string `json:"zone"`
    GameUid     string `json:"gameUid"`
    DeviceID    string `json:"deviceId"`
    ShumeiBoxId string `json:"shumeiBoxId"`
    AccessToken string `json:"accessToken"`
    IOSMode     bool   `json:"iosMode"`
}

var dynamicKeys = map[string]bool{
    "_id": true,
    "cmdBaseTime": true,
    "SecurityCode": true,
    "OneCode": true,
    "CoreV": true,
    "psh": true,
}

func main() {
    if len(os.Args) != 3 {
        fmt.Fprintln(os.Stderr, "usage: wfgg-native-template-login <capture> <session-config>")
        os.Exit(2)
    }
    capturePath, sessionPath := os.Args[1], os.Args[2]

    var cfg sessionConfig
    sb, err := os.ReadFile(sessionPath)
    if err != nil { fatal(err) }
    if err := json.Unmarshal(sb, &cfg); err != nil { fatal(err) }

    data, err := os.ReadFile(capturePath)
    if err != nil { fatal(err) }
    packets, err := pcap.Parse(data)
    if err != nil { fatal(err) }
    convs := pcap.Conversations(packets)

    var nativeRoot, nativeLogin, nativeParams *sfs.SFSObject
    var server pcap.Endpoint
    var found bool

    for _, conv := range convs {
        if conv.TLS { continue }
        client, err := conv.Client(netip.Addr{})
        if err != nil { continue }
        c2s, _ := conv.Reassemble(client)
        r := bytes.NewReader(c2s)
        for {
            body, err := sfs.ReadPacket(r)
            if err != nil {
                if errors.Is(err, io.EOF) { break }
                break
            }
            root, err := sfs.DecodeObject(body)
            if err != nil { continue }
            if root.GetInt("c") != 0 || root.GetInt("a") != 1 { continue }
            pv, ok := root.Get("p")
            if !ok { continue }
            login, ok := pv.Val.(*sfs.SFSObject)
            if !ok || login == nil { continue }
            ppv, ok := login.Get("p")
            if !ok { continue }
            params, ok := ppv.Val.(*sfs.SFSObject)
            if !ok || params == nil { continue }
            pkg := params.GetString("packageName")
            if pkg != "com.fun.lastwar.gp" && pkg != "com.lastwar.ios" { continue }
            if login.GetString("zn") != cfg.Zone { continue }

            nativeRoot, nativeLogin, nativeParams = root, login, params
            server = conv.A
            if server.Addr == client { server = conv.B }
            found = true
            break
        }
        if found { break }
    }
    if !found { fatal(fmt.Errorf("aucun Login natif compatible trouvé")) }

    serverID := strings.TrimPrefix(cfg.Zone, "APS")
    generated := auth.BuildLoginParams(auth.LoginParamsInput{
        FutureID: 1,
        DeviceID: cfg.DeviceID,
        AirKey: "lwDid_" + base64Std(cfg.DeviceID),
        GameUid: cfg.GameUid,
        AccessTok: cfg.AccessToken,
        ServerID: serverID,
        ShumeiBoxId: cfg.ShumeiBoxId,
        IOSMode: cfg.IOSMode,
    })

    finalParams := sfs.NewSFSObject()
    copiedNative := 0
    freshDynamic := 0
    for _, key := range nativeParams.Keys() {
        nv, _ := nativeParams.Get(key)
        if dynamicKeys[key] {
            if gv, ok := generated.Get(key); ok {
                finalParams.PutValue(key, gv)
                freshDynamic++
                continue
            }
        }
        finalParams.PutValue(key, nv)
        copiedNative++
    }

    finalLogin := sfs.NewSFSObject()
    for _, key := range nativeLogin.Keys() {
        if key == "p" {
            finalLogin.PutSFSObject("p", finalParams)
            continue
        }
        v, _ := nativeLogin.Get(key)
        finalLogin.PutValue(key, v)
    }

    finalRoot := sfs.NewSFSObject()
    for _, key := range nativeRoot.Keys() {
        if key == "p" {
            finalRoot.PutSFSObject("p", finalLogin)
            continue
        }
        v, _ := nativeRoot.Get(key)
        finalRoot.PutValue(key, v)
    }

    body, err := sfs.EncodeObject(finalRoot)
    if err != nil { fatal(err) }
    frame, err := sfs.EncodePacket(body)
    if err != nil { fatal(err) }

    fmt.Printf("NATIVE_FIELDS=%d COPIED_NATIVE=%d FRESH_DYNAMIC=%d\n", len(nativeParams.Keys()), copiedNative, freshDynamic)
    fmt.Printf("TARGET_ZONE=%s TARGET_PORT=%d\n", cfg.Zone, server.Port)

    conn, err := net.DialTimeout("tcp", server.String(), 10*time.Second)
    if err != nil { fatal(fmt.Errorf("dial: %w", err)) }
    defer conn.Close()
    _ = conn.SetDeadline(time.Now().Add(20 * time.Second))

    if _, err := conn.Write(frame); err != nil { fatal(fmt.Errorf("write login: %w", err)) }

    loginOK := false
    for i := 0; i < 200; i++ {
        rb, err := sfs.ReadPacket(conn)
        if err != nil {
            if ne, ok := err.(net.Error); ok && ne.Timeout() { break }
            fatal(fmt.Errorf("read: %w", err))
        }
        obj, err := sfs.DecodeObject(rb)
        if err != nil { continue }

        if obj.GetInt("c") == 0 && obj.GetInt("a") == 1 {
            pv, _ := obj.Get("p")
            p, _ := pv.Val.(*sfs.SFSObject)
            if p == nil {
                fmt.Println("LOGIN_RESPONSE=INVALID")
                os.Exit(3)
            }
            if ec, ok := p.Get("ec"); ok {
                fmt.Printf("LOGIN_RESPONSE=REJECTED EC=%v\n", scalarNumber(ec.Val))
                os.Exit(2)
            }
            fmt.Println("LOGIN_RESPONSE=OK")
            loginOK = true
            continue
        }

        if loginOK && obj.GetInt("c") == 1 {
            pv, ok := obj.Get("p")
            if !ok { continue }
            ext, ok := pv.Val.(*sfs.SFSObject)
            if !ok || ext == nil || ext.GetString("c") != "init" { continue }
            ppv, ok := ext.Get("p")
            if !ok { continue }
            initObj, ok := ppv.Val.(*sfs.SFSObject)
            if !ok || initObj == nil { continue }
            fmt.Printf("INIT_RECEIVED=yes TOP_FIELDS=%d HEROES=%d BUILDINGS=%d SCIENCE=%d\n",
                len(initObj.Keys()), arrayLen(initObj, "userHero"), arrayLen(initObj, "building_new"), arrayLen(initObj, "science_new"))
            return
        }
    }

    if loginOK {
        fmt.Println("INIT_RECEIVED=no_within_timeout")
        return
    }
    fmt.Println("LOGIN_RESPONSE=NO_RESPONSE")
    os.Exit(4)
}

func base64Std(s string) string {
    const table = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    b := []byte(s)
    out := make([]byte, 0, (len(b)+2)/3*4)
    for i := 0; i < len(b); i += 3 {
        var n uint32 = uint32(b[i]) << 16
        rem := len(b)-i
        if rem > 1 { n |= uint32(b[i+1]) << 8 }
        if rem > 2 { n |= uint32(b[i+2]) }
        out = append(out, table[(n>>18)&63], table[(n>>12)&63])
        if rem > 1 { out = append(out, table[(n>>6)&63]) } else { out = append(out, '=') }
        if rem > 2 { out = append(out, table[n&63]) } else { out = append(out, '=') }
    }
    return string(out)
}

func arrayLen(o *sfs.SFSObject, key string) int {
    v, ok := o.Get(key)
    if !ok { return 0 }
    if a, ok := v.Val.(*sfs.SFSArray); ok && a != nil { return len(a.Items()) }
    return 0
}

func scalarNumber(v any) any {
    switch n := v.(type) {
    case byte: return int(n)
    case int16: return int(n)
    case int32: return int(n)
    case int64: return n
    default: return "present"
    }
}

func fatal(err error) {
    fmt.Fprintln(os.Stderr, "phase5:", err)
    os.Exit(1)
}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-native-template-login
chmod 700 "$HELPER"

set +e
"$HELPER" "$CAPTURE" "$SESSION" > "$OUT_PRIVATE" 2>&1
RC=$?
set -e
chmod 600 "$OUT_PRIVATE" 2>/dev/null || true

cp -f "$OUT_PRIVATE" "$OUT_SHARE"
chmod 600 "$OUT_SHARE" 2>/dev/null || true

say "=== PHASE 5 TERMINEE ==="
say "EXIT=$RC"
say "Rapport expurgé: Téléchargements/WFGG_LASTWAR_PHASE5_NATIVE_TEMPLATE_REDACTED.txt"
say
cat "$OUT_PRIVATE"

exit "$RC"
