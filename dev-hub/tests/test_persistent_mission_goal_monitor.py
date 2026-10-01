import datetime,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"dev-hub/bin/persistent-mission-goal-monitor.py"
POL=json.loads((ROOT/"dev-hub/config/persistent-mission-goal-monitor.v1.json").read_text())
spec=importlib.util.spec_from_file_location("m",BIN);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=datetime.datetime(2026,10,2,tzinfo=datetime.timezone.utc)

def mission(hours=1,done=1,total=2,human=False):
    return {"schema":"chacha.dev/persistent-mission/v1","mission_id":"x","goal":"g","task_order":[str(i) for i in range(total)],
            "completed_tasks":[str(i) for i in range(done)],"human_boundary":human,
            "updated_at":(NOW-datetime.timedelta(hours=hours)).isoformat(),"deadline_at":None}

def test_healthy_progress():
    x=m.assess(POL,mission(),NOW);assert x["state"]=="HEALTHY" and x["progress"]==0.5

def test_stale_progress_detected():
    x=m.assess(POL,mission(hours=30),NOW);assert x["state"]=="STALE"

def test_stop_blocks():
    x=m.assess(POL,mission(),NOW,True);assert x["state"]=="BLOCKED"

def test_monitor_never_mutates_or_executes():
    x=m.assess(POL,mission(),NOW);assert x["monitor_executes_tasks"] is False and x["mission_state_mutation"] is False
