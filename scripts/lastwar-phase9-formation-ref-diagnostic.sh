#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 9
# OFFLINE ONLY. Classifies formation references by source field (heroes/tmpHeroes)
# and reports counts/shapes only. Raw UUIDs/IDs that do not resolve are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE9_FORMATION_REFS_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase9-formation-refs"
HELPER="${BASE}/wfgg-phase9-formation-refs"

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

say "=== WfGg Last War LAB · PHASE 9 ==="
say "Mode: OFFLINE / diagnostic formations / aucune connexion Last War"
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
)

type fieldStats struct {
    Present bool
    TypeTag byte
    Shape string
    RawRefs int
    Resolved int
    Unresolved int
}

type row struct {
    Kind string
    Index int64
    SquadNo int64
    Slots int64
    Heroes fieldStats
    Tmp fieldStats
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj,err:=findInit(os.Args[1]); if err!=nil{fatal(err)}

    heroMap:=map[int64]int64{}
    heroSet:=map[int64]bool{}
    for _,o:=range objectsForKey(initObj,"userHero") {
        id:=num(o,"heroId"); if id==0{continue}
        heroSet[id]=true
        if uuid:=num(o,"uuid"); uuid!=0 { heroMap[uuid]=id }
    }

    var rows []row
    for _,o:=range objectsForKey(initObj,"army_formation") {
        rows=append(rows,row{Kind:"ARMY",Index:firstNum(o,"index"),SquadNo:firstNum(o,"squadNo"),Slots:firstNum(o,"slots"),Heroes:analyse(o,"heroes",heroMap,heroSet),Tmp:analyse(o,"tmpHeroes",heroMap,heroSet)})
    }
    for _,o:=range objectsForKey(initObj,"formation_template") {
        rows=append(rows,row{Kind:"TEMPLATE",Index:firstNum(o,"index"),SquadNo:firstNum(o,"squadNo"),Slots:firstNum(o,"slots"),Heroes:analyse(o,"heroes",heroMap,heroSet),Tmp:analyse(o,"tmpHeroes",heroMap,heroSet)})
    }
    sort.SliceStable(rows,func(i,j int)bool{if rows[i].Kind!=rows[j].Kind{return rows[i].Kind<rows[j].Kind};if rows[i].SquadNo!=rows[j].SquadNo{return rows[i].SquadNo<rows[j].SquadNo};return rows[i].Index<rows[j].Index})

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600); if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 9 FORMATION REF DIAGNOSTIC")
    fmt.Fprintln(f,"OFFLINE ONLY · no raw unresolved values exported")
    fmt.Fprintln(f)
    totalMainUnresolved,totalTmpUnresolved:=0,0
    for _,r:=range rows {
        fmt.Fprintf(f,"%s index=%d squad=%d slots=%d\n",r.Kind,r.Index,r.SquadNo,r.Slots)
        printField(f,"heroes",r.Heroes)
        printField(f,"tmpHeroes",r.Tmp)
        mainMissing:=int(r.Slots)-r.Heroes.Resolved
        if mainMissing<0 {mainMissing=0}
        fmt.Fprintf(f,"  main_slots_missing_after_resolution=%d\n\n",mainMissing)
        totalMainUnresolved+=r.Heroes.Unresolved
        totalTmpUnresolved+=r.Tmp.Unresolved
    }
    fmt.Fprintf(f,"SUMMARY main_unresolved=%d tmp_unresolved=%d total=%d\n",totalMainUnresolved,totalTmpUnresolved,totalMainUnresolved+totalTmpUnresolved)
    fmt.Printf("MAIN_UNRESOLVED=%d TMP_UNRESOLVED=%d TOTAL=%d\n",totalMainUnresolved,totalTmpUnresolved,totalMainUnresolved+totalTmpUnresolved)
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func printField(w io.Writer,name string,s fieldStats){
    if !s.Present {fmt.Fprintf(w,"  %s: absent\n",name);return}
    fmt.Fprintf(w,"  %s: typeTag=%d shape=%s rawRefs=%d resolved=%d unresolved=%d\n",name,s.TypeTag,s.Shape,s.RawRefs,s.Resolved,s.Unresolved)
}

func analyse(o *sfs.SFSObject,key string,heroMap map[int64]int64,heroSet map[int64]bool) fieldStats {
    sv,ok:=o.Get(key); if !ok{return fieldStats{}}
    refs:=flattenRefs(sv.Val)
    s:=fieldStats{Present:true,TypeTag:sv.Type,Shape:shapeOf(sv.Val),RawRefs:len(refs)}
    for _,raw:=range refs {
        if raw==0 {continue}
        if _,ok:=heroMap[raw];ok{s.Resolved++;continue}
        if heroSet[raw]{s.Resolved++;continue}
        s.Unresolved++
    }
    return s
}

func shapeOf(v any) string {
    switch x:=v.(type){
    case *sfs.SFSArray: if x==nil{return "SFSArray(nil)"}; return fmt.Sprintf("SFSArray[%d]",len(x.Items()))
    case *sfs.SFSObject: if x==nil{return "SFSObject(nil)"}; return fmt.Sprintf("SFSObject[%d keys]",len(x.Keys()))
    case []int64:return fmt.Sprintf("[]int64[%d]",len(x)); case []int32:return fmt.Sprintf("[]int32[%d]",len(x)); case []int16:return fmt.Sprintf("[]int16[%d]",len(x)); case []byte:return fmt.Sprintf("[]byte[%d]",len(x)); case []string:return fmt.Sprintf("[]string[%d]",len(x));
    default:return fmt.Sprintf("%T",v)
    }
}

func flattenRefs(v any)[]int64{
    var out []int64
    switch x:=v.(type){
    case *sfs.SFSArray:
        if x==nil{return out}; for _,it:=range x.Items(){out=append(out,flattenRefs(it.Val)...)}
    case *sfs.SFSObject:
        if x==nil{return out}
        if id:=firstNum(x,"heroId");id!=0{return []int64{id}}
        if id:=firstNum(x,"heroUuid","uuid","heroUid","uid");id!=0{return []int64{id}}
        for _,k:=range x.Keys(){sv,_:=x.Get(k);out=append(out,flattenRefs(sv.Val)...)}
    case []int64: out=append(out,x...)
    case []int32: for _,n:=range x{out=append(out,int64(n))}
    case []int16: for _,n:=range x{out=append(out,int64(n))}
    case []byte: for _,n:=range x{out=append(out,int64(n))}
    case []string: for _,s:=range x{if n,err:=strconv.ParseInt(s,10,64);err==nil{out=append(out,n)}}
    case int64:out=append(out,x); case int32:out=append(out,int64(x)); case int16:out=append(out,int64(x)); case byte:out=append(out,int64(x)); case string:if n,err:=strconv.ParseInt(x,10,64);err==nil{out=append(out,n)}
    }
    return out
}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err}
    pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){if conv.TLS{continue};client,err:=conv.Client(netip.Addr{});if err!=nil{continue};_,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c);for{body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break};outer,err:=sfs.DecodeObject(body);if err!=nil{continue};pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue};pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}}}
    return nil,fmt.Errorf("init Last War introuvable")
}
func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n)};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase9:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase9-formation-refs
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 9 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE9_FORMATION_REFS_REDACTED.txt"
