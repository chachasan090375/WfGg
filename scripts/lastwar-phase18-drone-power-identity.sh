#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 18
# OFFLINE ONLY. Cross-checks the internal weapon/equip/chip power model against
# squadEquipPower and the explicitly named droneSkillArr payload.
# Raw UUID/GUID/UID/credentials are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE18_DRONE_POWER_IDENTITY_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase18-drone-power"
HELPER="${BASE}/wfgg-phase18-drone-power"

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

say "=== WfGg Last War LAB · PHASE 18 ==="
say "Mode: OFFLINE / preuve identité puissance Drone"
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

    player:=objectForKey(st.Init,"playerInfo")
    detail:=objectForKey(player,"powerDetail")
    weapons:=objectsForKey(st.Init,"weaponArr")
    equips:=objectsForKey(st.Init,"equipList")

    weaponArrPower:=int64(0)
    weaponLv:=int64(0)
    weaponExp:=int64(0)
    chipLv:=int64(0)
    chipExp:=int64(0)
    skill:=int64(0)
    skillLevel:=int64(0)
    if len(weapons)>0{
        weaponArrPower=num(weapons[0],"power")
        weaponLv=firstNum(weapons[0],"lv","lev","level")
        weaponExp=num(weapons[0],"exp")
        chipLv=num(weapons[0],"chipLv")
        chipExp=num(weapons[0],"chipExp")
        skill=num(weapons[0],"skill")
        skillLevel=num(weapons[0],"skillLevel")
    }

    equipSum:=int64(0)
    for _,e:=range equips{equipSum+=num(e,"power")}
    weaponEquipPower:=num(detail,"weaponEquipPower")
    weaponLevelPower:=num(detail,"weaponLevelPower")
    weaponChipPower:=num(detail,"weaponChipPower")
    squadEquipPower:=num(player,"squadEquipPower")

    eqEquip:=equipSum==weaponEquipPower && equipSum>0
    baseDelta:=(weaponLevelPower+weaponEquipPower)-weaponArrPower
    eqBase:=weaponArrPower>0 && abs(baseDelta)<=1
    eqTotal:=weaponArrPower+weaponChipPower==squadEquipPower && squadEquipPower>0
    droneChips:=arrayLen(st.ChipData,"droneSkillArr")
    semanticChipLink:=droneChips>0 && weaponChipPower>0

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600);if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 18 DRONE POWER IDENTITY")
    fmt.Fprintln(f,"OFFLINE ONLY · raw UUID/GUID/UID/credential values suppressed")
    fmt.Fprintln(f)

    fmt.Fprintln(f,"GLOBAL_WEAPON_OBJECT")
    fmt.Fprintf(f,"  weaponArrObjects=%d\n",len(weapons))
    fmt.Fprintf(f,"  lv=%d\n",weaponLv)
    fmt.Fprintf(f,"  exp=%d\n",weaponExp)
    fmt.Fprintf(f,"  power=%d\n",weaponArrPower)
    fmt.Fprintf(f,"  chipLv=%d\n",chipLv)
    fmt.Fprintf(f,"  chipExp=%d\n",chipExp)
    fmt.Fprintf(f,"  skill=%d\n",skill)
    fmt.Fprintf(f,"  skillLevel=%d\n",skillLevel)

    fmt.Fprintln(f,"\nSIX_COMPONENTS")
    sort.Slice(equips,func(i,j int)bool{return num(equips[i],"slot")<num(equips[j],"slot")})
    for _,e:=range equips{
        fmt.Fprintf(f,"  slot=%d cfgId=%d power=%d exp=%d num=%d\n",num(e,"slot"),num(e,"cfgId"),num(e,"power"),num(e,"exp"),num(e,"num"))
    }
    fmt.Fprintf(f,"  equipListPowerSum=%d\n",equipSum)
    fmt.Fprintf(f,"  weaponEquipPower=%d\n",weaponEquipPower)
    fmt.Fprintf(f,"  exactMatch=%t\n",eqEquip)

    fmt.Fprintln(f,"\nPOWER_IDENTITIES")
    fmt.Fprintf(f,"  weaponLevelPower=%d\n",weaponLevelPower)
    fmt.Fprintf(f,"  weaponEquipPower=%d\n",weaponEquipPower)
    fmt.Fprintf(f,"  weaponChipPower=%d\n",weaponChipPower)
    fmt.Fprintf(f,"  weaponArrPower=%d\n",weaponArrPower)
    fmt.Fprintf(f,"  squadEquipPower=%d\n",squadEquipPower)
    fmt.Fprintf(f,"  weaponLevelPower_plus_weaponEquipPower=%d\n",weaponLevelPower+weaponEquipPower)
    fmt.Fprintf(f,"  baseDelta_vs_weaponArrPower=%d\n",baseDelta)
    fmt.Fprintf(f,"  baseIdentityWithinRounding=%t\n",eqBase)
    fmt.Fprintf(f,"  weaponArrPower_plus_weaponChipPower=%d\n",weaponArrPower+weaponChipPower)
    fmt.Fprintf(f,"  totalIdentityExact=%t\n",eqTotal)

    fmt.Fprintln(f,"\nDRONE_CHIP_SEMANTIC_LINK")
    fmt.Fprintf(f,"  droneSkillEntries=%d\n",droneChips)
    fmt.Fprintf(f,"  weaponChipPower=%d\n",weaponChipPower)
    fmt.Fprintf(f,"  explicitDroneNamedChipPayloadPresent=%t\n",droneChips>0)
    fmt.Fprintf(f,"  semanticChipLinkPresent=%t\n",semanticChipLink)

    score:=0
    if len(weapons)==1 && weaponLv>0{score++}
    if eqEquip{score++}
    if eqBase{score++}
    if eqTotal{score++}
    if semanticChipLink{score++}

    fmt.Fprintln(f,"\nINTERPRETATION")
    fmt.Fprintf(f,"  evidenceScore=%d/5\n",score)
    if score==5{
        fmt.Fprintln(f,"  protocolConclusion=internal_weapon_equip_chip_subsystem_is_single_global_squad_equipment_entity")
        fmt.Fprintln(f,"  uiSemanticConclusion=high_confidence_match_to_Drone_system")
        fmt.Fprintln(f,"  model=globalDrone(level+6_components+chip_progress)+per_formation_4_chip_preset")
    }else{
        fmt.Fprintln(f,"  protocolConclusion=correlation_incomplete")
        fmt.Fprintln(f,"  uiSemanticConclusion=do_not_finalize_Drone_mapping")
    }
    fmt.Fprintln(f,"  note=one-point base-power delta is treated as rounding only when total squadEquipPower identity is exact")

    fmt.Printf("EVIDENCE_SCORE=%d/5 OUTPUT=%s\n",score,os.Args[2])
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
func num(o *sfs.SFSObject,k string)int64{if o==nil{return 0};v,ok:=o.Get(k);if !ok{return 0};n,_:=asInt64(v.Val);return n}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func asInt64(v any)(int64,bool){switch x:=v.(type){case int64:return x,true;case int32:return int64(x),true;case int16:return int64(x),true;case byte:return int64(x),true;case string:n,e:=strconv.ParseInt(x,10,64);return n,e==nil};return 0,false}
func abs(n int64)int64{if n<0{return -n};return n}
func fatal(err error){fmt.Fprintln(os.Stderr,"ERREUR:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase18-drone-power
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT"
rm -f "$HELPER"

say "=== PHASE 18 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE18_DRONE_POWER_IDENTITY_REDACTED.txt"
