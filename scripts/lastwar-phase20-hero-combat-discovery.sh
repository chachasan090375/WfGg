#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — PHASE 20
# OFFLINE ONLY. Discovers per-hero combat/progression fields from userHero
# without exporting private UUID/GUID/UID, names, credentials or resources.

BASE="${HOME}/.wfgg-lastwar-probe"
SRC="${BASE}/src"
DOWNLOADS="${HOME}/storage/downloads"
SHARED="${HOME}/storage/shared"
ANDROID_SHARED="/storage/emulated/0"
OUT="${DOWNLOADS}/WFGG_LASTWAR_PHASE20_HERO_COMBAT_DISCOVERY_REDACTED.txt"
TMP_CMD="${SRC}/cmd/wfgg-phase20-hero-combat"
HELPER="${BASE}/wfgg-phase20-hero-combat"

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

say "=== WfGg Last War LAB · PHASE 20 ==="
say "Mode: OFFLINE / découverte puissance & stats héros"
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

type fieldRow struct{ Path, Value string }
type heroRow struct{
    HeroID int64
    Level int64
    Rank int64
    State int64
    Fields []fieldRow
}

var interesting=[]string{"power","combat","attack","atk","damage","defence","defense","def","health","hp","armor","armour","crit","strength","skill","rank","star","level","lv"}

func main(){
    if len(os.Args)!=3{fatal(fmt.Errorf("usage: helper <capture> <output>"))}
    initObj,err:=findInit(os.Args[1]);if err!=nil{fatal(err)}
    heroes:=[]heroRow{}
    heroesWithPower:=0
    for _,o:=range objectsForKey(initObj,"userHero"){
        id:=num(o,"heroId");if id==0{continue}
        h:=heroRow{HeroID:id,Level:firstNum(o,"level","lv","lev"),Rank:firstNum(o,"rankLv","rank","star"),State:firstNum(o,"state")}
        walk(o,"",0,&h.Fields)
        h.Fields=dedupe(h.Fields)
        for _,r:=range h.Fields{if strings.Contains(strings.ToLower(r.Path),"power"){heroesWithPower++;break}}
        heroes=append(heroes,h)
    }
    sort.Slice(heroes,func(i,j int)bool{return heroes[i].HeroID<heroes[j].HeroID})

    player:=objectForKey(initObj,"playerInfo")
    detail:=objectForKey(player,"powerDetail")
    heroPower:=firstNum(player,"heroPower")
    if heroPower==0{heroPower=firstNum(detail,"heroPower")}

    f,err:=os.OpenFile(os.Args[2],os.O_CREATE|os.O_TRUNC|os.O_WRONLY,0600);if err!=nil{fatal(err)}
    defer f.Close()
    fmt.Fprintln(f,"WfGg Last War LAB — PHASE 20 HERO COMBAT DISCOVERY")
    fmt.Fprintln(f,"OFFLINE ONLY · private identifiers/names/credentials/resources suppressed")
    fmt.Fprintln(f)
    fmt.Fprintf(f,"HEROES=%d HEROES_WITH_POWER_NAMED_FIELD=%d ACCOUNT_HERO_POWER=%d\n",len(heroes),heroesWithPower,heroPower)
    for _,h:=range heroes{
        fmt.Fprintf(f,"\nHERO heroId=%d level=%d rank=%d state=%d\n",h.HeroID,h.Level,h.Rank,h.State)
        if len(h.Fields)==0{fmt.Fprintln(f,"  (aucun champ combat/progression scalaire sûr)");continue}
        for _,r:=range h.Fields{fmt.Fprintf(f,"  %s=%s\n",r.Path,r.Value)}
    }
    fmt.Fprintln(f,"\nINTERPRETATION")
    if heroesWithPower==len(heroes)&&len(heroes)>0{
        fmt.Fprintln(f,"  perHeroPowerNamedFields=complete")
    }else if heroesWithPower>0{
        fmt.Fprintln(f,"  perHeroPowerNamedFields=partial")
    }else{
        fmt.Fprintln(f,"  perHeroPowerNamedFields=absent_in_init_userHero")
    }
    fmt.Fprintln(f,"  next=use_only_observed_safe_fields_for_normalized_simulator_model")
    fmt.Printf("HEROES=%d HEROES_WITH_POWER=%d OUTPUT=%s\n",len(heroes),heroesWithPower,os.Args[2])
}

func walk(v any,path string,depth int,out *[]fieldRow){
    if depth>5{return}
    switch x:=v.(type){
    case *sfs.SFSObject:
        if x==nil{return}
        for _,k:=range x.Keys(){
            sv,_:=x.Get(k);p:=k;if path!=""{p=path+"."+k}
            if blocked(k){continue}
            if isInteresting(k){if s,ok:=scalar(sv.Val);ok{*out=append(*out,fieldRow{Path:p,Value:s})}}
            switch q:=sv.Val.(type){case *sfs.SFSObject:walk(q,p,depth+1,out);case *sfs.SFSArray:walk(q,p,depth+1,out)}
        }
    case *sfs.SFSArray:
        if x==nil{return}
        for _,it:=range x.Items(){walk(it.Val,path+"[]",depth+1,out)}
    }
}
func blocked(k string)bool{l:=strings.ToLower(k);for _,s:=range []string{"uuid","guid","owner","token","login","secret","email","name"}{if strings.Contains(l,s){return true}};return l=="uid"||strings.HasSuffix(l,"uid")}
func isInteresting(k string)bool{l:=strings.ToLower(k);for _,s:=range interesting{if strings.Contains(l,s){return true}};return false}
func scalar(v any)(string,bool){switch x:=v.(type){case int64:return strconv.FormatInt(x,10),true;case int32:return strconv.FormatInt(int64(x),10),true;case int16:return strconv.FormatInt(int64(x),10),true;case byte:return strconv.FormatInt(int64(x),10),true;case bool:return strconv.FormatBool(x),true};return "",false}
func dedupe(in []fieldRow)[]fieldRow{m:=map[string]fieldRow{};for _,r:=range in{m[r.Path+"="+r.Value]=r};out:=make([]fieldRow,0,len(m));for _,r:=range m{out=append(out,r)};sort.Slice(out,func(i,j int)bool{return out[i].Path<out[j].Path});return out}

func findInit(path string)(*sfs.SFSObject,error){data,err:=os.ReadFile(path);if err!=nil{return nil,err};pkts,err:=pcap.Parse(data);if err!=nil{return nil,err};for _,conv:=range pcap.Conversations(pkts){if conv.TLS{continue};client,err:=conv.Client(netip.Addr{});if err!=nil{continue};_,s2c:=conv.Reassemble(client);r:=bytes.NewReader(s2c);for{body,err:=sfs.ReadPacket(r);if err!=nil{if errors.Is(err,io.EOF){break};break};outer,err:=sfs.DecodeObject(body);if err!=nil{continue};pv,ok:=outer.Get("p");if !ok{continue};ext,ok:=pv.Val.(*sfs.SFSObject);if !ok||ext==nil||ext.GetString("c")!="init"{continue};pp,ok:=ext.Get("p");if !ok{continue};params,ok:=pp.Val.(*sfs.SFSObject);if ok&&params!=nil{return params,nil}}};return nil,fmt.Errorf("init Last War introuvable")}
func objectsForKey(o *sfs.SFSObject,key string)[]*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};a,ok:=v.Val.(*sfs.SFSArray);if !ok||a==nil{return nil};out:=[]*sfs.SFSObject{};for _,it:=range a.Items(){if q,ok:=it.Val.(*sfs.SFSObject);ok&&q!=nil{out=append(out,q)}};return out}
func objectForKey(o *sfs.SFSObject,key string)*sfs.SFSObject{if o==nil{return nil};v,ok:=o.Get(key);if !ok{return nil};q,_:=v.Val.(*sfs.SFSObject);return q}
func firstNum(o *sfs.SFSObject,keys ...string)int64{for _,k:=range keys{if n:=num(o,k);n!=0{return n}};return 0}
func num(o *sfs.SFSObject,k string)int64{if o==nil{return 0};v,ok:=o.Get(k);if !ok{return 0};switch x:=v.Val.(type){case int64:return x;case int32:return int64(x);case int16:return int64(x);case byte:return int64(x)};return 0}
func fatal(err error){fmt.Fprintln(os.Stderr,"phase20:",err);os.Exit(1)}
GOEOF

(
  cd "$SRC"
  "$REAL_GO" build -o "$HELPER" ./cmd/wfgg-phase20-hero-combat
)
chmod 700 "$HELPER"
"$HELPER" "$CAPTURE" "$OUT"
chmod 600 "$OUT"
rm -f "$HELPER"

say "=== PHASE 20 TERMINEE ==="
say "Aucune connexion Last War n'a été effectuée."
say "Fichier à partager: Téléchargements/WFGG_LASTWAR_PHASE20_HERO_COMBAT_DISCOVERY_REDACTED.txt"
