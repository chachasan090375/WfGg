#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 17
# OFFLINE ONLY. Tests whether the internal weaponArr / weapon* power subsystem is
# the strongest candidate for the global Drone core, without declaring semantic
# identity unless the captured data supports it. Raw UUID/GUID/UID/credentials
# are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE17_WEAPON_DRONE_CORRELATION_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase17-weapon-drone"
HELPER="${BASE}/wfgg-phase17-weapon-drone"

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

say "=== WfGg Last War LAB · PHASE 17 ==="
say "Mode: OFFLINE / corrélation weaponArr ↔ Drone"
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

type state struct {
    Init *sfs.SFSObject
    ChipData *sfs.SFSObject
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    data,err:=os.ReadFile(os.Args[1]); if err!=nil{fatal(err)}
    pkts,err:=pcap.Parse(data); if err!=nil{fatal(err)}
    st:=state{}
    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        _,s2c:=conv.Reassemble(client)
        scan(s2c,&st)
    }
    if st.Init==nil{fatal(fmt.Errorf("init Last War introuvable"))}

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600);if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 17 WEAPON/DRONE CORRELATION")
    fmt.Fprintln(f,"OFFLINE ONLY · raw UUID/GUID/UID/credential values suppressed")
    fmt.Fprintln(f)

    weapons:=objectsForKey(st.Init,"weaponArr")
    fmt.Fprintln(f,"WEAPONARR_SAFE_MODEL")
    fmt.Fprintf(f,"  count=%d\n",len(weapons))
    for i,o:=range weapons{
        ks:=append([]string{},o.Keys()...);sort.Strings(ks)
        fmt.Fprintf(f,"  item=%d keys=%s\n",i+1,strings.Join(ks,","))
        for _,k:=range ks{
            if !safeField(k){continue}
            v,_:=o.Get(k);if s,ok:=scalar(v.Val);ok{fmt.Fprintf(f,"    %s=%s\n",k,s)}
        }
    }

    player:=objectForKey(st.Init,"playerInfo")
    detail:=objectForKey(player,"powerDetail")
    fmt.Fprintln(f,"\nWEAPON_POWER_DETAIL")
    componentSum:=int64(0)
    componentCount:=0
    if detail==nil{fmt.Fprintln(f,"  powerDetail absent")}
    if detail!=nil{
        ks:=append([]string{},detail.Keys()...);sort.Strings(ks)
        for _,k:=range ks{
            if !strings.HasPrefix(strings.ToLower(k),"weapon"){continue}
            v,_:=detail.Get(k)
            if s,ok:=scalar(v.Val);ok{fmt.Fprintf(f,"  %s=%s\n",k,s)}
            lk:=strings.ToLower(k)
            if strings.HasSuffix(lk,"power") && !strings.HasSuffix(lk,"powerrate"){
                if n,ok:=asInt64(v.Val);ok{componentSum+=n;componentCount++}
            }
        }
    }
    fmt.Fprintf(f,"  componentPowerFields=%d\n",componentCount)
    fmt.Fprintf(f,"  componentPowerSum=%d\n",componentSum)
    weaponPower:=int64(0)
    if len(weapons)>0{weaponPower=num(weapons[0],"power")}
    fmt.Fprintf(f,"  weaponArrPower=%d\n",weaponPower)
    fmt.Fprintf(f,"  difference=weaponArrPower-componentPowerSum=%d\n",weaponPower-componentSum)

    fmt.Fprintln(f,"\nCHIP_DATA_CONTEXT")
    if st.ChipData==nil{fmt.Fprintln(f,"  chip.data absent")}
    if st.ChipData!=nil{
        for _,k:=range []string{"curEquipGroup","chipUnlock","chipOpenTime","chipPreviewTime"}{
            if v,ok:=st.ChipData.Get(k);ok{if s,ok:=scalar(v.Val);ok{fmt.Fprintf(f,"  %s=%s\n",k,s)}}
        }
        if v,ok:=st.ChipData.Get("skillChipGroup");ok{
            fmt.Fprintf(f,"  skillChipGroupShape=%s\n",shapeOf(v.Val))
            if a,ok:=v.Val.(*sfs.SFSArray);ok&&a!=nil{
                for i,it:=range a.Items(){if s,ok:=scalar(it.Val);ok{fmt.Fprintf(f,"  skillChipGroup[%d]=%s\n",i,s)}}
            }
        }
        if v,ok:=st.ChipData.Get("droneSkillArr");ok{fmt.Fprintf(f,"  droneSkillArrShape=%s\n",shapeOf(v.Val))}
    }

    fmt.Fprintln(f,"\nGLOBALITY_AND_CORRELATION")
    fmt.Fprintf(f,"  weaponArrObjects=%d\n",len(weapons))
    fmt.Fprintf(f,"  activeArmyFormations=%d\n",len(objectsForKey(st.Init,"army_formation")))
    fmt.Fprintf(f,"  droneSkillEntries=%d\n",arrayLen(st.ChipData,"droneSkillArr"))
    fmt.Fprintf(f,"  weaponSubsystemHasLevel=%t\n",len(weapons)>0&&num(weapons[0],"level")>0)
    fmt.Fprintf(f,"  weaponSubsystemHasChipProgress=%t\n",len(weapons)>0&&(num(weapons[0],"chipLv")>0||num(weapons[0],"chipExp")>0))
    fmt.Fprintf(f,"  weaponPowerExactlyExplained=%t\n",weaponPower>0&&componentCount>0&&weaponPower==componentSum)

    fmt.Fprintln(f,"\nINTERPRETATION")
    strong:=len(weapons)==1 && num(weapons[0],"level")>0 && num(weapons[0],"chipLv")>0 && arrayLen(st.ChipData,"droneSkillArr")>0
    if strong{
        fmt.Fprintln(f,"  hypothesis=weaponArr_is_strong_global_drone_core_candidate")
        fmt.Fprintln(f,"  confidence=strong_protocol_correlation_but_semantic_label_not_yet_proven")
    }else{
        fmt.Fprintln(f,"  hypothesis=weaponArr_drone_core_link_not_established")
        fmt.Fprintln(f,"  confidence=insufficient")
    }
    fmt.Fprintln(f,"  guardrail=do_not_rename_weaponArr_to_Drone_until_an_independent_correlation_confirms_the_UI_semantics")

    fmt.Printf("WEAPON_OBJECTS=%d COMPONENT_FIELDS=%d OUTPUT=%s\n",len(weapons),componentCount,os.Args[2])
}

func scan(buf []byte,st *state){
    r:=bytes.NewReader(buf)
    for{
        body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){return};return}
        outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
        pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil{continue}
        cmd:=ext.GetString("c");pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if !ok||params==nil{continue}
        if cmd=="init"&&st.Init==nil{st.Init=params}
        if cmd=="chip.data"&&st.ChipData==nil{st.ChipData=params}
    }
}

func objectForKey(o *sfs.SFSObject,key string)*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};x,_:=v.Val.(*sfs.SFSObject);return x}
func objectsForKey(o *sfs.SFSObject,key string)[]*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};a,ok:=v.Val.(*sfs.SFSArray);if !ok||a==nil{return nil};out:=[]*sfs.SFSObject{};for _,it:=range a.Items(){if x,ok:=it.Val.(*sfs.SFSObject);ok&&x!=nil{out=append(out,x)}};return out}
func arrayLen(o *sfs.SFSObject,key string)int{if o==nil{return 0};v,ok:=o.Get(key);if !ok{return 0};a,ok:=v.Val.(*sfs.SFSArray);if !ok||a==nil{return 0};return len(a.Items())}
func safeField(k string)bool{l:=strings.ToLower(k);if strings.Contains(l,"uuid")||strings.Contains(l,"guid")||l=="uid"||strings.HasSuffix(l,"uid")||strings.Contains(l,"token")||strings.Contains(l,"login")||strings.Contains(l,"secret")||strings.Contains(l,"email")||strings.Contains(l,"name"){return false};switch l{case "level","power","exp","chiplv","chipexp","skill","skilllevel","state","status","type","cfgid":return true};return false}
func num(o *sfs.SFSObject,k string)int64{if o==nil{return 0};v,ok:=o.Get(k);if !ok{return 0};n,_:=asInt64(v.Val);return n}
func asInt64(v any)(int64,bool){switch x:=v.(type){case int64:return x,true;case int32:return int64(x),true;case int16:return int64(x),true;case byte:return int64(x),true;case string:n,e:=strconv.ParseInt(x,10,64);return n,e==nil};return 0,false}
func scalar(v any)(string,bool){switch x:=v.(type){case int64:return strconv.FormatInt(x,10),true;case int32:return strconv.FormatInt(int64(x),10),true;case int16:return strconv.FormatInt(int64(x),10),true;case byte:return strconv.FormatInt(int64(x),10),true;case bool:return strconv.FormatBool(x),true;case string:if len(x)<=80{return x,true}};return "",false}
func shapeOf(v any)string{switch x:=v.(type){case *sfs.SFSObject:if x==nil{return "SFSObject(nil)"};return fmt.Sprintf("SFSObject[%d]",len(x.Keys()));case *sfs.SFSArray:if x==nil{return "SFSArray(nil)"};return fmt.Sprintf("SFSArray[%d]",len(x.Items()));case []int64:return fmt.Sprintf("[]int64[%d]",len(x));case []int32:return fmt.Sprintf("[]int32[%d]",len(x));case []int16:return fmt.Sprintf("[]int16[%d]",len(x));case []byte:return fmt.Sprintf("[]byte[%d]",len(x));case []string:return fmt.Sprintf("[]string[%d]",len(x));default:return fmt.Sprintf("%T",v)}}
func fatal(err error){fmt.Fprintln(os.Stderr,"ERREUR:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase17-weapon-drone
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT"
rm -f "$HELPER"

say "=== PHASE 17 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE17_WEAPON_DRONE_CORRELATION_REDACTED.txt"
