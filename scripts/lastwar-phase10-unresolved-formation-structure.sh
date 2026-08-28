#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 10
# OFFLINE ONLY. Describes the STRUCTURE of unresolved entries in formation
# heroes arrays without exporting any raw IDs/UUIDs or other field values.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE10_UNRESOLVED_STRUCTURE_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase10-unresolved-structure"
HELPER="${BASE}/wfgg-phase10-unresolved-structure"

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

say "=== WfGg Last War LAB · PHASE 10 ==="
say "Mode: OFFLINE / structure des références non résolues / aucune connexion Last War"
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
    "strings"
)

type formation struct {
    Kind string
    Index int64
    Squad int64
    Slots int64
    Obj *sfs.SFSObject
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj,err:=findInit(os.Args[1]); if err!=nil{fatal(err)}

    heroMap:=map[int64]int64{}
    heroSet:=map[int64]bool{}
    for _,o:=range objectsForKey(initObj,"userHero"){
        id:=num(o,"heroId"); if id==0{continue}; heroSet[id]=true
        if u:=num(o,"uuid");u!=0{heroMap[u]=id}
    }

    var forms []formation
    for _,o:=range objectsForKey(initObj,"army_formation"){
        forms=append(forms,formation{"ARMY",firstNum(o,"index"),firstNum(o,"squadNo"),firstNum(o,"slots"),o})
    }
    for _,o:=range objectsForKey(initObj,"formation_template"){
        forms=append(forms,formation{"TEMPLATE",firstNum(o,"index"),firstNum(o,"squadNo"),firstNum(o,"slots"),o})
    }
    sort.SliceStable(forms,func(i,j int)bool{if forms[i].Kind!=forms[j].Kind{return forms[i].Kind<forms[j].Kind};if forms[i].Squad!=forms[j].Squad{return forms[i].Squad<forms[j].Squad};return forms[i].Index<forms[j].Index})

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600);if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 10 UNRESOLVED FORMATION STRUCTURE")
    fmt.Fprintln(f,"OFFLINE ONLY · raw unresolved IDs/UUIDs and all field values suppressed")
    fmt.Fprintln(f)

    total:=0
    signatures:=map[string]int{}
    for _,form:=range forms{
        sv,ok:=form.Obj.Get("heroes");if !ok{continue}
        arr,ok:=sv.Val.(*sfs.SFSArray);if !ok||arr==nil{continue}
        unresolvedHere:=0
        for pos,item:=range arr.Items(){
            refs,refKey:=refsForItem(item.Val)
            itemUnresolved:=0
            for _,raw:=range refs{
                if raw==0{continue}
                if _,ok:=heroMap[raw];ok{continue}
                if heroSet[raw]{continue}
                itemUnresolved++
            }
            if itemUnresolved==0{continue}
            unresolvedHere+=itemUnresolved;total+=itemUnresolved
            sig:=signature(item.Val,refKey)
            signatures[sig]+=itemUnresolved
            fmt.Fprintf(f,"%s index=%d squad=%d slots=%d item_position=%d unresolved_refs=%d structure=%s\n",form.Kind,form.Index,form.Squad,form.Slots,pos+1,itemUnresolved,sig)
        }
        if unresolvedHere>0{fmt.Fprintln(f)}
    }

    fmt.Fprintln(f,"SIGNATURE_COUNTS")
    keys:=make([]string,0,len(signatures));for k:=range signatures{keys=append(keys,k)};sort.Strings(keys)
    for _,k:=range keys{fmt.Fprintf(f,"  count=%d structure=%s\n",signatures[k],k)}
    fmt.Fprintf(f,"\nSUMMARY unresolved=%d distinct_structures=%d\n",total,len(signatures))
    fmt.Printf("UNRESOLVED=%d DISTINCT_STRUCTURES=%d\n",total,len(signatures))
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func refsForItem(v any)([]int64,string){
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return nil,"object:nil"}
        for _,k:=range []string{"heroId","heroUuid","uuid","heroUid","uid"}{if n:=num(x,k);n!=0{return []int64{n},k}}
        return nil,"none"
    case int64:return []int64{x},"scalar:int64"
    case int32:return []int64{int64(x)},"scalar:int32"
    case int16:return []int64{int64(x)},"scalar:int16"
    case byte:return []int64{int64(x)},"scalar:byte"
    case []int64:return x,"array:int64"
    case []int32:out:=make([]int64,len(x));for i,n:=range x{out[i]=int64(n)};return out,"array:int32"
    case []int16:out:=make([]int64,len(x));for i,n:=range x{out[i]=int64(n)};return out,"array:int16"
    case []byte:out:=make([]int64,len(x));for i,n:=range x{out[i]=int64(n)};return out,"array:byte"
    }
    return nil,"none"
}

func signature(v any,refKey string)string{
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return "SFSObject(nil)"}
        parts:=make([]string,0,len(x.Keys()))
        keys:=append([]string(nil),x.Keys()...);sort.Strings(keys)
        for _,k:=range keys{sv,_:=x.Get(k);parts=append(parts,fmt.Sprintf("%s:t%d",safeKey(k),sv.Type))}
        return fmt.Sprintf("SFSObject refKey=%s keys=[%s]",safeKey(refKey),strings.Join(parts,","))
    case *sfs.SFSArray:
        if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()))
    default:return fmt.Sprintf("%T refKey=%s",v,safeKey(refKey))
    }
}

func safeKey(k string)string{
    if k==""{return "none"}
    var b strings.Builder
    for _,r:=range k{if (r>='a'&&r<='z')||(r>='A'&&r<='Z')||(r>='0'&&r<='9')||r=='_'{b.WriteRune(r)}}
    if b.Len()==0{return "other"};return b.String()
}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err};pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){if conv.TLS{continue};client,err:=conv.Client(netip.Addr{});if err!=nil{continue};_,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c);for{body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break};outer,err:=sfs.DecodeObject(body);if err!=nil{continue};pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue};pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}}}
    return nil,fmt.Errorf("init Last War introuvable")
}
func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{var out []*sfs.SFSObject;switch x:=v.Val.(type){case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}};case *sfs.SFSObject:if x==nil{return out};for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}};out=append(out,x)};return out}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n)};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase10:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase10-unresolved-structure
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 10 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE10_UNRESOLVED_STRUCTURE_REDACTED.txt"
