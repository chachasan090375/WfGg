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
    return {ok:false,response:json({error:"sentinel_auth_invalid"},401)};
  const row=await env.DB.prepare("SELECT public_key_spki_b64 FROM sentinel_identities WHERE key_id=?1 AND status='ACTIVE'").bind(keyId).first();
  if(!row)return {ok:false,response:json({error:"sentinel_identity_unknown"},403)};
  const ok=await verifyEd25519(row.public_key_spki_b64,sig,requestMessage(req,ts,body));
  return ok?{ok:true,keyId}:{ok:false,response:json({error:"sentinel_signature_invalid"},403)};
}
function repoValid(v){return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(String(v||""));}
function revValid(v){return /^[0-9a-f]{40}$/.test(String(v||""));}
async function githubRuns(repository,revision,workflowName,env){
  const url="https://api.github.com/repos/"+repository+"/actions/runs?head_sha="+encodeURIComponent(revision)+"&per_page=100";
  const headers={"accept":"application/vnd.github+json","user-agent":"ChaCha-DEV-Sentinel/1.0","x-github-api-version":"2022-11-28"};
  if(env.GITHUB_TOKEN)headers.authorization="Bearer "+env.GITHUB_TOKEN;
  let r;
  try{r=await fetch(url,{headers});}catch(e){return {state:"UNAVAILABLE",reason:"GITHUB_FETCH_FAILED"};}
  if(!r.ok)return {state:"UNAVAILABLE",reason:"GITHUB_HTTP_"+r.status};
  let x;try{x=await r.json();}catch{return {state:"UNAVAILABLE",reason:"GITHUB_JSON_INVALID"};}
  const runs=(x.workflow_runs||[]).filter(w=>String(w.name||"")===workflowName&&String(w.head_sha||"")===revision);
  if(!runs.length)return {state:"BLOCK",reason:"SENTINEL_WORKFLOW_MISSING"};
  runs.sort((a,b)=>String(b.updated_at||"").localeCompare(String(a.updated_at||"")));
  const run=runs[0];
  if(run.status!=="completed")return {state:"BLOCK",reason:"SENTINEL_WORKFLOW_NOT_COMPLETED",run};
  if(run.conclusion!=="success")return {state:"BLOCK",reason:"SENTINEL_WORKFLOW_NOT_SUCCESS",run};
  return {state:"PASS",run};
}
async function publishAssuranceObservation(env,source,receiptId){
  const base=String(env.ASSURANCE_EXCHANGE_URL||"").replace(/\/$/,"");
  if(!base)return {status:"NOT_CONFIGURED"};
  const payload={schema:"chacha.dev/assurance-exchange-observation-ref/v1",source,receipt_id:receiptId};
  let r;
  try{
    r=await fetch(base+"/v1/observations",{
      method:"POST",headers:{"content-type":"application/json","user-agent":"ChaCha-DEV-Sentinel/1.0"},
      body:JSON.stringify(payload)
    });
  }catch{return {status:"DEFERRED",reason:"EXCHANGE_UNAVAILABLE"};}
  let x={};try{x=await r.json();}catch{}
  return {status:r.ok?"DELIVERED":"DEFERRED",http_status:r.status,correlation:x.correlation||null};
}

async function releaseCheck(req,env){
  const body=await req.text();const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(p.schema!=="chacha.dev/sentinel-release-check-request/v1")return json({error:"schema_invalid"},400);
  const projectId=String(p.project_id||""),repository=String(p.repository||""),revision=String(p.revision||"");
  const workflowName=String(p.workflow_name||env.REQUIRED_WORKFLOW_NAME||"ChaCha DEV Sentinel technical assurance");
  if(!projectId||!repoValid(repository)||!revValid(revision))return json({error:"project_repository_revision_invalid"},400);
  const gh=await githubRuns(repository,revision,workflowName,env);
  const reasons=[];
  let verdict=gh.state;
  if(gh.reason)reasons.push(gh.reason);
  const claimedAudit=String(p.audit_digest||"") || (gh.run?"github-actions-run:"+String(gh.run.id):"");
  const advisory=Math.max(0,Number(p.advisory_count||0));
  const seed=projectId+"\n"+repository+"\n"+revision+"\n"+workflowName+"\n"+String(gh.run?.id||"none")+"\n"+claimedAudit+"\n"+Date.now();
  const receiptId="sentinel-"+(await sha256Hex(seed)).slice(0,32);
  await env.DB.prepare(
    `INSERT INTO technical_release_receipts(receipt_id,project_id,repository,revision,workflow_name,workflow_run_id,workflow_url,verdict,reason_codes_json,audit_digest,advisory_count,created_at)
     VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,datetime('now'))`
  ).bind(receiptId,projectId,repository,revision,workflowName,gh.run?String(gh.run.id):null,gh.run?String(gh.run.html_url||""):null,
         verdict,JSON.stringify([...new Set(reasons)]),claimedAudit,advisory).run();
  let directiveId=null;
  if(verdict!=="PASS"){
    directiveId="sentinel-remed-"+receiptId;
    await env.DB.prepare(
      `INSERT OR IGNORE INTO sentinel_directives(directive_id,receipt_id,project_id,revision,severity,required_action,reason_codes_json,status,created_at)
       VALUES(?1,?2,?3,?4,'BLOCK','CENTRAL_ORCHESTRATOR_REPLAN_REPAIR_RETEST',?5,'OPEN',datetime('now'))`
    ).bind(directiveId,receiptId,projectId,revision,JSON.stringify([...new Set(reasons)])).run();
  }
  const exchangeDelivery=await publishAssuranceObservation(env,"SENTINEL",receiptId);
  return json({
    schema:"chacha.dev/sentinel-technical-receipt/v1",receipt_id:receiptId,project_id:projectId,
    repository,revision,workflow_name:workflowName,workflow_run_id:gh.run?String(gh.run.id):null,
    workflow_url:gh.run?String(gh.run.html_url||""):null,verdict,reason_codes:[...new Set(reasons)],
    audit_digest:claimedAudit,advisory_count:advisory,directive_id:directiveId,
    sentinel:"external-worker",technical_scope_only:true,direct_code_mutation:false,
    central_orchestrator_owns_remediation:true,
    assurance_exchange_delivery:exchangeDelivery,
    checked_at:new Date().toISOString()
  },verdict==="PASS"?200:409);
}
async function receipt(req,env,id){
  const row=await env.DB.prepare(
    "SELECT receipt_id,project_id,repository,revision,workflow_name,workflow_run_id,verdict,audit_digest,advisory_count,created_at FROM technical_release_receipts WHERE receipt_id=?1"
  ).bind(id).first();
  if(!row)return json({error:"receipt_not_found"},404);
  return json({schema:"chacha.dev/sentinel-public-receipt/v1",...row,external_sentinel:true,direct_mutation:false});
}
async function directives(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),status=String(u.searchParams.get("status")||"OPEN").toUpperCase();
  const rows=await env.DB.prepare(
    "SELECT directive_id,receipt_id,project_id,revision,severity,required_action,reason_codes_json,status,created_at,delivered_at,applied_at FROM sentinel_directives WHERE status=?1 ORDER BY created_at ASC LIMIT 100"
  ).bind(status).all();
  return json({schema:"chacha.dev/sentinel-directive-batch/v1",items:(rows.results||[]).map(r=>({
    ...r,reason_codes:JSON.parse(r.reason_codes_json||"[]")
  }))});
}
async function delivered(req,env){
  const body=await req.text();const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  const ids=Array.isArray(p.directive_ids)?p.directive_ids.map(String).slice(0,100):[];
  let count=0;
  for(const id of ids){
    const r=await env.DB.prepare("UPDATE sentinel_directives SET status='DELIVERED',delivered_at=datetime('now') WHERE directive_id=?1 AND status='OPEN'").bind(id).run();
    count+=r.meta.changes||0;
  }
  return json({schema:"chacha.dev/sentinel-directive-delivery/v1",status:"DELIVERED",count});
}
export default{
  async fetch(req,env){
    const u=new URL(req.url);
    if(req.method==="GET"&&u.pathname==="/healthz")return json({
      status:"ok",service:"chacha-dev-sentinel",external_technical_assurance:true,
      technical_scope_only:true,continuous_commit_assurance:true,preproduction_release_gate:true,
      github_workflow_verification:true,public_receipt_verification:true,
      assurance_exchange_enabled:Boolean(env.ASSURANCE_EXCHANGE_URL),technical_receipt_exchange_publish:true,
      direct_code_mutation:false,direct_application_mutation:false,
      central_orchestrator_owns_remediation:true,automatic_external_spend_eur:0
    });
    if(req.method==="POST"&&u.pathname==="/v1/release-check")return releaseCheck(req,env);
    if(req.method==="GET"&&u.pathname.startsWith("/v1/receipts/"))return receipt(req,env,decodeURIComponent(u.pathname.slice("/v1/receipts/".length)));
    if(req.method==="GET"&&u.pathname==="/v1/directives")return directives(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/directives/delivered")return delivered(req,env);
    return json({error:"not_found"},404);
  }
};
