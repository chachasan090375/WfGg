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
  if(!url)return {ok:false,reason:source+"_URL_MISSING"};
  let r;
  try{r=await fetch(url,{headers:{"accept":"application/json","user-agent":"ChaCha-DEV-Assurance-Exchange/1.0"}});}
  catch{return {ok:false,reason:source+"_RECEIPT_UNAVAILABLE"};}
  if(!r.ok)return {ok:false,reason:source+"_RECEIPT_UNKNOWN"};
  let x;try{x=await r.json();}catch{return {ok:false,reason:source+"_RECEIPT_INVALID"};}
  return {ok:true,receipt:x,url};
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
      direct_mutation:false,central_orchestrator_owns_remediation:true,
      technology_watch_guard:true,architecture_council_guard:true,
      automatic_external_spend_eur:0
    });
    if(req.method==="POST"&&u.pathname==="/v1/observations")return observe(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/recommendations")return recommendations(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/recommendations/delivered")return markDelivered(req,env);
    if(req.method==="GET"&&u.pathname.startsWith("/v1/correlations/"))
      return publicCorrelation(req,env,decodeURIComponent(u.pathname.slice("/v1/correlations/".length)));
    return json({error:"not_found"},404);
  }
};
