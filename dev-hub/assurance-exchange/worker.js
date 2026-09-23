const enc=new TextEncoder();

function json(data,status=200){
  return new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});
}
function stable(v){
  if(v===null||typeof v!=="object")return JSON.stringify(v);
  if(Array.isArray(v))return "["+v.map(stable).join(",")+"]";
  return "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+stable(v[k])).join(",")+"}";
}
async function sha256Hex(text){
  const d=await crypto.subtle.digest("SHA-256",enc.encode(text));
  return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,"0")).join("");
}
function b64uToBytes(s){
  s=String(s).replace(/-/g,"+").replace(/_/g,"/");
  while(s.length%4)s+="=";
  return Uint8Array.from(atob(s),c=>c.charCodeAt(0));
}
async function importEd25519Spki(b64){
  return crypto.subtle.importKey("spki",b64uToBytes(b64),{name:"Ed25519"},false,["verify"]);
}
async function verifyEd25519(publicKeyB64,signatureB64,message){
  const key=await importEd25519Spki(publicKeyB64);
  return crypto.subtle.verify({name:"Ed25519"},key,b64uToBytes(signatureB64),enc.encode(message));
}
function requestMessage(req,ts,body=""){
  const u=new URL(req.url);
  return ts+"\n"+req.method+"\n"+u.pathname+u.search+"\n"+body;
}
async function requireCentral(req,env,body=""){
  const keyId=req.headers.get("x-chacha-key-id")||"";
  const ts=req.headers.get("x-chacha-timestamp")||"";
  const sig=req.headers.get("x-chacha-signature")||"";
  const millis=Date.parse(ts);
  if(!keyId||!sig||!Number.isFinite(millis)||Math.abs(Date.now()-millis)>120000)
    return {ok:false,response:json({error:"exchange_auth_invalid"},401)};
  const row=await env.DB.prepare("SELECT public_key_spki_b64 FROM exchange_identities WHERE key_id=?1 AND status='ACTIVE'").bind(keyId).first();
  if(!row)return {ok:false,response:json({error:"exchange_identity_unknown"},403)};
  const ok=await verifyEd25519(row.public_key_spki_b64,sig,requestMessage(req,ts,body));
  return ok?{ok:true,keyId}:{ok:false,response:json({error:"exchange_signature_invalid"},403)};
}
async function requireProjectAssurance(req,env,body,projectId){
  const keyId=req.headers.get("x-chacha-key-id")||"";
  const ts=req.headers.get("x-chacha-timestamp")||"";
  const sig=req.headers.get("x-chacha-signature")||"";
  const millis=Date.parse(ts);
  if(!keyId||!sig||!Number.isFinite(millis)||Math.abs(Date.now()-millis)>120000)
    return {ok:false,response:json({error:"project_assurance_auth_invalid"},401)};
  const row=await env.DB.prepare(
    "SELECT project_id,public_key_spki_b64 FROM project_assurance_identities WHERE key_id=?1 AND status='ACTIVE'"
  ).bind(keyId).first();
  if(!row)return {ok:false,response:json({error:"project_assurance_identity_unknown"},403)};
  if(String(row.project_id||"")!==String(projectId||""))
    return {ok:false,response:json({error:"project_assurance_identity_project_mismatch"},403)};
  const ok=await verifyEd25519(row.public_key_spki_b64,sig,requestMessage(req,ts,body));
  return ok?{ok:true,keyId,projectId:String(row.project_id)}:
    {ok:false,response:json({error:"project_assurance_signature_invalid"},403)};
}

async function registerProjectAssuranceIdentity(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/project-assurance-identity-registration/v1")
    return json({error:"project_assurance_identity_schema_invalid"},400);
  const projectId=String(p.project_id||""),keyId=String(p.key_id||""),pub=String(p.public_key_spki_b64||"");
  if(!projectId||!/^project-[a-f0-9]{16}$/.test(keyId)||!pub)
    return json({error:"project_assurance_identity_invalid"},400);
  await env.DB.prepare(
    `INSERT INTO project_assurance_identities(key_id,project_id,status,public_key_spki_b64,created_at)
     VALUES(?1,?2,'ACTIVE',?3,datetime('now'))
     ON CONFLICT(key_id) DO UPDATE SET project_id=excluded.project_id,status='ACTIVE',
       public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=NULL`
  ).bind(keyId,projectId,pub).run();
  return json({
    schema:"chacha.dev/project-assurance-identity-registration-result/v1",
    status:"PASS",project_id:projectId,key_id:keyId,scope:"PERIPHERAL_ASSURANCE",
    direct_mutation:false,client_secret_allowed:false
  });
}

function peripheralEventPrivacyOk(e){
  const privacy=e&&e.privacy&&typeof e.privacy==="object"?e.privacy:{};
  return privacy.raw_user_content===false&&privacy.credentials===false&&privacy.secrets===false&&e.direct_mutation===false;
}

async function peripheralEvents(req,env){
  const body=await req.text();
  let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/project-assurance-event-batch/v1")
    return json({error:"project_event_batch_schema_invalid"},400);
  const projectId=String(p.project_id||"");
  if(!projectId)return json({error:"project_event_batch_project_required"},400);
  const auth=await requireProjectAssurance(req,env,body,projectId);if(!auth.ok)return auth.response;
  const events=Array.isArray(p.events)?p.events:[];
  if(!events.length||events.length>50)return json({error:"project_event_batch_size_invalid"},400);
  const acceptedRoles=new Set(["curator","bastion","intendant"]);
  let accepted=0;
  for(const e of events){
    if(!e||e.schema!=="chacha.dev/project-assurance-event/v1")
      return json({error:"project_event_schema_invalid"},400);
    const eventId=String(e.event_id||""),eventProjectId=String(e.project_id||"");
    const version=String(e.application_version||""),role=String(e.assurance_role||"");
    const fields=e.fields&&typeof e.fields==="object"&&!Array.isArray(e.fields)?e.fields:{};
    if(eventProjectId!==projectId)return json({error:"project_event_project_mismatch"},403);
    if(!acceptedRoles.has(role))return json({error:"peripheral_role_invalid"},400);
    if(!eventId||!version||!peripheralEventPrivacyOk(e))
      return json({error:"project_event_identity_or_privacy_invalid"},400);
    const eventType=String(fields.event_type||""),severity=String(fields.severity||"INFO");
    const componentId=String(fields.component_id||"")||null;
    const componentVersion=String(fields.component_version||"")||null;
    const eventDigest=String(e.event_digest||await sha256Hex(stable(e)));
    await env.DB.prepare(
      `INSERT OR IGNORE INTO peripheral_project_events
       (event_id,project_id,application_version,assurance_role,event_type,severity,component_id,component_version,event_digest,fields_json,observed_at,ingested_at)
       VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,datetime('now'))`
    ).bind(eventId,projectId,version,role,eventType,severity,componentId,componentVersion,
           eventDigest,stable(fields),String(e.observed_at||new Date().toISOString())).run();
    accepted++;
  }
  return json({
    schema:"chacha.dev/peripheral-project-event-ingest/v1",
    status:"PASS",project_id:projectId,accepted,roles:[...new Set(events.map(e=>String(e.assurance_role||"")))].sort(),
    incremental:true,raw_user_content:false,direct_mutation:false,
    central_orchestrator_owns_remediation:true
  });
}

async function peripheralEventsQuery(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),project=String(u.searchParams.get("project_id")||"");
  const role=String(u.searchParams.get("role")||"");
  let q="SELECT * FROM peripheral_project_events WHERE 1=1",args=[];
  if(project){q+=" AND project_id=?"+(args.length+1);args.push(project);}
  if(role){q+=" AND assurance_role=?"+(args.length+1);args.push(role);}
  q+=" ORDER BY observed_at DESC LIMIT 200";
  let stmt=env.DB.prepare(q);if(args.length)stmt=stmt.bind(...args);
  const rows=(await stmt.all()).results||[];
  return json({
    schema:"chacha.dev/peripheral-project-event-batch/v1",
    items:rows.map(r=>({...r,fields:JSON.parse(r.fields_json||"{}")})),
    count:rows.length,source_evidence_preserved:true,direct_mutation:false
  });
}

function uniq(xs){return [...new Set((xs||[]).map(String).filter(Boolean))].sort();}
function severityFor(source,receipt){
  const verdict=String(receipt.verdict||"");
  if(verdict==="CRITICAL")return "CRITICAL";
  if(verdict==="BLOCK"||verdict==="UNAVAILABLE")return "BLOCK";
  return "INFO";
}
function sourceUrl(env,source,receiptId){
  const base=source==="GUARDIAN"?String(env.GUARDIAN_URL||""):String(env.SENTINEL_URL||"");
  if(!base)return null;
  const path=source==="GUARDIAN"?"/v1/functional-receipts/":"/v1/receipts/";
  return base.replace(/\/$/,"")+path+encodeURIComponent(receiptId);
}
async function fetchReceipt(env,source,receiptId){
  const url=sourceUrl(env,source,receiptId);
  const path=source==="GUARDIAN"
    ?"/v1/functional-receipts/"+encodeURIComponent(receiptId)
    :"/v1/receipts/"+encodeURIComponent(receiptId);
  const binding=source==="GUARDIAN"?env.GUARDIAN_SERVICE:env.SENTINEL_SERVICE;
  let r;
  try{
    if(binding){
      r=await binding.fetch(new Request("https://assurance-source.internal"+path,{
        method:"GET",
        headers:{"accept":"application/json","user-agent":"ChaCha-DEV-Assurance-Exchange/1.1"}
      }));
    }else{
      if(!url)return {ok:false,reason:source+"_URL_MISSING"};
      r=await fetch(url,{headers:{"accept":"application/json","user-agent":"ChaCha-DEV-Assurance-Exchange/1.1"}});
    }
  }catch{return {ok:false,reason:source+"_RECEIPT_UNAVAILABLE"};}
  if(!r.ok)return {ok:false,reason:source+"_RECEIPT_UNKNOWN"};
  let x;try{x=await r.json();}catch{return {ok:false,reason:source+"_RECEIPT_INVALID"};}
  return {ok:true,receipt:x,url:url||("service://"+source.toLowerCase()+path)};
}
function receiptSignals(source,x){
  const signals=[];
  for(const v of (Array.isArray(x.signal_codes)?x.signal_codes:[]))signals.push(String(v));
  for(const v of (Array.isArray(x.reason_codes)?x.reason_codes:[]))signals.push(source+"_REASON:"+String(v));
  if(source==="SENTINEL"&&Number(x.advisory_count||0)>0)signals.push("TECHNICAL_ADVISORY_PRESENT");
  if(source==="GUARDIAN"&&Number(x.passed_required_criteria_count||0)<Number(x.required_criteria_count||0))
    signals.push("FUNCTIONAL_CRITERIA_GAP");
  return uniq(signals);
}
function receiptRefs(source,x,url){
  const refs=[source.toLowerCase()+"-receipt:"+String(x.receipt_id||"")];
  if(url)refs.push(url);
  if(x.workflow_url)refs.push(String(x.workflow_url));
  if(x.audit_digest)refs.push("audit:"+String(x.audit_digest));
  if(x.contract_digest)refs.push("functional-contract:"+String(x.contract_digest));
  return uniq(refs);
}
async function upsertObservation(env,source,fr){
  const x=fr.receipt;
  const receiptId=String(x.receipt_id||"");
  const projectId=String(x.project_id||"");
  const revision=String(x.revision||"");
  if(!receiptId||!projectId||!/^[0-9a-f]{40}$/.test(revision))
    return {ok:false,reason:"SOURCE_RECEIPT_IDENTITY_INVALID"};
  const obsId="obs-"+(await sha256Hex(source+"\n"+receiptId)).slice(0,32);
  const signals=receiptSignals(source,x);
  const refs=receiptRefs(source,x,fr.url);
  const reasons=uniq(x.reason_codes||[]);
  const payloadDigest="sha256:"+await sha256Hex(stable(x));
  await env.DB.prepare(
    `INSERT INTO assurance_observations
      (observation_id,source,source_receipt_id,project_id,revision,verdict,severity,reason_codes_json,signal_codes_json,source_refs_json,source_payload_digest,observed_at,created_at)
     VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,datetime('now'))
     ON CONFLICT(source,source_receipt_id) DO UPDATE SET
       verdict=excluded.verdict,severity=excluded.severity,reason_codes_json=excluded.reason_codes_json,
       signal_codes_json=excluded.signal_codes_json,source_refs_json=excluded.source_refs_json,
       source_payload_digest=excluded.source_payload_digest,observed_at=excluded.observed_at`
  ).bind(obsId,source,receiptId,projectId,revision,String(x.verdict||"UNKNOWN"),severityFor(source,x),
         JSON.stringify(reasons),JSON.stringify(signals),JSON.stringify(refs),payloadDigest,
         String(x.checked_at||x.created_at||new Date().toISOString())).run();
  return {ok:true,observation_id:obsId,receipt_id:receiptId,project_id:projectId,revision,receipt:x,signals,refs};
}
function classify(g,s){
  const gv=String(g.receipt.verdict||""),sv=String(s.receipt.verdict||"");
  const gPass=gv==="PASS",sPass=sv==="PASS";
  const advisory=Number(s.receipt.advisory_count||0)>0;
  if(!gPass&&!sPass)return {priority:"BLOCKER",type:"JOINT_REMEDIATION_REQUIRED"};
  if(!gPass)return {priority:"BLOCKER",type:"FUNCTIONAL_REMEDIATION_REQUIRED"};
  if(!sPass)return {priority:"BLOCKER",type:"TECHNICAL_REMEDIATION_REQUIRED"};
  if(advisory)return {priority:"OPTIMIZE",type:"OPTIMIZE_WITH_FUNCTIONAL_GUARDRAIL"};
  return {priority:"OBSERVE",type:"OBSERVE_HEALTHY_REVISION"};
}
async function correlate(env,projectId,revision){
  const rows=(await env.DB.prepare(
    `SELECT * FROM assurance_observations WHERE project_id=?1 AND revision=?2
     ORDER BY created_at DESC`
  ).bind(projectId,revision).all()).results||[];
  const g=rows.find(x=>x.source==="GUARDIAN"),s=rows.find(x=>x.source==="SENTINEL");
  if(!g||!s)return {status:"WAITING_FOR_PEER"};
  const gReceipt=(await fetchReceipt(env,"GUARDIAN",g.source_receipt_id));
  const sReceipt=(await fetchReceipt(env,"SENTINEL",s.source_receipt_id));
  if(!gReceipt.ok||!sReceipt.ok)return {status:"SOURCE_RECEIPT_REVERIFY_FAILED"};
  const gg={receipt:gReceipt.receipt,signals:receiptSignals("GUARDIAN",gReceipt.receipt),refs:receiptRefs("GUARDIAN",gReceipt.receipt,gReceipt.url)};
  const ss={receipt:sReceipt.receipt,signals:receiptSignals("SENTINEL",sReceipt.receipt),refs:receiptRefs("SENTINEL",sReceipt.receipt,sReceipt.url)};
  const cls=classify(gg,ss);
  const shared=gg.signals.filter(x=>ss.signals.includes(x));
  const causality=shared.length?"CORRELATED":"UNPROVEN";
  const reasons=uniq([
    "GUARDIAN_VERDICT:"+String(gg.receipt.verdict||"UNKNOWN"),
    "SENTINEL_VERDICT:"+String(ss.receipt.verdict||"UNKNOWN"),
    ...gg.signals,...ss.signals
  ]);
  const evidence=uniq([...gg.refs,...ss.refs]);
  const correlationId="corr-"+(await sha256Hex(projectId+"\n"+revision+"\n"+g.source_receipt_id+"\n"+s.source_receipt_id)).slice(0,32);
  await env.DB.prepare(
    `INSERT INTO assurance_correlations
      (correlation_id,project_id,revision,guardian_observation_id,sentinel_observation_id,guardian_receipt_id,sentinel_receipt_id,
       priority,recommendation_type,causality_status,reason_codes_json,signal_codes_json,evidence_refs_json,
       technology_watch_required_if_architecture_change,architecture_council_required_if_architecture_change,
       direct_mutation_allowed,remediation_owner,status,created_at)
     VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,1,1,0,'central-orchestrator','OPEN',datetime('now'))
     ON CONFLICT(guardian_receipt_id,sentinel_receipt_id) DO UPDATE SET
       priority=excluded.priority,recommendation_type=excluded.recommendation_type,
       causality_status=excluded.causality_status,reason_codes_json=excluded.reason_codes_json,
       signal_codes_json=excluded.signal_codes_json,evidence_refs_json=excluded.evidence_refs_json`
  ).bind(correlationId,projectId,revision,g.observation_id,s.observation_id,g.source_receipt_id,s.source_receipt_id,
         cls.priority,cls.type,causality,JSON.stringify(reasons),JSON.stringify(uniq([...gg.signals,...ss.signals])),
         JSON.stringify(evidence)).run();
  return {status:"CORRELATED",correlation_id:correlationId,priority:cls.priority,recommendation_type:cls.type,causality_status:causality};
}
function finalReviewBinding(env,source){
  if(source==="GUARDIAN")return env.GUARDIAN_SERVICE;
  if(source==="SENTINEL")return env.SENTINEL_SERVICE;
  if(source==="CURATOR")return env.CURATOR_SERVICE;
  if(source==="BASTION")return env.BASTION_SERVICE;
  if(source==="INTENDANT")return env.INTENDANT_SERVICE;
  return null;
}
function finalReviewPath(source,receiptId){
  const id=encodeURIComponent(receiptId);
  if(source==="GUARDIAN"||source==="SENTINEL")return "/v1/final-reviews/"+id;
  return "/v1/reviews/"+id;
}
async function fetchExternalFinalReview(env,source,receiptId){
  const binding=finalReviewBinding(env,source);
  if(!binding)return {ok:false,reason:source+"_SERVICE_BINDING_MISSING"};
  let r;try{
    r=await binding.fetch(new Request("https://final-review-source.internal"+finalReviewPath(source,receiptId),{
      method:"GET",headers:{"accept":"application/json","user-agent":"ChaCha-DEV-Assurance-Exchange/1.3"}
    }));
  }catch{return {ok:false,reason:source+"_FINAL_REVIEW_UNAVAILABLE"};}
  if(!r.ok)return {ok:false,reason:source+"_FINAL_REVIEW_UNKNOWN"};
  let x;try{x=await r.json();}catch{return {ok:false,reason:source+"_FINAL_REVIEW_INVALID"};}
  if(x.schema!=="chacha.dev/compromise-agent-review/v1")return {ok:false,reason:"FINAL_REVIEW_SCHEMA_INVALID"};
  if(String(x.agent||"").toUpperCase()!==source)return {ok:false,reason:"FINAL_REVIEW_SOURCE_MISMATCH"};
  return {ok:true,review:x};
}
async function finalReviewRef(req,env){
  let p;try{p=await req.json();}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/final-review-ref/v1")return json({error:"schema_invalid"},400);
  const source=String(p.source||"").toUpperCase(),receiptId=String(p.receipt_id||"");
  if(!["GUARDIAN","SENTINEL","CURATOR","BASTION","INTENDANT"].includes(source)||!receiptId)
    return json({error:"source_or_receipt_invalid"},400);
  const fr=await fetchExternalFinalReview(env,source,receiptId);
  if(!fr.ok)return json({error:fr.reason},409);
  const x=fr.review,projectId=String(x.project_id||""),revision=String(x.revision||""),
        compromise=String(x.compromise_digest||"");
  if(!projectId||!/^[0-9a-f]{40}$/.test(revision)||!compromise)
    return json({error:"final_review_identity_invalid"},409);
  const payloadDigest="sha256:"+await sha256Hex(stable(x));
  await env.DB.prepare(`INSERT INTO external_final_reviews
    (source,receipt_id,project_id,revision,compromise_digest,verdict,hard_objections_json,soft_objections_json,
     evidence_refs_json,implementation_verified,source_payload_digest,created_at)
    VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,datetime('now'))
    ON CONFLICT(source,receipt_id) DO UPDATE SET
      verdict=excluded.verdict,hard_objections_json=excluded.hard_objections_json,
      soft_objections_json=excluded.soft_objections_json,evidence_refs_json=excluded.evidence_refs_json,
      implementation_verified=excluded.implementation_verified,source_payload_digest=excluded.source_payload_digest`)
    .bind(source,receiptId,projectId,revision,compromise,String(x.verdict||"UNKNOWN"),
      JSON.stringify(x.hard_objections||[]),JSON.stringify(x.soft_objections||[]),JSON.stringify(x.evidence_refs||[]),
      x.implementation_verified===true?1:0,payloadDigest).run();
  return json({
    schema:"chacha.dev/final-review-exchange-result/v1",status:"RECORDED",
    source,receipt_id:receiptId,project_id:projectId,revision,compromise_digest:compromise,
    source_reverified:true,direct_mutation:false
  });
}
async function finalReviews(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),project=String(u.searchParams.get("project_id")||""),
        revision=String(u.searchParams.get("revision")||""),
        compromise=String(u.searchParams.get("compromise_digest")||"");
  if(!project||!revision||!compromise)return json({error:"project_revision_compromise_required"},400);
  const rows=(await env.DB.prepare(
    `SELECT * FROM external_final_reviews
     WHERE project_id=?1 AND revision=?2 AND compromise_digest=?3
     ORDER BY source ASC, created_at ASC, receipt_id ASC`
  ).bind(project,revision,compromise).all()).results||[];
  const latest=new Map();
  for(const row of rows)latest.set(String(row.source||""),row);
  const selected=[...latest.values()].sort((a,b)=>String(a.source||"").localeCompare(String(b.source||"")));
  return json({
    schema:"chacha.dev/external-final-review-batch/v1",
    project_id:project,revision,compromise_digest:compromise,
    items:selected.map(r=>({
      schema:"chacha.dev/compromise-agent-review/v1",
      agent:String(r.source||"").toLowerCase(),receipt_id:r.receipt_id,
      project_id:r.project_id,revision:r.revision,compromise_digest:r.compromise_digest,
      verdict:r.verdict,hard_objections:JSON.parse(r.hard_objections_json||"[]"),
      soft_objections:JSON.parse(r.soft_objections_json||"[]"),
      evidence_refs:JSON.parse(r.evidence_refs_json||"[]"),
      implementation_verified:Boolean(r.implementation_verified),
      source_authority:"EXTERNAL",source_reverified:true,
      source_payload_digest:r.source_payload_digest,post_implementation_second_read:true,
      direct_mutation:false,reviewed_at:r.created_at
    })),
    count:selected.length,total_historical_reviews:rows.length,
    latest_review_per_source:true,
    required_external_agents:["guardian","sentinel","curator","bastion","intendant"],
    source_reverified:true,direct_mutation:false
  });
}

function specialistBinding(env,source){
  if(source==="CURATOR")return env.CURATOR_SERVICE;
  if(source==="BASTION")return env.BASTION_SERVICE;
  if(source==="INTENDANT")return env.INTENDANT_SERVICE;
  return null;
}
async function fetchSpecialistReview(env,source,receiptId){
  const binding=specialistBinding(env,source);
  if(!binding)return {ok:false,reason:source+"_SERVICE_BINDING_MISSING"};
  let r;
  try{
    r=await binding.fetch(new Request(
      "https://specialist.internal/v1/reviews/"+encodeURIComponent(receiptId),
      {method:"GET",headers:{"accept":"application/json","user-agent":"ChaCha-DEV-Assurance-Exchange/1.2"}}
    ));
  }catch{return {ok:false,reason:source+"_REVIEW_UNAVAILABLE"};}
  if(!r.ok)return {ok:false,reason:source+"_REVIEW_UNKNOWN"};
  let x;try{x=await r.json();}catch{return {ok:false,reason:source+"_REVIEW_INVALID"};}
  if(String(x.agent||"").toUpperCase()!==source)return {ok:false,reason:"SPECIALIST_REVIEW_SOURCE_MISMATCH"};
  return {ok:true,review:x};
}
async function specialistReviewRef(req,env){
  let p;try{p=await req.json();}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/specialist-review-ref/v1")return json({error:"schema_invalid"},400);
  const source=String(p.source||"").toUpperCase(),receiptId=String(p.receipt_id||"");
  if(!["CURATOR","BASTION","INTENDANT"].includes(source)||!receiptId)
    return json({error:"source_or_receipt_invalid"},400);
  const fr=await fetchSpecialistReview(env,source,receiptId);
  if(!fr.ok)return json({error:fr.reason},409);
  const x=fr.review,projectId=String(x.project_id||""),revision=String(x.revision||"");
  const compromise=String(x.compromise_digest||"");
  if(!projectId||!/^[0-9a-f]{40}$/.test(revision)||!compromise)
    return json({error:"specialist_review_identity_invalid"},409);
  const payloadDigest="sha256:"+await sha256Hex(stable(x));
  await env.DB.prepare(`INSERT INTO specialist_authority_reviews
    (source,receipt_id,project_id,revision,compromise_digest,verdict,hard_objections_json,soft_objections_json,
     evidence_refs_json,implementation_verified,source_payload_digest,created_at)
    VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,datetime('now'))
    ON CONFLICT(source,receipt_id) DO UPDATE SET
      verdict=excluded.verdict,hard_objections_json=excluded.hard_objections_json,
      soft_objections_json=excluded.soft_objections_json,evidence_refs_json=excluded.evidence_refs_json,
      implementation_verified=excluded.implementation_verified,source_payload_digest=excluded.source_payload_digest`)
    .bind(source,receiptId,projectId,revision,compromise,String(x.verdict||"UNKNOWN"),
      JSON.stringify(x.hard_objections||[]),JSON.stringify(x.soft_objections||[]),JSON.stringify(x.evidence_refs||[]),
      x.implementation_verified===true?1:0,payloadDigest).run();
  return json({
    schema:"chacha.dev/specialist-review-exchange-result/v1",status:"RECORDED",
    source,receipt_id:receiptId,project_id:projectId,revision,compromise_digest:compromise,
    source_reverified:true,direct_mutation:false
  });
}
async function specialistReviews(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),project=String(u.searchParams.get("project_id")||"");
  const revision=String(u.searchParams.get("revision")||""),compromise=String(u.searchParams.get("compromise_digest")||"");
  if(!project||!revision||!compromise)return json({error:"project_revision_compromise_required"},400);
  const rows=(await env.DB.prepare(
    `SELECT * FROM specialist_authority_reviews
     WHERE project_id=?1 AND revision=?2 AND compromise_digest=?3 ORDER BY source ASC`
  ).bind(project,revision,compromise).all()).results||[];
  return json({
    schema:"chacha.dev/specialist-review-exchange-batch/v1",
    project_id:project,revision,compromise_digest:compromise,
    items:rows.map(r=>({
      agent:String(r.source||"").toLowerCase(),receipt_id:r.receipt_id,verdict:r.verdict,
      hard_objections:JSON.parse(r.hard_objections_json||"[]"),
      soft_objections:JSON.parse(r.soft_objections_json||"[]"),
      evidence_refs:JSON.parse(r.evidence_refs_json||"[]"),
      implementation_verified:Boolean(r.implementation_verified),
      source_payload_digest:r.source_payload_digest,source_reverified:true
    })),
    count:rows.length,direct_mutation:false
  });
}

async function observe(req,env){
  let p;try{p=await req.json();}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/assurance-exchange-observation-ref/v1")return json({error:"schema_invalid"},400);
  const source=String(p.source||"").toUpperCase(),receiptId=String(p.receipt_id||"");
  if(!["GUARDIAN","SENTINEL"].includes(source)||!receiptId)return json({error:"source_or_receipt_invalid"},400);
  const fr=await fetchReceipt(env,source,receiptId);
  if(!fr.ok)return json({error:fr.reason},409);
  const obs=await upsertObservation(env,source,fr);
  if(!obs.ok)return json({error:obs.reason},409);
  const correlation=await correlate(env,obs.project_id,obs.revision);
  return json({schema:"chacha.dev/assurance-exchange-observation-result/v1",status:"RECORDED",
               source,receipt_id:receiptId,observation_id:obs.observation_id,
               project_id:obs.project_id,revision:obs.revision,correlation,
               direct_mutation:false,central_orchestrator_owns_remediation:true});
}
function correlationView(r){
  let reasons=[],signals=[],evidence=[];
  try{reasons=JSON.parse(r.reason_codes_json||"[]");}catch{}
  try{signals=JSON.parse(r.signal_codes_json||"[]");}catch{}
  try{evidence=JSON.parse(r.evidence_refs_json||"[]");}catch{}
  return {
    schema:"chacha.dev/assurance-exchange-recommendation/v1",
    correlation_id:r.correlation_id,project_id:r.project_id,revision:r.revision,
    guardian_receipt_id:r.guardian_receipt_id,sentinel_receipt_id:r.sentinel_receipt_id,
    priority:r.priority,recommendation_type:r.recommendation_type,causality_status:r.causality_status,
    reason_codes:reasons,signal_codes:signals,evidence_refs:evidence,status:r.status,
    technology_watch_required_if_architecture_change:Boolean(r.technology_watch_required_if_architecture_change),
    architecture_council_required_if_architecture_change:Boolean(r.architecture_council_required_if_architecture_change),
    direct_mutation_allowed:false,remediation_owner:"central-orchestrator",
    created_at:r.created_at,delivered_at:r.delivered_at,resolved_at:r.resolved_at
  };
}
async function recommendations(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),status=String(u.searchParams.get("status")||"OPEN").toUpperCase();
  const project=String(u.searchParams.get("project_id")||"");
  let q=`SELECT * FROM assurance_correlations WHERE status=?1`,args=[status];
  if(project){q+=" AND project_id=?2";args.push(project);}
  q+=" ORDER BY CASE priority WHEN 'BLOCKER' THEN 3 WHEN 'OPTIMIZE' THEN 2 ELSE 1 END DESC, created_at ASC LIMIT 100";
  const stmt=env.DB.prepare(q);
  const rows=(await (args.length===2?stmt.bind(args[0],args[1]):stmt.bind(args[0])).all()).results||[];
  return json({schema:"chacha.dev/assurance-exchange-recommendation-batch/v1",
               items:rows.map(correlationView),count:rows.length,
               direct_mutation:false,central_orchestrator_owns_remediation:true});
}
async function markDelivered(req,env){
  const body=await req.text();const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  const ids=Array.isArray(p.correlation_ids)?p.correlation_ids.map(String).slice(0,100):[];
  let count=0;
  for(const id of ids){
    const r=await env.DB.prepare(
      "UPDATE assurance_correlations SET status='DELIVERED',delivered_at=datetime('now') WHERE correlation_id=?1 AND status='OPEN'"
    ).bind(id).run();
    count+=r.meta.changes||0;
  }
  return json({schema:"chacha.dev/assurance-exchange-delivery/v1",status:"DELIVERED",count});
}
async function publicCorrelation(req,env,id){
  const r=await env.DB.prepare("SELECT * FROM assurance_correlations WHERE correlation_id=?1").bind(id).first();
  if(!r)return json({error:"correlation_not_found"},404);
  return json(correlationView(r));
}
export default{
  async fetch(req,env){
    const u=new URL(req.url);
    if(req.method==="GET"&&u.pathname==="/healthz")return json({
      status:"ok",service:"chacha-dev-assurance-exchange",external_control_plane:true,
      guardian_sentinel_correlation:true,evidence_preserving:true,causality_not_invented:true,
      guardian_service_binding:Boolean(env.GUARDIAN_SERVICE),
      sentinel_service_binding:Boolean(env.SENTINEL_SERVICE),
      project_assurance_identity_registration:true,
      curator_local_ingest:true,bastion_local_ingest:true,intendant_local_ingest:true,
      five_agent_local_probe_fabric:true,incremental_peripheral_events:true,
      curator_service_binding:Boolean(env.CURATOR_SERVICE),
      bastion_service_binding:Boolean(env.BASTION_SERVICE),
      intendant_service_binding:Boolean(env.INTENDANT_SERVICE),
      specialist_review_source_reverification:true,
      five_external_final_review_reverification:true,
      seven_agent_final_compromise_support:true,
      direct_mutation:false,central_orchestrator_owns_remediation:true,
      technology_watch_guard:true,architecture_council_guard:true,
      automatic_external_spend_eur:0
    });
    if(req.method==="POST"&&u.pathname==="/v1/project-assurance-identities/register")
      return registerProjectAssuranceIdentity(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/peripheral-events")return peripheralEvents(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/peripheral-events")return peripheralEventsQuery(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/observations")return observe(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/specialist-reviews")return specialistReviewRef(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/specialist-reviews")return specialistReviews(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/final-reviews")return finalReviewRef(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/final-reviews")return finalReviews(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/recommendations")return recommendations(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/recommendations/delivered")return markDelivered(req,env);
    if(req.method==="GET"&&u.pathname.startsWith("/v1/correlations/"))
      return publicCorrelation(req,env,decodeURIComponent(u.pathname.slice("/v1/correlations/".length)));
    return json({error:"not_found"},404);
  }
};
