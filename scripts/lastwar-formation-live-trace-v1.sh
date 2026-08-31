#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
PORT=8788
BASE="$ROOT/frontend/lab/master-assets-v2/live-trace"
DATA="$ROOT/frontend/lab/formation-live-trace-data"
STATE="$BASE/current.env"
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-live-trace.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
mkdir -p "$BASE/sessions" "$DATA"

ensure_adb(){
  if ! command -v adb >/dev/null 2>&1; then
    printf 'ADB_ABSENT\nInstalle android-tools avec: pkg install -y android-tools\n' >&2
    return 2
  fi
}
first_device(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}'; }
try_mdns_connect(){
  local ep
  ep="$(adb mdns services 2>/dev/null | awk '/_adb-tls-connect\._tcp/{print $NF; exit}' | tr -d '\r')"
  if [[ -n "$ep" ]]; then adb connect "$ep" >/dev/null 2>&1 || true; fi
}
ensure_device(){
  ensure_adb || return $?
  local d="$(first_device)"
  if [[ -z "$d" ]]; then try_mdns_connect; sleep 1; d="$(first_device)"; fi
  if [[ -z "$d" ]]; then
    printf 'ADB_NOT_CONNECTED\n' >&2
    printf 'Active Débogage sans fil sur Android, puis lance: bash scripts/lastwar-formation-live-trace-v1.sh pair\n' >&2
    return 3
  fi
  printf '%s\n' "$d"
}
adbx(){ local serial="$1"; shift; adb -s "$serial" "$@"; }

snapshot_files(){
  local serial="$1" out="$2"
  adbx "$serial" shell "BASE=/sdcard/Android/data/$PKG; if [ -d \"\$BASE\" ]; then find \"\$BASE\" -type f 2>/dev/null | while IFS= read -r f; do stat -c '%n|%s|%Y' \"\$f\" 2>/dev/null || echo \"\$f||\"; done; fi" >"$out" 2>/dev/null || :
}
snapshot_sockets(){ local serial="$1" out="$2"; adbx "$serial" shell 'ss -tun 2>/dev/null || netstat -an 2>/dev/null || true' >"$out" 2>/dev/null || :; }
snapshot_mem(){ local serial="$1" out="$2"; adbx "$serial" shell dumpsys meminfo "$PKG" >"$out" 2>/dev/null || :; }

cmd_pair(){
  ensure_adb || exit $?
  printf '%s\n' '--- SERVICES ADB DÉTECTÉS ---'
  adb mdns services 2>/dev/null || true
  printf 'Dans Android: Options développeur > Débogage sans fil > Associer appareil avec code.\n'
  printf 'Adresse de jumelage (IP:PORT): '
  IFS= read -r endpoint
  printf 'Code de jumelage à 6 chiffres: '
  IFS= read -r code
  [[ -n "$endpoint" && -n "$code" ]] || fail "adresse/code manquant"
  adb pair "$endpoint" "$code"
  sleep 1
  printf '%s\n' '--- CONNEXION ---'
  adb mdns services 2>/dev/null || true
  try_mdns_connect
  sleep 1
  adb devices
  if [[ -z "$(first_device)" ]]; then
    printf 'PAIR_OK_MAIS_CONNEXION_ABSENTE\nDans Débogage sans fil, relève aussi l’adresse IP et port de connexion puis exécute: adb connect IP:PORT\n'
  else
    printf 'FORMATION_LIVE_TRACE_ADB_READY device=%s\n' "$(first_device)"
  fi
}

cmd_check(){
  ensure_adb || exit $?
  try_mdns_connect
  local serial="$(first_device)"
  printf 'FORMATION_LIVE_TRACE_CHECK\n'
  printf 'adb=%s\n' "$(adb version 2>/dev/null | head -1 || true)"
  printf 'device=%s\n' "${serial:-NONE}"
  if [[ -n "$serial" ]]; then
    printf 'package='; adbx "$serial" shell pm path "$PKG" 2>/dev/null | head -1 | tr -d '\r' || true
    printf 'pid='; adbx "$serial" shell pidof "$PKG" 2>/dev/null | tr -d '\r' || true; printf '\n'
    printf 'uid='; adbx "$serial" shell dumpsys package "$PKG" 2>/dev/null | sed -n 's/.*userId=\([0-9][0-9]*\).*/\1/p' | head -1 | tr -d '\r' || true; printf '\n'
  fi
}

cmd_start(){
  [[ ! -f "$STATE" ]] || fail "une capture est déjà active; lance d’abord: $0 stop"
  local label="${*:-formation-change}"
  local serial="$(ensure_device)" || exit $?
  local sid="$(date +%Y%m%d_%H%M%S)"
  local dir="$BASE/sessions/$sid"
  mkdir -p "$dir"
  printf '%s\n' "$label" >"$dir/label.txt"
  local pid uid
  pid="$(adbx "$serial" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  if [[ -z "$pid" ]]; then
    adbx "$serial" shell monkey -p "$PKG" 1 >/dev/null 2>&1 || true
    sleep 4
    pid="$(adbx "$serial" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  fi
  [[ -n "$pid" ]] || fail "Last War ne tourne pas et n’a pas pu être lancé"
  uid="$(adbx "$serial" shell dumpsys package "$PKG" 2>/dev/null | sed -n 's/.*userId=\([0-9][0-9]*\).*/\1/p' | head -1 | tr -d '\r')"
  snapshot_files "$serial" "$dir/files-before.txt"
  snapshot_sockets "$serial" "$dir/sockets-before.txt"
  snapshot_mem "$serial" "$dir/mem-before.txt"
  adbx "$serial" shell dumpsys activity top >"$dir/activity-before.txt" 2>/dev/null || :
  local capmode
  if [[ -n "$uid" ]] && adbx "$serial" logcat --help 2>&1 | grep -q -- '--uid'; then
    capmode="uid:$uid"
    adbx "$serial" logcat --uid="$uid" -v epoch >"$dir/logcat.txt" 2>&1 &
  else
    capmode="pid:$pid"
    adbx "$serial" logcat --pid="$pid" -v epoch >"$dir/logcat.txt" 2>&1 &
  fi
  local cappid=$!
  cat >"$STATE" <<EOF
SESSION_ID=$sid
SESSION_DIR=$dir
SERIAL=$serial
APP_PID=$pid
APP_UID=${uid:-}
CAPTURE_PID=$cappid
CAPTURE_MODE=$capmode
START_EPOCH=$(date +%s)
EOF
  printf 'FORMATION_LIVE_TRACE_STARTED session=%s device=%s appPid=%s mode=%s\n' "$sid" "$serial" "$pid" "$capmode"
  printf 'ACTION: va maintenant dans Last War et effectue UNE SEULE modification de formation.\n'
  printf 'Puis reviens dans Termux et lance:\n  bash scripts/lastwar-formation-live-trace-v1.sh stop\n'
}

analyze_session(){
  local dir="$1" sid="$2"
  python - "$dir" "$DATA/latest.json" "$sid" <<'PY'
from pathlib import Path
import json,re,sys,time
sess,out,sid=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
label=(sess/'label.txt').read_text('utf-8','replace').strip() if (sess/'label.txt').exists() else 'formation-change'
logp=sess/'logcat.txt'
lines=logp.read_text('utf-8','replace').splitlines() if logp.exists() else []
exact=['UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','A_Hero_Audie_01','Murphy','Audie','RenderTexture','targetTexture','RawImage','AssetBundle.LoadAsset','LoadAsset','Instantiate','XLua','LWLuaFile']
keywords=['formation','hero','assetbundle','bundle','lua','xlua','rendertexture','targettexture','rawimage','camera','loadasset','instantiate','prefab','audie','murphy']

def rank(line):
    lo=line.lower(); score=0; hits=[]
    for a in exact:
        if a.lower() in lo: score+=100; hits.append(a)
    for k in keywords:
        if k in lo: score+=8; hits.append(k)
    return score,sorted(set(hits),key=str.lower)
relevant=[]; direct=[]
for i,line in enumerate(lines):
    s,h=rank(line)
    if s:
        row={'line':i+1,'text':line[:2000],'score':s,'hits':h}
        relevant.append(row)
        if s>=100: direct.append(row)
relevant.sort(key=lambda r:(-r['score'],r['line']))
direct.sort(key=lambda r:(-r['score'],r['line']))

def parse_files(p):
    d={}
    if not p.exists(): return d
    for line in p.read_text('utf-8','replace').splitlines():
        parts=line.rsplit('|',2)
        if len(parts)==3:
            path,size,mtime=parts
            d[path]={'size':int(size) if size.isdigit() else None,'mtime':int(mtime) if mtime.isdigit() else None}
        elif line.strip(): d[line.strip()]={'size':None,'mtime':None}
    return d
before=parse_files(sess/'files-before.txt'); after=parse_files(sess/'files-after.txt')
filedelta=[]
for p in sorted(set(before)|set(after)):
    a,b=before.get(p),after.get(p)
    if a is None: filedelta.append({'path':p,'change':'created','after':b})
    elif b is None: filedelta.append({'path':p,'change':'removed','before':a})
    elif a!=b: filedelta.append({'path':p,'change':'modified','before':a,'after':b})

def line_set(p):
    return set(x.strip() for x in p.read_text('utf-8','replace').splitlines() if x.strip()) if p.exists() else set()
sb=line_set(sess/'sockets-before.txt'); sa=line_set(sess/'sockets-after.txt')
sock_added=sorted(sa-sb)[:500]; sock_removed=sorted(sb-sa)[:500]
verdict='DIRECT_RUNTIME_EVIDENCE' if direct else ('PARTIAL_RUNTIME_EVIDENCE' if relevant else 'LOGCAT_SILENT_FOR_ASSET_LOADERS')
result={
 'format':'WFGG_LASTWAR_FORMATION_LIVE_TRACE_V1','sessionId':sid,'label':label,'generatedAt':int(time.time()),
 'summary':{'logLines':len(lines),'relevantLines':len(relevant),'directEvidence':len(direct),'fileChanges':len(filedelta),'socketAdded':len(sock_added),'socketRemoved':len(sock_removed)},
 'verdict':verdict,
 'directEvidence':direct[:300], 'relevant':relevant[:1000], 'fileDelta':filedelta[:1000],
 'socketAdded':sock_added,'socketRemoved':sock_removed,
 'knownStaticMap':{
   'Murphy':{'prefabName':'A_Hero_Audie_01','prefabBundle':17859,'meshBundle':26631,'textureBundles':[26633,26634],
             'note':'Référentiel statique déjà prouvé; affiché séparément des observations live.'}
 },
 'evidencePolicy':{'directEvidence':'texte réellement observé pendant la fenêtre de capture','relevant':'mots-clés observés; ne prouve pas à lui seul une liaison','knownStaticMap':'connaissance statique antérieure, pas un événement observé pendant cette capture'},
 'rawTail':lines[-1500:]
}
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
(sess/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_LIVE_TRACE_ANALYZED session={sid} logLines={len(lines)} relevant={len(relevant)} direct={len(direct)} fileChanges={len(filedelta)} verdict={verdict}")
PY
}

ensure_server(){
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then return 0; fi
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >"$BASE/http-server.log" 2>&1 & echo $! >"$BASE/http-server.pid")
  sleep 1
}

cmd_stop(){
  [[ -f "$STATE" ]] || fail "aucune capture active"
  # shellcheck disable=SC1090
  source "$STATE"
  kill "$CAPTURE_PID" 2>/dev/null || true
  wait "$CAPTURE_PID" 2>/dev/null || true
  snapshot_files "$SERIAL" "$SESSION_DIR/files-after.txt"
  snapshot_sockets "$SERIAL" "$SESSION_DIR/sockets-after.txt"
  snapshot_mem "$SERIAL" "$SESSION_DIR/mem-after.txt"
  adbx "$SERIAL" shell dumpsys activity top >"$SESSION_DIR/activity-after.txt" 2>/dev/null || :
  analyze_session "$SESSION_DIR" "$SESSION_ID"
  rm -f "$STATE"
  ensure_server
  printf 'FORMATION_LIVE_TRACE_STOPPED session=%s\n' "$SESSION_ID"
  printf 'VIEWER=%s\n' "$VIEWER"
}

cmd_auto(){
  local seconds="${1:-35}"; shift || true
  [[ "$seconds" =~ ^[0-9]+$ ]] || fail "durée invalide"
  cmd_start "${*:-formation-change-auto}"
  printf 'FENÊTRE_ACTIVE=%ss — passe dans le jeu maintenant.\n' "$seconds"
  sleep "$seconds"
  cmd_stop
}

case "${1:-help}" in
  pair) shift; cmd_pair "$@";;
  check) shift; cmd_check "$@";;
  start) shift; cmd_start "$@";;
  stop) shift; cmd_stop "$@";;
  auto) shift; cmd_auto "$@";;
  *) cat <<EOF
Formation Live Trace V1

Usage:
  $0 check
  $0 pair
  $0 start "Murphy -> autre héros"
  $0 stop
  $0 auto 35 "Murphy -> autre héros"

Le mode start/stop est recommandé: démarre la capture, fais UNE modification dans Last War, puis arrête-la.
EOF
  ;;
esac
