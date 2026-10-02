from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "lib"))
from guardian_stop_evidence_resolver import resolve_evidence
from guardian_stop_applicability import classify

REV_RE = re.compile(r"^[0-9a-f]{40}$")

def active_revision(current: Path) -> str:
    marker = current / ".revision"
    if not marker.is_file(): raise RuntimeError("ACTIVE_REVISION_MARKER_MISSING")
    revision = marker.read_text(encoding="utf-8").strip().lower()
    if not REV_RE.fullmatch(revision): raise RuntimeError("ACTIVE_REVISION_MARKER_INVALID")
    return revision

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--guardian-root",type=Path,required=True); ap.add_argument("--current",type=Path,required=True); ap.add_argument("--live-candidate",action="append",default=[]); ap.add_argument("--stale-revision",action="append",default=[]); a=ap.parse_args()
    active=active_revision(a.current); rows=[]
    for path in sorted((a.guardian_root/"alerts").glob("*.json")):
        try: alert=json.loads(path.read_text(encoding="utf-8"))
        except Exception: continue
        if str(alert.get("severity") or "").upper()!="CRITICAL" or str(alert.get("status") or "").upper()!="OPEN": continue
        ev=resolve_evidence(alert,a.guardian_root); app=classify(ev,active,set(a.live_candidate),set(a.stale_revision)); rows.append({"alert_id":alert.get("alert_id"),"evidence":ev,"applicability":app})
    counts={k:sum(1 for r in rows if r["applicability"]["classification"]==k) for k in ("PRODUCTION_APPLICABLE","CANDIDATE_APPLICABLE","STALE_STOP_CANDIDATE","UNKNOWN_APPLICABILITY")}
    print(json.dumps({"schema":"chacha.dev/guardian-stop-latch-v2-dry-run/v1","active_revision":active,"active_revision_evidence":str(a.current/".revision"),"counts":counts,"global_latch_sources":[r for r in rows if r["applicability"]["global_latch_eligible"]],"scoped_sources":[r for r in rows if not r["applicability"]["global_latch_eligible"]],"mutation_performed":False},indent=2,ensure_ascii=False)); return 0
if __name__=="__main__": raise SystemExit(main())
