#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 14
# OFFLINE ONLY. Scans every decoded SFS packet in the user's own PCAP, not only
# the init response. This is needed because Drone data may arrive on a later
# command (for example chip-related data) while the Drone itself remains global.
# Raw UUID/GUID/UID/credentials are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE14_FULL_PCAP_DRONE_DISCOVERY_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase14-drone-discovery"
HELPER="${BASE}/wfgg-phase14-drone-discovery"

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

REAL_GO="${PREFIX:-/data/data/com.termux/files/usr}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 14 ==="
say "Mode: OFFLINE / scan complet PCAP / Drone + Battle Cards"
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

type hit struct { Command, Direction, Path, Shape string }
type arrayDump struct { Command, Direction, Path string; Value any }

type state struct {
    Hits []hit
    DroneArrays []arrayDump
    BattleArrays []arrayDump
    Commands map[string]int
    Init *sfs.SFSObject
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    data,err:=os.ReadFile(os.Args[1]); if err!=nil{fatal(err)}
    pkts,err:=pcap.Parse(data); if err!=nil{fatal(err)}
    st:=state{Commands:map[string]int{}}

    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        c2s,s2c:=conv.Reassemble(client)
        scanStream(c2s,"client_to_server",&st)
        scanStream(s2c,"server_to_client",&st)
    }

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600); if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 14 FULL PCAP DRONE DISCOVERY")
    fmt.Fprintln(f,"OFFLINE ONLY · raw UUID/GUID/UID/credential values suppressed")
    fmt.Fprintln(f)

    fmt.Fprintln(f,"COMMANDS_WITH_DRONE_OR_BATTLECARD_PATHS")
    keys:=sortedKeys(st.Commands)
    if len(keys)==0{fmt.Fprintln(f,"  (aucun)")}
    for _,k:=range keys{fmt.Fprintf(f,"  count=%d command=%s\n",st.Commands[k],k)}

    fmt.Fprintln(f,"\nMATCHED_PATHS")
    for _,h:=range dedupeHits(st.Hits){fmt.Fprintf(f,"  command=%s direction=%s path=%s shape=%s\n",h.Command,h.Direction,h.Path,h.Shape)}

    fmt.Fprintln(f,"\nDRONE_ARRAY_DETAILS")
    if len(st.DroneArrays)==0{fmt.Fprintln(f,"  (aucun)")}
    for _,a:=range dedupeArrays(st.DroneArrays){
        fmt.Fprintf(f,"  command=%s direction=%s path=%s\n",a.Command,a.Direction,a.Path)
        printArraySafe(f,a.Value,"    ")
    }

    fmt.Fprintln(f,"\nUSER_BATTLE_CARD_DETAILS")
    if len(st.BattleArrays)==0{fmt.Fprintln(f,"  (aucun)")}
    for _,a:=range dedupeArrays(st.BattleArrays){
        fmt.Fprintf(f,"  command=%s direction=%s path=%s\n",a.Command,a.Direction,a.Path)
        printArraySafe(f,a.Value,"    ")
    }

    if st.Init!=nil {
        fmt.Fprintln(f,"\nPLAYERINFO_BATTLECARD_POWER")
        printBattlePower(f,st.Init)
        army:=objectsForKey(st.Init,"army_formation")
        templates:=objectsForKey(st.Init,"formation_template")
        refs:=map[int64]bool{}
        for _,a:=range st.DroneArrays{collectPrivateRefs(a.Value,refs)}
        fmt.Fprintf(f,"DRONE_PRIVATE_REFS_UNIQUE=%d\n",len(refs))
        fmt.Fprintf(f,"ARMY_DRONE_PRIVATE_REF_MATCHES=%d\n",countMatchesObjects(army,refs))
        fmt.Fprintf(f,"TEMPLATE_DRONE_PRIVATE_REF_MATCHES=%d\n",countMatchesObjects(templates,refs))
        if len(refs)>0 && countMatchesObjects(army,refs)==0 && countMatchesObjects(templates,refs)==0 {
            fmt.Fprintln(f,"DRONE_FORMATION_LINK_MODEL=no_private_reference_match_global_or_implicit")
        } else if countMatchesObjects(army,refs)>0 || countMatchesObjects(templates,refs)>0 {
            fmt.Fprintln(f,"DRONE_FORMATION_LINK_MODEL=explicit_private_reference_match_detected")
        } else {
            fmt.Fprintln(f,"DRONE_FORMATION_LINK_MODEL=no_drone_private_reference_available")
        }
    }

    fmt.Printf("HITS=%d DRONE_ARRAYS=%d BATTLECARD_ARRAYS=%d COMMANDS=%d\n",len(st.Hits),len(st.DroneArrays),len(st.BattleArrays),len(st.Commands))
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func scanStream(buf []byte,dir string,st *state){
    r:=bytes.NewReader(buf)
    for {
        body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){return};return}
        outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
        pv,ok:=outer.Get("p");if !ok{continue}
        ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil{continue}
        cmd:=ext.GetString("c");if cmd==""{cmd="(no-command)"}
        pp,ok:=ext.Get("p");if !ok{continue}
        params,ok:=pp.Val.(*sfs.SFSObject);if !ok||params==nil{continue}
        if cmd=="init" && st.Init==nil{st.Init=params}
        walk(params,"p",cmd,dir,st)
    }
}

func walk(o *sfs.SFSObject,path,cmd,dir string,st *state){
    if o==nil{return}
    for _,k:=range o.Keys(){
        sv,_:=o.Get(k);p:=path+"."+k;l:=strings.ToLower(k)
        matched:=strings.Contains(l,"drone")||strings.Contains(l,"uav")||strings.Contains(l,"battlecard")||strings.Contains(l,"battle_card")
        if matched {
            st.Hits=append(st.Hits,hit{cmd,dir,p,shapeOf(sv.Val)})
            st.Commands[cmd]++
        }
        if strings.EqualFold(k,"droneSkillArr") {st.DroneArrays=append(st.DroneArrays,arrayDump{cmd,dir,p,sv.Val})}
        if strings.EqualFold(k,"userBattleCards") {st.BattleArrays=append(st.BattleArrays,arrayDump{cmd,dir,p,sv.Val})}
        walkValue(sv.Val,p,cmd,dir,st)
    }
}
func walkValue(v any,path,cmd,dir string,st *state){
    switch x:=v.(type){
    case *sfs.SFSObject:walk(x,path,cmd,dir,st)
    case *sfs.SFSArray:
        if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{walk(o,path+"[]",cmd,dir,st)}}}
    }
}

func printArraySafe(w io.Writer,v any,indent string){
    a,ok:=v.(*sfs.SFSArray);if !ok||a==nil{fmt.Fprintf(w,"%sshape=%s\n",indent,shapeOf(v));return}
    fmt.Fprintf(w,"%scount=%d\n",indent,len(a.Items()))
    sigs:=map[string]int{}
    for i,it:=range a.Items(){
        o,ok:=it.Val.(*sfs.SFSObject);if !ok||o==nil{continue}
        ks:=append([]string{},o.Keys()...);sort.Strings(ks);sigs[strings.Join(ks,",")]++
        vals:=[]string{}
        for _,k:=range ks{
            if !safeField(k){continue};sv,_:=o.Get(k);if s,ok:=scalarString(sv.Val);ok{vals=append(vals,k+"="+s)}
        }
        if len(vals)>0{fmt.Fprintf(w,"%sitem=%d %s\n",indent,i+1,strings.Join(vals," "))}
    }
    sk:=sortedKeys(sigs);for _,s:=range sk{fmt.Fprintf(w,"%ssignature_count=%d keys=%s\n",indent,sigs[s],s)}
}
func safeField(k string)bool{
    l:=strings.ToLower(k)
    if strings.Contains(l,"uuid")||strings.Contains(l,"guid")||l=="uid"||strings.HasSuffix(l,"uid")||strings.Contains(l,"owner")||strings.Contains(l,"token")||strings.Contains(l,"login")||strings.Contains(l,"secret"){return false}
    switch l {case "cfgid","cardid","skillid","level","lv","star","num","slot","exp","equipgroup","state","status","type","power","ranklv":return true}
    return false
}
func scalarString(v any)(string,bool){switch x:=v.(type){case int64:return strconv.FormatInt(x,10),true;case int32:return strconv.FormatInt(int64(x),10),true;case int16:return strconv.FormatInt(int64(x),10),true;case byte:return strconv.FormatInt(int64(x),10),true;case float32:return strconv.FormatFloat(float64(x),'f',-1,32),true;case float64:return strconv.FormatFloat(x,'f',-1,64),true;case bool:return strconv.FormatBool(x),true};return "",false}

func printBattlePower(w io.Writer,init *sfs.SFSObject){
    pv,ok:=init.Get("playerInfo");if !ok{fmt.Fprintln(w,"  playerInfo absent");return}
    po,ok:=pv.Val.(*sfs.SFSObject);if !ok||po==nil{fmt.Fprintln(w,"  playerInfo invalid");return}
    total:=num(po,"battleCardPower")
    fmt.Fprintf(w,"  battleCardPower=%d\n",total)
    dv,ok:=po.Get("powerDetail");if !ok{return};d,ok:=dv.Val.(*sfs.SFSObject);if !ok||d==nil{return}
    sum:=int64(0)
    for _,k:=range []string{"battleCardBasePower","battleCardLevelPower","battleCardStarPower"}{n:=num(d,k);sum+=n;fmt.Fprintf(w,"  %s=%d\n",k,n)}
    fmt.Fprintf(w,"  component_sum=%d\n",sum)
    fmt.Fprintf(w,"  difference=%d\n",total-sum)
}

func collectPrivateRefs(v any,out map[int64]bool){
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return};for _,k:=range x.Keys(){sv,_:=x.Get(k);l:=strings.ToLower(k);if strings.Contains(l,"uuid")||strings.Contains(l,"guid"){if n,ok:=asInt64(sv.Val);ok&&n!=0{out[n]=true}};collectPrivateRefs(sv.Val,out)}
    case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){collectPrivateRefs(it.Val,out)}}
    }
}
func countMatchesObjects(objs []*sfs.SFSObject,targets map[int64]bool)int{n:=0;for _,o:=range objs{n+=countMatches(o,targets)};return n}
func countMatches(v any,t map[int64]bool)int{n:=0;switch x:=v.(type){case *sfs.SFSObject:if x!=nil{for _,k:=range x.Keys(){sv,_:=x.Get(k);n+=countMatches(sv.Val,t)}};case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){n+=countMatches(it.Val,t)}};case []int64:for _,q:=range x{if t[q]{n++}};case []int32:for _,q:=range x{if t[int64(q)]{n++}};case int64:if t[x]{n++};case int32:if t[int64(x)]{n++};case string:if q,e:=strconv.ParseInt(x,10,64);e==nil&&t[q]{n++}};return n}
func asInt64(v any)(int64,bool){switch x:=v.(type){case int64:return x,true;case int32:return int64(x),true;case int16:return int64(x),true;case byte:return int64(x),true;case string:n,e:=strconv.ParseInt(x,10,64);return n,e==nil};return 0,false}

func shapeOf(v any)string{switch x:=v.(type){case *sfs.SFSObject:if x==nil{return "SFSObject(nil)"};return fmt.Sprintf("SFSObject[%d]",len(x.Keys()));case *sfs.SFSArray:if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()));case []int64:return fmt.Sprintf("[]int64[%d]",len(x));case []int32:return fmt.Sprintf("[]int32[%d]",len(x));case []int16:return fmt.Sprintf("[]int16[%d]",len(x));case []byte:return fmt.Sprintf("[]byte[%d]",len(x));case []string:return fmt.Sprintf("[]string[%d]",len(x));default:return fmt.Sprintf("%T",v)}}
func dedupeHits(in []hit)[]hit{m:=map[string]hit{};for _,h:=range in{k:=h.Command+"|"+h.Direction+"|"+h.Path+"|"+h.Shape;m[k]=h};out:=make([]hit,0,len(m));for _,h:=range m{out=append(out,h)};sort.Slice(out,func(i,j int)bool{if out[i].Command!=out[j].Command{return out[i].Command<out[j].Command};return out[i].Path<out[j].Path});return out}
func dedupeArrays(in []arrayDump)[]arrayDump{m:=map[string]arrayDump{};for _,a:=range in{k:=a.Command+"|"+a.Direction+"|"+a.Path;m[k]=a};out:=make([]arrayDump,0,len(m));for _,a:=range m{out=append(out,a)};sort.Slice(out,func(i,j int)bool{return out[i].Path<out[j].Path});return out}
func sortedKeys[T any](m map[string]T)[]string{ks:=make([]string,0,len(m));for k:=range m{ks=append(ks,k)};sort.Strings(ks);return ks}

func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func num(o *sfs.SFSObject,k string)int64{sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n);case string:x,e:=strconv.ParseInt(n,10,64);if e==nil{return x}};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase14:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase14-drone-discovery
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 14 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE14_FULL_PCAP_DRONE_DISCOVERY_REDACTED.txt"
