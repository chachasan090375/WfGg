from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/session-bootstrap-cockpit/v1"
UNRESOLVED={"status":"UNRESOLVED","reason":"CANONICAL_AUTHORITY_NOT_PROVEN"}

def _json(path:Path)->dict[str,Any]|None:
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else None
    except (OSError,json.JSONDecodeError): return None

def _text(path:Path)->str|None:
    try:
        v=path.read_text(encoding="utf-8").strip()
        return v or None
    except OSError:return None

def _active_revision(current:Path)->tuple[str|None,str]:
    """Resolve revision from the deployed release root passed by Direct Operator."""
    revision_file=current/".revision"
    active=_text(revision_file)
    if active:return active,str(revision_file)
    # Candidate checkouts do not carry production authority. The runtime's
    # platform/current symlink is the proven production authority.
    canonical=Path("/opt/chacha-dev/platform/current/.revision")
    active=_text(canonical)
    return active,str(canonical)

def build(runtime:Path,current:Path)->dict[str,Any]:
    """Read-only bootstrap over proven canonical runtime authorities."""
    active,active_source=_active_revision(current)
    coverage=_json(runtime/"guardian"/"coverage-latest.json")
    remediation=_json(runtime/"guardian"/"remediation-index.json")
    guardian_stop=_json(runtime/"control"/"guardian-stop-required.json")
    stop=_json(runtime/"control"/"emergency-stop.json")
    progress=_json(runtime/"progress"/"progress.json")
    guardian={
      "coverage_snapshot":coverage,
      "remediation_index":remediation,
      "stop_required":guardian_stop,
      "source_root":str(runtime/"guardian"),
      "distributed_authority":True,
    }
    required_ok=bool(active and stop is not None and progress is not None and coverage is not None and guardian_stop is not None)
    return {
      "schema":SCHEMA,"status":"OK" if required_ok else "DEGRADED",
      "active_production":{"revision":active,"source":active_source},
      "live_candidates":dict(UNRESOLVED),
      "guardian":guardian,
      "stop":{"state":stop,"source":str(runtime/"control"/"emergency-stop.json")},
      "progress":{"state":progress,"source":str(runtime/"progress"/"progress.json")},
      "authority":"CHACHA_DEV_CANONICAL_RUNTIME",
      "chat_history_required":False,"read_only":True,
      "automatic_external_spend_eur":0
    }
