#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,re,subprocess,sys,time,uuid
from pathlib import Path
from typing import Any

OUT_SCHEMA="chacha.dev/functional-translation/v1"
SEMANTIC_SCHEMA="chacha.dev/conversation-semantic-intent/v1"
HUMAN_INTENT_SCHEMA="chacha.dev/human-interface-intent/v1"

FUNCTIONAL_HEADERS={
    "objectif","objectif fonctionnel","but","demande","livrable","livrables",
    "résultat attendu","resultat attendu","ce que je veux","besoin fonctionnel"
}
META_HEADERS={
    "important","conditions de pass","conditions de réussite","conditions de reussite",
    "si le test échoue ou bloque","si le test echoue ou bloque","si ça échoue","si ca echoue",
    "état final attendu","etat final attendu","processus","gouvernance","contraintes de processus"
}
DIRECT_ACTION_RE=re.compile(
    r"^\s*(crée|cree|créer|creer|ajoute|ajouter|modifie|modifier|corrige|corriger|construis|"
    r"construire|écris|ecris|écrire|ecrire|génère|genere|générer|generer|traduis|traduire|"
    r"localise|localiser|déploie|deploie|déployer|deployer|installe|installer|supprime|supprimer)\b",re.I)
META_PATTERNS=[
    r"\bdoit traverser\b",r"\bpasse(?:r)? par\b",r"\bsans contourner\b",r"\bne contourne\b",
    r"\bguardian\b",r"\bsentinel\b",r"\brun controller\b",r"\bscheduler\b",r"\bleases?\b",
    r"\bvérification indépendante\b",r"\bverification independante\b",
    r"\bbarres? de progression\b",r"\bdépense externe automatique\b",r"\bdepense externe automatique\b",
    r"\bruntime roots?\b",r"\bwrite roots?\b",r"\bécriture sauvage\b",r"\becriture sauvage\b",
    r"\bcontinue automatiquement\b",r"\bne rejoue pas\b",r"\bdernier checkpoint\b",
    r"\bfrontière humaine\b",r"\bfrontiere humaine\b",r"\bapprobation humaine\b",
    r"\brépare uniquement\b",r"\brepare uniquement\b",r"\bdiagnostique automatiquement\b",
    r"\brollback immédiat\b",r"\brollback automatique\b",r"\bcas d[’']échec\b",r"\bcas d[’']echec\b",
]
META_RE=[re.compile(x,re.I) for x in META_PATTERNS]
HEADING_RE=re.compile(r"^\s*([A-ZÀ-ÖØ-Þ0-9][A-ZÀ-ÖØ-Þ0-9 ÉÈÊËÀÂÄÎÏÔÖÙÛÜÇ'’/\-]{2,})\s*:?[ \t]*$")
ARTIFACT_ACTION_RE=re.compile(r"\b(crée|cree|créer|creer|écris|ecris|écrire|ecrire|génère|genere|générer|generer)\b",re.I)
NON_ARTIFACT_ACTION_RE=re.compile(r"\b(traduis|traduire|translate|localise|localiser|déploie|deploie|déployer|deployer|deploy|installe|installer|supprime|supprimer|modifie|modifier)\b",re.I)
FILENAME_RE=re.compile(r"\b([A-Za-z0-9][A-Za-z0-9._/-]{0,239}\.[A-Za-z0-9][A-Za-z0-9_-]{0,15})\b")

def now_iso()->str:return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
def save(p:Path,x:dict[str,Any])->None:
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(p))
    return x
def fd(p:Path)->str:return "sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd:list[str],timeout:int=120)->None:
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=False,timeout=timeout)
    if p.returncode!=0:raise SystemExit("FUNCTIONAL_TRANSLATOR_CHILD_FAILED:"+p.stderr[-1200:])
def fold(s:str)->str:return re.sub(r"\s+"," ",s.strip().casefold()).strip(" :")

def heading_kind(line:str)->str|None:
    candidate=fold(line)
    if candidate in FUNCTIONAL_HEADERS:return "FUNCTIONAL"
    if candidate in META_HEADERS:return "META"
    if HEADING_RE.match(line):return "OTHER"
    return None

def looks_meta(text:str)->bool:
    s=fold(text)
    if not s:return False
    # An explicit deliverable action is functional unless it is merely asking to
    # control ChaCha DEV's own execution path.
    if DIRECT_ACTION_RE.search(text) and not any(x in s for x in (
        "guardian","sentinel","scheduler","run controller","barre de progression","runtime root","write root")):
        return False
    return any(rx.search(text) for rx in META_RE)

def exact_text_artifact_spec(text:str)->dict[str,str]|None:
    if not ARTIFACT_ACTION_RE.search(text):return None
    if not re.search(r"\b(fichier|file|artefact|artifact)\b",text,re.I):return None
    if NON_ARTIFACT_ACTION_RE.search(text):return None
    pm=FILENAME_RE.search(text)
    if not pm:return None
    path=pm.group(1).strip().rstrip(".,;:")
    content=None
    patterns=(
      r"(?:contenu(?:\s+final)?(?:\s+doit\s+être|\s+doit\s+etre)?(?:\s+exactement)?|content(?:\s+must\s+be)?(?:\s+exactly)?)\s*:\s*\n\s*([^\n]+)",
      r"(?:contenu(?:\s+final)?(?:\s+doit\s+être|\s+doit\s+etre)?(?:\s+exactement)?|content(?:\s+must\s+be)?(?:\s+exactly)?)\s*:\s*[\"']([^\"']+)[\"']",
      r"(?:contenant(?:\s+uniquement)?|containing(?:\s+only)?)\s+[\"']([^\"']+)[\"']",
      r"(?:contenant(?:\s+uniquement)?|containing(?:\s+only)?)\s+([A-Za-z0-9_.:+/@= -]{1,512})"
    )
    for rx in patterns:
        m=re.search(rx,text,re.I)
        if m:
            content=m.group(1).strip()
            if rx==patterns[-1]:content=content.rstrip(".,;:")
            break
    if not content:return None
    if '\n' in content or len(content.encode('utf-8'))>64*1024:return None
    if '..' in Path(path).parts or path.startswith('/'):return None
    return {'action':'write-text','path':path,'content':content}

def normalize_functional_prompt(text:str)->tuple[str,dict[str,Any]]:
    spec=exact_text_artifact_spec(text)
    if spec is None:
        return text,{'applied':False,'kind':'NONE','reason':'NO_UNAMBIGUOUS_CANONICALIZATION'}
    content=spec['content']
    quote='"' if '"' not in content else "'" if "'" not in content else ''
    if not quote:
        return text,{'applied':False,'kind':'NONE','reason':'CONTENT_QUOTING_AMBIGUOUS'}
    canonical=f"Crée un fichier {spec['path']} contenant uniquement {quote}{content}{quote}."
    return canonical,{'applied':True,'kind':'EXACT_TEXT_ARTIFACT','workspace_file':spec,'source':'contextual-functional-translator'}

def semantic_partition(text:str)->dict[str,Any]:
    lines=text.replace("\r\n","\n").replace("\r","\n").split("\n")
    explicit_functional_header=any(heading_kind(x.strip())=="FUNCTIONAL" for x in lines if x.strip())
    current="UNSCOPED";functional=[];meta=[];context=[];saw_functional_header=False
    for raw in lines:
        line=raw.strip()
        if not line:continue
        hk=heading_kind(line)
        if hk is not None:
            current=hk
            saw_functional_header=saw_functional_header or hk=="FUNCTIONAL"
            continue
        if current=="META":meta.append(line);continue
        if current=="OTHER":context.append(line);continue
        if current=="FUNCTIONAL":
            (meta if looks_meta(line) else functional).append(line)
            continue
        # When the user explicitly declares an objective section, prose before it
        # is context/preamble and must not activate business domains.
        if explicit_functional_header:
            context.append(line)
        else:
            # Unsectioned natural language: classify at paragraph/line granularity.
            (meta if looks_meta(line) else functional).append(line)
    if saw_functional_header and not functional:
        # Fail closed toward preserved meaning: never erase the request entirely.
        functional=[x for x in lines if x.strip() and heading_kind(x.strip()) is None and not looks_meta(x)]
    functional_core="\n".join(functional).strip() or text.strip()
    routing_text,normalization=normalize_functional_prompt(functional_core)
    return {
      "schema":SEMANTIC_SCHEMA,
      "strategy":"CONTEXTUAL_SECTION_AND_CLAUSE_PARTITION_V2",
      "raw_text_preserved":True,
      "functional_core":functional_core,
      "routing_text":routing_text,
      "normalization":normalization,
      "governance_and_process_constraints":meta,
      "contextual_references":context,
      "functional_header_detected":saw_functional_header,
      "keyword_routing_is_fallback_only":True,
      "automatic_external_spend_eur":0
    }

def main()->int:
    ap=argparse.ArgumentParser(description="ChaCha DEV satellite Functional Translator")
    ap.add_argument("--repo-root",type=Path,default=Path("/opt/chacha-dev/platform/current"))
    ap.add_argument("--text",required=True)
    ap.add_argument("--project",default="chacha-dev-platform")
    ap.add_argument("--source",default="direct-operator")
    ap.add_argument("--operator",default="authenticated-operator")
    ap.add_argument("--request-id")
    ap.add_argument("--output-dir",type=Path,required=True)
    a=ap.parse_args();root=a.repo_root.resolve();out=a.output_dir.resolve();out.mkdir(parents=True,exist_ok=True)
    request_id=a.request_id or ("fit-"+uuid.uuid4().hex);original=a.text.strip()
    if not original:raise SystemExit("FUNCTIONAL_TRANSLATOR_EMPTY_TEXT")
    semantic=semantic_partition(original);functional_text=str(semantic["routing_text"])
    semantic_path=out/"semantic-intent.json";save(semantic_path,semantic)
    raw={
      "name":"Direct Operator Request "+request_id[:12],"text":functional_text,"objective":functional_text,
      "raw_user_text":original,"semantic_intent":semantic,"project":a.project,"source":a.source,
      "operator_identity":a.operator,"constraints":{"automatic_external_spend_eur":0,
        "functional_requirement_has_priority_over_user_technical_suggestion":True,
        "translator_has_execution_authority":False,"translator_has_architecture_authority":False,
        "central_orchestrator_required":True,"contextual_semantic_partition_required":True}
    }
    raw_path=out/"functional-source-intent.json";save(raw_path,raw)
    contract=out/"functional-contract.json";preplan=out/"functional-preplan.json"
    run([sys.executable,str(root/"dev-hub/bin/specification-compiler.py"),"--intent",str(raw_path),"--output",str(contract)])
    run([sys.executable,str(root/"dev-hub/bin/functional-intent-orchestrator.py"),
         "--config",str(root/"dev-hub/config/domain-orchestration.v1.json"),"--intent",str(raw_path),"--output",str(preplan)])
    cv=load(contract);pv=load(preplan)
    interface_intent={
      "schema":HUMAN_INTENT_SCHEMA,"request_id":request_id,"received_at":now_iso(),
      "source":"functional-translator-satellite","route":"CHACHA_DEV","command":"INSTRUCTION",
      "user_text":functional_text,"raw_user_text":original,"functional_text":functional_text,"semantic_intent":semantic,
      "semantic_intent_path":str(semantic_path),"semantic_intent_digest":fd(semantic_path),
      "project_id":a.project,"target_scope":"PLATFORM" if a.project=="chacha-dev-platform" else "PROJECT",
      "interface_decision_authority":False,"functional_contract":str(contract),
      "functional_contract_digest":fd(contract),"functional_preplan":str(preplan),
      "functional_preplan_digest":fd(preplan)
    }
    interface_path=out/"interface-intent.json";save(interface_path,interface_intent)
    result={
      "schema":OUT_SCHEMA,"translated_at":now_iso(),"request_id":request_id,"project_id":a.project,
      "source":a.source,"operator_identity":a.operator,"raw_text_preserved":True,
      "raw_text_digest":"sha256:"+hashlib.sha256(original.encode()).hexdigest(),
      "semantic_intent":str(semantic_path),"semantic_intent_digest":fd(semantic_path),
      "functional_text":functional_text,"functional_contract":str(contract),"functional_contract_digest":fd(contract),
      "functional_preplan":str(preplan),"functional_preplan_digest":fd(preplan),
      "interface_intent":str(interface_path),"interface_intent_digest":fd(interface_path),
      "primary_domains":pv.get("primary_domains") or [],"review_domains":pv.get("review_domains") or [],
      "criteria_count":len(cv.get("criteria") or []),"translator_execution_authority":False,
      "translator_architecture_authority":False,"central_orchestrator_required":True,
      "contextual_semantic_partition_applied":True,"automatic_external_spend_eur":0
    }
    save(out/"translation.json",result);print(json.dumps(result,indent=2,ensure_ascii=False));return 0
if __name__=="__main__":raise SystemExit(main())
