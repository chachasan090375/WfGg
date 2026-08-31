#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
BASE="$ROOT/frontend/lab/master-assets-v2/formation-strace-live-v1"
DATA="$ROOT/frontend/lab/formation-strace-live-data"
STATE="$BASE/current.env"
PORT=8788
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-strace-live.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
mkdir -p "$BASE/sessions" "$DATA"
command -v adb >/dev/null 2>&1 || fail "adb absent"
first_device(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1;exit}'; }
ensure_device(){ local s="$(first_device)"; [[ -n "$s" ]] || fail "ADB non connecté"; printf '%s' "$s"; }
choose_filter(){
  local s="$1" pid="$2" out="$3" f rc txt
  : > "$out"
  local filters=(
    'openat,read,pread64,mmap,connect,sendto,recvfrom,sendmsg,recvmsg'
    'openat,read,mmap,connect,sendto,recvfrom'
    'file,network'
    'openat,read'
  )
  for f in "${filters[@]}"; do
    printf 'TEST_FILTER=%s\n' "$f" | tee -a "$out" >&2
    set +e
    txt="$(timeout 2 adb -s "$s" shell "timeout 1 strace -tt -f -p $pid -e trace=$f -s 80 2>&1" 2>&1 | tr -d '\r')"
    rc=$?
    set -e
    printf 'rc=%s\n%s\n---\n' "$rc" "$txt" >> "$out"
    if ! printf '%s' "$txt" | grep -Eqi 'invalid|unknown syscall|invalid system call|unrecognized|not found|operation not permitted|permission denied|ptrace.*denied'; then
      if printf '%s' "$txt" | grep -Eqi 'attached|detached|^[[:space:]]*[0-9]+[[:space:]]+[0-9:.]+|^[0-9:.]+[[:space:]]'; then
        printf '%s' "$f"
        return 0
      fi
    fi
  done
  return 1
}
start_capture(){
  [[ ! -f "$STATE" ]] || fail "capture déjà active; lance stop"
  local label="${*:-formation-strace-change}" s pid sid dir filter lp threads
  s="$(ensure_device)"
  pid="$(timeout 2 adb -s "$s" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  [[ -n "$pid" ]] || fail "Last War ne tourne pas"
  sid="$(date +%Y%m%d_%H%M%S)"; dir="$BASE/sessions/$sid"; mkdir -p "$dir"
  printf '%s\n' "$label" > "$dir/label.txt"
  threads="$(timeout 2 adb -s "$s" shell "ls /proc/$pid/task 2>/dev/null | wc -l" 2>/dev/null | tr -dc '0-9' || true)"
  printf 'FORMATION_STRACE_LIVE_V1_PREP device=%s pid=%s threads=%s session=%s\n' "$s" "$pid" "${threads:-?}" "$sid"
  filter="$(choose_filter "$s" "$pid" "$dir/filter-probe.txt")" || fail "aucun filtre strace exploitable; voir $dir/filter-probe.txt"
  printf 'STRACE_FILTER_SELECTED=%s\n' "$filter"
  printf '%s\n' "$filter" > "$dir/filter.txt"
  # Main runtime trace. -f follows threads/forks from the attached process. -yy is attempted only when supported by this strace.
  adb -s "$s" shell "strace -tt -f -p $pid -e trace=$filter -s 512 2>&1" > "$dir/strace.txt" 2>&1 &
  lp=$!
  sleep .7
  printf '%s\n' '--- STRACE START STATUS ---'
  head -n 8 "$dir/strace.txt" 2>/dev/null || true
  if grep -Eqi 'invalid|unknown syscall|invalid system call|unrecognized|operation not permitted|permission denied|ptrace.*denied' "$dir/strace.txt" 2>/dev/null; then
    kill "$lp" 2>/dev/null || true
    fail "strace a refusé la capture; voir $dir/strace.txt"
  fi
  cat > "$STATE" <<EOF
SESSION_ID=$sid
SESSION_DIR=$dir
SERIAL=$s
APP_PID=$pid
LOCAL_TRACE_PID=$lp
FILTER=$filter
START_EPOCH=$(date +%s)
EOF
  printf 'FORMATION_STRACE_LIVE_V1_STARTED session=%s filter=%s\n' "$sid" "$filter"
  printf 'ACTION=Dans Last War, fais UNE seule modification de formation puis reviens dans Termux.\n'
  printf 'STOP=bash scripts/lastwar-formation-strace-live-v1.sh stop\n'
}
analyze(){
  local dir="$1" sid="$2"
  python - "$dir" "$DATA/latest.json" "$sid" <<'PY'
from pathlib import Path
import sys,re,json,collections,time
sess,out,sid=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
label=(sess/'label.txt').read_text('utf-8','replace').strip() if (sess/'label.txt').exists() else ''
filter_txt=(sess/'filter.txt').read_text('utf-8','replace').strip() if (sess/'filter.txt').exists() else ''
lines=(sess/'strace.txt').read_text('utf-8','replace').splitlines() if (sess/'strace.txt').exists() else []
err_re=re.compile(r'(?i)invalid|unknown syscall|invalid system call|unrecognized|operation not permitted|permission denied|ptrace.*denied')
errors=[x for x in lines if err_re.search(x)]
call_re=re.compile(r'\b(openat|open|read|pread64|mmap|connect|sendto|recvfrom|sendmsg|recvmsg)\s*\(')
q_re=re.compile(r'"((?:\\.|[^"\\])*)"')
syscalls=collections.Counter(); paths=collections.Counter(); timeline=[]; net=[]
for i,line in enumerate(lines):
    m=call_re.search(line)
    if not m: continue
    call=m.group(1); syscalls[call]+=1
    qs=q_re.findall(line)
    path=None
    if call in ('open','openat') and qs:
        # openat's first quoted string is the pathname in normal strace output.
        path=qs[0].replace('\\"','"')
        paths[path]+=1
    ret=None
    rm=re.search(r'=\s*(-?\d+)\s*$',line)
    if rm:
        try:ret=int(rm.group(1))
        except:pass
    item={'line':i+1,'syscall':call,'text':line[:3000]}
    if path is not None:item['path']=path
    if ret is not None:item['result']=ret
    timeline.append(item)
    if call in ('connect','sendto','recvfrom','sendmsg','recvmsg'):
        net.append(item)

def score_path(p):
    lo=p.lower(); score=0; hits=[]
    for k,w in [
      ('assetbundle',100),('.bundle',90),('bundle',55),('gamers_',55),('hero',65),('formation',90),
      ('prefab',75),('lwscripts',85),('lua',30),('.unity3d',80),('audie',80),('murphy',90),
      ('streamingassets',40),('/files/',20),('/cache/',10),('lastwar',20)
    ]:
        if k in lo:score+=w;hits.append(k)
    return score,hits
pathrows=[]
for p,c in paths.items():
    s,h=score_path(p);pathrows.append({'path':p,'count':c,'score':s,'hits':h})
pathrows.sort(key=lambda x:(-x['score'],-x['count'],x['path']))
strong=[x for x in pathrows if x['score']>=50]
# Also retain lines containing exact project anchors even if not an open path.
anchor_re=re.compile(r'(?i)A_Hero_|Audie|Murphy|FormationRT|UIHeroPVPFormationPanel|AssetBundle|LWScripts|gamers_|prefab|bundle')
anchor_lines=[{'line':i+1,'text':x[:3000]} for i,x in enumerate(lines) if anchor_re.search(x)]
# Network result-size histogram can reveal a stable formation RPC even under TLS.
net_sizes=collections.Counter()
for x in net:
    if isinstance(x.get('result'),int) and x['result']>=0: net_sizes[str(x['result'])]+=1
verdict='STRACE_TARGET_PATH_EVIDENCE' if strong else ('STRACE_ANCHOR_EVIDENCE' if anchor_lines else ('STRACE_RUNTIME_ACTIVITY' if sum(syscalls.values()) else 'STRACE_NO_SYSCALL_ACTIVITY'))
result={
 'format':'WFGG_LASTWAR_FORMATION_STRACE_LIVE_V1','sessionId':sid,'label':label,'generatedAt':int(time.time()),'filter':filter_txt,'verdict':verdict,
 'summary':{'rawLines':len(lines),'syscalls':sum(syscalls.values()),'openPaths':len(pathrows),'strongPaths':len(strong),'anchorLines':len(anchor_lines),'networkCalls':len(net),'errors':len(errors)},
 'syscalls':dict(syscalls),'strongPaths':strong[:500],'openPaths':pathrows[:2000],'anchorLines':anchor_lines[:800],
 'networkTimeline':net[:2500],'networkResultSizes':dict(net_sizes.most_common(200)),'timeline':timeline[:8000],
 'errors':errors[:120],'traceHead':lines[:120],'traceTail':lines[-120:],
 'method':'Adaptive strace attachment to Last War during one formation mutation. Paths come directly from open/openat arguments; network calls are retained even when payloads are TLS-encrypted.'
}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
(sess/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_STRACE_LIVE_V1_ANALYZED session={sid} raw={len(lines)} syscalls={sum(syscalls.values())} paths={len(pathrows)} strong={len(strong)} anchors={len(anchor_lines)} net={len(net)} verdict={verdict}")
print('--- SYSCALLS ---')
for k,v in syscalls.most_common(): print(k,v)
print('--- TOP PATHS ---')
for x in pathrows[:30]: print(x)
print('--- ANCHORS ---')
for x in anchor_lines[:30]: print(x)
print('JSON='+str(out))
PY
}
ensure_server(){
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then return; fi
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &); sleep 1
}
stop_capture(){
  [[ -f "$STATE" ]] || fail "aucune capture active"
  source "$STATE"
  printf 'FORMATION_STRACE_LIVE_V1_STOPPING session=%s\n' "$SESSION_ID"
  # Ask remote strace to detach cleanly, then close local adb transport.
  timeout 2 adb -s "$SERIAL" shell "pkill -INT -f 'strace.*-p $APP_PID' 2>/dev/null || true" >/dev/null 2>&1 || true
  sleep .5
  kill "$LOCAL_TRACE_PID" 2>/dev/null || true
  sleep .2
  kill -9 "$LOCAL_TRACE_PID" 2>/dev/null || true
  analyze "$SESSION_DIR" "$SESSION_ID"
  rm -f "$STATE"
  ensure_server
  printf 'VIEWER=%s\n' "$VIEWER"
}
case "${1:-help}" in
 start) shift; start_capture "$@";;
 stop) stop_capture;;
 *) printf 'Usage: %s start "autre héros -> Murphy" | stop\n' "$0";;
esac
