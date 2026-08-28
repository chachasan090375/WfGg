#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 11
# OFFLINE ONLY. Cross-references unresolved formation heroUuid values against
# the entire captured init tree. Raw unresolved IDs/UUIDs are never exported;
# only matching field paths and counts are written.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE11_UNRESOLVED_CROSSREF_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase11-unresolved-crossref"
HELPER="${BASE}/wfgg-phase11-unresolved-crossref"

say(){ printf '%s\n' "$*"; }
die(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

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
  CAPTURE="$(printf '%s\n' "$CANDIDATES" | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 11 ==="
say "Mode: OFFLINE / cross-reference formations / aucune connexion Last War"
say "Capture: $CAPTURE"

mkdir -p "$TMP_CMD"
cleanup(){ rm -rf "$TMP_CMD" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

cat > "$TMP_CMD/main.go" <<'GOEOF'
package main

import (
    "bytes"
    "errors"
    "fmt"
    "io"
    "lastwar-client/internal/pcap"
    "lastwar-client/internal/sfs"
    "net/netip"
    "os"
    "sort"
    "strconv"
    "strings"
)

func main() {
    if len(os.Args) != 3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj, err := findInit(os.Args[1]); if err != nil { fatal(err) }

    heroMap := map[int64]int64{}
    heroSet := map[int64]bool{}
    for _, o := range objectsForKey(initObj, "userHero") {
        id := num(o, "heroId"); if id == 0 { continue }
        heroSet[id] = true
        if uuid := num(o, "uuid"); uuid != 0 { heroMap[uuid] = id }
    }

    unresolved := map[int64]bool{}
    collectUnresolved(objectsForKey(initObj, "army_formation"), heroMap, heroSet, unresolved)
    collectUnresolved(objectsForKey(initObj, "formation_template"), heroMap, heroSet, unresolved)

    pathCounts := map[string]int{}
    sourceCounts := map[string]int{}
    walkObject(initObj, "", unresolved, pathCounts, sourceCounts)

    outsideTotal := 0
    for _, n := range pathCounts { outsideTotal += n }
    sourceTotal := 0
    for _, n := range sourceCounts { sourceTotal += n }

    f, err := os.OpenFile(os.Args[2], os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0600); if err != nil { fatal(err) }
    defer f.Close()
    fmt.Fprintln(f, "WfGg Last War LAB — PHASE 11 UNRESOLVED CROSS-REFERENCE")
    fmt.Fprintln(f, "OFFLINE ONLY · unresolved raw IDs/UUIDs and all matched values suppressed")
    fmt.Fprintln(f)
    fmt.Fprintf(f, "UNRESOLVED_UNIQUE=%d\n", len(unresolved))
    fmt.Fprintf(f, "FORMATION_SOURCE_MATCHES=%d\n", sourceTotal)
    fmt.Fprintf(f, "MATCHES_OUTSIDE_FORMATIONS=%d\n\n", outsideTotal)

    fmt.Fprintln(f, "OUTSIDE_FORMATION_PATHS")
    keys := sortedKeys(pathCounts)
    if len(keys) == 0 { fmt.Fprintln(f, "  (aucun)") }
    for _, p := range keys { fmt.Fprintf(f, "  count=%d path=%s\n", pathCounts[p], p) }

    fmt.Fprintln(f)
    fmt.Fprintln(f, "FORMATION_SOURCE_PATHS")
    keys = sortedKeys(sourceCounts)
    if len(keys) == 0 { fmt.Fprintln(f, "  (aucun)") }
    for _, p := range keys { fmt.Fprintf(f, "  count=%d path=%s\n", sourceCounts[p], p) }

    fmt.Fprintln(f)
    if outsideTotal == 0 {
        fmt.Fprintln(f, "INTERPRETATION=no_cross_reference_outside_formations")
    } else {
        fmt.Fprintln(f, "INTERPRETATION=cross_reference_found_outside_formations")
    }

    fmt.Printf("UNRESOLVED_UNIQUE=%d OUTSIDE_MATCHES=%d SOURCE_MATCHES=%d\n", len(unresolved), outsideTotal, sourceTotal)
    fmt.Printf("OUTPUT=%s\n", os.Args[2])
}

func collectUnresolved(objs []*sfs.SFSObject, heroMap map[int64]int64, heroSet map[int64]bool, out map[int64]bool) {
    for _, o := range objs {
        sv, ok := o.Get("heroes"); if !ok { continue }
        for _, raw := range flattenRefs(sv.Val) {
            if raw == 0 { continue }
            if _, ok := heroMap[raw]; ok { continue }
            if heroSet[raw] { continue }
            out[raw] = true
        }
    }
}

func walkObject(o *sfs.SFSObject, path string, targets map[int64]bool, outside, source map[string]int) {
    if o == nil { return }
    for _, k := range o.Keys() {
        sv, _ := o.Get(k)
        p := k
        if path != "" { p = path + "." + k }
        walkValue(sv.Val, p, targets, outside, source)
    }
}

func walkValue(v any, path string, targets map[int64]bool, outside, source map[string]int) {
    switch x := v.(type) {
    case *sfs.SFSObject:
        walkObject(x, path, targets, outside, source)
    case *sfs.SFSArray:
        if x == nil { return }
        for _, it := range x.Items() { walkValue(it.Val, path+"[]", targets, outside, source) }
    case []int64:
        for _, n := range x { record(n, path+"[]", targets, outside, source) }
    case []int32:
        for _, n := range x { record(int64(n), path+"[]", targets, outside, source) }
    case []int16:
        for _, n := range x { record(int64(n), path+"[]", targets, outside, source) }
    case []byte:
        for _, n := range x { record(int64(n), path+"[]", targets, outside, source) }
    case []string:
        for _, s := range x { if n, err := strconv.ParseInt(s,10,64); err == nil { record(n,path+"[]",targets,outside,source) } }
    case int64:
        record(x, path, targets, outside, source)
    case int32:
        record(int64(x), path, targets, outside, source)
    case int16:
        record(int64(x), path, targets, outside, source)
    case byte:
        record(int64(x), path, targets, outside, source)
    case string:
        if n, err := strconv.ParseInt(x,10,64); err == nil { record(n,path,targets,outside,source) }
    }
}

func record(n int64, path string, targets map[int64]bool, outside, source map[string]int) {
    if !targets[n] { return }
    if isFormationSource(path) { source[path]++ } else { outside[path]++ }
}

func isFormationSource(path string) bool {
    p := strings.ToLower(path)
    return (strings.HasPrefix(p,"army_formation") || strings.HasPrefix(p,"formation_template")) && strings.Contains(p,".heroes[]")
}

func sortedKeys(m map[string]int) []string {
    keys := make([]string,0,len(m)); for k := range m { keys = append(keys,k) }; sort.Strings(keys); return keys
}

func flattenRefs(v any) []int64 {
    var out []int64
    switch x := v.(type) {
    case *sfs.SFSArray:
        if x == nil { return out }; for _, it := range x.Items() { out = append(out, flattenRefs(it.Val)...) }
    case *sfs.SFSObject:
        if x == nil { return out }
        if id := firstNum(x,"heroId"); id != 0 { return []int64{id} }
        if id := firstNum(x,"heroUuid","uuid","heroUid","uid"); id != 0 { return []int64{id} }
    case []int64: out = append(out,x...)
    case []int32: for _,n := range x { out=append(out,int64(n)) }
    case []int16: for _,n := range x { out=append(out,int64(n)) }
    case []byte: for _,n := range x { out=append(out,int64(n)) }
    case []string: for _,s := range x { if n,err:=strconv.ParseInt(s,10,64);err==nil{out=append(out,n)} }
    case int64: out=append(out,x)
    case int32: out=append(out,int64(x))
    case int16: out=append(out,int64(x))
    case byte: out=append(out,int64(x))
    case string: if n,err:=strconv.ParseInt(x,10,64);err==nil{out=append(out,n)}
    }
    return out
}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err}
    pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        _,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c)
        for{
            body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break}
            outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
            pv,ok:=outer.Get("p");if !ok{continue}
            ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue}
            pp,ok:=ext.Get("p");if !ok{continue}
            params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}
        }
    }
    return nil,fmt.Errorf("init Last War introuvable")
}
func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n);case string:if x,err:=strconv.ParseInt(n,10,64);err==nil{return x}};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase11:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase11-unresolved-crossref
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 11 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE11_UNRESOLVED_CROSSREF_REDACTED.txt"
