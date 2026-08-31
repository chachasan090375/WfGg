#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
PORT=8788
BASE="$ROOT/frontend/lab/master-assets-v2/live-trace-v2"
DATA="$ROOT/frontend/lab/formation-live-trace-data"
STATE="$BASE/current.env"
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-live-trace.html?v=2"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
mkdir -p "$BASE/sessions" "$DATA"
command -v adb >/dev/null 2>&1 || fail "adb absent"

first_device(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}'; }
adbx(){ local s="$1"; shift; adb -s "$s" "$@"; }
quick(){ timeout "${1:-3}" "${@:2}" 2>/dev/null || true; }

ensure_device(){
  local s="$(first_device)"
  [[ -n "$s" ]] || fail "ADB non connecté; relance le pair-v2 si nécessaire"
  printf '%s' "$s"
}

quick_snapshot(){
  local s="$1" dir="$2" phase="$3"
  printf 'LIVE_TRACE_%s snapshot=activity\n' "$phase"
  quick 2 adb -s "$s" shell dumpsys activity top >"$dir/activity-$phase.txt"
  printf 'LIVE_TRACE_%s snapshot=sockets\n' "$phase"
  quick 2 adb -s "$s" shell 'ss -tun 2>/dev/null || netstat -an 2>/dev/null || true' >"$dir/sockets-$phase.txt"
}

start_capture(){
  [[ ! -f "$STATE" ]] || fail "capture V2 déjà active; lance: bash scripts/lastwar-formation-live-trace-v2.sh stop"
  local label="${*:-formation-change}" s pid sid dir capmode cappid
  s="$(ensure_device)"
  printf 'FORMATION_LIVE_TRACE_V2_PREP device=%s\n' "$s"
  pid="$(quick 2 adb -s "$s" shell pidof "$PKG" | tr -d '\r' | awk '{print $1}')"
  [[ -n "$pid" ]] || fail "Last War ne tourne pas; ouvre le jeu puis relance"
  sid="$(date +%Y%m%d_%H%M%S)"; dir="$BASE/sessions/$sid"; mkdir -p "$dir"
  printf '%s\n' "$label" >"$dir/label.txt"
  printf 'LIVE_TRACE_APP pid=%s\n' "$pid"
  quick_snapshot "$s" "$dir" before
  printf 'LIVE_TRACE_LOGCAT_START\n'
  # Use PID filtering when supported; otherwise full logcat for the short capture window.
  if timeout 2 adb -s "$s" logcat --help 2>&1 | grep -q -- '--pid'; then
    capmode="pid:$pid"
    adb -s "$s" logcat --pid="$pid" -v epoch >"$dir/logcat.txt" 2>&1 &
  else
    capmode="full"
    adb -s "$s" logcat -v epoch >"$dir/logcat.txt" 2>&1 &
  fi
  cappid=$!
  cat >"$STATE" <<EOF
SESSION_ID=$sid
SESSION_DIR=$dir
SERIAL=$s
APP_PID=$pid
CAPTURE_PID=$cappid
CAPTURE_MODE=$capmode
START_EPOCH=$(date +%s)
EOF
  printf 'FORMATION_LIVE_TRACE_V2_STARTED session=%s mode=%s\n' "$sid" "$capmode"
  printf 'ACTION=Dans Last War, fais UNE SEULE modification: retire Murphy et mets un seul autre héros, puis valide.\n'
  printf 'STOP=bash scripts/lastwar-formation-live-trace-v2.sh stop\n'
}

analyze(){
  local dir="$1" sid="$2"
  python - "$dir" "$DATA/latest.json" "$sid" <<'PY'
from pathlib import Path
import json,sys,time,re
sess,out,sid=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
label=(sess/'label.txt').read_text('utf-8','replace').strip() if (sess/'label.txt').exists() else 'formation-change'
lines=(sess/'logcat.txt').read_text('utf-8','replace').splitlines() if (sess/'logcat.txt').exists() else []
exact=['UIHeroPVPFormationPanel','FormationRT','FormationBg','FormationContent','A_Hero_Audie_01','Murphy','Audie','RenderTexture','targetTexture','RawImage','AssetBundle.LoadAsset','LoadAsset','Instantiate','XLua','LWLuaFile']
keywords=['formation','hero','assetbundle','bundle','lua','xlua','rendertexture','targettexture','rawimage','camera','loadasset','instantiate','prefab','audie','murphy','slot','squad']
def rank(line):
    lo=line.lower(); score=0; hits=[]
    for a in exact:
        if a.lower() in lo: score+=100; hits.append(a)
    for k in keywords:
        if k in lo: score+=8; hits.append(k)
    return score,sorted(set(hits),key=str.lower)
relevant=[]; direct=[]
for i,line in enumerate(lines,1):
    s,h=rank(line)
    if s:
        row={'line':i,'text':line[:2200],'score':s,'hits':h}
        relevant.append(row)
        if s>=100: direct.append(row)
relevant.sort(key=lambda r:(-r['score'],r['line'])); direct.sort(key=lambda r:(-r['score'],r['line']))
def lset(name):
    p=sess/name
    return set(x.strip() for x in p.read_text('utf-8','replace').splitlines() if x.strip()) if p.exists() else set()
sb,sa=lset('sockets-before.txt'),lset('sockets-after.txt')
added,removed=sorted(sa-sb)[:500],sorted(sb-sa)[:500]
verdict='DIRECT_RUNTIME_EVIDENCE' if direct else ('PARTIAL_RUNTIME_EVIDENCE' if relevant else 'LOGCAT_SILENT_FOR_ASSET_LOADERS')
result={
 'format':'WFGG_LASTWAR_FORMATION_LIVE_TRACE_V2','sessionId':sid,'label':label,'generatedAt':int(time.time()),
 'summary':{'logLines':len(lines),'relevantLines':len(relevant),'directEvidence':len(direct),'fileChanges':0,'socketAdded':len(added),'socketRemoved':len(removed)},
 'verdict':verdict,'directEvidence':direct[:300],'relevant':relevant[:1200],'fileDelta':[],
 'socketAdded':added,'socketRemoved':removed,
 'knownStaticMap':{'Murphy':{'prefabName':'A_Hero_Audie_01','prefabBundle':17859,'meshBundle':26631,'textureBundles':[26633,26634],'note':'Référentiel statique antérieur; séparé des observations live.'}},
 'evidencePolicy':{'directEvidence':'texte réellement observé dans logcat pendant la modification','relevant':'mot-clé observé, sans preuve automatique de liaison','knownStaticMap':'référentiel statique antérieur'},
 'rawTail':lines[-1800:]
}
out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
(sess/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_LIVE_TRACE_V2_ANALYZED session={sid} logLines={len(lines)} relevant={len(relevant)} direct={len(direct)} verdict={verdict}")
PY
}

ensure_server(){
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then return 0; fi
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >"$BASE/http-server.log" 2>&1 & echo $! >"$BASE/http-server.pid")
  sleep 1
}

stop_capture(){
  [[ -f "$STATE" ]] || fail "aucune capture V2 active"
  # shellcheck disable=SC1090
  source "$STATE"
  printf 'FORMATION_LIVE_TRACE_V2_STOPPING session=%s\n' "$SESSION_ID"
  kill "$CAPTURE_PID" 2>/dev/null || true
  sleep 1
  kill -9 "$CAPTURE_PID" 2>/dev/null || true
  quick_snapshot "$SERIAL" "$SESSION_DIR" after
  analyze "$SESSION_DIR" "$SESSION_ID"
  rm -f "$STATE"
  ensure_server
  printf 'FORMATION_LIVE_TRACE_V2_STOPPED session=%s\n' "$SESSION_ID"
  printf 'VIEWER=%s\n' "$VIEWER"
}

case "${1:-help}" in
  start) shift; start_capture "$@";;
  stop) shift; stop_capture;;
  check) s="$(ensure_device)"; printf 'FORMATION_LIVE_TRACE_V2_CHECK device=%s\n' "$s"; quick 2 adb -s "$s" shell pidof "$PKG" | tr -d '\r'; printf '\n';;
  *) printf 'Usage: %s check | start "Murphy -> autre héros" | stop\n' "$0";;
esac
