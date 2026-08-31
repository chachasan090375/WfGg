#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="portal-auth-lastwar-lab-v1"
PKG="com.fun.lastwar.gp"
BASE="$ROOT/frontend/lab/master-assets-v2/deep-live-trace-v1"
DATA="$ROOT/frontend/lab/formation-deep-live-trace-data"
STATE="$BASE/current.env"
PORT=8788
VIEWER="http://127.0.0.1:${PORT}/lab/lastwar-formation-deep-live-trace.html?v=1"
fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
cd "$ROOT"
[[ "$(git branch --show-current)" == "$BRANCH" ]] || fail "branche LAB incorrecte"
mkdir -p "$BASE/sessions" "$DATA"
command -v adb >/dev/null 2>&1 || fail "adb absent"
first_device(){ adb devices 2>/dev/null | awk 'NR>1 && $2=="device"{print $1; exit}'; }
ensure_device(){ local s="$(first_device)"; [[ -n "$s" ]] || fail "ADB non connecté"; printf '%s' "$s"; }
fd_snapshot(){ local s="$1" pid="$2"; adb -s "$s" shell "for f in /proc/$pid/fd/*; do x=\$(readlink \"\$f\" 2>/dev/null || true); [ -n \"\$x\" ] && printf '%s\\n' \"\$x\"; done" 2>/dev/null | tr -d '\r' | sort -u; }
start_capture(){
  [[ ! -f "$STATE" ]] || fail "capture déjà active; lance stop"
  local label="${*:-formation-deep-change}" s pid sid dir fdp sp
  s="$(ensure_device)"
  pid="$(timeout 2 adb -s "$s" shell pidof "$PKG" 2>/dev/null | tr -d '\r' | awk '{print $1}')"
  [[ -n "$pid" ]] || fail "Last War ne tourne pas"
  sid="$(date +%Y%m%d_%H%M%S)"; dir="$BASE/sessions/$sid"; mkdir -p "$dir"
  printf '%s\n' "$label" > "$dir/label.txt"
  printf 'DEEP_LIVE_TRACE_PREP device=%s pid=%s session=%s\n' "$s" "$pid" "$sid"
  fd_snapshot "$s" "$pid" > "$dir/fd-before.txt" || true
  printf 'DEEP_LIVE_TRACE_FD_POLL_START\n'
  # Persistent shell avoids repeated adb setup. Each frame starts with @timestamp and ends with --.
  adb -s "$s" shell "while [ -d /proc/$pid/fd ]; do printf '@'; date +%s.%N; for f in /proc/$pid/fd/*; do x=\$(readlink \"\$f\" 2>/dev/null || true); [ -n \"\$x\" ] && printf '%s\\n' \"\$x\"; done; printf '%s\\n' '--'; sleep 0.12; done" > "$dir/fd-samples.txt" 2>"$dir/fd-poll.err" &
  fdp=$!
  printf 'DEEP_LIVE_TRACE_STRACE_START\n'
  # Attachment may be denied on production builds; failure is recorded and does not abort fd tracing.
  adb -s "$s" shell "strace -tt -f -p $pid -e trace=openat,read,mmap,connect,sendto,recvfrom -s 300 2>&1" > "$dir/strace.txt" 2>&1 &
  sp=$!
  cat > "$STATE" <<EOF
SESSION_ID=$sid
SESSION_DIR=$dir
SERIAL=$s
APP_PID=$pid
FD_POLL_PID=$fdp
STRACE_PID=$sp
START_EPOCH=$(date +%s)
EOF
  printf 'FORMATION_DEEP_LIVE_TRACE_V1_STARTED session=%s\n' "$sid"
  printf 'ACTION=Dans Last War, fais UNE seule modification de formation puis reviens dans Termux.\n'
  printf 'STOP=bash scripts/lastwar-formation-deep-live-trace-v1.sh stop\n'
}
analyze(){
  local dir="$1" sid="$2"
  python - "$dir" "$DATA/latest.json" "$sid" <<'PY'
from pathlib import Path
import sys,re,json,collections,time
sess,out,sid=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
label=(sess/'label.txt').read_text('utf-8','replace').strip() if (sess/'label.txt').exists() else ''
before=set((sess/'fd-before.txt').read_text('utf-8','replace').splitlines()) if (sess/'fd-before.txt').exists() else set()
samples=(sess/'fd-samples.txt').read_text('utf-8','replace').splitlines() if (sess/'fd-samples.txt').exists() else []
seen=collections.Counter(); frames=0
for line in samples:
    line=line.strip()
    if not line: continue
    if line.startswith('@'): frames+=1; continue
    if line=='--': continue
    seen[line]+=1
new=[p for p in seen if p not in before]
def score_path(p):
    lo=p.lower(); s=0; hits=[]
    for k,w in [('assetbundle',80),('bundle',50),('lwscripts',80),('lua',35),('gamers_',30),('hero',45),('formation',60),('prefab',55),('.unity3d',60),('/files/',20),('/cache/',10),('lastwar',20)]:
        if k in lo:s+=w;hits.append(k)
    if p.startswith('socket:') or p.startswith('pipe:') or p.startswith('anon_inode:'): s-=30
    return s,hits
fdrows=[]
for p,c in seen.items():
    s,h=score_path(p)
    fdrows.append({'path':p,'samples':c,'new':p not in before,'score':s,'hits':h})
fdrows.sort(key=lambda x:(-x['score'],-int(x['new']),-x['samples'],x['path']))
strace=(sess/'strace.txt').read_text('utf-8','replace').splitlines() if (sess/'strace.txt').exists() else []
attach_denied=any(re.search(r'(?i)operation not permitted|permission denied|ptrace.*denied|attach.*denied',x) for x in strace[:80])
openrows=[]; syscall_counts=collections.Counter(); path_counts=collections.Counter()
qpath=re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
for line in strace:
    m=re.search(r'\b(openat|read|mmap|connect|sendto|recvfrom)\s*\(',line)
    if m: syscall_counts[m.group(1)]+=1
    if 'openat(' in line:
        qm=qpath.search(line)
        if qm:
            p=qm.group(1); path_counts[p]+=1
for p,c in path_counts.items():
    s,h=score_path(p); openrows.append({'path':p,'count':c,'score':s,'hits':h})
openrows.sort(key=lambda x:(-x['score'],-x['count'],x['path']))
strong=[x for x in openrows if x['score']>=40] + [x for x in fdrows if x['new'] and x['score']>=40]
verdict='STRACE_AND_FD_EVIDENCE' if openrows and not attach_denied else ('PROC_FD_CHANGE_EVIDENCE' if any(x['new'] and x['score']>0 for x in fdrows) else ('PROC_FD_OBSERVABLE_STRACE_DENIED' if attach_denied else 'NO_ASSET_PATH_OBSERVED'))
result={
 'format':'WFGG_LASTWAR_FORMATION_DEEP_LIVE_TRACE_V1','sessionId':sid,'label':label,'generatedAt':int(time.time()),'verdict':verdict,
 'summary':{'fdFrames':frames,'fdUnique':len(seen),'fdNew':len(new),'straceLines':len(strace),'straceAttachDenied':attach_denied,'openPaths':len(openrows),'strongCandidates':len(strong)},
 'fdCandidates':fdrows[:1200],'straceOpenPaths':openrows[:1200],'syscalls':dict(syscall_counts),'strongCandidates':strong[:400],
 'straceHead':strace[:120],'fdPollErrors':(sess/'fd-poll.err').read_text('utf-8','replace').splitlines()[:80] if (sess/'fd-poll.err').exists() else [],
 'method':'Fast /proc/PID/fd polling plus best-effort strace attachment during one formation change.'
}
out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
(sess/'analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
print(f"FORMATION_DEEP_LIVE_TRACE_V1_ANALYZED session={sid} frames={frames} fdUnique={len(seen)} fdNew={len(new)} straceLines={len(strace)} openPaths={len(openrows)} strong={len(strong)} verdict={verdict}")
print('--- TOP STRONG ---')
for x in strong[:30]: print(x)
PY
}
ensure_server(){
  if command -v curl >/dev/null 2>&1 && curl -fsS --max-time 1 "http://127.0.0.1:${PORT}/lab/" >/dev/null 2>&1; then return; fi
  (cd "$ROOT/frontend" && nohup python -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 &)
  sleep 1
}
stop_capture(){
  [[ -f "$STATE" ]] || fail "aucune capture active"
  source "$STATE"
  printf 'FORMATION_DEEP_LIVE_TRACE_V1_STOPPING session=%s\n' "$SESSION_ID"
  kill "$FD_POLL_PID" "$STRACE_PID" 2>/dev/null || true
  sleep .5
  kill -9 "$FD_POLL_PID" "$STRACE_PID" 2>/dev/null || true
  fd_snapshot "$SERIAL" "$APP_PID" > "$SESSION_DIR/fd-after.txt" || true
  analyze "$SESSION_DIR" "$SESSION_ID"
  rm -f "$STATE"
  ensure_server
  printf 'VIEWER=%s\n' "$VIEWER"
}
case "${1:-help}" in
 start) shift; start_capture "$@";;
 stop) stop_capture;;
 *) printf 'Usage: %s start "Murphy -> autre héros" | stop\n' "$0";;
esac
