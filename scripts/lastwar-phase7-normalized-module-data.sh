#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 7
# OFFLINE ONLY. Reads the user's own PCAP and emits a normalized, module-ready
# JSON document. No Last War network connection is opened.
#
# Privacy rules:
# - no access token, loginKey, deviceId, anti-fraud fingerprint or e-mail;
# - no player/alliance name and no network/database infrastructure;
# - no raw Last War instance UUIDs are exported;
# - formation/equipment references are converted from private instance UUIDs
#   to public catalog heroId values whenever possible;
# - resources/currencies are intentionally not exported at this stage.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE7_NORMALIZED_MODULE_DATA.json"
TMP_CMD="${SRC}/cmd/wfgg-normalized-module-data"
HELPER="${BASE}/wfgg-normalized-module-data"

say() { printf '%s\n' "$*"; }
die() { printf 'ERREUR: %s\n' "$*" >&2; exit 1; }

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
  if [[ -z "$CANDIDATES" && -e "$SHARED" ]]; then
    CANDIDATES="$(find -L "$SHARED" -type f \( -iname '*.pcap' -o -iname '*.pcapng' -o -iname '*.cap' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr || true)"
  fi
  CAPTURE="$(printf '%s\n' "$CANDIDATES" | head -n1 | cut -d' ' -f2-)"
fi
[[ -n "$CAPTURE" && -f "$CAPTURE" ]] || die "aucun PCAP/PCAPNG trouvé"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 7 ==="
say "Mode: OFFLINE / normalisation module / aucune connexion Last War"
say "Capture: $CAPTURE"

mkdir -p "$TMP_CMD"
cleanup_tmp() { rm -rf "$TMP_CMD" 2>/dev/null || true; }
trap cleanup_tmp EXIT INT TERM

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
    "strings"
)

type privacyInfo struct {
    NetworkUsed bool `json:"networkUsed"`
    RawCredentialsExported bool `json:"rawCredentialsExported"`
    RawInstanceUUIDsExported bool `json:"rawInstanceUUIDsExported"`
    NamesExported bool `json:"namesExported"`
    ResourceBalancesExported bool `json:"resourceBalancesExported"`
}

type counts struct {
    Heroes int `json:"heroes"`
    ArmyFormations int `json:"armyFormations"`
    FormationTemplates int `json:"formationTemplates"`
    HeroEquipment int `json:"heroEquipment"`
    GeneralEquipment int `json:"generalEquipment"`
    Weapons int `json:"weapons"`
    Buildings int `json:"buildings"`
    Science int `json:"science"`
}

type heroRow struct {
    HeroID int64 `json:"heroId"`
    Level int64 `json:"level,omitempty"`
    RankLv int64 `json:"rankLv,omitempty"`
    AwakenLv int64 `json:"awakenLv,omitempty"`
    SkinID int64 `json:"skinId,omitempty"`
    State int64 `json:"state,omitempty"`
    SkillCount int `json:"skillCount,omitempty"`
    HasWeaponInfo bool `json:"hasWeaponInfo,omitempty"`
}

type formationRow struct {
    Index int64 `json:"index,omitempty"`
    SquadNo int64 `json:"squadNo,omitempty"`
    Type int64 `json:"type,omitempty"`
    Slots int64 `json:"slots,omitempty"`
    State int64 `json:"state,omitempty"`
    ChipEquipGroup int64 `json:"chipEquipGroup,omitempty"`
    DefencePriority int64 `json:"defencePriority,omitempty"`
    HeroIDs []int64 `json:"heroIds,omitempty"`
    TmpHeroIDs []int64 `json:"tmpHeroIds,omitempty"`
    SoldierEntries int `json:"soldierEntries,omitempty"`
    UnresolvedHeroRefs int `json:"unresolvedHeroRefs,omitempty"`
}

type heroEquipRow struct {
    HeroID int64 `json:"heroId,omitempty"`
    CfgID int64 `json:"cfgId"`
    Level int64 `json:"level,omitempty"`
    Promote int64 `json:"promote,omitempty"`
}

type equipRow struct {
    CfgID int64 `json:"cfgId"`
    Exp int64 `json:"exp,omitempty"`
    Num int64 `json:"num,omitempty"`
    Power int64 `json:"power,omitempty"`
    Slot int64 `json:"slot,omitempty"`
}

type weaponRow struct {
    Level int64 `json:"level,omitempty"`
    Power int64 `json:"power,omitempty"`
    Exp int64 `json:"exp,omitempty"`
    ChipLv int64 `json:"chipLv,omitempty"`
    ChipExp int64 `json:"chipExp,omitempty"`
    Skill int64 `json:"skill,omitempty"`
    SkillLevel int64 `json:"skillLevel,omitempty"`
}

type buildingRow struct {
    BuildingID int64 `json:"bId"`
    InstanceOrdinal int `json:"instanceOrdinal"`
    Level int64 `json:"level,omitempty"`
    State int64 `json:"state,omitempty"`
    ProductionStatus int64 `json:"prodStatus,omitempty"`
}

type scienceRow struct {
    ScienceID int64 `json:"scienceId"`
    Level int64 `json:"level,omitempty"`
}

type exportDoc struct {
    Format string `json:"format"`
    Source string `json:"source"`
    Privacy privacyInfo `json:"privacy"`
    InitTopLevelFields int `json:"initTopLevelFields"`
    Counts counts `json:"counts"`
    PlayerProgress map[string]any `json:"playerProgress,omitempty"`
    Heroes []heroRow `json:"heroes,omitempty"`
    ArmyFormations []formationRow `json:"armyFormations,omitempty"`
    FormationTemplates []formationRow `json:"formationTemplates,omitempty"`
    HeroEquipment []heroEquipRow `json:"heroEquipment,omitempty"`
    GeneralEquipment []equipRow `json:"generalEquipment,omitempty"`
    Weapons []weaponRow `json:"weapons,omitempty"`
    Buildings []buildingRow `json:"buildings,omitempty"`
    Science []scienceRow `json:"science,omitempty"`
}

func main() {
    if len(os.Args) != 3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    initObj, err := findInit(os.Args[1])
    if err != nil { fatal(err) }

    heroObjects := objectsForKey(initObj, "userHero")
    heroUUIDToID := map[int64]int64{}
    heroes := make([]heroRow, 0, len(heroObjects))
    for _, o := range heroObjects {
        heroID := num(o, "heroId")
        if heroID == 0 { continue }
        uuid := num(o, "uuid")
        if uuid != 0 { heroUUIDToID[uuid] = heroID }
        heroes = append(heroes, heroRow{
            HeroID: heroID,
            Level: firstNum(o, "lev", "lv", "level"),
            RankLv: firstNum(o, "rankLv", "rank"),
            AwakenLv: firstNum(o, "awakenLv", "awaken"),
            SkinID: firstNum(o, "skinId"),
            State: firstNum(o, "state"),
            SkillCount: childArrayLen(o, "skills"),
            HasWeaponInfo: hasObject(o, "weaponInfo"),
        })
    }
    sort.Slice(heroes, func(i,j int) bool { return heroes[i].HeroID < heroes[j].HeroID })

    armyFormations := extractFormations(objectsForKey(initObj, "army_formation"), heroUUIDToID, false)
    templates := extractFormations(objectsForKey(initObj, "formation_template"), heroUUIDToID, true)
    heroEquipment := extractHeroEquipment(objectsForKey(initObj, "heroEquips"), heroUUIDToID)
    generalEquipment := extractGeneralEquipment(objectsForKey(initObj, "equipList"))
    weapons := extractWeapons(objectsForKey(initObj, "weaponArr"))
    buildings := extractBuildings(objectsForKey(initObj, "building_new"))
    science := extractScience(objectsForKey(initObj, "science_new"))

    doc := exportDoc{
        Format: "WFGG_LASTWAR_MODULE_DATA_V1",
        Source: "local_pcap_init",
        Privacy: privacyInfo{
            NetworkUsed:false,
            RawCredentialsExported:false,
            RawInstanceUUIDsExported:false,
            NamesExported:false,
            ResourceBalancesExported:false,
        },
        InitTopLevelFields: len(initObj.Keys()),
        Counts: counts{
            Heroes:len(heroes), ArmyFormations:len(armyFormations), FormationTemplates:len(templates),
            HeroEquipment:len(heroEquipment), GeneralEquipment:len(generalEquipment), Weapons:len(weapons),
            Buildings:len(buildings), Science:len(science),
        },
        Heroes:heroes,
        ArmyFormations:armyFormations,
        FormationTemplates:templates,
        HeroEquipment:heroEquipment,
        GeneralEquipment:generalEquipment,
        Weapons:weapons,
        Buildings:buildings,
        Science:science,
    }
    if p := objectForKey(initObj, "playerInfo"); p != nil {
        doc.PlayerProgress = safePlayerProgress(p)
    }

    out, err := json.MarshalIndent(doc, "", "  ")
    if err != nil { fatal(err) }
    if err := os.WriteFile(os.Args[2], out, 0600); err != nil { fatal(err) }

    fmt.Printf("HEROES=%d ARMY_FORMATIONS=%d TEMPLATES=%d HERO_EQUIPS=%d BUILDINGS=%d SCIENCE=%d\n",
        len(heroes), len(armyFormations), len(templates), len(heroEquipment), len(buildings), len(science))
    fmt.Printf("OUTPUT=%s\n", os.Args[2])
}

func findInit(path string) (*sfs.SFSObject, error) {
    data, err := os.ReadFile(path)
    if err != nil { return nil, err }
    pkts, err := pcap.Parse(data)
    if err != nil { return nil, err }
    for _, conv := range pcap.Conversations(pkts) {
        if conv.TLS { continue }
        client, err := conv.Client(netip.Addr{})
        if err != nil { continue }
        _, s2c := conv.Reassemble(client)
        r := bytes.NewReader(s2c)
        for {
            body, err := sfs.ReadPacket(r)
            if err != nil {
                if errors.Is(err, io.EOF) { break }
                break
            }
            outer, err := sfs.DecodeObject(body)
            if err != nil { continue }
            pv, ok := outer.Get("p")
            if !ok { continue }
            ext, ok := pv.Val.(*sfs.SFSObject)
            if !ok || ext == nil || ext.GetString("c") != "init" { continue }
            pp, ok := ext.Get("p")
            if !ok { continue }
            params, ok := pp.Val.(*sfs.SFSObject)
            if ok && params != nil { return params, nil }
        }
    }
    return nil, fmt.Errorf("init Last War introuvable dans la capture")
}

func objectForKey(init *sfs.SFSObject, key string) *sfs.SFSObject {
    v, ok := init.Get(key); if !ok { return nil }
    o, _ := v.Val.(*sfs.SFSObject)
    return o
}

func objectsForKey(init *sfs.SFSObject, key string) []*sfs.SFSObject {
    v, ok := init.Get(key); if !ok { return nil }
    return objectsFrom(v)
}

func objectsFrom(v sfs.SFSValue) []*sfs.SFSObject {
    var out []*sfs.SFSObject
    switch x := v.Val.(type) {
    case *sfs.SFSArray:
        if x == nil { return out }
        for _, item := range x.Items() {
            if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { out = append(out,o) }
        }
    case *sfs.SFSObject:
        if x == nil { return out }
        for _, preferred := range []string{"list","data","arr","items"} {
            if sv, ok := x.Get(preferred); ok {
                if a, ok := sv.Val.(*sfs.SFSArray); ok && a != nil {
                    for _, item := range a.Items() {
                        if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { out = append(out,o) }
                    }
                    if len(out)>0 { return out }
                }
            }
        }
        for _, k := range x.Keys() {
            sv, _ := x.Get(k)
            if a, ok := sv.Val.(*sfs.SFSArray); ok && a != nil {
                var tmp []*sfs.SFSObject
                for _, item := range a.Items() {
                    if o, ok := item.Val.(*sfs.SFSObject); ok && o != nil { tmp = append(tmp,o) }
                }
                if len(tmp)>0 { return tmp }
            }
        }
        out = append(out, x)
    }
    return out
}

func extractFormations(objs []*sfs.SFSObject, heroMap map[int64]int64, template bool) []formationRow {
    out := make([]formationRow,0,len(objs))
    for _, o := range objs {
        heroes, unresolved := heroIDsFromArray(o, "heroes", heroMap)
        tmpHeroes, unresolvedTmp := heroIDsFromArray(o, "tmpHeroes", heroMap)
        row := formationRow{
            Index:firstNum(o,"index"), SquadNo:firstNum(o,"squadNo"), Type:firstNum(o,"type"),
            Slots:firstNum(o,"slots"), State:firstNum(o,"state"), ChipEquipGroup:firstNum(o,"chipEquipGroup"),
            DefencePriority:firstNum(o,"defencePriority"), HeroIDs:heroes, TmpHeroIDs:tmpHeroes,
            SoldierEntries:childArrayLen(o,"soldiers"), UnresolvedHeroRefs:unresolved+unresolvedTmp,
        }
        out = append(out,row)
    }
    sort.SliceStable(out, func(i,j int) bool {
        if template && out[i].SquadNo != out[j].SquadNo { return out[i].SquadNo < out[j].SquadNo }
        return out[i].Index < out[j].Index
    })
    return out
}

func heroIDsFromArray(o *sfs.SFSObject, key string, heroMap map[int64]int64) ([]int64,int) {
    sv, ok := o.Get(key); if !ok { return nil,0 }
    a, ok := sv.Val.(*sfs.SFSArray); if !ok || a==nil { return nil,0 }
    var ids []int64
    unresolved := 0
    for _, item := range a.Items() {
        raw := scalarInt(item.Val)
        if raw == 0 {
            if obj, ok := item.Val.(*sfs.SFSObject); ok && obj != nil { raw = firstNum(obj,"uuid","heroUid","uid") }
        }
        if raw == 0 { continue }
        if heroID, ok := heroMap[raw]; ok { ids = append(ids, heroID) } else { unresolved++ }
    }
    return ids, unresolved
}

func extractHeroEquipment(objs []*sfs.SFSObject, heroMap map[int64]int64) []heroEquipRow {
    var out []heroEquipRow
    for _, o := range objs {
        cfg := firstNum(o,"cfgId")
        if cfg==0 { continue }
        heroID := heroMap[firstNum(o,"heroUid")]
        out = append(out, heroEquipRow{HeroID:heroID, CfgID:cfg, Level:firstNum(o,"level","lv"), Promote:firstNum(o,"promote")})
    }
    sort.SliceStable(out, func(i,j int) bool {
        if out[i].HeroID==out[j].HeroID { return out[i].CfgID < out[j].CfgID }
        return out[i].HeroID < out[j].HeroID
    })
    return out
}

func extractGeneralEquipment(objs []*sfs.SFSObject) []equipRow {
    var out []equipRow
    for _, o := range objs {
        cfg := firstNum(o,"cfgId"); if cfg==0 { continue }
        out = append(out,equipRow{CfgID:cfg,Exp:firstNum(o,"exp"),Num:firstNum(o,"num"),Power:firstNum(o,"power"),Slot:firstNum(o,"slot")})
    }
    sort.SliceStable(out, func(i,j int) bool { if out[i].Slot==out[j].Slot { return out[i].CfgID<out[j].CfgID }; return out[i].Slot<out[j].Slot })
    return out
}

func extractWeapons(objs []*sfs.SFSObject) []weaponRow {
    var out []weaponRow
    for _, o := range objs {
        out = append(out,weaponRow{Level:firstNum(o,"lv","level"),Power:firstNum(o,"power"),Exp:firstNum(o,"exp"),ChipLv:firstNum(o,"chipLv"),ChipExp:firstNum(o,"chipExp"),Skill:firstNum(o,"skill"),SkillLevel:firstNum(o,"skillLevel")})
    }
    return out
}

func extractBuildings(objs []*sfs.SFSObject) []buildingRow {
    type raw struct { id,level,state,prod int64 }
    var rows []raw
    for _, o := range objs {
        id:=firstNum(o,"bId"); if id==0 { continue }
        rows=append(rows,raw{id:id,level:firstNum(o,"lv","lev","level"),state:firstNum(o,"state"),prod:firstNum(o,"prodStatus")})
    }
    sort.SliceStable(rows,func(i,j int) bool { if rows[i].id==rows[j].id { return rows[i].level<rows[j].level }; return rows[i].id<rows[j].id })
    ord:=map[int64]int{}
    out:=make([]buildingRow,0,len(rows))
    for _, r:=range rows { ord[r.id]++; out=append(out,buildingRow{BuildingID:r.id,InstanceOrdinal:ord[r.id],Level:r.level,State:r.state,ProductionStatus:r.prod}) }
    return out
}

func extractScience(objs []*sfs.SFSObject) []scienceRow {
    var out []scienceRow
    for _, o := range objs {
        id:=firstNum(o,"scienceId","itemId","id","sId"); if id==0 { continue }
        out=append(out,scienceRow{ScienceID:id,Level:firstNum(o,"lv","lev","level")})
    }
    sort.Slice(out,func(i,j int) bool { return out[i].ScienceID<out[j].ScienceID })
    return out
}

func safePlayerProgress(o *sfs.SFSObject) map[string]any {
    allowed := map[string]bool{
        "armyKill":true,"armyPower":true,"battleCardPower":true,"buildingPower":true,
        "decoPower":true,"dominatorPower":true,"heroPower":true,"playerMaxPower":true,
        "pveLevel":true,"sciencePower":true,"squadEquipPower":true,"stamina":true,
    }
    out:=map[string]any{}
    for _, k:=range o.Keys() {
        if !allowed[k] { continue }
        sv,_:=o.Get(k)
        switch n:=sv.Val.(type) {
        case int64: out[k]=n
        case int32: out[k]=n
        case int16: out[k]=n
        case byte: out[k]=n
        case float64: out[k]=n
        case float32: out[k]=n
        }
    }
    return out
}

func hasObject(o *sfs.SFSObject,key string) bool { sv,ok:=o.Get(key); if !ok{return false}; x,ok:=sv.Val.(*sfs.SFSObject); return ok&&x!=nil }
func childArrayLen(o *sfs.SFSObject,key string) int { sv,ok:=o.Get(key); if !ok{return 0}; a,ok:=sv.Val.(*sfs.SFSArray); if !ok||a==nil{return 0}; return len(a.Items()) }
func firstNum(o *sfs.SFSObject, keys ...string) int64 { for _,k:=range keys { if n:=num(o,k); n!=0{return n} }; return 0 }
func num(o *sfs.SFSObject,k string) int64 { sv,ok:=o.Get(k); if !ok{return 0}; return scalarInt(sv.Val) }
func scalarInt(v any) int64 { switch n:=v.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n)}; return 0 }
func fatal(err error){ fmt.Fprintln(os.Stderr,"phase7:",err); os.Exit(1) }

var _ = strings.Builder{}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-normalized-module-data
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 7 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE7_NORMALIZED_MODULE_DATA.json"
say "Les UUID privés, jetons, deviceId, empreintes anti-fraude, noms et soldes de ressources ne sont pas exportés."
