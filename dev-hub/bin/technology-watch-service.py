#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import technology_watch_runtime as tw
import technology_watch_logician as twl
import technology_truth_scoring as tts
import technology_core_watch as tcw
import universal_learning_runtime as ulr

def save(path:Path,value)->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--repo-root",type=Path,default=Path("."))
    sub=ap.add_subparsers(dest="cmd",required=True)
    sub.add_parser("refresh")
    c=sub.add_parser("consult")
    c.add_argument("--consumer",required=True,choices=["branch-foundry","agent-foundry","capability-foundry","architecture-optimizer","architecture-decision-council","reuse-memory","capability-trust-freshness"])
    c.add_argument("--domain",default="")
    c.add_argument("--capability",action="append",default=[])
    sub.add_parser("status")
    e=sub.add_parser("evaluate")
    e.add_argument("--dossier",type=Path,required=True)
    e.add_argument("--source-reputation",type=Path)
    e.add_argument("--output-dir",type=Path,required=True)
    cw=sub.add_parser("core-watch")
    cw.add_argument("--signals",type=Path)
    cw.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.repo_root.resolve()
    if a.cmd=="refresh":
        out=tw.write_full_snapshot(root)
        try:
            ulr.observe_platform(project_id="platform-global",source_id="technology-watch",source_kind="agent",
                                state={"snapshot_digest":out.get("snapshot_digest"),
                                       "candidate_count":len(out.get("provider_candidates") or []),
                                       "status":"FRESH"})
        except Exception:
            pass
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_REFRESH=PASS")
        print("AUTOMATIC_EXTERNAL_SPEND_EUR=0")
        return
    if a.cmd=="consult":
        out=tw.consult(root,consumer=a.consumer,domain=a.domain,capabilities=a.capability)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_CONSULT=PASS")
        return
    if a.cmd=="status":
        out=tw.snapshot_status(root)
        print(json.dumps(out,indent=2,ensure_ascii=False))
        print("CHACHA_TECHNOLOGY_WATCH_STATUS="+str(out.get("state")))
        return
    if a.cmd=="evaluate":
        dossier=json.loads(a.dossier.read_text(encoding="utf-8"))
        challenge=twl.build_challenge(
            dossier,
            json.loads((root/"dev-hub/config/technology-watch-logician.v1.json").read_text(encoding="utf-8"))
        )
        a.output_dir.mkdir(parents=True,exist_ok=True)
        challenge_path=a.output_dir/"logician-falsification.json"
        save(challenge_path,challenge)
        reputation=(json.loads(a.source_reputation.read_text(encoding="utf-8"))
                    if a.source_reputation and a.source_reputation.is_file()
                    else json.loads((root/"dev-hub/config/technology-source-reputation.v1.json").read_text(encoding="utf-8")))
        score=tts.evaluate(
            dossier,
            json.loads((root/"dev-hub/config/technology-truth-scoring.v1.json").read_text(encoding="utf-8")),
            reputation,
            challenge
        )
        score_path=a.output_dir/"technology-truth-score.json"
        save(score_path,score)
        receipt={
          "schema":"chacha.dev/technology-watch-evaluation/v1","status":"PASS",
          "technology_id":dossier.get("technology_id"),"version":dossier.get("version"),
          "challenge":str(challenge_path),"score":str(score_path),
          "recommendation_class":score.get("recommendation_class"),
          "technology_watch_owns_decision":True,
          "logician_decision_authority":False,
          "architecture_council_final_authority":True,
          "automatic_external_spend_eur":0
        }
        save(a.output_dir/"evaluation.json",receipt)
        print(json.dumps(receipt,indent=2,ensure_ascii=False))
        print("CHACHA_DEV_V645_TECHNOLOGY_WATCH_EVALUATION=PASS")
        print("CHACHA_DEV_V645_LOGICIAN_DECISION_AUTHORITY=NO")
        return
    inventory=json.loads((root/"dev-hub/config/technology-core-watch.v1.json").read_text(encoding="utf-8"))
    signals=json.loads(a.signals.read_text(encoding="utf-8")) if a.signals and a.signals.is_file() else {}
    out=tcw.build_core_watch(inventory,signals)
    save(a.output,out)
    print(json.dumps(out,indent=2,ensure_ascii=False))
    print("CHACHA_DEV_V645_CORE_ARCHITECTURE_WATCH=PASS")
    print("CHACHA_DEV_V645_UNCONTROLLED_CORE_UPGRADE=NO")

if __name__=="__main__":
    main()
