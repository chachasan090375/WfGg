#!/usr/bin/env python3
from __future__ import annotations
import json,ssl,sys,time,urllib.request,urllib.error

URL="https://100.67.99.19:8443/api/v1/intent"
PAYLOAD={
  "text": (
    "PILOT UNIQUEMENT — full domain control plane isolé. "
    "Candidat exact 70f4e826d369cfee870c64ca5386c06959d25c7f déjà matérialisé et qualifié. "
    "Réutiliser sans rejouer les preuves acquises: 3 vérifications historiques VERIFIED et 4 differential pilots VERIFIED, "
    "FOUR_PREVIOUS_BLOCKER_CONDITIONS_CLEARED=PASS. "
    "Exécuter maintenant uniquement le PILOT end-to-end réel via Direct Operator → Project Control → Scheduler → Run Controller, "
    "dans un environnement candidat isolé, production ACTIVE inchangée. "
    "Prouver domain_execution_verified=true et absence de DOMAIN_EXECUTION_VERIFICATION_REQUIRED. "
    "Guardian, Sentinelle et STOP restent autoritaires; aucune dépense externe automatique; aucune promotion production; "
    "ne pas modifier Remote MCP V0.2. "
    "Afficher DECIDED / EXECUTED / VERIFIED et arrêter avant toute promotion. "
    "ANTI-BOUCLE: ne rejouer aucune qualification/test déjà PASS et ne lancer aucune recherche GitHub/source_git_root/ingress."
  ),
  "project":"chacha-dev-platform",
  "channel":"BUILD",
  "client_request_id":"full-domain-isolated-pilot-"+str(int(time.time())),
}

body=json.dumps(PAYLOAD,separators=(",",":"),ensure_ascii=False).encode("utf-8")
req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
ctx=ssl._create_unverified_context()
try:
    with urllib.request.urlopen(req,timeout=30,context=ctx) as r:
        raw=r.read().decode("utf-8","replace")
        print("HTTP_STATUS="+str(r.status))
        print(raw)
except urllib.error.HTTPError as e:
    raw=e.read().decode("utf-8","replace")
    print("HTTP_STATUS="+str(e.code))
    print(raw)
    raise SystemExit(1)
except Exception as e:
    print("PILOT_LAUNCH_FAIL="+type(e).__name__+":"+str(e))
    raise SystemExit(2)
