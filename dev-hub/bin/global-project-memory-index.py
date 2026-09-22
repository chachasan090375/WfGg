#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sqlite3,time
from pathlib import Path

def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--experience-db",type=Path,required=True); ap.add_argument("--delta-db",type=Path,required=True); ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(); projects={}
    if a.experience_db.exists():
        db=sqlite3.connect(a.experience_db)
        for p,learner,obs in db.execute("SELECT project_id,learner,observed_at FROM experience"):
            q=projects.setdefault(p,{"experience_count":0,"learning_delta_count":0,"learners":set(),"sources":set(),"anomalies":{},"latest_activity":None})
            q["experience_count"]+=1;q["learners"].add(learner);q["latest_activity"]=max(filter(None,[q["latest_activity"],obs]))
    if a.delta_db.exists():
        db=sqlite3.connect(a.delta_db)
        for p,source,kind,obs,sev in db.execute("SELECT project_id,source_id,source_kind,observed_at,anomaly_severity FROM deltas"):
            q=projects.setdefault(p,{"experience_count":0,"learning_delta_count":0,"learners":set(),"sources":set(),"anomalies":{},"latest_activity":None})
            q["learning_delta_count"]+=1;q["sources"].add(source);q["learners"].add(kind);q["latest_activity"]=max(filter(None,[q["latest_activity"],obs]))
            if sev:q["anomalies"][sev]=q["anomalies"].get(sev,0)+1
    for q in projects.values(): q["learners"]=sorted(q["learners"]);q["sources"]=sorted(q["sources"])
    out={"schema":"chacha.dev/global-project-memory-index/v1","generated_at":now(),"project_count":len(projects),"projects":projects}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("CHACHA_DEV_GLOBAL_PROJECT_MEMORY_INDEX=PASS");print("PROJECTS="+str(len(projects)))
if __name__=="__main__":main()
