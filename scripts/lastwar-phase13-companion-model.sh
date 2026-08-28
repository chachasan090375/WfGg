#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 13
# OFFLINE ONLY. Builds a redacted companion model for Drone/UAV-like systems
# and Dominator/Overlord data from the captured init tree.
#
# Privacy:
# - no network connection to Last War
# - no credentials
# - no UUID/GUID/UID/owner identifiers
# - catalog/config IDs and progression values may be exported when their field
#   name is clearly non-private (e.g. dominatorId, level, rank, stage, power).

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE13_COMPANION_MODEL_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase13-companion-model"
HELPER="${BASE}/wfgg-phase13-companion-model"

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

say "=== WfGg Last War LAB · PHASE 13 ==="
say "Mode: OFFLINE / modèle compagnons Drone + Overlord"
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

var droneTokens = []string{"drone","uav","plane","aircraft","airship"}
var domTokens = []string{"dominator","overlord"}

type line struct { Path, Type, Value string }

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj,err:=findInit(os.Args[1]); if err!=nil{fatal(err)}

    var droneLines, domLines, powerLines []line
    walkNamed(initObj,"",droneTokens,&droneLines)
    walkNamed(initObj,"",domTokens,&domLines)

    if p,ok:=initObj.Get("playerInfo"); ok {
        if po,ok:=p.Val.(*sfs.SFSObject); ok && po!=nil {
            walkNamed(po,"playerInfo",append(append([]string{},droneTokens...),domTokens...),&powerLines)
        }
    }

    army:=objectsForKey(initObj,"army_formation")
    templates:=objectsForKey(initObj,"formation_template")

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600); if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 13 COMPANION MODEL")
    fmt.Fprintln(f,"OFFLINE ONLY · UUID/GUID/UID/owner values suppressed")
    fmt.Fprintln(f)

    printLines(f,"DRONE_UAV_CANDIDATE_TREE",dedupe(droneLines))
    fmt.Fprintln(f)
    printLines(f,"DOMINATOR_OVERLORD_TREE",dedupe(domLines))
    fmt.Fprintln(f)
    printLines(f,"PLAYERINFO_COMPANION_FIELDS",dedupe(powerLines))
    fmt.Fprintln(f)

    fmt.Fprintf(f,"ARMY_FORMATIONS=%d FORMATION_TEMPLATES=%d\n",len(army),len(templates))
    fmt.Fprintf(f,"ARMY_WITH_DRONE_NAMED_FIELD=%d\n",countNamed(army,droneTokens))
    fmt.Fprintf(f,"TEMPLATES_WITH_DRONE_NAMED_FIELD=%d\n",countNamed(templates,droneTokens))
    fmt.Fprintf(f,"ARMY_WITH_DOMINATOR_NAMED_FIELD=%d\n",countNamed(army,domTokens))
    fmt.Fprintf(f,"TEMPLATES_WITH_DOMINATOR_NAMED_FIELD=%d\n",countNamed(templates,domTokens))

    domRefs:=collectPrivateRefs(objectsForKey(initObj,"userDominators"))
    fmt.Fprintf(f,"DOMINATOR_PRIVATE_REFS_UNIQUE=%d\n",len(domRefs))
    fmt.Fprintf(f,"ARMY_DOMINATOR_REF_MATCHES=%d\n",countPrivateRefMatches(army,domRefs))
    fmt.Fprintf(f,"TEMPLATE_DOMINATOR_REF_MATCHES=%d\n",countPrivateRefMatches(templates,domRefs))

    fmt.Fprintln(f)
    if countNamed(army,droneTokens)==0 && countNamed(templates,droneTokens)==0 {
        fmt.Fprintln(f,"DRONE_RELATION_MODEL=account_global_or_implicit_not_assigned_per_formation")
    } else {
        fmt.Fprintln(f,"DRONE_RELATION_MODEL=explicit_named_formation_field_present")
    }
    if countPrivateRefMatches(army,domRefs)>0 || countPrivateRefMatches(templates,domRefs)>0 {
        fmt.Fprintln(f,"OVERLORD_RELATION_MODEL=explicit_private_reference_embedded_in_formation")
    } else {
        fmt.Fprintln(f,"OVERLORD_RELATION_MODEL=no_private_reference_match_found")
    }

    fmt.Printf("DRONE_TREE_LINES=%d DOM_TREE_LINES=%d ARMY_DOM_MATCHES=%d TEMPLATE_DOM_MATCHES=%d\n",len(dedupe(droneLines)),len(dedupe(domLines)),countPrivateRefMatches(army,domRefs),countPrivateRefMatches(templates,domRefs))
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func walkNamed(o *sfs.SFSObject,path string,tokens []string,out *[]line){
    if o==nil{return}
    for _,k:=range o.Keys(){
        sv,_:=o.Get(k)
        p:=k;if path!=""{p=path+"."+k}
        if containsAny(k,tokens){
            appendNode(p,k,sv,out)
            walkSubtree(sv.Val,p,out,0)
        } else {
            switch x:=sv.Val.(type){
            case *sfs.SFSObject: walkNamed(x,p,tokens,out)
            case *sfs.SFSArray:
                if x!=nil{for _,it:=range x.Items(){if q,ok:=it.Val.(*sfs.SFSObject);ok&&q!=nil{walkNamed(q,p+"[]",tokens,out)}}}
            }
        }
    }
}

func walkSubtree(v any,path string,out *[]line,depth int){
    if depth>5{return}
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return}
        for _,k:=range x.Keys(){sv,_:=x.Get(k);p:=path+"."+k;appendNode(p,k,sv,out);walkSubtree(sv.Val,p,out,depth+1)}
    case *sfs.SFSArray:
        if x==nil{return}
        for _,it:=range x.Items(){walkSubtree(it.Val,path+"[]",out,depth+1)}
    }
}

func appendNode(path,key string,sv sfs.SFSValue,out *[]line){
    typ:=fmt.Sprintf("t%d/%s",sv.Type,shapeOf(sv.Val))
    val:="suppressed"
    if safeValueKey(key){if s,ok:=scalarString(sv.Val);ok{val=s}}
    *out=append(*out,line{Path:path,Type:typ,Value:val})
}

func safeValueKey(k string)bool{
    l:=strings.ToLower(k)
    if strings.Contains(l,"uuid")||strings.Contains(l,"guid")||strings.Contains(l,"owner")||l=="uid"||strings.HasSuffix(l,"uid")||strings.Contains(l,"token")||strings.Contains(l,"login")||strings.Contains(l,"key"){return false}
    safe:=[]string{"level","lv","rank","stage","power","exp","star","skill","type","tag","status","state","count","num","id"}
    for _,s:=range safe{if strings.Contains(l,s){return true}}
    return false
}

func scalarString(v any)(string,bool){
    switch x:=v.(type){
    case int64:return strconv.FormatInt(x,10),true
    case int32:return strconv.FormatInt(int64(x),10),true
    case int16:return strconv.FormatInt(int64(x),10),true
    case byte:return strconv.FormatInt(int64(x),10),true
    case bool:if x{return "true",true};return "false",true
    case string:
        if len(x)<=80{return x,true}
    }
    return "",false
}

func shapeOf(v any)string{
    switch x:=v.(type){
    case *sfs.SFSObject:if x==nil{return "SFSObject(nil)"};return fmt.Sprintf("SFSObject[%d]",len(x.Keys()))
    case *sfs.SFSArray:if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()))
    case []int64:return fmt.Sprintf("[]int64[%d]",len(x));case []int32:return fmt.Sprintf("[]int32[%d]",len(x));case []int16:return fmt.Sprintf("[]int16[%d]",len(x));case []byte:return fmt.Sprintf("[]byte[%d]",len(x));case []string:return fmt.Sprintf("[]string[%d]",len(x));default:return fmt.Sprintf("%T",v)
    }
}

func dedupe(in []line)[]line{
    m:=map[string]line{}
    for _,x:=range in{k:=x.Path+"|"+x.Type+"|"+x.Value;m[k]=x}
    out:=make([]line,0,len(m));for _,x:=range m{out=append(out,x)}
    sort.Slice(out,func(i,j int)bool{return out[i].Path<out[j].Path})
    return out
}
func printLines(w io.Writer,title string,rows []line){fmt.Fprintln(w,title);if len(rows)==0{fmt.Fprintln(w,"  (aucun)");return};for _,r:=range rows{fmt.Fprintf(w,"  path=%s type=%s value=%s\n",r.Path,r.Type,r.Value)}}

func countNamed(objs []*sfs.SFSObject,tokens []string)int{n:=0;for _,o:=range objs{if o==nil{continue};found:=false;for _,k:=range o.Keys(){if containsAny(k,tokens){found=true;break}};if found{n++}};return n}
func containsAny(s string,tokens []string)bool{l:=strings.ToLower(s);for _,t:=range tokens{if strings.Contains(l,t){return true}};return false}

func collectPrivateRefs(objs []*sfs.SFSObject)map[int64]bool{
    out:=map[int64]bool{}
    for _,o:=range objs{collectPrivateRefsValue(o,out)}
    return out
}
func collectPrivateRefsValue(v any,out map[int64]bool){
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return};for _,k:=range x.Keys(){sv,_:=x.Get(k);l:=strings.ToLower(k);if strings.Contains(l,"uuid")||strings.Contains(l,"guid"){if n,ok:=asInt64(sv.Val);ok&&n!=0{out[n]=true}};collectPrivateRefsValue(sv.Val,out)}
    case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){collectPrivateRefsValue(it.Val,out)}}
    }
}
func countPrivateRefMatches(objs []*sfs.SFSObject,targets map[int64]bool)int{n:=0;for _,o:=range objs{n+=countMatchesValue(o,targets)};return n}
func countMatchesValue(v any,targets map[int64]bool)int{
    n:=0
    switch x:=v.(type){
    case *sfs.SFSObject:if x!=nil{for _,k:=range x.Keys(){sv,_:=x.Get(k);n+=countMatchesValue(sv.Val,targets)}}
    case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){n+=countMatchesValue(it.Val,targets)}}
    case []int64:for _,q:=range x{if targets[q]{n++}}
    case []int32:for _,q:=range x{if targets[int64(q)]{n++}}
    case []int16:for _,q:=range x{if targets[int64(q)]{n++}}
    case int64:if targets[x]{n++}
    case int32:if targets[int64(x)]{n++}
    case int16:if targets[int64(x)]{n++}
    case string:if q,e:=strconv.ParseInt(x,10,64);e==nil&&targets[q]{n++}
    }
    return n
}
func asInt64(v any)(int64,bool){switch x:=v.(type){case int64:return x,true;case int32:return int64(x),true;case int16:return int64(x),true;case byte:return int64(x),true;case string:n,e:=strconv.ParseInt(x,10,64);return n,e==nil};return 0,false}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err};pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){if conv.TLS{continue};client,err:=conv.Client(netip.Addr{});if err!=nil{continue};_,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c);for{body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break};outer,err:=sfs.DecodeObject(body);if err!=nil{continue};pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue};pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}}}
    return nil,fmt.Errorf("init Last War introuvable")
}
func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase13:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase13-companion-model
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 13 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE13_COMPANION_MODEL_REDACTED.txt"
