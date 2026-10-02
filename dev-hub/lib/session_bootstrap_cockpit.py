from __future__ import annotations
import json
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/session-bootstrap-cockpit/v1"

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

def build(runtime:Path,current:Path)->dict[str,Any]:
    """Read-only bootstrap view. Authorities remain canonical files; nothing is copied back."""
    active=_text(current/".revision")
    guardian=_json(runtime/"guardian"/"state.json") or _json(runtime/"guardian"/"guardian-state.json")
    stop=_json(runtime/"emergency-stop"/"state.json") or _json(runtime/"stop"/"state.json")
    progress=_json(runtime/"progress"/"state.json") or _json(runtime/"progress-state.json")
    coverage=_json(runtime/"guardian"/"coverage-latest.json")
    return {
      "schema":SCHEMA,"status":"OK" if active else "DEGRADED",
      "active_production":{"revision":active,"source":str(current/".revision")},
      "guardian":{"state":guardian,"coverage_snapshot":coverage,"source_root":str(runtime/"guardian")},
      "stop":{"state":stop,"source_root":str(runtime)},
      "progress":{"state":progress,"source_root":str(runtime)},
      "authority":"CHACHA_DEV_CANONICAL_RUNTIME",
      "chat_history_required":False,
      "read_only":True,
      "automatic_external_spend_eur":0
    }
