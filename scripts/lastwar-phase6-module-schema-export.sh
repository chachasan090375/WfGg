#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 6
# OFFLINE ONLY. Reads the user's own PCAP and produces a module-oriented,
# shareable JSON inventory. No Last War network connection is opened.
#
# Export policy:
# - never exports access tokens, loginKey, device identifiers or anti-fraud data;
# - never exports player/alliance names, e-mail, network/database infrastructure;
# - exports schema/type information for module-relevant init domains;
# - exports only catalog IDs + progression levels for heroes/buildings/science;
# - exports numeric power/progression scalars from playerInfo.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE6_MODULE_SCHEMA.json"
TMP_CMD="${SRC}/cmd/wfgg-module-schema"
HELPER="${BASE}/wfgg-module-schema"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

[[ -d "$SRC/.git" ]] || die "source du probe absente; exécute d'abord la phase 1"
[[ -d "$DOWNLOADS" ]] || die "accès stockage Android absent; exécute termux-setup-storage"

CAPTURE="${1:-}"
if [[ -z "$CAPTURE" ]]; then
  CANDIDATES="$({
    for root in "$DOWNLOADS" "$SHARED/Download" "$SHARED/Documents" "$SHARED/PCAPdroid" "$ANDROID_SHARED/Download" "$ANDROID_SHARED/Documents"; do
      [[ -e "$root" ]] || continue
      find -L "$root" -maxdepth 6 -type f \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) -printf '%T@ %p\n' 2>/dev/null || true
    done
  } | sort -nr)"
  if [[ -z "$CANDIDATES" && -e "$SHARED" ]]; then
    CANDIDATES="$(find -L "$SHARED" -type f \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr || true)"
  fi
  CAPTURE="$(printf '%s\n' "$CANDIDATES" | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 6 ==="
say "Mode: OFFLINE / PCAP uniquement / export module expurgé"
say "Capture: $CAPTURE"

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
    "sort"
    "strings"
)

type fieldSchema struct {
    Name string   `json:"name"`
    Types []string `json:"types"`
}

type domainSchema struct {
    Present bool `json:"present"`
    Kind string `json:"kind,omitempty"`
    Count int `json:"count,omitempty"`
    Fields []fieldSchema `json:"fields,omitempty"`
}

type heroRow struct {
    HeroID int64 `json:"heroId"`
    Level int64 `json:"level,omitempty"`
    Rank int64 `json:"rankLv,omitempty"`
    Awaken int64 `json:"awakenLv,omitempty"`
    SkinID int64 `json:"skinId,omitempty"`
}

type buildingRow struct {
    BuildingID int64 `json:"bId"`
    Level int64 `json:"level,omitempty"`
    PointID int64 `json:"pId,omitempty"`
}

type scienceRow struct {
    ScienceID int64 `json:"scienceId"`
    Level int64 `json:"level,omitempty"`
}

type exportDoc struct {
    Format string `json:"format"`
    Source string `json:"source"`
    NetworkUsed bool `json:"networkUsed"`
    InitTopLevelFields int `json:"initTopLevelFields"`
    Domains map[string]domainSchema `json:"domains"`
    PlayerProgress map[string]any `json:"playerProgress,omitempty"`
    Heroes []heroRow `json:"heroes,omitempty"`
    Buildings []buildingRow `json:"buildings,omitempty"`
    Science []scienceRow `json:"science,omitempty"`
}

var domains = []string{
    "playerInfo", "userHero", "army_formation", "formation_template",
    "heroEquips", "equipList", "weaponArr", "science_new", "building_new",
    "resource_items", "resource",
}

func main() {
    if len(os.Args) != 3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj, err := findInit(os.Args[1])
    if err != nil { fatal(err) }

    doc := exportDoc{
        Format: "WFGG_LASTWAR_MODULE_SCHEMA_V1",
        Source: "local_pcap_init",
        NetworkUsed: false,
        InitTopLevelFields: len(initObj.Keys()),
        Domains: map[string]domainSchema{},
    }

    for _, name := range domains {
        v, ok := initObj.Get(name)
        if !ok {
            doc.Domains[name] = domainSchema{Present:false}
            continue
        }
        doc.Domains[name] = schemaOf(v)
    }

    if v, ok := initObj.Get("playerInfo"); ok {
        if obj, ok := v.Val.(*sfs.SFSObject); ok && obj != nil {
            doc.PlayerProgress = safePlayerProgress(obj)
        }
    }
    if v, ok := initObj.Get("userHero"); ok { doc.Heroes = extractHeroes(v) }
    if v, ok := initObj.Get("building_new"); ok { doc.Buildings = extractBuildings(v) }
    if v, ok := initObj.Get("science_new"); ok { doc.Science = extractScience(v) }

    out, err := json.MarshalIndent(doc, "", "  ")
    if err != nil { fatal(err) }
    if err := os.WriteFile(os.Args[2], out, 0600); err != nil { fatal(err) }

    fmt.Printf("INIT_TOP_FIELDS=%d HEROES=%d BUILDINGS=%d SCIENCE=%d\n", doc.InitTopLevelFields, len(doc.Heroes), len(doc.Buildings), len(doc.Science))
    fmt.Printf("OUTPUT=%s\n", os.Args[2])
}

func findInit(path string) (*sfs.SFSObject, error) {
    data, err := os.ReadFile(path)
    if err != nil { return nil, err }
    pkts, err := pcap.Parse(data)
    if err != nil { return nil, err }
    for _, conv := range pcap.Conversations(pkts) {
        if conv.TLS { continue }
        client, err := conv.Client(netip.Addr{})
        if err != nil { continue }
        _, s2c := conv.Reassemble(client)
        r := bytes.NewReader(s2c)
        for {
            body, err := sfs.ReadPacket(r)
            if err != nil {
                if errors.Is(err, io.EOF) { break }
                break
            }
            outer, err := sfs.DecodeObject(body)
            if err != nil { continue }
            pv, ok := outer.Get("p")
            if !ok { continue }
            ext, ok := pv.Val.(*sfs.SFSObject)
            if !ok || ext == nil || ext.GetString("c") != "init" { continue }
            pp, ok := ext.Get("p")
            if !ok { continue }
            params, ok := pp.Val.(*sfs.SFSObject)
            if ok && params != nil { return params, nil }
        }
    }
    return nil, fmt.Errorf("init Last War introuvable dans la capture")
}

func schemaOf(v sfs.SFSValue) domainSchema {
    d := domainSchema{Present:true, Kind:typeName(v.Val)}
    objs := objectsFrom(v)
    if len(objs) > 0 {
        d.Count = len(objs)
        m := map[string]map[string]bool{}
        for _, o := range objs {
            for _, k := range o.Keys() {
                sv, _ := o.Get(k)
                if m[k] == nil { m[k] = map[string]bool{} }
                m[k][typeName(sv.Val)] = true
            }
        }
        keys := make([]string, 0, len(m))
        for k := range m { keys = append(keys, k) }
        sort.Strings(keys)
        for _, k := range keys {
            ts := make([]string,0,len(m[k]))
            for t := range m[k] { ts = append(ts,t) }
            sort.Strings(ts)
            d.Fields = append(d.Fields, fieldSchema{Name:k, Types:ts})
        }
        return d
    }
    if a, ok := v.Val.(*sfs.SFSArray); ok && a != nil { d.Count = len(a.Items()) }
    if o, ok := v.Val.(*sfs.SFSObject); ok && o != nil {
        d.Count = 1
        for _, k := range o.Keys() {
            sv, _ := o.Get(k)
            d.Fields = append(d.Fields, fieldSchema{Name:k, Types:[]string{typeName(sv.Val)}})
        }
        sort.Slice(d.Fields, func(i,j int) bool { return d.Fields[i].Name < d.Fields[j].Name })
    }
    return d
}

func objectsFrom(v sfs.SFSValue) []*sfs.SFSObject {
    var out []*sfs.SFSObject
    switch x := v.Val.(type) {
    case *sfs.SFSArray:
        if x == nil { return out }
        for _, item := range x.Items() {
            if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { out = append(out,o) }
        }
    case *sfs.SFSObject:
        if x == nil { return out }
        for _, preferred := range []string{"list","data","arr","items"} {
            if sv, ok := x.Get(preferred); ok {
                if a, ok := sv.Val.(*sfs.SFSArray); ok && a != nil {
                    for _, item := range a.Items() {
                        if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { out = append(out,o) }
                    }
                    if len(out)>0 { return out }
                }
            }
        }
        // Fallback: first array-of-objects child.
        for _, k := range x.Keys() {
            sv, _ := x.Get(k)
            if a, ok := sv.Val.(*sfs.SFSArray); ok && a != nil {
                var tmp []*sfs.SFSObject
                for _, item := range a.Items() {
                    if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { tmp = append(tmp,o) }
                }
                if len(tmp)>0 { return tmp }
            }
        }
    }
    return out
}

func extractHeroes(v sfs.SFSValue) []heroRow {
    var out []heroRow
    for _, o := range objectsFrom(v) {
        id := num(o,"heroId")
        if id == 0 { continue }
        out = append(out, heroRow{HeroID:id, Level:firstNum(o,"lev","lv","level"), Rank:firstNum(o,"rankLv","rank"), Awaken:firstNum(o,"awakenLv","awaken"), SkinID:firstNum(o,"skinId")})
    }
    sort.Slice(out, func(i,j int) bool { return out[i].HeroID < out[j].HeroID })
    return out
}

func extractBuildings(v sfs.SFSValue) []buildingRow {
    var out []buildingRow
    for _, o := range objectsFrom(v) {
        id := num(o,"bId")
        if id == 0 { continue }
        out = append(out, buildingRow{BuildingID:id, Level:firstNum(o,"lv","lev","level"), PointID:firstNum(o,"pId")})
    }
    sort.Slice(out, func(i,j int) bool { if out[i].BuildingID==out[j].BuildingID { return out[i].Level<out[j].Level }; return out[i].BuildingID<out[j].BuildingID })
    return out
}

func extractScience(v sfs.SFSValue) []scienceRow {
    var out []scienceRow
    for _, o := range objectsFrom(v) {
        id := firstNum(o,"scienceId","itemId","id","sId")
        if id == 0 { continue }
        out = append(out, scienceRow{ScienceID:id, Level:firstNum(o,"lv","lev","level")})
    }
    sort.Slice(out, func(i,j int) bool { return out[i].ScienceID < out[j].ScienceID })
    return out
}

func safePlayerProgress(o *sfs.SFSObject) map[string]any {
    out := map[string]any{}
    for _, k := range o.Keys() {
        lk := strings.ToLower(k)
        if strings.Contains(lk,"power") || strings.Contains(lk,"kill") || strings.Contains(lk,"stamina") || lk=="level" || lk=="lev" || strings.Contains(lk,"pve") {
            sv,_ := o.Get(k)
            switch n := sv.Val.(type) {
            case int64: out[k]=n
            case int32: out[k]=n
            case int16: out[k]=n
            case byte: out[k]=n
            case float64: out[k]=n
            case float32: out[k]=n
            }
        }
    }
    return out
}

func firstNum(o *sfs.SFSObject, keys ...string) int64 {
    for _, k := range keys { if n:=num(o,k); n!=0 { return n } }
    return 0
}
func num(o *sfs.SFSObject, k string) int64 {
    sv, ok := o.Get(k); if !ok { return 0 }
    switch n := sv.Val.(type) {
    case int64: return n
    case int32: return int64(n)
    case int16: return int64(n)
    case byte: return int64(n)
    }
    return 0
}
func typeName(v any) string {
    switch v.(type) {
    case nil: return "null"
    case string: return "string"
    case bool: return "bool"
    case byte: return "byte"
    case int16: return "int16"
    case int32: return "int32"
    case int64: return "int64"
    case float32: return "float32"
    case float64: return "float64"
    case *sfs.SFSObject: return "object"
    case *sfs.SFSArray: return "array"
    case []bool: return "bool[]"
    case []byte: return "byte[]"
    case []int16: return "int16[]"
    case []int32: return "int32[]"
    case []int64: return "int64[]"
    case []float32: return "float32[]"
    case []float64: return "float64[]"
    case []string: return "string[]"
    default: return fmt.Sprintf("%T",v)
    }
}
func fatal(err error) { fmt.Fprintln(os.Stderr,"phase6:",err); os.Exit(1) }
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-module-schema
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 6 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE6_MODULE_SCHEMA.json"
say "Ce fichier ne contient ni jeton, ni deviceId, ni empreinte anti-fraude, ni nom de joueur/alliance."
