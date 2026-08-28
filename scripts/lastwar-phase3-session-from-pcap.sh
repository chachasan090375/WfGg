#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 3
# Extract the REAL Last War session identity from a local PCAP/PCAPNG and
# immediately exercise it in read-only mode. The live credentials NEVER go
# to stdout, GitHub, Cloudflare or D1: they are written only to a 0600 file
# inside ~/.wfgg-lastwar-probe/home.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
LAB_HOME="${BASE}/home"
BIN="${BASE}/lastwar-client"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
SESSION="${LAB_HOME}/.lastwar_goclient_session.json"
OUT_PRIVATE="${BASE}/WFGG_LASTWAR_PHASE3_REAL_SESSION_REDACTED.txt"
OUT_SHARE="${DOWNLOADS}/WFGG_LASTWAR_PHASE3_REAL_SESSION_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-session-from-pcap"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source du probe absente; exécute d'abord la phase 1"
[[ -d "$LAB_HOME" ]] || die "HOME du laboratoire absent"
[[ -d "$DOWNLOADS" ]] || die "accès stockage Android absent; exécute termux-setup-storage"

CAPTURE="${1:-}"
if [[ -z "$CAPTURE" ]]; then
  # PCAPdroid can save through Android's document picker, so the file is not
  # guaranteed to land in ~/storage/downloads. Search the common shared-storage
  # locations first, then the whole shared tree as a fallback. -L is important:
  # Termux's ~/storage/* entries are symlinks.
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
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé dans le stockage Android. Depuis PCAPdroid, exporte/copier la capture vers Téléchargements, ou relance ce script en lui donnant le chemin exact."

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 3 ==="
say "Capture locale: $CAPTURE"
say "Extraction locale de l'identité de session réelle…"
say "Aucun jeton/empreinte/deviceId ne sera affiché."

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
    "lastwar-client/internal/pcap"
    "lastwar-client/internal/sfs"
    "net/netip"
    "os"
    "path/filepath"
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

type safeMeta struct {
    IP        string `json:"ip"`
    Port      int    `json:"port"`
    Zone      string `json:"zone"`
    GameUid   string `json:"gameUid"`
    Platform  string `json:"platform"`
    App       string `json:"appVersion"`
    Build     string `json:"versionCode"`
    TokenLen  int    `json:"accessTokenLength"`
    ShumeiLen int    `json:"shumeiLength"`
}

func main() {
    if len(os.Args) != 3 {
        fmt.Fprintln(os.Stderr, "usage: wfgg-session-from-pcap <capture> <output-config>")
        os.Exit(2)
    }
    capPath, outPath := os.Args[1], os.Args[2]
    data, err := os.ReadFile(capPath)
    if err != nil { fatal(err) }
    packets, err := pcap.Parse(data)
    if err != nil { fatal(err) }
    convs := pcap.Conversations(packets)

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
            obj, err := sfs.DecodeObject(body)
            if err != nil { continue }
            if obj.GetInt("c") != 0 || obj.GetInt("a") != 1 { continue }

            pv, ok := obj.Get("p")
            if !ok { continue }
            login, ok := pv.Val.(*sfs.SFSObject)
            if !ok || login == nil { continue }
            ppv, ok := login.Get("p")
            if !ok { continue }
            params, ok := ppv.Val.(*sfs.SFSObject)
            if !ok || params == nil { continue }

            pkg := params.GetString("packageName")
            if pkg != "com.fun.lastwar.gp" && pkg != "com.lastwar.ios" { continue }
            token := params.GetString("at")
            deviceID := params.GetString("deviceId")
            shumei := params.GetString("shumeiBoxId")
            zone := login.GetString("zn")
            gameUid := login.GetString("un")
            if gameUid == "" { gameUid = params.GetString("gameUid") }
            if token == "" || deviceID == "" || zone == "" || gameUid == "" {
                continue
            }

            server := conv.A
            if server.Addr == client { server = conv.B }
            cfg := sessionConfig{
                IP: server.Addr.String(), Port: int(server.Port), Zone: zone,
                GameUid: gameUid, DeviceID: deviceID, ShumeiBoxId: shumei,
                AccessToken: token, IOSMode: pkg == "com.lastwar.ios",
            }
            b, err := json.MarshalIndent(cfg, "", "  ")
            if err != nil { fatal(err) }
            if err := os.MkdirAll(filepath.Dir(outPath), 0700); err != nil { fatal(err) }
            tmp, err := os.CreateTemp(filepath.Dir(outPath), ".wfgg-session-*.tmp")
            if err != nil { fatal(err) }
            tmpName := tmp.Name()
            _ = tmp.Chmod(0600)
            if _, err := tmp.Write(b); err != nil { _ = tmp.Close(); _ = os.Remove(tmpName); fatal(err) }
            if err := tmp.Sync(); err != nil { _ = tmp.Close(); _ = os.Remove(tmpName); fatal(err) }
            if err := tmp.Close(); err != nil { _ = os.Remove(tmpName); fatal(err) }
            if err := os.Rename(tmpName, outPath); err != nil { _ = os.Remove(tmpName); fatal(err) }
            _ = os.Chmod(outPath, 0600)

            meta := safeMeta{
                IP: cfg.IP, Port: cfg.Port, Zone: cfg.Zone, GameUid: cfg.GameUid,
                Platform: params.GetString("platform"), App: params.GetString("appVersion"),
                Build: params.GetString("versionCode"), TokenLen: len(token), ShumeiLen: len(shumei),
            }
            mb, _ := json.Marshal(meta)
            fmt.Println(string(mb))
            return
        }
    }
    fatal(fmt.Errorf("aucun Login natif Last War exploitable trouvé dans la capture"))
}

func fatal(err error) {
    fmt.Fprintln(os.Stderr, "extractor:", err)
    os.Exit(1)
}
GOEOF

cd "$SRC"
EXTRACTOR="${BASE}/wfgg-session-from-pcap"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$EXTRACTOR" ./cmd/wfgg-session-from-pcap
chmod 700 "$EXTRACTOR"

if [[ -s "$SESSION" ]]; then
  BACKUP="${SESSION}.bak.$(date +%Y%m%d-%H%M%S)"
  cp -p "$SESSION" "$BACKUP"
  chmod 600 "$BACKUP" 2>/dev/null || true
  say "Ancienne session sauvegardée localement: $(basename "$BACKUP")"
fi

META="$($EXTRACTOR "$CAPTURE" "$SESSION")"
chmod 600 "$SESSION" 2>/dev/null || true
say "Session extraite: oui"
say "Métadonnées non sensibles: $META"
say "Fichier session privé: $SESSION"
say
say "Test immédiat en lecture seule avec cette session réelle…"

# The locally built probe binary is already patched for Android state-file persistence.
# No -collect: this only logs in, consumes init, and prints the redacted building list.
set +e
HOME="$LAB_HOME" "$BIN" -config "$SESSION" -list-buildings -log-level info >"$OUT_PRIVATE" 2>&1
RC=$?
set -e
chmod 600 "$OUT_PRIVATE" 2>/dev/null || true

if [[ -d "$DOWNLOADS" ]]; then
  cp -f "$OUT_PRIVATE" "$OUT_SHARE"
  chmod 600 "$OUT_SHARE" 2>/dev/null || true
fi

say "=== PHASE 3 TERMINEE ==="
say "EXIT=$RC"
say "Session PCAP conservée localement avec permissions 0600: oui"
if [[ -f "$OUT_SHARE" ]]; then
  say "Rapport expurgé: Téléchargements/WFGG_LASTWAR_PHASE3_REAL_SESSION_REDACTED.txt"
else
  say "Rapport expurgé privé: $OUT_PRIVATE"
fi
say
say "--- dernières lignes expurgées ---"
tail -n 40 "$OUT_PRIVATE" 2>/dev/null || true

exit "$RC"
