#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 19
# OFFLINE ONLY. Produces the module-ready V3 model after the Drone/Overlord
# topology was established by phases 11-18.
#
# V3 model:
#   squad = 5 heroes + global Drone + per-formation 4-chip preset + 0/1 Overlord
#
# Privacy:
# - no Last War network connection
# - no credentials, player/alliance names or resource balances
# - no raw hero/Dominator UUID/GUID/UID values are exported

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
PHASE8="${DOWNLOADS}/WFGG_LASTWAR_PHASE8_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
TMP_CMD="${SRC}/cmd/wfgg-phase19-normalized"
HELPER="${BASE}/wfgg-phase19-normalized"

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

if [[ ! -s "$PHASE8" ]]; then
  say "Phase 8 absente : génération hors ligne préalable…"
  bash "$HOME/wfgg-lastwar-preview/scripts/lastwar-phase8-formations-normalized.sh" "$CAPTURE"
fi
[[ -s "$PHASE8" ]] || die "fichier Phase 8 absent"

REAL_GO="${PREFIX:-/data/data/com.termux/files/usr}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 19 ==="
say "Mode: OFFLINE / modèle escouade V3"
say "Capture: $CAPTURE"

mkdir -p "$TMP_CMD"
cleanup(){ rm -rf "$TMP_CMD" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

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
    "strconv"
)

type state struct {
    Init     *sfs.SFSObject
    ChipData *sfs.SFSObject
}

type formationRow struct {
    Index              int64   `json:"index,omitempty"`
    SquadNo            int64   `json:"squadNo,omitempty"`
    Type               int64   `json:"type,omitempty"`
    Slots              int64   `json:"slots,omitempty"`
    State              int64   `json:"state,omitempty"`
    ChipEquipGroup     int64   `json:"chipEquipGroup,omitempty"`
    DefencePriority    int64   `json:"defencePriority,omitempty"`
    HeroIDs            []int64 `json:"heroIds,omitempty"`
    TmpHeroIDs         []int64 `json:"tmpHeroIds,omitempty"`
    OverlordOrdinals   []int   `json:"overlordOrdinals,omitempty"`
    SoldierEntries     int     `json:"soldierEntries,omitempty"`
    MissingHeroSlots   int     `json:"missingHeroSlots,omitempty"`
    UnresolvedRefs     int     `json:"unresolvedRefs,omitempty"`
}

type resolutionStats struct {
    ArmyHeroRefs       int `json:"armyHeroRefs"`
    TemplateHeroRefs   int `json:"templateHeroRefs"`
    ArmyOverlordRefs   int `json:"armyOverlordRefs"`
    TemplateOverlordRefs int `json:"templateOverlordRefs"`
    UnresolvedRefs     int `json:"unresolvedRefs"`
    MissingHeroSlots   int `json:"missingHeroSlots"`
}

type overlordRow struct {
    Ordinal     int   `json:"ordinal"`
    DominatorID int64 `json:"dominatorId,omitempty"`
    Power       int64 `json:"power,omitempty"`
    Rank        int64 `json:"rank,omitempty"`
    Level       int64 `json:"level,omitempty"`
    SkillCount  int   `json:"skillCount,omitempty"`
}

type droneComponent struct {
    Slot  int64 `json:"slot"`
    CfgID int64 `json:"cfgId"`
    Power int64 `json:"power,omitempty"`
    Exp   int64 `json:"exp,omitempty"`
    Num   int64 `json:"num,omitempty"`
}

type droneModel struct {
    Level                  int64            `json:"level,omitempty"`
    Exp                    int64            `json:"exp,omitempty"`
    BasePower              int64            `json:"basePower,omitempty"`
    ChipLevel              int64            `json:"chipLevel,omitempty"`
    ChipExp                int64            `json:"chipExp,omitempty"`
    SkillID                int64            `json:"skillId,omitempty"`
    SkillLevel             int64            `json:"skillLevel,omitempty"`
    LevelPower             int64            `json:"levelPower,omitempty"`
    ComponentPower         int64            `json:"componentPower,omitempty"`
    ChipPower              int64            `json:"chipPower,omitempty"`
    TotalSquadEquipPower   int64            `json:"totalSquadEquipPower,omitempty"`
    BaseIdentityWithinRounding bool          `json:"baseIdentityWithinRounding"`
    TotalIdentityExact     bool             `json:"totalIdentityExact"`
    Components             []droneComponent `json:"components,omitempty"`
}

type droneChip struct {
    CfgID int64 `json:"cfgId"`
    Slot  int64 `json:"slot,omitempty"`
    Star  int64 `json:"star,omitempty"`
    Level int64 `json:"level,omitempty"`
    Exp   int64 `json:"exp,omitempty"`
    Num   int64 `json:"num,omitempty"`
}

type droneChipGroup struct {
    EquipGroup int64       `json:"equipGroup"`
    Chips      []droneChip `json:"chips"`
    UsedByArmies []int64   `json:"usedByArmies,omitempty"`
}

func main(){
    if len(os.Args)!=4 { fatal(fmt.Errorf("usage: helper <capture> <phase8> <output>")) }
    st,err:=findState(os.Args[1]); if err!=nil{fatal(err)}
    if st.Init==nil{fatal(fmt.Errorf("init Last War introuvable"))}

    heroMap:=map[int64]int64{}
    heroSet:=map[int64]bool{}
    for _,o:=range objectsForKey(st.Init,"userHero"){
        id:=num(o,"heroId"); if id==0{continue}
        heroSet[id]=true
        if uuid:=num(o,"uuid");uuid!=0{heroMap[uuid]=id}
    }

    domMap:=map[int64]int{}
    overlords:=[]overlordRow{}
    for i,o:=range objectsForKey(st.Init,"userDominators"){
        ord:=i+1
        if uuid:=num(o,"uuid");uuid!=0{domMap[uuid]=ord}
        overlords=append(overlords,overlordRow{
            Ordinal:ord,
            DominatorID:firstNum(o,"dominatorId","cfgId","id"),
            Power:firstNum(o,"power"),
            Rank:firstNum(o,"rank","rankLv"),
            Level:firstNum(o,"level","lv","lev"),
            SkillCount:anyArrayLen(o,"skills"),
        })
    }

    army:=extractFormations(objectsForKey(st.Init,"army_formation"),heroMap,heroSet,domMap,false)
    templates:=extractFormations(objectsForKey(st.Init,"formation_template"),heroMap,heroSet,domMap,true)

    b,err:=os.ReadFile(os.Args[2]);if err!=nil{fatal(err)}
    var doc map[string]any
    if err:=json.Unmarshal(b,&doc);err!=nil{fatal(err)}
    if fmt.Sprint(doc["format"])!="WFGG_LASTWAR_MODULE_DATA_V2"{fatal(fmt.Errorf("format Phase 8 inattendu"))}

    stats:=resolutionStats{}
    for _,f:=range army{
        stats.ArmyHeroRefs+=len(f.HeroIDs)+len(f.TmpHeroIDs)
        stats.ArmyOverlordRefs+=len(f.OverlordOrdinals)
        stats.UnresolvedRefs+=f.UnresolvedRefs
        stats.MissingHeroSlots+=f.MissingHeroSlots
    }
    for _,f:=range templates{
        stats.TemplateHeroRefs+=len(f.HeroIDs)+len(f.TmpHeroIDs)
        stats.TemplateOverlordRefs+=len(f.OverlordOrdinals)
        stats.UnresolvedRefs+=f.UnresolvedRefs
        stats.MissingHeroSlots+=f.MissingHeroSlots
    }

    drone:=extractDrone(st.Init)
    chipGroups:=extractChipGroups(st.ChipData,army)

    doc["format"]="WFGG_LASTWAR_MODULE_DATA_V3"
    doc["armyFormations"]=army
    doc["formationTemplates"]=templates
    doc["formationResolution"]=stats
    doc["overlords"]=overlords
    doc["drone"]=drone
    doc["droneChipGroups"]=chipGroups
    if privacy,ok:=doc["privacy"].(map[string]any);ok{
        privacy["rawFormationRefsExported"]=false
        privacy["rawDominatorRefsExported"]=false
    }
    if counts,ok:=doc["counts"].(map[string]any);ok{
        counts["overlords"]=len(overlords)
        counts["droneComponents"]=len(drone.Components)
        n:=0;for _,g:=range chipGroups{n+=len(g.Chips)}
        counts["droneChipEntries"]=n
    }

    out,err:=json.MarshalIndent(doc,"","  ");if err!=nil{fatal(err)}
    if err:=os.WriteFile(os.Args[3],out,0600);err!=nil{fatal(err)}

    activeDroneRefs:=0
    for _,f:=range army{if f.ChipEquipGroup>0{activeDroneRefs++}}
    fmt.Printf("V3 ARMY_HERO_REFS=%d ARMY_OVERLORD_REFS=%d ACTIVE_DRONE_PRESETS=%d UNRESOLVED=%d\n",
        stats.ArmyHeroRefs,stats.ArmyOverlordRefs,activeDroneRefs,stats.UnresolvedRefs)
    fmt.Printf("DRONE_LEVEL=%d COMPONENTS=%d CHIP_GROUPS=%d OVERLORDS=%d\n",drone.Level,len(drone.Components),len(chipGroups),len(overlords))
    fmt.Printf("OUTPUT=%s\n",os.Args[3])
}

func extractFormations(objs []*sfs.SFSObject,heroMap map[int64]int64,heroSet map[int64]bool,domMap map[int64]int,template bool)[]formationRow{
    out:=make([]formationRow,0,len(objs))
    for _,o:=range objs{
        heroes,doms,u1:=classifyRefs(o,"heroes",heroMap,heroSet,domMap)
        tmp,tmpDoms,u2:=classifyRefs(o,"tmpHeroes",heroMap,heroSet,domMap)
        doms=append(doms,tmpDoms...)
        slots:=firstNum(o,"slots")
        missing:=int(slots)-len(heroes)-len(tmp)
        if missing<0{missing=0}
        out=append(out,formationRow{
            Index:firstNum(o,"index"),SquadNo:firstNum(o,"squadNo"),Type:firstNum(o,"type"),
            Slots:slots,State:firstNum(o,"state"),ChipEquipGroup:firstNum(o,"chipEquipGroup"),
            DefencePriority:firstNum(o,"defencePriority"),HeroIDs:heroes,TmpHeroIDs:tmp,
            OverlordOrdinals:uniqueInts(doms),SoldierEntries:anyArrayLen(o,"soldiers"),
            MissingHeroSlots:missing,UnresolvedRefs:u1+u2,
        })
    }
    sort.SliceStable(out,func(i,j int)bool{
        if template&&out[i].SquadNo!=out[j].SquadNo{return out[i].SquadNo<out[j].SquadNo}
        return out[i].Index<out[j].Index
    })
    return out
}

func classifyRefs(o *sfs.SFSObject,key string,heroMap map[int64]int64,heroSet map[int64]bool,domMap map[int64]int)([]int64,[]int,int){
    sv,ok:=o.Get(key);if !ok{return nil,nil,0}
    refs:=flattenRefs(sv.Val)
    heroes:=[]int64{};doms:=[]int{};unresolved:=0
    for _,raw:=range refs{
        if raw==0{continue}
        if id,ok:=heroMap[raw];ok{heroes=append(heroes,id);continue}
        if heroSet[raw]{heroes=append(heroes,raw);continue}
        if ord,ok:=domMap[raw];ok{doms=append(doms,ord);continue}
        unresolved++
    }
    return heroes,doms,unresolved
}

func extractDrone(init *sfs.SFSObject)droneModel{
    d:=droneModel{}
    weapons:=objectsForKey(init,"weaponArr")
    if len(weapons)>0{
        w:=weapons[0]
        d.Level=firstNum(w,"lv","level")
        d.Exp=firstNum(w,"exp")
        d.BasePower=firstNum(w,"power")
        d.ChipLevel=firstNum(w,"chipLv")
        d.ChipExp=firstNum(w,"chipExp")
        d.SkillID=firstNum(w,"skill","skillId")
        d.SkillLevel=firstNum(w,"skillLevel")
    }
    for _,o:=range objectsForKey(init,"equipList"){
        d.Components=append(d.Components,droneComponent{Slot:firstNum(o,"slot"),CfgID:firstNum(o,"cfgId"),Power:firstNum(o,"power"),Exp:firstNum(o,"exp"),Num:firstNum(o,"num")})
    }
    sort.Slice(d.Components,func(i,j int)bool{return d.Components[i].Slot<d.Components[j].Slot})
    player:=objectForKey(init,"playerInfo")
    detail:=objectForKey(player,"powerDetail")
    if detail!=nil{
        d.LevelPower=firstNum(detail,"weaponLevelPower")
        d.ComponentPower=firstNum(detail,"weaponEquipPower")
        d.ChipPower=firstNum(detail,"weaponChipPower")
        d.TotalSquadEquipPower=firstNum(detail,"squadEquipPower")
    }
    if d.TotalSquadEquipPower==0 && player!=nil{d.TotalSquadEquipPower=firstNum(player,"squadEquipPower")}
    delta:=(d.LevelPower+d.ComponentPower)-d.BasePower
    if delta<0{delta=-delta}
    d.BaseIdentityWithinRounding=d.BasePower>0&&delta<=1
    d.TotalIdentityExact=d.BasePower>0&&d.ChipPower>0&&d.TotalSquadEquipPower>0&&d.BasePower+d.ChipPower==d.TotalSquadEquipPower
    return d
}

func extractChipGroups(chipData *sfs.SFSObject,army []formationRow)[]droneChipGroup{
    if chipData==nil{return nil}
    sv,ok:=chipData.Get("droneSkillArr");if !ok{return nil}
    a,ok:=sv.Val.(*sfs.SFSArray);if !ok||a==nil{return nil}
    groups:=map[int64][]droneChip{}
    for _,it:=range a.Items(){
        o,ok:=it.Val.(*sfs.SFSObject);if !ok||o==nil{continue}
        g:=firstNum(o,"equipGroup")
        groups[g]=append(groups[g],droneChip{CfgID:firstNum(o,"cfgId"),Slot:firstNum(o,"slot"),Star:firstNum(o,"star"),Level:firstNum(o,"lv","level"),Exp:firstNum(o,"exp"),Num:firstNum(o,"num")})
    }
    keys:=make([]int,0,len(groups));for g:=range groups{keys=append(keys,int(g))};sort.Ints(keys)
    out:=make([]droneChipGroup,0,len(keys))
    for _,gi:=range keys{
        g:=int64(gi);chips:=groups[g]
        sort.Slice(chips,func(i,j int)bool{if chips[i].Slot!=chips[j].Slot{return chips[i].Slot<chips[j].Slot};return chips[i].CfgID<chips[j].CfgID})
        used:=[]int64{}
        for _,f:=range army{if f.ChipEquipGroup==g{used=append(used,f.Index)}}
        out=append(out,droneChipGroup{EquipGroup:g,Chips:chips,UsedByArmies:used})
    }
    return out
}

func findState(path string)(state,error){
    data,err:=os.ReadFile(path);if err!=nil{return state{},err}
    pkts,err:=pcap.Parse(data);if err!=nil{return state{},err}
    st:=state{}
    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        _,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c)
        for{
            body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break}
            outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
            pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil{continue}
            cmd:=ext.GetString("c");pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if !ok||params==nil{continue}
            if cmd=="init"&&st.Init==nil{st.Init=params}
            if cmd=="chip.data"&&st.ChipData==nil{st.ChipData=params}
        }
    }
    return st,nil
}

func flattenRefs(v any)[]int64{
    var out []int64
    switch x:=v.(type){
    case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){out=append(out,flattenRefs(it.Val)...)} }
    case *sfs.SFSObject:
        if x==nil{return out}
        if id:=firstNum(x,"heroId");id!=0{return []int64{id}}
        if id:=firstNum(x,"heroUuid","uuid","heroUid","uid");id!=0{return []int64{id}}
    case []int64:out=append(out,x...)
    case []int32:for _,n:=range x{out=append(out,int64(n))}
    case []int16:for _,n:=range x{out=append(out,int64(n))}
    case []byte:for _,n:=range x{out=append(out,int64(n))}
    case []string:for _,s:=range x{if n,e:=strconv.ParseInt(s,10,64);e==nil{out=append(out,n)}}
    case int64:out=append(out,x)
    case int32:out=append(out,int64(x))
    case int16:out=append(out,int64(x))
    case byte:out=append(out,int64(x))
    case string:if n,e:=strconv.ParseInt(x,10,64);e==nil{out=append(out,n)}
    }
    return out
}

func objectForKey(o *sfs.SFSObject,key string)*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};x,_:=v.Val.(*sfs.SFSObject);return x}
func objectsForKey(o *sfs.SFSObject,key string)[]*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{
    out:=[]*sfs.SFSObject{}
    switch x:=v.Val.(type){
    case *sfs.SFSArray:if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}}
    case *sfs.SFSObject:
        if x==nil{return out}
        for _,k:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(k);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}}
        out=append(out,x)
    }
    return out
}
func anyArrayLen(o *sfs.SFSObject,key string)int{if o==nil{return 0};sv,ok:=o.Get(key);if !ok{return 0};switch a:=sv.Val.(type){case *sfs.SFSArray:if a!=nil{return len(a.Items())};case []int64:return len(a);case []int32:return len(a);case []int16:return len(a);case []byte:return len(a);case []string:return len(a)};return 0}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{if o==nil{return 0};sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n);case string:q,_:=strconv.ParseInt(n,10,64);return q};return 0}
func uniqueInts(in []int)[]int{m:=map[int]bool{};out:=[]int{};for _,n:=range in{if n>0&&!m[n]{m[n]=true;out=append(out,n)}};sort.Ints(out);return out}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase19:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase19-normalized
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$PHASE8" "$OUT"
chmod 600 "$OUT"
rm -f "$HELPER"

say "=== PHASE 19 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE19_NORMALIZED_MODULE_DATA.json"
say "Modèle V3: 5 héros + Drone global/preset de puces + Overlord séparé."
