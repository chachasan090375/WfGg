#!/usr/bin/env python3
from __future__ import annotations

import argparse,hashlib,json,os,sqlite3,time
from pathlib import Path
from typing import Any

POLICY_SCHEMA="chacha.dev/human-behavior-center-policy/v1"
OBS_SCHEMA="chacha.dev/human-behavior-observation/v1"
SPEC_SCHEMA="chacha.dev/fictional-persona-spec/v1"
CARD_SCHEMA="chacha.dev/fictional-persona-card/v1"
FEEDBACK_SCHEMA="chacha.dev/persona-feedback/v1"
DELTA_SCHEMA="chacha.dev/human-behavior-evidence-delta/v1"

def now_iso()->str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())

def load(path:Path)->dict[str,Any]:
    x=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(x,dict):raise ValueError("JSON_ROOT_NOT_OBJECT:"+str(path))
    return x

def save(path:Path,x:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(x,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    os.replace(tmp,path)

def canonical(x:Any)->bytes:
    return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")

def digest(x:Any)->str:
    return "sha256:"+hashlib.sha256(canonical(x)).hexdigest()

def connect(db:Path)->sqlite3.Connection:
    db.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(db))
    con.row_factory=sqlite3.Row
    con.execute("""CREATE TABLE IF NOT EXISTS observations(
      observation_id TEXT PRIMARY KEY,
      source_type TEXT NOT NULL,
      source_ref TEXT NOT NULL,
      evidence_scope TEXT NOT NULL,
      domain TEXT NOT NULL,
      facets_json TEXT NOT NULL,
      pattern TEXT NOT NULL,
      context TEXT,
      confidence REAL NOT NULL,
      source_weight REAL NOT NULL,
      corroboration_json TEXT NOT NULL,
      payload_sha256 TEXT NOT NULL,
      ingested_at TEXT NOT NULL
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hbc_obs_domain ON observations(domain)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hbc_obs_source_type ON observations(source_type)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hbc_obs_scope ON observations(evidence_scope)")
    con.execute("""CREATE TABLE IF NOT EXISTS persona_feedback(
      feedback_id TEXT PRIMARY KEY,
      persona_id TEXT NOT NULL,
      interaction_context TEXT NOT NULL,
      observed_effect TEXT NOT NULL,
      rating INTEGER NOT NULL,
      adjustment_hint TEXT,
      payload_sha256 TEXT NOT NULL,
      recorded_at TEXT NOT NULL
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_hbc_feedback_persona ON persona_feedback(persona_id)")
    con.commit()
    return con

def clean_text(v:Any,max_len:int=3000)->str:
    return str(v or "").strip()[:max_len]

def values(v:Any)->list[str]:
    if isinstance(v,list):raw=v
    elif v in (None,""):raw=[]
    else:raw=[v]
    out=[]
    for x in raw:
        s=clean_text(x,180)
        if s and s not in out:out.append(s)
    return out

def validate_policy(policy:dict[str,Any])->None:
    if policy.get("schema")!=POLICY_SCHEMA:raise ValueError("HBC_POLICY_SCHEMA_INVALID")
    auth=policy.get("authority") or {}
    forbidden=("decision_authority","architecture_authority","execution_authority",
               "production_mutation_authority","permission_expansion_authority","may_modify_own_contract")
    if any(auth.get(k) is not False for k in forbidden):
        raise ValueError("HBC_AUTHORITY_MUST_BE_FALSE")
    if float(policy.get("automatic_external_spend_eur",-1))!=0:
        raise ValueError("HBC_EXTERNAL_SPEND_MUST_BE_ZERO")

def validate_observation(obs:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if obs.get("schema")!=OBS_SCHEMA:raise ValueError("OBSERVATION_SCHEMA_INVALID")
    oid=clean_text(obs.get("observation_id"),160)
    if len(oid)<3:raise ValueError("OBSERVATION_ID_INVALID")
    source=obs.get("source") if isinstance(obs.get("source"),dict) else {}
    source_type=clean_text(source.get("type"),120)
    source_ref=clean_text(source.get("ref"),1000)
    classes=policy.get("source_classes") if isinstance(policy.get("source_classes"),dict) else {}
    if source_type not in classes:raise ValueError("SOURCE_CLASS_NOT_ALLOWED:"+source_type)
    if not source_ref:raise ValueError("SOURCE_REF_REQUIRED")
    scope=clean_text(obs.get("evidence_scope"),80)
    allowed_scopes=classes[source_type].get("allowed_scopes") or []
    if scope not in allowed_scopes:raise ValueError("EVIDENCE_SCOPE_NOT_ALLOWED_FOR_SOURCE")
    domain=clean_text(obs.get("domain"),120)
    if domain not in (policy.get("observation_domains") or []):raise ValueError("OBSERVATION_DOMAIN_NOT_ALLOWED")
    if obs.get("derived_not_raw") is not True:raise ValueError("DERIVED_NOT_RAW_REQUIRED")
    pattern=clean_text(obs.get("pattern"),3000)
    if len(pattern)<3:raise ValueError("OBSERVATION_PATTERN_REQUIRED")
    try:confidence=float(obs.get("confidence"))
    except Exception:raise ValueError("CONFIDENCE_INVALID")
    if not 0<=confidence<=1:raise ValueError("CONFIDENCE_OUT_OF_RANGE")
    facets=obs.get("facets") if isinstance(obs.get("facets"),dict) else {}
    clean_facets={}
    for k,v in facets.items():
        key=clean_text(k,80)
        vals=values(v)
        if key and vals:clean_facets[key]=vals if isinstance(v,list) else vals[0]
    corroboration=values(obs.get("corroboration_refs"))
    out={
      "schema":OBS_SCHEMA,"observation_id":oid,
      "source":{
        "type":source_type,"ref":source_ref,
        **{k:clean_text(source.get(k),500) for k in ("title","creator","published_at") if clean_text(source.get(k),500)}
      },
      "evidence_scope":scope,"domain":domain,"facets":clean_facets,
      "pattern":pattern,"confidence":confidence,"derived_not_raw":True
    }
    context=clean_text(obs.get("context"),3000)
    if context:out["context"]=context
    if corroboration:out["corroboration_refs"]=corroboration
    notes=values(obs.get("notes"))
    if notes:out["notes"]=notes
    return out

def ingest(con:sqlite3.Connection,obs:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    x=validate_observation(obs,policy)
    sha=digest(x)
    prior=con.execute("SELECT payload_sha256 FROM observations WHERE observation_id=?",(x["observation_id"],)).fetchone()
    if prior:
        if prior["payload_sha256"]==sha:
            return {"status":"UNCHANGED","observation_id":x["observation_id"],"payload_sha256":sha}
        raise ValueError("OBSERVATION_ID_CONFLICT")
    cls=policy["source_classes"][x["source"]["type"]]
    con.execute("""INSERT INTO observations(
      observation_id,source_type,source_ref,evidence_scope,domain,facets_json,pattern,context,
      confidence,source_weight,corroboration_json,payload_sha256,ingested_at
    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
      x["observation_id"],x["source"]["type"],x["source"]["ref"],x["evidence_scope"],x["domain"],
      json.dumps(x["facets"],ensure_ascii=False,sort_keys=True),x["pattern"],x.get("context"),
      x["confidence"],float(cls.get("weight") or 0),json.dumps(x.get("corroboration_refs") or [],ensure_ascii=False),
      sha,now_iso()
    ))
    con.commit()
    return {"status":"INGESTED","observation_id":x["observation_id"],"payload_sha256":sha,
            "source_type":x["source"]["type"],"evidence_scope":x["evidence_scope"],
            "automatic_external_spend_eur":0}

ALIASES={
 "regions":"region","region":"region",
 "cultures":"culture","culture":"culture",
 "social_milieu":"social_milieu",
 "education":"education",
 "occupations":"occupation","occupation":"occupation",
 "languages":"language","language":"language",
 "sociolect":"sociolect",
 "presentation_gender":"presentation_gender",
 "age_band":"age_band","era":"era"
}

def persona_facets(spec:dict[str,Any])->dict[str,list[str]]:
    out={}
    for raw,canon in ALIASES.items():
        if raw in spec:
            vals=values(spec.get(raw))
            if vals:out.setdefault(canon,[])
            for v in vals:
                if v not in out[canon]:out[canon].append(v)
    return out

def observation_facets(raw:dict[str,Any])->dict[str,list[str]]:
    out={}
    for k,v in raw.items():
        canon=ALIASES.get(k,k)
        vals=values(v)
        if vals:out[canon]=vals
    return out

def folded(vals:list[str])->set[str]:
    return {x.casefold().strip() for x in vals if x.strip()}

def match_score(row:sqlite3.Row,spec_facets:dict[str,list[str]])->tuple[float,int,int]:
    obs=observation_facets(json.loads(row["facets_json"]))
    matches=0;mismatches=0
    hard_identity_facets={"region","culture","presentation_gender","age_band","social_milieu"}
    for k,ovals in obs.items():
        pvals=spec_facets.get(k)
        if not pvals:continue
        if folded(ovals)&folded(pvals):
            matches+=1
        else:
            mismatches+=1
            if k in hard_identity_facets:
                return (0.0,matches,mismatches)
    if mismatches and matches==0:return (0.0,matches,mismatches)
    base=float(row["confidence"])*float(row["source_weight"])
    if matches:base*=1.0+min(0.35,matches*0.08)
    if mismatches:base*=max(0.15,0.5**mismatches)
    corroboration=json.loads(row["corroboration_json"] or "[]")
    if corroboration:base*=1.0+min(0.2,len(corroboration)*0.04)
    return (min(base,1.5),matches,mismatches)

def validate_spec(spec:dict[str,Any],policy:dict[str,Any])->dict[str,Any]:
    if spec.get("schema")!=SPEC_SCHEMA:raise ValueError("PERSONA_SPEC_SCHEMA_INVALID")
    if spec.get("mode")!="FICTIONAL_ARCHETYPE":raise ValueError("PERSONA_MODE_MUST_BE_FICTIONAL_ARCHETYPE")
    persona_id=clean_text(spec.get("persona_id"),160)
    display=clean_text(spec.get("display_name"),240)
    if not persona_id or not display:raise ValueError("PERSONA_ID_AND_NAME_REQUIRED")
    p=policy.get("persona") or {}
    try:intensity=int(spec.get("stereotype_intensity",p.get("default_stereotype_intensity",1)))
    except Exception:raise ValueError("STEREOTYPE_INTENSITY_INVALID")
    lo=int(p.get("stereotype_intensity_min",0));hi=int(p.get("stereotype_intensity_max",3))
    if not lo<=intensity<=hi:raise ValueError("STEREOTYPE_INTENSITY_OUT_OF_RANGE")
    out={"schema":SPEC_SCHEMA,"persona_id":persona_id,"mode":"FICTIONAL_ARCHETYPE",
         "display_name":display,"stereotype_intensity":intensity}
    scalar=("presentation_gender","age_band","era")
    lists=("regions","cultures","social_milieu","education","occupations","languages","sociolect",
           "temperament","values","speech_style","creative_notes")
    for k in scalar:
        v=clean_text(spec.get(k),240)
        if v:out[k]=v
    for k in lists:
        v=values(spec.get(k))
        if v:out[k]=v
    return out

def synthesize(con:sqlite3.Connection,spec:dict[str,Any],policy:dict[str,Any],max_hints:int=24)->dict[str,Any]:
    s=validate_spec(spec,policy)
    pf=persona_facets(s)
    rows=con.execute("SELECT * FROM observations").fetchall()
    ranked=[]
    for row in rows:
        score,matches,mismatches=match_score(row,pf)
        if score<=0:continue
        ranked.append((score,matches,mismatches,row))
    ranked.sort(key=lambda x:(x[0],x[1]),reverse=True)
    intensity=s["stereotype_intensity"]
    multiplier=intensity/3.0 if intensity else 0.0
    hints=[];mix={};dimensions={}
    for score,matches,mismatches,row in ranked[:max(1,max_hints)]:
        scope=row["evidence_scope"]
        source_type=row["source_type"]
        mix[source_type]=mix.get(source_type,0)+1
        applied=min(1.0,score*multiplier)
        hint={
          "observation_id":row["observation_id"],"domain":row["domain"],
          "pattern":row["pattern"],"evidence_scope":scope,"source_type":source_type,
          "source_ref":row["source_ref"],"confidence":round(float(row["confidence"]),3),
          "compatibility_score":round(score,3),"creative_application_strength":round(applied,3),
          "matched_facets":matches,"mismatched_facets":mismatches,
          "representation_only":scope=="REPRESENTATION_ONLY"
        }
        hints.append(hint)
        dimensions.setdefault(row["domain"],[]).append({
          "pattern":row["pattern"],"strength":round(applied,3),
          "evidence_scope":scope,"observation_id":row["observation_id"]
        })
    assumptions=[]
    for k in ("temperament","values","speech_style","creative_notes"):
        for v in s.get(k) or []:
            assumptions.append(f"Explicit creative specification — {k}: {v}")
    identity={k:s[k] for k in (
      "presentation_gender","age_band","regions","cultures","social_milieu","education",
      "occupations","era","languages","sociolect"
    ) if k in s}
    return {
      "schema":CARD_SCHEMA,"persona_id":s["persona_id"],"display_name":s["display_name"],
      "mode":"FICTIONAL_ARCHETYPE","stereotype_intensity":intensity,
      "identity_frame":identity,"behavior_dimensions":dimensions,
      "creative_assumptions":assumptions,"evidence_hints":hints,"source_mix":mix,
      "governance":{
        "fictional_persona":True,"creative_archetype":True,
        "stereotype_intensity_is_creative_control":True,
        "not_a_prediction_about_real_people":True,
        "real_person_trait_inference_forbidden":True,
        "psychological_diagnosis_forbidden":True,
        "fictional_representation_never_empirical_truth":True,
        "contradictory_evidence_may_coexist":True,
        "decision_authority":False,"execution_authority":False,
        "automatic_external_spend_eur":0
      },
      "generated_at":now_iso(),"automatic_external_spend_eur":0
    }

def record_feedback(con:sqlite3.Connection,fb:dict[str,Any])->dict[str,Any]:
    if fb.get("schema")!=FEEDBACK_SCHEMA:raise ValueError("PERSONA_FEEDBACK_SCHEMA_INVALID")
    fid=clean_text(fb.get("feedback_id"),160);pid=clean_text(fb.get("persona_id"),160)
    ctx=clean_text(fb.get("interaction_context"),3000);effect=clean_text(fb.get("observed_effect"),3000)
    hint=clean_text(fb.get("adjustment_hint"),1500)
    try:rating=int(fb.get("rating"))
    except Exception:raise ValueError("PERSONA_FEEDBACK_RATING_INVALID")
    if not fid or not pid or not ctx or not effect or rating not in (-2,-1,0,1,2):
        raise ValueError("PERSONA_FEEDBACK_FIELDS_INVALID")
    normalized={"schema":FEEDBACK_SCHEMA,"feedback_id":fid,"persona_id":pid,
                "interaction_context":ctx,"observed_effect":effect,"rating":rating}
    if hint:normalized["adjustment_hint"]=hint
    sha=digest(normalized)
    prior=con.execute("SELECT payload_sha256 FROM persona_feedback WHERE feedback_id=?",(fid,)).fetchone()
    if prior:
        if prior["payload_sha256"]==sha:return {"status":"UNCHANGED","feedback_id":fid}
        raise ValueError("PERSONA_FEEDBACK_ID_CONFLICT")
    con.execute("""INSERT INTO persona_feedback(
      feedback_id,persona_id,interaction_context,observed_effect,rating,adjustment_hint,payload_sha256,recorded_at
    ) VALUES(?,?,?,?,?,?,?,?)""",(fid,pid,ctx,effect,rating,hint or None,sha,now_iso()))
    con.commit()
    return {"status":"RECORDED","feedback_id":fid,"persona_id":pid,
            "policy_mutated":False,"permissions_changed":False,"automatic_external_spend_eur":0}

def learning_delta(con:sqlite3.Connection,limit:int=100)->dict[str,Any]:
    obs=[dict(r) for r in con.execute("""SELECT observation_id,source_type,source_ref,evidence_scope,domain,
      confidence,payload_sha256,ingested_at FROM observations ORDER BY ingested_at DESC LIMIT ?""",(limit,)).fetchall()]
    fb=[dict(r) for r in con.execute("""SELECT feedback_id,persona_id,rating,payload_sha256,recorded_at
      FROM persona_feedback ORDER BY recorded_at DESC LIMIT ?""",(limit,)).fetchall()]
    return {
      "schema":DELTA_SCHEMA,"kind":"human-behavior-evidence-delta","generated_at":now_iso(),
      "observations":obs,"persona_feedback":fb,
      "policy_change_requested":False,"permission_change_requested":False,
      "central_memory_target":"chacha-dev","guardian_required_for_material_change":True,
      "sentinel_required_for_material_change":True,"automatic_external_spend_eur":0
    }

def stats(con:sqlite3.Connection)->dict[str,Any]:
    obs=con.execute("SELECT COUNT(*) c FROM observations").fetchone()["c"]
    fb=con.execute("SELECT COUNT(*) c FROM persona_feedback").fetchone()["c"]
    by_scope={r["evidence_scope"]:r["c"] for r in con.execute("SELECT evidence_scope,COUNT(*) c FROM observations GROUP BY evidence_scope")}
    by_source={r["source_type"]:r["c"] for r in con.execute("SELECT source_type,COUNT(*) c FROM observations GROUP BY source_type")}
    return {"schema":"chacha.dev/human-behavior-center-stats/v1","observations":obs,"persona_feedback":fb,
            "by_scope":by_scope,"by_source":by_source,"automatic_external_spend_eur":0}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--policy",type=Path,required=True)
    ap.add_argument("--db",type=Path,required=True)
    sub=ap.add_subparsers(dest="command",required=True)
    p=sub.add_parser("ingest");p.add_argument("--observation",type=Path,required=True);p.add_argument("--output",type=Path)
    p=sub.add_parser("persona");p.add_argument("--spec",type=Path,required=True);p.add_argument("--output",type=Path,required=True);p.add_argument("--max-hints",type=int,default=24)
    p=sub.add_parser("feedback");p.add_argument("--feedback",type=Path,required=True);p.add_argument("--output",type=Path)
    p=sub.add_parser("learning-delta");p.add_argument("--output",type=Path,required=True);p.add_argument("--limit",type=int,default=100)
    p=sub.add_parser("stats");p.add_argument("--output",type=Path)
    a=ap.parse_args()
    policy=load(a.policy);validate_policy(policy);con=connect(a.db)
    if a.command=="ingest":out=ingest(con,load(a.observation),policy)
    elif a.command=="persona":
        out=synthesize(con,load(a.spec),policy,a.max_hints);save(a.output,out)
    elif a.command=="feedback":out=record_feedback(con,load(a.feedback))
    elif a.command=="learning-delta":
        out=learning_delta(con,a.limit);save(a.output,out)
    else:out=stats(con)
    if getattr(a,"output",None) and a.command not in ("persona","learning-delta"):save(a.output,out)
    print(json.dumps(out,ensure_ascii=False))
    print("CHACHA_DEV_V812_HUMAN_BEHAVIOR_CENTER=PASS",file=os.sys.stderr)
    print("CHACHA_DEV_V812_AUTOMATIC_EXTERNAL_SPEND_EUR=0",file=os.sys.stderr)
    return 0

if __name__=="__main__":raise SystemExit(main())
