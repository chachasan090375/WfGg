#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 15
# OFFLINE ONLY. Maps drone chip equipGroup presets to army/template chipEquipGroup
# and inspects the surrounding chip.data payload without exporting private refs.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE15_DRONE_CHIP_GROUPS_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase15-drone-chip-groups"
HELPER="${BASE}/wfgg-phase15-drone-chip-groups"

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

say "=== WfGg Last War LAB · PHASE 15 ==="
say "Mode: OFFLINE / groupes de puces Drone / aucune connexion Last War"
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

type chip struct {
    CfgID int64
    EquipGroup int64
    Exp int64
    Lv int64
    Num int64
    Slot int64
    Star int64
}

type formation struct {
    Kind string
    Index int64
    SquadNo int64
    Slots int64
    ChipEquipGroup int64
}

type state struct {
    Init *sfs.SFSObject
    ChipData []*sfs.SFSObject
    DroneArrays []*sfs.SFSArray
}

func main(){
    if len(os.Args)!=3 { fatal(fmt.Errorf("usage: helper <capture> <output>")) }
    data,err:=os.ReadFile(os.Args[1]); if err!=nil{fatal(err)}
    pkts,err:=pcap.Parse(data); if err!=nil{fatal(err)}
    st:=state{}

    for _,conv:=range pcap.Conversations(pkts){
        if conv.TLS{continue}
        client,err:=conv.Client(netip.Addr{});if err!=nil{continue}
        c2s,s2c:=conv.Reassemble(client)
        scanStream(c2s,"client_to_server",&st)
        scanStream(s2c,"server_to_client",&st)
    }

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600);if err!=nil{fatal(err)}
    defer f.Close()

    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 15 DRONE CHIP GROUPS")
    fmt.Fprintln(f,"OFFLINE ONLY · no raw UUID/GUID/UID/credential values exported")
    fmt.Fprintln(f)

    chips:=collectChips(st.DroneArrays)
    groups:=groupChips(chips)
    fmt.Fprintln(f,"DRONE_CHIP_GROUP_SUMMARY")
    keys:=make([]int,0,len(groups));for g:=range groups{keys=append(keys,int(g))};sort.Ints(keys)
    for _,gi:=range keys{
        g:=int64(gi); items:=groups[g]
        slots:=[]int{}; cfgs:=[]string{}
        for _,c:=range items{if c.Slot>0{slots=append(slots,int(c.Slot))};cfgs=append(cfgs,fmt.Sprintf("%d",c.CfgID))}
        sort.Ints(slots);sort.Strings(cfgs)
        fmt.Fprintf(f,"  equipGroup=%d count=%d activeSlots=%s cfgIds=%s\n",g,len(items),joinInts(slots),strings.Join(cfgs,","))
        for _,c:=range items{
            fmt.Fprintf(f,"    slot=%d cfgId=%d star=%d lv=%d exp=%d num=%d\n",c.Slot,c.CfgID,c.Star,c.Lv,c.Exp,c.Num)
        }
    }

    if st.Init!=nil{
        forms:=append(parseFormations(st.Init,"army_formation","army"),parseFormations(st.Init,"formation_template","template")...)
        fmt.Fprintln(f,"\nFORMATION_TO_DRONE_CHIP_GROUP_LINKS")
        activeGroups:=map[int64]bool{}
        for _,fr:=range forms{
            count:=len(groups[fr.ChipEquipGroup])
            if fr.Kind=="army"{activeGroups[fr.ChipEquipGroup]=true}
            if fr.Kind=="army"{
                fmt.Fprintf(f,"  kind=army index=%d slots=%d chipEquipGroup=%d matchedDroneChipEntries=%d\n",fr.Index,fr.Slots,fr.ChipEquipGroup,count)
            }else{
                fmt.Fprintf(f,"  kind=template index=%d squadNo=%d slots=%d chipEquipGroup=%d matchedDroneChipEntries=%d\n",fr.Index,fr.SquadNo,fr.Slots,fr.ChipEquipGroup,count)
            }
        }
        fmt.Fprintln(f,"\nACTIVE_ARMY_DRONE_MODEL")
        for _,fr:=range forms{if fr.Kind!="army"{continue};fmt.Fprintf(f,"  army=%d -> globalDrone + chipPresetGroup=%d (%d equipped entries)\n",fr.Index,fr.ChipEquipGroup,len(groups[fr.ChipEquipGroup]))}
        unused:=[]int{};for _,gi:=range keys{g:=int64(gi);if g>0&&!activeGroups[g]{unused=append(unused,gi)}}
        fmt.Fprintf(f,"  unassignedInventoryEntries=%d\n",len(groups[0]))
        fmt.Fprintf(f,"  nonActivePresetGroups=%s\n",joinInts(unused))
        fmt.Fprintln(f,"  conclusion=drone_global_entity_with_per-formation_chipEquipGroup_preset")
    }

    fmt.Fprintln(f,"\nCHIP_DATA_SAFE_TOPOLOGY")
    if len(st.ChipData)==0{fmt.Fprintln(f,"  (chip.data absent)")}
    for i,o:=range st.ChipData{
        fmt.Fprintf(f,"  response=%d\n",i+1)
        printObjectSafe(f,o,"    ",0,2)
    }

    fmt.Printf("DRONE_CHIPS=%d GROUPS=%d CHIP_DATA_RESPONSES=%d\n",len(chips),len(groups),len(st.ChipData))
    fmt.Printf("OUTPUT=%s\n",os.Args[2])
}

func scanStream(buf []byte,dir string,st *state){
    r:=bytes.NewReader(buf)
    for{
        body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){return};return}
        outer,err:=sfs.DecodeObject(body);if err!=nil{continue}
        pv,ok:=outer.Get("p");if !ok{continue}
        ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil{continue}
        cmd:=ext.GetString("c")
        pp,ok:=ext.Get("p");if !ok{continue}
        params,ok:=pp.Val.(*sfs.SFSObject);if !ok||params==nil{continue}
        if cmd=="init" && dir=="server_to_client" && st.Init==nil{st.Init=params}
        if cmd=="chip.data" && dir=="server_to_client"{
            st.ChipData=append(st.ChipData,params)
            if v,ok:=params.Get("droneSkillArr");ok{if a,ok:=v.Val.(*sfs.SFSArray);ok&&a!=nil{st.DroneArrays=append(st.DroneArrays,a)}}
        }
    }
}

func collectChips(arrs []*sfs.SFSArray)[]chip{
    out:=[]chip{};seen:=map[string]bool{}
    for _,a:=range arrs{if a==nil{continue};for _,it:=range a.Items(){o,ok:=it.Val.(*sfs.SFSObject);if !ok||o==nil{continue};c:=chip{CfgID:num(o,"cfgId"),EquipGroup:num(o,"equipGroup"),Exp:num(o,"exp"),Lv:num(o,"lv"),Num:num(o,"num"),Slot:num(o,"slot"),Star:num(o,"star")};k:=fmt.Sprintf("%d|%d|%d|%d|%d|%d|%d",c.CfgID,c.EquipGroup,c.Exp,c.Lv,c.Num,c.Slot,c.Star);if !seen[k]{seen[k]=true;out=append(out,c)}}}
    sort.Slice(out,func(i,j int)bool{if out[i].EquipGroup!=out[j].EquipGroup{return out[i].EquipGroup<out[j].EquipGroup};if out[i].Slot!=out[j].Slot{return out[i].Slot<out[j].Slot};return out[i].CfgID<out[j].CfgID})
    return out
}
func groupChips(in []chip)map[int64][]chip{m:=map[int64][]chip{};for _,c:=range in{m[c.EquipGroup]=append(m[c.EquipGroup],c)};return m}

func parseFormations(init *sfs.SFSObject,key,kind string)[]formation{
    out:=[]formation{};v,ok:=init.Get(key);if !ok{return out};a,ok:=v.Val.(*sfs.SFSArray);if !ok||a==nil{return out}
    for _,it:=range a.Items(){o,ok:=it.Val.(*sfs.SFSObject);if !ok||o==nil{continue};out=append(out,formation{Kind:kind,Index:num(o,"index"),SquadNo:num(o,"squadNo"),Slots:num(o,"slots"),ChipEquipGroup:num(o,"chipEquipGroup")})}
    sort.Slice(out,func(i,j int)bool{if out[i].SquadNo!=out[j].SquadNo{return out[i].SquadNo<out[j].SquadNo};return out[i].Index<out[j].Index});return out
}

func printObjectSafe(w io.Writer,o *sfs.SFSObject,indent string,depth,maxDepth int){
    if o==nil||depth>maxDepth{return}
    ks:=append([]string{},o.Keys()...);sort.Strings(ks)
    for _,k:=range ks{
        if sensitiveKey(k){continue};sv,_:=o.Get(k)
        if s,ok:=safeScalar(k,sv.Val);ok{fmt.Fprintf(w,"%s%s=%s\n",indent,k,s);continue}
        switch x:=sv.Val.(type){
        case *sfs.SFSObject:
            fmt.Fprintf(w,"%s%s=SFSObject[%d]\n",indent,k,len(x.Keys()));if depth<maxDepth{printObjectSafe(w,x,indent+"  ",depth+1,maxDepth)}
        case *sfs.SFSArray:
            fmt.Fprintf(w,"%s%s=SFSArray[%d]\n",indent,k,len(x.Items()))
        default:
            fmt.Fprintf(w,"%s%s=%T\n",indent,k,sv.Val)
        }
    }
}

func sensitiveKey(k string)bool{l:=strings.ToLower(k);return strings.Contains(l,"uuid")||strings.Contains(l,"guid")||l=="uid"||strings.HasSuffix(l,"uid")||strings.Contains(l,"token")||strings.Contains(l,"login")||strings.Contains(l,"secret")||strings.Contains(l,"email")||strings.Contains(l,"name")}
func safeScalar(k string,v any)(string,bool){
    l:=strings.ToLower(k)
    allow:=map[string]bool{"cfgid":true,"cardid":true,"skillid":true,"level":true,"lv":true,"star":true,"num":true,"slot":true,"exp":true,"equipgroup":true,"state":true,"status":true,"type":true,"power":true,"ranklv":true,"chipEquipGroup":true,"index":true,"squadno":true,"slots":true}
    if !allow[l] && !allow[k]{return "",false}
    switch x:=v.(type){case int64:return strconv.FormatInt(x,10),true;case int32:return strconv.FormatInt(int64(x),10),true;case int16:return strconv.FormatInt(int64(x),10),true;case byte:return strconv.FormatInt(int64(x),10),true;case float32:return strconv.FormatFloat(float64(x),'f',-1,32),true;case float64:return strconv.FormatFloat(x,'f',-1,64),true;case bool:return strconv.FormatBool(x),true};return "",false
}
func num(o *sfs.SFSObject,k string)int64{if o==nil{return 0};v,ok:=o.Get(k);if !ok{return 0};switch x:=v.Val.(type){case int64:return x;case int32:return int64(x);case int16:return int64(x);case byte:return int64(x);case string:n,_:=strconv.ParseInt(x,10,64);return n};return 0}
func joinInts(in []int)string{if len(in)==0{return "none"};ss:=make([]string,len(in));for i,n:=range in{ss[i]=strconv.Itoa(n)};return strings.Join(ss,",")}
func fatal(err error){fmt.Fprintln(os.Stderr,"ERREUR:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase15-drone-chip-groups
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT"

say "=== PHASE 15 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE15_DRONE_CHIP_GROUPS_REDACTED.txt"
say "Les UUID/GUID/UID privés ne sont jamais exportés."
