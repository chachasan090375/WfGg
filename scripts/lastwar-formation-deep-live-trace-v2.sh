#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
BASE="$ROOT/frontend/lab/master-assets-v2/deep-live-trace-v2"
DATA="$ROOT/frontend/lab/formation-deep-live-trace-data"
STATE="$BASE/current.env"
PORT=8788
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-deep-live-trace.html?v=2"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
mkdir -p "$BASE/sessions" "$DATA"
command -v adb >/dev/null 2>&1 || fail "adb absent"
first_device(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}'; }
ensure_device(){ local s="$(first_device)"; [[ -n "$s" ]] || fail "ADB non connecté"; printf '%s' "$s"; }
fd_snapshot(){ local s="$1" pid="$2"; timeout 3 adb -s "$s" shell "ls -l /proc/$pid/fd 2>&1" 2>/dev/null | tr -d '\r'; }
start_capture(){
  [[ ! -f "$STATE" ]] || fail "capture déjà active; lance stop"
  local label="${*:-formation-deep-change}" s pid sid dir fdp sp
  s="$(ensure_device)"
  pid="$(timeout 2 adb -s "$s" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  [[ -n "$pid" ]] || fail "Last War ne tourne pas"
  sid="$(date +%Y%m%d_%H%M%S)"; dir="$BASE/sessions/$sid"; mkdir -p "$dir"
  printf '%s\n' "$label" > "$dir/label.txt"
  printf 'DEEP_LIVE_TRACE_V2_PREP device=%s pid=%s session=%s\n' "$s" "$pid" "$sid"
  fd_snapshot "$s" "$pid" > "$dir/fd-before.txt" || true
  printf 'DEEP_LIVE_TRACE_V2_FD_POLL_START\n'
  adb -s "$s" shell "while [ -d /proc/$pid/fd ]; do printf '@'; date +%s.%N; ls -l /proc/$pid/fd 2>&1; printf '%s\\n' '--'; sleep 0.15; done" > "$dir/fd-samples.txt" 2>"$dir/fd-poll.err" &
  fdp=$!
  printf 'DEEP_LIVE_TRACE_V2_STRACE_START\n'
  adb -s "$s" shell "strace -tt -f -p $pid -e trace=openat,openat2,read,pread64,mmap,connect,sendto,recvfrom -s 300 2>&1" > "$dir/strace.txt" 2>&1 &
  sp=$!
  sleep .6
  printf '%s\n' '--- STRACE EARLY STATUS ---'
  head -n 3 "$dir/strace.txt" 2>/dev/null || true
  cat > "$STATE" <<EOF
SESSION_ID=$sid
SESSION_DIR=$dir
SERIAL=$s
APP_PID=$pid
FD_POLL_PID=$fdp
STRACE_PID=$sp
START_EPOCH=$(date +%s)
EOF
  printf 'FORMATION_DEEP_LIVE_TRACE_V2_STARTED session=%s\n' "$sid"
  printf 'ACTION=Dans Last War, fais UNE seule modification de formation puis reviens dans Termux.\n'
  printf 'STOP=bash scripts/lastwar-formation-deep-live-trace-v2.sh stop\n'
}
analyze(){
  local dir="$1" sid="$2"
  python - "$dir" "$DATA/latest.json" "$sid" <<'PY'
from pathlib import Path
import sys,re,json,collections,time
sess,out,sid=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
label=(sess/'label.txt').read_text('utf-8','replace').strip() if (sess/'label.txt').exists() else ''
arrow=re.compile(r'\s->\s(.+)$')
def targets(lines):
    res=[]
    for line in lines:
        m=arrow.search(line.strip())
        if m: res.append(m.group(1).strip())
    return res
before_lines=(sess/'fd-before.txt').read_text('utf-8','replace').splitlines() if (sess/'fd-before.txt').exists() else []
before=set(targets(before_lines))
samples=(sess/'fd-samples.txt').read_text('utf-8','replace').splitlines() if (sess/'fd-samples.txt').exists() else []
seen=collections.Counter(); frames=0; rawFdLines=0; permissionLines=[]
for line in samples:
    line=line.strip()
    if not line: continue
    if line.startswith('@'): frames+=1; continue
    if line=='--': continue
    if re.search(r'(?i)permission denied|operation not permitted',line):
        if len(permissionLines)<30: permissionLines.append(line)
        continue
    m=arrow.search(line)
    if m:
        rawFdLines+=1; seen[m.group(1).strip()]+=1
new=[p for p in seen if p not in before]
def score_path(p):
    lo=p.lower(); s=0; hits=[]
    for k,w in [('assetbundle',90),('.bundle',80),('bundle',45),('lwscripts',90),('lua',35),('gamers_',35),('hero',50),('formation',70),('prefab',60),('.unity3d',70),('/files/',20),('/cache/',10),('lastwar',20),('split_install_time_pack',25)]:
        if k in lo:s+=w;hits.append(k)
    if p.startswith(('socket:','pipe:','anon_inode:')): s-=30
    return s,hits
fdrows=[]
for p,c in seen.items():
    s,h=score_path(p); fdrows.append({'path':p,'samples':c,'new':p not in before,'score':s,'hits':h})
fdrows.sort(key=lambda x:(-x['score'],-int(x['new']),-x['samples'],x['path']))
strace=(sess/'strace.txt').read_text('utf-8','replace').splitlines() if (sess/'strace.txt').exists() else []
attach_error=''
for x in strace[:50]:
    if re.search(r'(?i)operation not permitted|permission denied|ptrace|attach|no such process|not found',x):
        attach_error=x.strip(); break
openrows=[]; syscall_counts=collections.Counter(); path_counts=collections.Counter()
qpath=re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
for line in strace:
    m=re.search(r'\b(openat2?|read|pread64|mmap|connect|sendto|recvfrom)\s*\(',line)
    if m: syscall_counts[m.group(1)]+=1
    if 'openat(' in line or 'openat2(' in line:
        qs=qpath.findall(line)
        if qs:
            p=qs[0]; path_counts[p]+=1
for p,c in path_counts.items():
    s,h=score_path(p); openrows.append({'path':p,'count':c,'score':s,'hits':h})
openrows.sort(key=lambda x:(-x['score'],-x['count'],x['path']))
strong=[dict(x,source='strace') for x in openrows if x['score']>=40] + [dict(x,source='procFd') for x in fdrows if x['new'] and x['score']>=40]
if strong: verdict='DEEP_FILE_RUNTIME_EVIDENCE'
elif seen: verdict='PROC_FD_PATHS_VISIBLE_NO_TARGET_ASSET'
elif permissionLines: verdict='PROC_FD_LIST_VISIBLE_TARGETS_HIDDEN'
elif attach_error: verdict='STRACE_DENIED_NO_FD_TARGETS'
else: verdict='NO_DEEP_PATH_EVIDENCE'
result={'format':'WFGG_LASTWAR_FORMATION_DEEP_LIVE_TRACE_V2','sessionId':sid,'label':label,'generatedAt':int(time.time()),'verdict':verdict,
 'summary':{'fdFrames':frames,'fdRawTargetLines':rawFdLines,'fdUnique':len(seen),'fdNew':len(new),'straceLines':len(strace),'straceAttachError':bool(attach_error),'openPaths':len(openrows),'strongCandidates':len(strong)},
 'fdCandidates':fdrows[:1500],'straceOpenPaths':openrows[:1500],'syscalls':dict(syscall_counts),'strongCandidates':strong[:500],
 'straceHead':strace[:120],'straceAttachError':attach_error,'fdPermissionLines':permissionLines,
 'fdPollErrors':(sess/'fd-poll.err').read_text('utf-8','replace').splitlines()[:80] if (sess/'fd-poll.err').exists() else [],
 'method':'Robust ls -l /proc/PID/fd polling parsed from symlink arrows, plus best-effort strace.'}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');(sess/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_DEEP_LIVE_TRACE_V2_ANALYZED session={sid} frames={frames} fdRaw={rawFdLines} fdUnique={len(seen)} fdNew={len(new)} straceLines={len(strace)} openPaths={len(openrows)} strong={len(strong)} verdict={verdict}")
if attach_error: print('STRACE_ATTACH_ERROR='+attach_error)
if permissionLines: print('FD_PERMISSION_SAMPLE='+permissionLines[0])
print('--- TOP FD ---')
for x in fdrows[:20]: print(x)
print('--- TOP STRONG ---')
for x in strong[:30]: print(x)
PY
}
ensure_server(){
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then return; fi
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &); sleep 1
}
stop_capture(){
  [[ -f "$STATE" ]] || fail "aucune capture active"
  source "$STATE"
  printf 'FORMATION_DEEP_LIVE_TRACE_V2_STOPPING session=%s\n' "$SESSION_ID"
  kill "$FD_POLL_PID" "$STRACE_PID" 2>/dev/null || true; sleep .5; kill -9 "$FD_POLL_PID" "$STRACE_PID" 2>/dev/null || true
  fd_snapshot "$SERIAL" "$APP_PID" > "$SESSION_DIR/fd-after.txt" || true
  analyze "$SESSION_DIR" "$SESSION_ID"
  rm -f "$STATE"; ensure_server; printf 'VIEWER=%s\n' "$VIEWER"
}
case "${1:-help}" in start) shift; start_capture "$@";; stop) stop_capture;; *) printf 'Usage: %s start "Murphy -> autre héros" | stop\n' "$0";; esac
