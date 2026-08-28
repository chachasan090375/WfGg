#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 4
# Local-only comparison of the native Login request captured by PCAPdroid
# against the Login request the pinned Go client would build from the same
# local session config. NO network connection is opened by this script.
#
# The report is safe to share: credential/device values are never printed.
# For sensitive/opaque fields we report only field name, type, length and
# MATCH/DIFF. A small whitelist of non-sensitive protocol constants may show
# their values to make version/platform/config mismatches immediately visible.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
LAB_HOME="${BASE}/home"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
SESSION="${LAB_HOME}/.lastwar_goclient_session.json"
OUT_PRIVATE="${BASE}/WFGG_LASTWAR_PHASE4_LOGIN_DIFF_REDACTED.txt"
OUT_SHARE="${DOWNLOADS}/WFGG_LASTWAR_PHASE4_LOGIN_DIFF_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-login-diff"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source du probe absente; exécute d'abord la phase 1"
[[ -s "$SESSION" ]] || die "session locale absente; exécute d'abord la phase 3"
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

say "=== WfGg Last War LAB · PHASE 4 ==="
say "Comparaison locale du Login natif et du Login généré."
say "Aucune connexion au serveur Last War ne sera ouverte."
say "Capture: $CAPTURE"

mkdir -p "$TMP_CMD"
cleanup_tmp() { rm -rf "$TMP_CMD" 2>/dev/null || true; }
trap cleanup_tmp EXIT INT TERM

cat > "$TMP_CMD/main.go" <<'GOEOF'
package main

import (
    "bytes"
    "encoding/base64"
    "encoding/json"
    "errors"
    "fmt"
    "io"
    "lastwar-client/internal/auth"
    "lastwar-client/internal/pcap"
    "lastwar-client/internal/sfs"
    "net/netip"
    "os"
    "reflect"
    "sort"
    "strings"
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

type nativeLogin struct {
    Outer  *sfs.SFSObject
    Params *sfs.SFSObject
}

var safeValueKeys = map[string]bool{
    "packageName": true,
    "platform": true,
    "pf": true,
    "appVersion": true,
    "versionCode": true,
    "serverId": true,
    "resVersion": true,
    "lang": true,
    "KCPMode": true,
    "gmLogin": true,
    "configNumber": true,
    "forbidden_froce_merge": true,
    "useZstd": true,
    "netType": true,
    "isSimulator": true,
    "is3D": true,
    "google_available": true,
    "lat": true,
}

var expectedDynamicKeys = map[string]bool{
    "_id": true,
    "cmdBaseTime": true,
    "SecurityCode": true,
    "OneCode": true,
    "CoreV": true,
    "psh": true,
}

var opaqueIdentityKeys = map[string]bool{
    "ta": true,
    "distinct_id": true,
    "mt": true,
    "device_string": true,
    "phone_model": true,
    "osVersion": true,
    "country": true,
    "suggestCountry": true,
    "fromCountry": true,
    "timeoffset": true,
    "gcmRegisterId": true,
    "referrer": true,
    "firebaseId": true,
    "afuid": true,
    "gaid": true,
    "AndroidID": true,
    "androidDid": true,
    "IMEI": true,
    "googleName": true,
    "googlePlay": true,
    "deeplinkParams": true,
    "pfId": true,
    "parseRegisterId": true,
    "idfa": true,
    "idfv": true,
}

func main() {
    if len(os.Args) != 4 {
        fmt.Fprintln(os.Stderr, "usage: wfgg-login-diff <capture> <session.json> <report>")
        os.Exit(2)
    }
    capturePath, sessionPath, reportPath := os.Args[1], os.Args[2], os.Args[3]

    var cfg sessionConfig
    cfgBytes, err := os.ReadFile(sessionPath)
    if err != nil { fatal(err) }
    if err := json.Unmarshal(cfgBytes, &cfg); err != nil { fatal(err) }

    native, err := findNativeLogin(capturePath)
    if err != nil { fatal(err) }

    airKey := "lwDid_" + base64.StdEncoding.EncodeToString([]byte(cfg.DeviceID))
    serverID := strings.TrimPrefix(cfg.Zone, "APS")
    generated := auth.BuildLoginParams(auth.LoginParamsInput{
        FutureID: native.Params.GetInt("_id"),
        DeviceID: cfg.DeviceID,
        AirKey: airKey,
        GameUid: cfg.GameUid,
        AccessTok: cfg.AccessToken,
        ServerID: serverID,
        ShumeiBoxId: cfg.ShumeiBoxId,
        IOSMode: cfg.IOSMode,
    })

    var out strings.Builder
    out.WriteString("WfGg Last War LAB — PHASE 4 LOGIN DIFF\n")
    out.WriteString("Mode: local-only / no network / values sensibles masquées\n\n")

    out.WriteString("=== OUTER LOGIN ===\n")
    compareOuter(&out, "zn", native.Outer.GetString("zn"), cfg.Zone, false)
    compareOuter(&out, "un", native.Outer.GetString("un"), cfg.GameUid, true)
    compareOuter(&out, "pw", native.Outer.GetString("pw"), "", true)
    out.WriteString("\n")

    nativeKeys := native.Params.Keys()
    generatedKeys := generated.Keys()
    nativeSet := make(map[string]bool, len(nativeKeys))
    generatedSet := make(map[string]bool, len(generatedKeys))
    for _, k := range nativeKeys { nativeSet[k] = true }
    for _, k := range generatedKeys { generatedSet[k] = true }

    missing := difference(nativeSet, generatedSet)
    extra := difference(generatedSet, nativeSet)

    var stableDiff, maskedDiff, dynamicDiff, matches []string
    common := make([]string, 0)
    for k := range nativeSet {
        if generatedSet[k] { common = append(common, k) }
    }
    sort.Strings(common)

    for _, k := range common {
        nv, _ := native.Params.Get(k)
        gv, _ := generated.Get(k)
        same := reflect.DeepEqual(nv.Val, gv.Val) && nv.Type == gv.Type
        if same {
            matches = append(matches, k)
            continue
        }
        if expectedDynamicKeys[k] {
            dynamicDiff = append(dynamicDiff, fmt.Sprintf("%s: DIFF attendu/dynamique (%s -> %s)", k, descriptor(nv), descriptor(gv)))
            continue
        }
        if safeValueKeys[k] {
            stableDiff = append(stableDiff, fmt.Sprintf("%s: native=%s | généré=%s", k, safeScalar(nv), safeScalar(gv)))
            continue
        }
        maskedDiff = append(maskedDiff, fmt.Sprintf("%s: DIFF masqué | native=%s | généré=%s", k, descriptor(nv), descriptor(gv)))
    }

    out.WriteString("=== RESUME ===\n")
    fmt.Fprintf(&out, "Champs natifs: %d\n", len(nativeKeys))
    fmt.Fprintf(&out, "Champs générés: %d\n", len(generatedKeys))
    fmt.Fprintf(&out, "Champs identiques: %d\n", len(matches))
    fmt.Fprintf(&out, "Différences stables/non sensibles: %d\n", len(stableDiff))
    fmt.Fprintf(&out, "Différences masquées/identité: %d\n", len(maskedDiff))
    fmt.Fprintf(&out, "Différences dynamiques attendues: %d\n", len(dynamicDiff))
    fmt.Fprintf(&out, "Absents du client généré: %d\n", len(missing))
    fmt.Fprintf(&out, "Supplémentaires dans le client généré: %d\n\n", len(extra))

    section(&out, "CHAMPS NATIFS ABSENTS DU LOGIN GENERE", missing)
    section(&out, "CHAMPS SUPPLEMENTAIRES DU LOGIN GENERE", extra)
    section(&out, "DIFFERENCES STABLES / VALEURS NON SENSIBLES", stableDiff)
    section(&out, "DIFFERENCES IDENTITE / VALEURS MASQUEES", maskedDiff)
    section(&out, "DIFFERENCES DYNAMIQUES ATTENDUES", dynamicDiff)

    if len(stableDiff) == 0 && len(missing) == 0 && len(extra) == 0 && len(maskedDiff) == 0 {
        out.WriteString("Aucune différence stable détectée hors champs dynamiques.\n")
    }

    if err := os.WriteFile(reportPath, []byte(out.String()), 0600); err != nil { fatal(err) }
    fmt.Println("PHASE4_OK")
}

func findNativeLogin(path string) (*nativeLogin, error) {
    data, err := os.ReadFile(path)
    if err != nil { return nil, err }
    packets, err := pcap.Parse(data)
    if err != nil { return nil, err }
    for _, conv := range pcap.Conversations(packets) {
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
            obj, err := sfs.DecodeObject(body)
            if err != nil { continue }
            if obj.GetInt("c") != 0 || obj.GetInt("a") != 1 { continue }
            pv, ok := obj.Get("p")
            if !ok { continue }
            outer, ok := pv.Val.(*sfs.SFSObject)
            if !ok || outer == nil { continue }
            ppv, ok := outer.Get("p")
            if !ok { continue }
            params, ok := ppv.Val.(*sfs.SFSObject)
            if !ok || params == nil { continue }
            pkg := params.GetString("packageName")
            if pkg == "com.fun.lastwar.gp" || pkg == "com.lastwar.ios" {
                return &nativeLogin{Outer: outer, Params: params}, nil
            }
        }
    }
    return nil, fmt.Errorf("aucun Login natif Last War trouvé")
}

func difference(a, b map[string]bool) []string {
    out := make([]string, 0)
    for k := range a {
        if !b[k] { out = append(out, k) }
    }
    sort.Strings(out)
    return out
}

func section(out *strings.Builder, title string, lines []string) {
    out.WriteString("=== " + title + " ===\n")
    if len(lines) == 0 {
        out.WriteString("(aucun)\n\n")
        return
    }
    for _, line := range lines { out.WriteString(line + "\n") }
    out.WriteString("\n")
}

func compareOuter(out *strings.Builder, key, native, generated string, masked bool) {
    status := "MATCH"
    if native != generated { status = "DIFF" }
    if masked {
        fmt.Fprintf(out, "%s: %s (valeurs masquées, longueurs %d/%d)\n", key, status, len(native), len(generated))
    } else {
        fmt.Fprintf(out, "%s: %s native=%q généré=%q\n", key, status, native, generated)
    }
}

func descriptor(v sfs.SFSValue) string {
    switch x := v.Val.(type) {
    case string:
        return fmt.Sprintf("type=%d string_len=%d", v.Type, len(x))
    case *sfs.SFSObject:
        if x == nil { return fmt.Sprintf("type=%d object=nil", v.Type) }
        return fmt.Sprintf("type=%d object_fields=%d", v.Type, len(x.Keys()))
    case *sfs.SFSArray:
        if x == nil { return fmt.Sprintf("type=%d array=nil", v.Type) }
        return fmt.Sprintf("type=%d array_items=%d", v.Type, len(x.Items()))
    case []byte:
        return fmt.Sprintf("type=%d bytes_len=%d", v.Type, len(x))
    case []string:
        return fmt.Sprintf("type=%d strings_len=%d", v.Type, len(x))
    default:
        return fmt.Sprintf("type=%d go=%T", v.Type, v.Val)
    }
}

func safeScalar(v sfs.SFSValue) string {
    switch x := v.Val.(type) {
    case string:
        return fmt.Sprintf("%q", x)
    case bool, byte, int16, int32, int64, float32, float64:
        return fmt.Sprintf("%v", x)
    default:
        return descriptor(v)
    }
}

func fatal(err error) {
    fmt.Fprintln(os.Stderr, "phase4:", err)
    os.Exit(1)
}

var _ = sfs.IsSensitiveSFSKey
var _ = opaqueIdentityKeys
GOEOF

cd "$SRC"
DIFF_BIN="${BASE}/wfgg-login-diff"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$DIFF_BIN" ./cmd/wfgg-login-diff
chmod 700 "$DIFF_BIN"

rm -f "$OUT_PRIVATE" "$OUT_SHARE"
"$DIFF_BIN" "$CAPTURE" "$SESSION" "$OUT_PRIVATE"
chmod 600 "$OUT_PRIVATE" 2>/dev/null || true
cp -f "$OUT_PRIVATE" "$OUT_SHARE"
chmod 600 "$OUT_SHARE" 2>/dev/null || true

say
say "=== PHASE 4 TERMINEE ==="
say "Aucune connexion réseau effectuée."
say "Rapport expurgé: Téléchargements/WFGG_LASTWAR_PHASE4_LOGIN_DIFF_REDACTED.txt"
say
cat "$OUT_PRIVATE"
