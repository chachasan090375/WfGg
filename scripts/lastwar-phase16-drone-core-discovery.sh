#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 16
# OFFLINE ONLY. Discovers safe Drone/core/chip topology across all decoded SFS packets.
# Raw UUID/GUID/UID/credentials are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE16_DRONE_CORE_DISCOVERY_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase16-drone-core"
HELPER="${BASE}/wfgg-phase16-drone-core"

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

say "=== WfGg Last War LAB · PHASE 16 ==="
say "Mode: OFFLINE / découverte Drone core + chip topology"
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

type found struct{ Command, Direction, Path, Shape string; Value any }

type state struct{ Items []found }

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    data,err:=os.ReadFile(os.Args[1]); if err!=nil{fatal(err)}
    pkts,err:=pcap.Parse(data); if err!=nil{fatal(err)}
    st:=state{}
    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{}); if err!=nil{continue}
        c2s,s2c:=conv.Reassemble(client)
        scan(c2s,"client_to_server",&st)
        scan(s2c,"server_to_client",&st)
    }
    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600); if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 16 DRONE CORE DISCOVERY")
    fmt.Fprintln(f,"OFFLINE ONLY · raw UUID/GUID/UID/credential values suppressed")
    fmt.Fprintln(f)

    items:=dedupe(st.Items)
    fmt.Fprintln(f,"DRONE_OR_CHIP_RELATED_PATHS")
    for _,x:=range items{
        fmt.Fprintf(f,"  command=%s direction=%s path=%s shape=%s",x.Command,x.Direction,x.Path,x.Shape)
        if s,ok:=safeScalarForPath(x.Path,x.Value);ok{fmt.Fprintf(f," value=%s",s)}
        fmt.Fprintln(f)
    }

    fmt.Fprintln(f,"\nCHIP_DATA_DETAIL")
    for _,x:=range items{
        if x.Command!="chip.data"{continue}
        lp:=strings.ToLower(x.Path)
        if strings.Contains(lp,"droneskillarr"){continue}
        fmt.Fprintf(f,"  path=%s shape=%s",x.Path,x.Shape)
        if s,ok:=safeScalarForPath(x.Path,x.Value);ok{fmt.Fprintf(f," value=%s",s)}
        fmt.Fprintln(f)
        printSafeObjectOrArray(f,x.Value,"    ",2)
    }

    fmt.Fprintln(f,"\nCANDIDATE_DRONE_CORE_OBJECTS")
    n:=0
    for _,x:=range items{
        lp:=strings.ToLower(x.Path)
        if strings.Contains(lp,"droneskillarr")||strings.Contains(lp,"battlecard") {continue}
        if !(strings.Contains(lp,"drone")||strings.Contains(lp,"uav")||strings.Contains(lp,"aircraft")) {continue}
        n++
        fmt.Fprintf(f,"  candidate=%d command=%s path=%s shape=%s\n",n,x.Command,x.Path,x.Shape)
        printSafeObjectOrArray(f,x.Value,"    ",2)
    }
    if n==0{fmt.Fprintln(f,"  (aucun objet core explicite trouvé par nom)")}

    fmt.Fprintln(f,"\nINTERPRETATION_GUARDRAILS")
    fmt.Fprintln(f,"  chipEquipGroup=per-formation drone-chip preset selector (confirmed in phase15)")
    fmt.Fprintln(f,"  curEquipGroup=chip.data client/current preset state; not automatically an army assignment")
    fmt.Fprintln(f,"  planeFeature*=candidate only; do not label as Drone core without cross-evidence")
    fmt.Fprintln(f,"  battle cards remain separate from drone chips")
    fmt.Printf("MATCHED_PATHS=%d OUTPUT=%s\n",len(items),os.Args[2])
}

func scan(buf []byte,dir string,st *state){
    r:=bytes.NewReader(buf)
    for{
        body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){return};return}
        outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
        pv,ok:=outer.Get("p");if !ok{continue}; ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil{continue}
        cmd:=ext.GetString("c");if cmd==""{cmd="(no-command)"}
        pp,ok:=ext.Get("p");if !ok{continue}; params,ok:=pp.Val.(*sfs.SFSObject);if !ok||params==nil{continue}
        walk(params,"p",cmd,dir,st)
    }
}

func walk(o *sfs.SFSObject,path,cmd,dir string,st *state){
    if o==nil{return}
    for _,k:=range o.Keys(){
        sv,_:=o.Get(k); p:=path+"."+k; l:=strings.ToLower(k)
        if related(l){st.Items=append(st.Items,found{cmd,dir,p,shapeOf(sv.Val),sv.Val})}
        switch x:=sv.Val.(type){
        case *sfs.SFSObject: walk(x,p,cmd,dir,st)
        case *sfs.SFSArray: if x!=nil{for _,it:=range x.Items(){if oo,ok:=it.Val.(*sfs.SFSObject);ok&&oo!=nil{walk(oo,p+"[]",cmd,dir,st)}}}
        }
    }
}

func related(l string)bool{
    terms:=[]string{"drone","uav","aircraft","chip","planefeature"}
    for _,t:=range terms{if strings.Contains(l,t){return true}}
    return false
}

func safeScalarForPath(path string,v any)(string,bool){
    k:=path[strings.LastIndex(path,".")+1:]
    if !safeField(k){return "",false}
    return scalar(v)
}

func safeField(k string)bool{
    l:=strings.ToLower(k)
    if strings.Contains(l,"uuid")||strings.Contains(l,"guid")||l=="uid"||strings.HasSuffix(l,"uid")||strings.Contains(l,"owner")||strings.Contains(l,"token")||strings.Contains(l,"login")||strings.Contains(l,"secret")||strings.Contains(l,"email")||strings.Contains(l,"name"){return false}
    switch l{
    case "cfgid","id","type","level","lv","ranklv","star","power","exp","num","slot","equipgroup","state","status","stage","step","curgroup","curequipgroup","chipunlock","chipopentime","chippreviewtime","skillid","skilllevel":return true
    }
    return strings.HasSuffix(l,"power")||strings.HasSuffix(l,"level")||strings.HasSuffix(l,"lv")
}

func printSafeObjectOrArray(w io.Writer,v any,indent string,depth int){
    if depth<0{return}
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return}; ks:=append([]string{},x.Keys()...);sort.Strings(ks)
        for _,k:=range ks{sv,_:=x.Get(k);if safeField(k){if s,ok:=scalar(sv.Val);ok{fmt.Fprintf(w,"%s%s=%s\n",indent,k,s)}}; if depth>0{switch sv.Val.(type){case *sfs.SFSObject,*sfs.SFSArray:fmt.Fprintf(w,"%s%s shape=%s\n",indent,k,shapeOf(sv.Val));printSafeObjectOrArray(w,sv.Val,indent+"  ",depth-1)}}}
    case *sfs.SFSArray:
        if x==nil{return};fmt.Fprintf(w,"%scount=%d\n",indent,len(x.Items()))
        limit:=len(x.Items());if limit>20{limit=20}
        for i:=0;i<limit;i++{it:=x.Items()[i];fmt.Fprintf(w,"%sitem=%d shape=%s\n",indent,i+1,shapeOf(it.Val));printSafeObjectOrArray(w,it.Val,indent+"  ",depth-1)}
        if len(x.Items())>limit{fmt.Fprintf(w,"%s... %d item(s) additional omitted\n",indent,len(x.Items())-limit)}
    }
}

func scalar(v any)(string,bool){switch x:=v.(type){case int64:return strconv.FormatInt(x,10),true;case int32:return strconv.FormatInt(int64(x),10),true;case int16:return strconv.FormatInt(int64(x),10),true;case byte:return strconv.FormatInt(int64(x),10),true;case float32:return strconv.FormatFloat(float64(x),'f',-1,32),true;case float64:return strconv.FormatFloat(x,'f',-1,64),true;case bool:return strconv.FormatBool(x),true;case string:if len(x)<=80{return x,true}};return "",false}
func shapeOf(v any)string{switch x:=v.(type){case *sfs.SFSObject:if x==nil{return "SFSObject(nil)"};return fmt.Sprintf("SFSObject[%d]",len(x.Keys()));case *sfs.SFSArray:if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()));case []int64:return fmt.Sprintf("[]int64[%d]",len(x));case []int32:return fmt.Sprintf("[]int32[%d]",len(x));case []int16:return fmt.Sprintf("[]int16[%d]",len(x));case []byte:return fmt.Sprintf("[]byte[%d]",len(x));case []string:return fmt.Sprintf("[]string[%d]",len(x));default:return fmt.Sprintf("%T",v)}}
func dedupe(in []found)[]found{m:=map[string]found{};for _,x:=range in{k:=x.Command+"|"+x.Direction+"|"+x.Path+"|"+x.Shape;m[k]=x};out:=make([]found,0,len(m));for _,x:=range m{out=append(out,x)};sort.Slice(out,func(i,j int)bool{if out[i].Command!=out[j].Command{return out[i].Command<out[j].Command};return out[i].Path<out[j].Path});return out}
func fatal(err error){fmt.Fprintln(os.Stderr,"ERREUR:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase16-drone-core
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT"
rm -f "$HELPER"

say "=== PHASE 16 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/$(basename "$OUT")"
