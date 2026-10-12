"""Read-only canonical STOP inspection. Unknown state blocks execution."""
from __future__ import annotations
import json
from pathlib import Path

CANONICAL_STOP = Path('/opt/chacha-dev/runtime/control/emergency-stop.json')

def inspect_stop(path: Path = CANONICAL_STOP) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'state': 'UNKNOWN', 'reason': 'STOP_STATE_MISSING'}
    except (OSError, ValueError, UnicodeError):
        return {'state': 'UNKNOWN', 'reason': 'STOP_STATE_UNREADABLE'}
    if not isinstance(value, dict) or not isinstance(value.get('active'), bool):
        return {'state': 'UNKNOWN', 'reason': 'STOP_STATE_INVALID'}
    return {'state': 'ACTIVE' if value['active'] else 'CLEAR', 'reason': None}

def blocks_execution(path: Path = CANONICAL_STOP) -> bool:
    return inspect_stop(path)['state'] != 'CLEAR'
