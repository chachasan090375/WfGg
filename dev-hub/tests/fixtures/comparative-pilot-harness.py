#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--architecture",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--variant",required=True)
    a=ap.parse_args()
    arch=json.loads(a.architecture.read_text(encoding="utf-8"))
    raw=json.dumps(arch,sort_keys=True)
    # Deterministic fixture used only to prove identical isolated runtime mechanics.
    # Production comparisons must provide a real project/domain harness.
    current=(a.variant=="CURRENT")
    metrics={
      "schema":"chacha.dev/comparative-pilot-metrics/v1",
      "acceptance_pass":True,
      "quality_score":99 if current else 97,
      "stability_score":99 if current else 98,
      "latency_ms":20 if current else 30,
      "memory_mb":64 if current else 72,
      "external_spend_eur":0,
      "error_rate":0,
      "variant":a.variant,
      "architecture_digest_input_length":len(raw),
      "observed_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
    }
    a.output.write_text(json.dumps(metrics,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(metrics,separators=(",",":")))

if __name__=="__main__":main()
