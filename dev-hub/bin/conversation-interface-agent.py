#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,time
from pathlib import Path
from typing import Any

RECEIPT_SCHEMA="chacha.dev/central-interface-receipt/v1"
OUT_SCHEMA="chacha.dev/conversation-response/v1"

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise SystemExit("JSON_ROOT_NOT_OBJECT")
    return x
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def humanize(v:str)->str:
    return re.sub(r"[_-]+"," ",v).strip().lower()
def first_text(d:dict[str,Any],keys:list[str])->str:
    for k in keys:
        v=d.get(k)
        if isinstance(v,str) and v.strip(): return v.strip()
    return ""
def compose(receipt:dict[str,Any],intent:dict[str,Any]|None=None)->dict[str,Any]:
    if receipt.get("schema")!=RECEIPT_SCHEMA: raise SystemExit("CONVERSATION_CENTRAL_RECEIPT_INVALID")
    status=str(receipt.get("status") or "UNKNOWN");next_action=str(receipt.get("next_action") or "AWAIT_USER_DIRECTIVE")
    decision=receipt.get("decision") if isinstance(receipt.get("decision"),dict) else {}
    message=first_text(decision,["human_message","message","summary","result","reason","detail"])
    needs=bool(decision.get("requires_user_response") is True or decision.get("requires_confirmation") is True or "AWAIT" in next_action or "CONFIRM" in next_action)
    if status in {"BRAIN_UNAVAILABLE","BRAIN_RECEIPT_INVALID"}: kind="ERROR"
    elif status=="STOP_ACTIVE": kind="WARNING"
    elif bool(decision.get("requires_confirmation")): kind="CONFIRMATION"
    elif needs: kind="QUESTION"
    elif status in {"PASS","COMPLETE","COMPLETED","SUCCESS","OK"}: kind="RESULT"
    else: kind="INFO"
    if not message:
        platform=decision.get("platform_status") if isinstance(decision.get("platform_status"),dict) else None
        if platform:
            bits=[]
            version=str(platform.get("platform_version") or "").strip()
            if version: bits.append("version active "+version)
            if "emergency_stop_active" in platform:
                bits.append("arrêt d’urgence "+("actif" if platform.get("emergency_stop_active") else "désactivé"))
            if "guardian_all_hooks_active" in platform:
                bits.append("Guardian "+("actif" if platform.get("guardian_all_hooks_active") else "à vérifier"))
            if platform.get("agent_count") is not None:
                bits.append(str(platform.get("agent_count"))+" agents enregistrés")
            hygiene=platform.get("hygiene") if isinstance(platform.get("hygiene"),dict) else {}
            metrics=hygiene.get("metrics") if isinstance(hygiene.get("metrics"),dict) else {}
            if metrics.get("hygiene_debt_score") is not None:
                bits.append("dette d’hygiène "+str(metrics.get("hygiene_debt_score")))
            message="ChaCha DEV est opérationnel."
            if bits: message+=" "+", ".join(bits)+"."
        else:
            defaults={
              "BRAIN_UNAVAILABLE":"Je n’arrive pas à joindre correctement le cerveau central pour le moment.",
              "BRAIN_RECEIPT_INVALID":"La réponse du cerveau central n’est pas exploitable telle quelle.",
              "STOP_ACTIVE":"L’arrêt d’urgence est actif.",
              "PASS":"C’est validé.","SUCCESS":"C’est validé.","OK":"C’est bon.","COMPLETE":"C’est terminé.","COMPLETED":"C’est terminé."
            }
            message=defaults.get(status,"Le cerveau central a répondu : "+humanize(status)+".")
    action_text={
      "AWAIT_USER_DIRECTIVE":"Dis-moi ce que tu veux faire ensuite.",
      "AWAIT_NEW_INSTRUCTION":"Donne-moi une nouvelle instruction.",
      "RETRY_WHEN_BRAIN_AVAILABLE":"Tu peux me demander de réessayer.",
      "AWAIT_EXPLICIT_RESET_AND_HEALTH_CHECK":"Il faut une confirmation explicite avant de réactiver le système."
    }.get(next_action)
    if action_text and action_text.casefold() not in message.casefold(): message=message.rstrip()+("\n\n"+action_text)
    return {
      "schema":OUT_SCHEMA,"agent_id":"conversation-interface-agent",
      "responded_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
      "kind":kind,"message":message,"requires_user_response":needs,
      "status":status,"next_action":next_action,"project_id":receipt.get("project_id"),
      "central_authority_preserved":True,"decision_modified":False,
      "source_request_id":(intent or {}).get("request_id"),
      "automatic_external_spend_eur":0
    }
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument("--receipt",type=Path,required=True);ap.add_argument("--intent",type=Path);ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args();out=compose(load(a.receipt),load(a.intent) if a.intent and a.intent.is_file() else None);save(a.output,out);print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V800_CONVERSATION_INTERFACE=PASS");print("CHACHA_DEV_V800_CONVERSATION_DECISION_AUTHORITY=NO");return 0
if __name__=="__main__": raise SystemExit(main())
