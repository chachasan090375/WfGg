#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 8
# OFFLINE ONLY. Re-reads the user's own PCAP, resolves formation hero
# references to public heroId catalogue values, then merges them into the
# Phase 7 normalized module JSON. No Last War network connection is opened.
# Raw hero instance UUIDs are used only in memory and are never exported.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
PHASE7="${DOWNLOADS}/WFGG_LASTWAR_PHASE7_NORMALIZED_MODULE_DATA.json"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE8_NORMALIZED_MODULE_DATA.json"
TMP_CMD="${SRC}/cmd/wfgg-phase8-formations"
HELPER="${BASE}/wfgg-phase8-formations"

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

if [[ ! -s "$PHASE7" ]]; then
  say "Phase 7 absente : génération hors ligne préalable…"
  bash "$HOME/wfgg-lastwar-preview/scripts/lastwar-phase7-normalized-module-data.sh" "$CAPTURE"
fi
[[ -s "$PHASE7" ]] || die "fichier Phase 7 absent"

TERMUX_PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
REAL_GO="${TERMUX_PREFIX}/bin/go"
[[ -x "$REAL_GO" ]] || die "compilateur Go Termux absent"

say "=== WfGg Last War LAB · PHASE 8 ==="
say "Mode: OFFLINE / résolution formations / aucune connexion Last War"
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

type resolutionStats struct {
    ArmyHeroRefs int `json:"armyHeroRefs"`
    TemplateHeroRefs int `json:"templateHeroRefs"`
    UnresolvedHeroRefs int `json:"unresolvedHeroRefs"`
}

func main(){
    if len(os.Args)!=4 { fatal(fmt.Errorf("usage: helper <capture> <phase7> <output>")) }
    initObj,err:=findInit(os.Args[1]); if err!=nil{fatal(err)}

    heroMap:=map[int64]int64{}
    heroSet:=map[int64]bool{}
    for _,o:=range objectsForKey(initObj,"userHero") {
        id:=num(o,"heroId"); if id==0{continue}
        heroSet[id]=true
        if uuid:=num(o,"uuid"); uuid!=0 { heroMap[uuid]=id }
    }

    army:=extractFormations(objectsForKey(initObj,"army_formation"),heroMap,heroSet,false)
    templates:=extractFormations(objectsForKey(initObj,"formation_template"),heroMap,heroSet,true)

    phase7Bytes,err:=os.ReadFile(os.Args[2]); if err!=nil{fatal(err)}
    var doc map[string]any
    if err:=json.Unmarshal(phase7Bytes,&doc); err!=nil{fatal(err)}
    if fmt.Sprint(doc["format"])!="WFGG_LASTWAR_MODULE_DATA_V1" { fatal(fmt.Errorf("format Phase 7 inattendu")) }

    stats:=resolutionStats{}
    for _,f:=range army { stats.ArmyHeroRefs+=len(f.HeroIDs)+len(f.TmpHeroIDs); stats.UnresolvedHeroRefs+=f.UnresolvedHeroRefs }
    for _,f:=range templates { stats.TemplateHeroRefs+=len(f.HeroIDs)+len(f.TmpHeroIDs); stats.UnresolvedHeroRefs+=f.UnresolvedHeroRefs }

    doc["format"]="WFGG_LASTWAR_MODULE_DATA_V2"
    doc["armyFormations"]=army
    doc["formationTemplates"]=templates
    doc["formationResolution"]=stats
    if privacy,ok:=doc["privacy"].(map[string]any); ok {
        privacy["rawFormationRefsExported"]=false
    }

    out,err:=json.MarshalIndent(doc,"","  "); if err!=nil{fatal(err)}
    if err:=os.WriteFile(os.Args[3],out,0600); err!=nil{fatal(err)}

    fmt.Printf("ARMY_FORMATIONS=%d TEMPLATES=%d ARMY_HERO_REFS=%d TEMPLATE_HERO_REFS=%d UNRESOLVED=%d\n",
        len(army),len(templates),stats.ArmyHeroRefs,stats.TemplateHeroRefs,stats.UnresolvedHeroRefs)
    fmt.Printf("OUTPUT=%s\n",os.Args[3])
}

func extractFormations(objs []*sfs.SFSObject, heroMap map[int64]int64, heroSet map[int64]bool, template bool) []formationRow {
    out:=make([]formationRow,0,len(objs))
    for _,o:=range objs {
        heroes,u1:=resolveHeroRefs(o,"heroes",heroMap,heroSet)
        tmp,u2:=resolveHeroRefs(o,"tmpHeroes",heroMap,heroSet)
        out=append(out,formationRow{
            Index:firstNum(o,"index"),SquadNo:firstNum(o,"squadNo"),Type:firstNum(o,"type"),
            Slots:firstNum(o,"slots"),State:firstNum(o,"state"),ChipEquipGroup:firstNum(o,"chipEquipGroup"),
            DefencePriority:firstNum(o,"defencePriority"),HeroIDs:heroes,TmpHeroIDs:tmp,
            SoldierEntries:anyArrayLen(o,"soldiers"),UnresolvedHeroRefs:u1+u2,
        })
    }
    sort.SliceStable(out,func(i,j int)bool{
        if template && out[i].SquadNo!=out[j].SquadNo{return out[i].SquadNo<out[j].SquadNo}
        return out[i].Index<out[j].Index
    })
    return out
}

func resolveHeroRefs(o *sfs.SFSObject,key string,heroMap map[int64]int64,heroSet map[int64]bool)([]int64,int){
    sv,ok:=o.Get(key); if !ok{return nil,0}
    refs:=flattenRefs(sv.Val)
    ids:=make([]int64,0,len(refs)); unresolved:=0
    for _,raw:=range refs {
        if raw==0{continue}
        if id,ok:=heroMap[raw];ok{ids=append(ids,id);continue}
        if heroSet[raw]{ids=append(ids,raw);continue}
        unresolved++
    }
    return ids,unresolved
}

func flattenRefs(v any)[]int64{
    var out []int64
    switch x:=v.(type){
    case *sfs.SFSArray:
        if x==nil{return out}
        for _,it:=range x.Items(){out=append(out,flattenRefs(it.Val)...)}
    case *sfs.SFSObject:
        if x==nil{return out}
        if id:=firstNum(x,"heroId");id!=0{return []int64{id}}
        if id:=firstNum(x,"uuid","heroUid","uid");id!=0{return []int64{id}}
    case []int64:
        out=append(out,x...)
    case []int32:
        for _,n:=range x{out=append(out,int64(n))}
    case []int16:
        for _,n:=range x{out=append(out,int64(n))}
    case []byte:
        for _,n:=range x{out=append(out,int64(n))}
    case []string:
        for _,s:=range x{if n,err:=strconv.ParseInt(s,10,64);err==nil{out=append(out,n)}}
    case int64: out=append(out,x)
    case int32: out=append(out,int64(x))
    case int16: out=append(out,int64(x))
    case byte: out=append(out,int64(x))
    case string:
        if n,err:=strconv.ParseInt(x,10,64);err==nil{out=append(out,n)}
    }
    return out
}

func anyArrayLen(o *sfs.SFSObject,key string)int{
    sv,ok:=o.Get(key);if !ok{return 0}
    switch a:=sv.Val.(type){
    case *sfs.SFSArray: if a!=nil{return len(a.Items())}
    case []int64:return len(a);case []int32:return len(a);case []int16:return len(a);case []byte:return len(a);case []string:return len(a);case []bool:return len(a)
    }
    return 0
}

func findInit(path string)(*sfs.SFSObject,error){
    data,err:=os.ReadFile(path);if err!=nil{return nil,err}
    pkts,err:=pcap.Parse(data);if err!=nil{return nil,err}
    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        _,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c)
        for{
            body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break}
            outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
            pv,ok:=outer.Get("p");if !ok{continue}
            ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue}
            pp,ok:=ext.Get("p");if !ok{continue}
            params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}
        }
    }
    return nil,fmt.Errorf("init Last War introuvable")
}

func objectsForKey(init *sfs.SFSObject,key string)[]*sfs.SFSObject{v,ok:=init.Get(key);if !ok{return nil};return objectsFrom(v)}
func objectsFrom(v sfs.SFSValue)[]*sfs.SFSObject{
    var out []*sfs.SFSObject
    switch x:=v.Val.(type){
    case *sfs.SFSArray:
        if x!=nil{for _,it:=range x.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}}}
    case *sfs.SFSObject:
        if x==nil{return out}
        for _,preferred:=range []string{"list","data","arr","items"}{if sv,ok:=x.Get(preferred);ok{if a,ok:=sv.Val.(*sfs.SFSArray);ok&&a!=nil{for _,it:=range a.Items(){if o,ok:=it.Val.(*sfs.SFSObject);ok&&o!=nil{out=append(out,o)}};if len(out)>0{return out}}}}
        out=append(out,x)
    }
    return out
}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{sv,ok:=o.Get(k);if !ok{return 0};switch n:=sv.Val.(type){case int64:return n;case int32:return int64(n);case int16:return int64(n);case byte:return int64(n)};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase8:",err);os.Exit(1)}
GOEOF

cd "$SRC"
GOTOOLCHAIN=auto "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase8-formations
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$PHASE7" "$OUT"
chmod 600 "$OUT" 2>/dev/null || true

say "=== PHASE 8 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE8_NORMALIZED_MODULE_DATA.json"
say "Les références d'instances privées des formations ne sont jamais exportées."
