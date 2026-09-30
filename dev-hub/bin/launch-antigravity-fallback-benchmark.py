#!/usr/bin/env python3
from __future__ import annotations
import json,subprocess,time,urllib.request,urllib.error,ssl

def tailscale_dns()->str:
    p=subprocess.run(["tailscale","status","--json"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=15)
    if p.returncode!=0:
        raise RuntimeError("TAILSCALE_STATUS_FAILED:"+p.stderr.strip()[-300:])
    x=json.loads(p.stdout)
    dns=str((x.get("Self") or {}).get("DNSName") or "").rstrip(".")
    if not dns:
        raise RuntimeError("TAILSCALE_DNSNAME_MISSING")
    return dns

DNS=tailscale_dns()
URL=f"https://{DNS}:8443/api/v1/intent"

TEXT=(
"BENCHMARK UNIQUEMENT — aucune modification ChaCha DEV, aucune installation, aucune promotion. "
"Faire exécuter Technology Watch puis falsification Logicien pour comparer Google Antigravity 2.0 et OpenCode comme moteur/agent de développement pour ChaCha DEV. "
"Comparer au minimum: qualité agentique, autonomie long-running, CLI/headless, API/SDK, multi-agent, MCP, Git/GitHub, IDE/terminal, Linux VPS, isolation, observabilité, reprise après erreur, coûts et quotas, possibilité 0 euro, modèles/providers supportés, modèles locaux, sécurité, gouvernance Guardian/Sentinelle/STOP, facilité d'intégration comme adapter/provider, maintenance et stabilité. "
"Chercher aussi 2 à 4 alternatives sérieuses réellement utilisables à 0 euro ou quasi 0 euro et les benchmarker brièvement. "
"Tester l'hypothèse suivante: conserver Antigravity comme route primaire quand son quota gratuit est disponible et utiliser OpenCode ou un meilleur candidat comme fallback automatique quand Antigravity est EXHAUSTED/BLOCKED, avec retour automatique vers Antigravity après reset. "
"Proposer l'architecture de routage zero-cost la plus robuste pour ChaCha DEV: détection quota/provider health, provider registry, ordre de préférence, failover, anti-loop, aucun achat automatique, aucun downgrade silencieux de qualité, et journalisation cockpit des quotas. "
"Le benchmark doit distinguer clairement ce qui est équivalent, ce qui ne l'est pas, les écarts fonctionnels, les limites connues et les risques. "
"Produire un verdict final avec score pondéré et recommandation unique: REPLACE, KEEP_BOTH ou KEEP_ANTIGRAVITY_ONLY. "
"Si KEEP_BOTH, préciser exactement quelle route doit prendre chaque type de tâche et dans quelles conditions la bascule se fait. "
"Aucune mutation à l'issue de ce benchmark. Recommandation uniquement. "
"Réutiliser les preuves domaine déjà acquises; ne rejouer aucune qualification PASS; ne lancer aucune recherche GitHub générique; respecter Guardian, Sentinelle, STOP et automatic_external_spend_eur=0."
)

payload={
  "text":TEXT,
  "project":"chacha-dev-platform",
  "channel":"BUILD",
  "client_request_id":"antigravity-fallback-benchmark-"+str(int(time.time())),
}
body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
req=urllib.request.Request(URL,data=body,headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
ctx=ssl.create_default_context()
try:
    with urllib.request.urlopen(req,timeout=30,context=ctx) as r:
        raw=r.read().decode("utf-8","replace")
        print("TAILSCALE_DNS="+DNS)
        print("HTTP_STATUS="+str(r.status))
        print(raw)
except urllib.error.HTTPError as e:
    raw=e.read().decode("utf-8","replace")
    print("TAILSCALE_DNS="+DNS)
    print("HTTP_STATUS="+str(e.code))
    print(raw)
    raise SystemExit(1)
except Exception as e:
    print("BENCHMARK_LAUNCH_FAIL="+type(e).__name__+":"+str(e))
    raise SystemExit(2)
