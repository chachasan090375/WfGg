#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 12
# OFFLINE ONLY. Determines how companion systems relate to formations:
# - Dominator / Overlord linkage already observed via heroUuid;
# - drone/UAV-like data are searched across the full init tree;
# - exact scalar references are cross-matched against army_formation and
#   formation_template WITHOUT exporting any raw ID/UUID value.
#
# The goal is topology, not gameplay: identify whether the drone is explicitly
# referenced per squad, shared globally, or represented through another field.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE12_COMPANION_TOPOLOGY_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase12-companion-topology"
HELPER="${BASE}/wfgg-phase12-companion-topology"

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

say "=== WfGg Last War LAB · PHASE 12 ==="
say "Mode: OFFLINE / topologie drone + Overlord / aucune connexion Last War"
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

var droneTokens = []string{"drone", "uav", "aircraft", "airship", "plane"}
var dominatorTokens = []string{"dominator", "overlord"}

type matchSummary struct {
    CandidatePaths map[string]int
    ScalarRefs map[int64]bool
    FormationScalarMatches map[string]int
    FormationNamedFields map[string]int
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj,err:=findInit(os.Args[1]); if err!=nil{fatal(err)}

    drone:=matchSummary{map[string]int{},map[int64]bool{},map[string]int{},map[string]int{}}
    dom:=matchSummary{map[string]int{},map[int64]bool{},map[string]int{},map[string]int{}}

    walkCandidates(initObj,"",droneTokens,&drone)
    walkCandidates(initObj,"",dominatorTokens,&dom)

    analyseFormationObjects(objectsForKey(initObj,"army_formation"),"army_formation",droneTokens,dominatorTokens,&drone,&dom)
    analyseFormationObjects(objectsForKey(initObj,"formation_template"),"formation_template",droneTokens,dominatorTokens,&drone,&dom)

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600); if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 12 COMPANION TOPOLOGY")
    fmt.Fprintln(f,"OFFLINE ONLY · raw IDs/UUIDs/credential values suppressed")
    fmt.Fprintln(f)

    printSection(f,"DRONE_OR_UAV_CANDIDATE_PATHS",drone.CandidatePaths)
    fmt.Fprintf(f,"DRONE_LARGE_SCALAR_REFS_UNIQUE=%d\n",len(drone.ScalarRefs))
    printSection(f,"DRONE_NAMED_FIELDS_IN_FORMATIONS",drone.FormationNamedFields)
    printSection(f,"DRONE_SCALAR_MATCHES_IN_FORMATIONS",drone.FormationScalarMatches)
    fmt.Fprintln(f)

    printSection(f,"DOMINATOR_OR_OVERLORD_CANDIDATE_PATHS",dom.CandidatePaths)
    fmt.Fprintf(f,"DOMINATOR_LARGE_SCALAR_REFS_UNIQUE=%d\n",len(dom.ScalarRefs))
    printSection(f,"DOMINATOR_NAMED_FIELDS_IN_FORMATIONS",dom.FormationNamedFields)
    printSection(f,"DOMINATOR_SCALAR_MATCHES_IN_FORMATIONS",dom.FormationScalarMatches)
    fmt.Fprintln(f)

    army:=objectsForKey(initObj,"army_formation")
    templates:=objectsForKey(initObj,"formation_template")
    fmt.Fprintf(f,"ARMY_FORMATIONS=%d FORMATION_TEMPLATES=%d\n",len(army),len(templates))
    fmt.Fprintln(f,"FORMATION_FIELD_SIGNATURES")
    sigs:=formationSignatures(army,templates)
    for _,s:=range sortedKeys(sigs){fmt.Fprintf(f,"  count=%d keys=%s\n",sigs[s],s)}
    fmt.Fprintln(f)

    droneExplicit:=len(drone.FormationNamedFields)>0 || len(drone.FormationScalarMatches)>0
    domExplicit:=len(dom.FormationNamedFields)>0 || len(dom.FormationScalarMatches)>0
    if droneExplicit {fmt.Fprintln(f,"DRONE_TOPOLOGY=explicit_or_indirect_formation_link_detected")} else if len(drone.CandidatePaths)>0 {fmt.Fprintln(f,"DRONE_TOPOLOGY=global_or_implicit_companion_no_formation_reference_detected")} else {fmt.Fprintln(f,"DRONE_TOPOLOGY=no_drone_named_structure_found_in_init")}
    if domExplicit {fmt.Fprintln(f,"OVERLORD_TOPOLOGY=formation_link_detected")} else {fmt.Fprintln(f,"OVERLORD_TOPOLOGY=no_direct_formation_link_detected")}

    fmt.Printf("DRONE_PATHS=%d DRONE_FORMATION_MATCH_PATHS=%d DOMINATOR_PATHS=%d DOMINATOR_FORMATION_MATCH_PATHS=%d\n",len(drone.CandidatePaths),len(drone.FormationScalarMatches)+len(drone.FormationNamedFields),len(dom.CandidatePaths),len(dom.FormationScalarMatches)+len(dom.FormationNamedFields))
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func walkCandidates(o *sfs.SFSObject,path string,tokens []string,s *matchSummary){
    if o==nil{return}
    for _,k:=range o.Keys(){
        sv,_:=o.Get(k)
        p:=k;if path!=""{p=path+"."+k}
        if containsToken(k,tokens){
            s.CandidatePaths[normalisePath(p,sv.Val)]++
            collectLargeScalars(sv.Val,s.ScalarRefs)
        }
        walkValueCandidates(sv.Val,p,tokens,s)
    }
}

func walkValueCandidates(v any,path string,tokens []string,s *matchSummary){
    switch x:=v.(type){
    case *sfs.SFSObject: walkCandidates(x,path,tokens,s)
    case *sfs.SFSArray:
        if x!=nil{for _,it:=range x.Items(){walkValueCandidates(it.Val,path+"[]",tokens,s)}}
    }
}

func collectLargeScalars(v any,out map[int64]bool){
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x!=nil{for _,k:=range x.Keys(){sv,_:=x.Get(k);collectLargeScalars(sv.Val,out)}}
    case *sfs.SFSArray:
        if x!=nil{for _,it:=range x.Items(){collectLargeScalars(it.Val,out)}}
    case []int64:for _,n:=range x{addLarge(n,out)}
    case []int32:for _,n:=range x{addLarge(int64(n),out)}
    case []int16:for _,n:=range x{addLarge(int64(n),out)}
    case []string:for _,v:=range x{if n,e:=strconv.ParseInt(v,10,64);e==nil{addLarge(n,out)}}
    case int64:addLarge(x,out)
    case int32:addLarge(int64(x),out)
    case int16:addLarge(int64(x),out)
    case string:if n,e:=strconv.ParseInt(x,10,64);e==nil{addLarge(n,out)}
    }
}
func addLarge(n int64,out map[int64]bool){if n>1000||n< -1000{out[n]=true}}

func analyseFormationObjects(objs []*sfs.SFSObject,root string,droneTokens,domTokens []string,drone,dom *matchSummary){
    for _,o:=range objs{
        if o==nil{continue}
        for _,k:=range o.Keys(){
            sv,_:=o.Get(k);p:=root+"[]."+k
            if containsToken(k,droneTokens){drone.FormationNamedFields[p]++}
            if containsToken(k,domTokens){dom.FormationNamedFields[p]++}
            crossMatchScalars(sv.Val,p,drone.ScalarRefs,drone.FormationScalarMatches)
            crossMatchScalars(sv.Val,p,dom.ScalarRefs,dom.FormationScalarMatches)
        }
    }
}

func crossMatchScalars(v any,path string,targets map[int64]bool,out map[string]int){
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x!=nil{for _,k:=range x.Keys(){sv,_:=x.Get(k);crossMatchScalars(sv.Val,path+"."+k,targets,out)}}
    case *sfs.SFSArray:
        if x!=nil{for _,it:=range x.Items(){crossMatchScalars(it.Val,path+"[]",targets,out)}}
    case []int64:for _,n:=range x{if targets[n]{out[path+"[]"]++}}
    case []int32:for _,n:=range x{if targets[int64(n)]{out[path+"[]"]++}}
    case []int16:for _,n:=range x{if targets[int64(n)]{out[path+"[]"]++}}
    case []string:for _,v:=range x{if n,e:=strconv.ParseInt(v,10,64);e==nil&&targets[n]{out[path+"[]"]++}}
    case int64:if targets[x]{out[path]++}
    case int32:if targets[int64(x)]{out[path]++}
    case int16:if targets[int64(x)]{out[path]++}
    case string:if n,e:=strconv.ParseInt(x,10,64);e==nil&&targets[n]{out[path]++}
    }
}

func formationSignatures(army,templates []*sfs.SFSObject)map[string]int{
    out:=map[string]int{}
    all:=append(append([]*sfs.SFSObject{},army...),templates...)
    for _,o:=range all{
        if o==nil{continue};parts:=make([]string,0,len(o.Keys()))
        for _,k:=range o.Keys(){sv,_:=o.Get(k);parts=append(parts,fmt.Sprintf("%s:t%d",k,sv.Type))}
        sort.Strings(parts);out[strings.Join(parts,",")]++
    }
    return out
}

func containsToken(s string,tokens []string)bool{l:=strings.ToLower(s);for _,t:=range tokens{if strings.Contains(l,t){return true}};return false}
func normalisePath(path string,v any)string{return path+" "+shapeOf(v)}
func shapeOf(v any)string{switch x:=v.(type){case *sfs.SFSObject:if x==nil{return "SFSObject(nil)"};return fmt.Sprintf("SFSObject[%d]",len(x.Keys()));case *sfs.SFSArray:if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()));case []int64:return fmt.Sprintf("[]int64[%d]",len(x));case []int32:return fmt.Sprintf("[]int32[%d]",len(x));case []int16:return fmt.Sprintf("[]int16[%d]",len(x));case []string:return fmt.Sprintf("[]string[%d]",len(x));default:return fmt.Sprintf("%T",v)}}
func printSection(w io.Writer,title string,m map[string]int){fmt.Fprintln(w,title);keys:=sortedKeys(m);if len(keys)==0{fmt.Fprintln(w,"  (aucun)");return};for _,k:=range keys{fmt.Fprintf(w,"  count=%d path=%s\n",m[k],k)}}
func sortedKeys(m map[string]int)[]string{keys:=make([]string,0,len(m));for k:=range m{keys=append(keys,k)};sort.Strings(keys);return keys}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err};pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){if conv.TLS{continue};client,err:=conv.Client(netip.Addr{});if err!=nil{continue};_,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c);for{body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break};outer,err:=sfs.DecodeObject(body);if err!=nil{continue};pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue};pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}}}
    return nil,fmt.Errorf("init Last War introuvable")
}
func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase12:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase12-companion-topology
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 12 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE12_COMPANION_TOPOLOGY_REDACTED.txt"
