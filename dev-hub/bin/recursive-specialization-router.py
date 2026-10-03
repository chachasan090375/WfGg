#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from typing import Any

SCHEMA="chacha.dev/recursive-specialization-resolution/v1"
NON_OVERRIDABLE_DEFAULT={"security","governance","external_spend","privacy","production_authority"}

def load(p:Path)->dict[str,Any]:
    x=json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(x,dict): raise ValueError("JSON_ROOT_NOT_OBJECT")
    return x

def save(p:Path,x:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def cycle(nodes:dict[str,dict[str,Any]], edge_key:str)->list[str]|None:
    visiting=set();done=set();stack=[]
    def walk(n:str):
        if n in done:return None
        if n in visiting:
            i=stack.index(n) if n in stack else 0;return stack[i:]+[n]
        visiting.add(n);stack.append(n)
        row=nodes[n]
        if edge_key=="parent": nxt=[row.get("parent_id")] if row.get("parent_id") else []
        else:nxt=list(row.get("dependencies") or [])
        for m in nxt:
            if m in nodes:
                r=walk(m)
                if r:return r
        stack.pop();visiting.remove(n);done.add(n);return None
    for n in nodes:
        r=walk(n)
        if r:return r
    return None

def depth(node_id:str,nodes:dict[str,dict[str,Any]])->int:
    d=0;seen=set();cur=node_id
    while nodes[cur].get("parent_id"):
        cur=str(nodes[cur]["parent_id"]);d+=1
        if cur in seen or cur not in nodes:return 10**6
        seen.add(cur)
    return d

def resolve(graph:dict[str,Any],fabric:dict[str,Any],deliverables:dict[str,Any],archetypes:dict[str,Any])->dict[str,Any]:
    raw=graph.get("nodes") or []
    max_nodes=int(fabric["recursive_model"]["guards"]["max_nodes"]);max_depth=int(fabric["recursive_model"]["guards"]["max_depth"])
    blockers=[];warnings=[]
    if len(raw)>max_nodes:blockers.append("RECURSIVE_NODE_LIMIT_EXCEEDED")
    nodes={}
    for r in raw:
        nid=str(r.get("node_id") or "")
        if not nid or nid in nodes:blockers.append("NODE_ID_MISSING_OR_DUPLICATE:"+nid);continue
        nodes[nid]=dict(r)
    for nid,row in nodes.items():
        p=row.get("parent_id")
        if p and p not in nodes:blockers.append(f"PARENT_NOT_FOUND:{nid}:{p}")
        for dep in row.get("dependencies") or []:
            if dep not in nodes:blockers.append(f"DEPENDENCY_NOT_FOUND:{nid}:{dep}")
    pc=cycle(nodes,"parent")
    if pc:blockers.append("OWNERSHIP_CYCLE:"+"->".join(pc))
    dc=cycle(nodes,"dependencies")
    if dc:blockers.append("DEPENDENCY_CYCLE:"+"->".join(dc))
    if any(depth(n,nodes)>max_depth for n in nodes):blockers.append("RECURSIVE_DEPTH_LIMIT_EXCEEDED")

    roots=[n for n,r in nodes.items() if not r.get("parent_id")]
    resolved={};classes=set(deliverables.get("classes") or {})
    araw=archetypes.get("archetypes") or {}
    archetype_ids=set(araw.keys()) if isinstance(araw,dict) else {str(a.get("id")) for a in araw if isinstance(a,dict) and a.get("id")}
    order=sorted(nodes,key=lambda n:depth(n,nodes))
    for nid in order:
        row=nodes[nid];parent=resolved.get(str(row.get("parent_id") or ""),{})
        inherited=dict(parent.get("constraints_effective") or {})
        inherited_no=set(parent.get("non_overridable_constraints") or NON_OVERRIDABLE_DEFAULT)
        inherited_no.update(row.get("non_overridable_constraints") or [])
        local=dict(row.get("constraints_local") or {});over=dict(row.get("constraint_overrides") or {})
        for k,v in over.items():
            if k in inherited_no and k in inherited and inherited[k]!=v:blockers.append(f"NON_OVERRIDABLE_CONSTRAINT_WEAKEN_OR_CHANGE:{nid}:{k}")
            else:inherited[k]=v
        inherited.update(local)
        c=dict(row.get("classification") or {});conf=float(c.get("confidence") or 0)
        dcx=c.get("deliverable_class");state="COMMITTED"
        if conf<float(fabric["recursive_model"]["classification"]["minimum_confidence_for_committed_classification"]):state="SHADOW_UNCERTAIN"
        if dcx and dcx not in classes:state="SHADOW_UNCERTAIN";warnings.append(f"UNKNOWN_DELIVERABLE_CLASS:{nid}:{dcx}")
        arch=c.get("archetype")
        if dcx=="application" and arch and arch not in archetype_ids:warnings.append(f"UNKNOWN_APPLICATION_ARCHETYPE:{nid}:{arch}");state="SHADOW_UNCERTAIN"
        cells=[];seen=set()
        for domain in row.get("domain_requirements") or []:
            if domain not in seen:cells.append({"domain":domain,"model":"CANONICAL_HEAD_PLUS_ARM_REFERENCE"});seen.add(domain)
        resolved[nid]={**row,"classification_state":state,"constraints_effective":inherited,"non_overridable_constraints":sorted(inherited_no),"specialist_cells":cells,"authority":{"execution":False,"production":False,"permission_escalation":False}}
    shared={}
    for nid,row in nodes.items():
        for ref in row.get("shared_component_refs") or []:shared.setdefault(ref,[]).append(nid)
    return {"schema":SCHEMA,"status":"BLOCKED" if blockers else "PASS","project_id":graph.get("project_id"),"root_nodes":roots,"node_count":len(nodes),"nodes":[resolved[n] for n in order if n in resolved],"shared_component_reuse":shared,"blockers":sorted(set(blockers)),"warnings":sorted(set(warnings)),"production_activation":False,"execution_authority":False,"automatic_external_spend_eur":0,"resolved_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}

def main()->int:
    a=argparse.ArgumentParser();a.add_argument('--graph',type=Path,required=True);a.add_argument('--fabric',type=Path,default=Path('dev-hub/config/specialization-fabric.v2.json'));a.add_argument('--deliverables',type=Path,default=Path('dev-hub/config/deliverable-specialization.v1.json'));a.add_argument('--archetypes',type=Path,default=Path('dev-hub/config/application-archetype-specialization.v1.json'));a.add_argument('--output',type=Path,required=True);x=a.parse_args()
    out=resolve(load(x.graph),load(x.fabric),load(x.deliverables),load(x.archetypes));save(x.output,out);print("CHACHA_DEV_RECURSIVE_SPECIALIZATION_ROUTER="+out['status']);print("AUTOMATIC_EXTERNAL_SPEND_EUR=0");return 0 if out['status']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
