const enc = new TextEncoder();
const SENSITIVE = new Set([
  "production-deploy","production-data-write","secret-change",
  "destructive-operation","technology-replacement"
]);

function json(data,status=200){
  return new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}});
}
function stable(v){
  if(v===null||typeof v!=="object") return JSON.stringify(v);
  if(Array.isArray(v)) return "["+v.map(stable).join(",")+"]";
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
    return {ok:false,response:json({error:"guardian_auth_invalid"},401)};
  const row=await env.DB.prepare("SELECT public_key_spki_b64 FROM guardian_identities WHERE key_id=?1 AND status='ACTIVE'").bind(keyId).first();
  if(!row)return {ok:false,response:json({error:"guardian_identity_unknown"},403)};
  const ok=await verifyEd25519(row.public_key_spki_b64,sig,requestMessage(req,ts,body));
  return ok?{ok:true,keyId}:{ok:false,response:json({error:"guardian_signature_invalid"},403)};
}
function arr(v){
  try{const x=typeof v==="string"?JSON.parse(v):v;return Array.isArray(x)?x.map(String):[];}catch{return [];}
}
function allows(list,value){return list.includes("*")||list.includes(String(value||""));}
function truthyEvidence(evidence,key){
  const v=(evidence||{})[key];
  return v===true||v==="PASS"||v==="YES"||v==="OK"||v==="VERIFIED";
}
async function contractById(env,id){
  if(!id)return null;
  return env.DB.prepare("SELECT * FROM role_contracts WHERE contract_id=?1").bind(id).first();
}
async function resolveRoleContract(env,role){
  role=String(role||"");
  let row=await contractById(env,"role:"+role);
  if(row)return row;
  const lower=role.toLowerCase();
  if(lower.includes("foundry"))return contractById(env,"role:__foundry__");
  if(lower.endsWith("-agent")||lower==="agent")return contractById(env,"role:__agent__");
  if(lower.includes("orchestrator"))return contractById(env,"role:__orchestrator__");
  return contractById(env,"role:__unknown__");
}
async function dynamicContract(env,contractId,version){
  if(!contractId)return null;
  if(version){
    return env.DB.prepare(
      "SELECT * FROM dynamic_role_contracts WHERE contract_id=?1 AND version=?2 AND status='ACTIVE'"
    ).bind(String(contractId),String(version)).first();
  }
  return env.DB.prepare(
    "SELECT * FROM dynamic_role_contracts WHERE contract_id=?1 AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1"
  ).bind(String(contractId)).first();
}
async function dynamicComponentContract(env,contractId,version){
  if(!contractId)return null;
  if(version){
    return env.DB.prepare(
      "SELECT * FROM dynamic_component_contracts WHERE contract_id=?1 AND version=?2 AND status='ACTIVE'"
    ).bind(String(contractId),String(version)).first();
  }
  return env.DB.prepare(
    "SELECT * FROM dynamic_component_contracts WHERE contract_id=?1 AND status='ACTIVE' ORDER BY created_at DESC LIMIT 1"
  ).bind(String(contractId)).first();
}
function order(sev){return ({INFO:0,WARNING:1,BLOCK:2,CRITICAL:3})[sev]??0;}
function mergeEval(a,b){
  const severity=order(b.severity)>order(a.severity)?b.severity:a.severity;
  return {...a,severity,verdict:severity==="CRITICAL"?"CRITICAL":severity==="BLOCK"?"BLOCK":severity==="WARNING"?"WARNING":"PASS",
          reason_codes:[...new Set([...(a.reason_codes||[]),...(b.reason_codes||[])])]};
}
function addReason(state,severity,code){
  state.reasons.push(code);
  if(order(severity)>order(state.severity))state.severity=severity;
}
function verdictFromSeverity(severity){
  if(severity==="CRITICAL")return "CRITICAL";
  if(severity==="BLOCK")return "BLOCK";
  if(severity==="WARNING")return "WARNING";
  return "PASS";
}
async function evaluate(event,env){
  const state={severity:"INFO",reasons:[]};
  const actor=String(event.actor||"");
  const subjectRole=String(event.subject_role||"");
  const action=String(event.action||"");
  const permission=String(event.permission||"read");
  const phase=String(event.phase||"");
  const evidence=event.evidence||{};
  const context=event.context||{};

  if(event.schema!=="chacha.dev/governance-action/v1")addReason(state,"BLOCK","EVENT_SCHEMA_INVALID");
  if(!event.event_id)addReason(state,"BLOCK","EVENT_ID_MISSING");
  if(!["PRE_ACTION","POST_ACTION"].includes(phase))addReason(state,"BLOCK","EVENT_PHASE_INVALID");
  if(!actor)addReason(state,"BLOCK","ACTOR_MISSING");
  if(!subjectRole)addReason(state,"BLOCK","SUBJECT_ROLE_MISSING");
  if(!action)addReason(state,"BLOCK","ACTION_MISSING");

  const actorContract=await contractById(env,"component:"+actor)||await resolveRoleContract(env,actor);
  const subjectContractId=String(event.subject_contract_id||"");
  const subjectContractVersion=String(event.subject_contract_version||"");
  const dynAgent=subjectContractId?await dynamicContract(env,subjectContractId,subjectContractVersion):null;
  const dynComponent=subjectContractId?await dynamicComponentContract(env,subjectContractId,subjectContractVersion):null;
  let roleContract=dynAgent||dynComponent||await resolveRoleContract(env,subjectRole);
  const dynamicAgentRole=subjectRole.endsWith(":ephemeral-agent")||subjectRole.endsWith(":reusable-agent");
  const dynamicComponentClaim=subjectContractId.startsWith("branch:")||subjectContractId.startsWith("orchestrator:");
  if(dynamicAgentRole&&!subjectContractId)addReason(state,"BLOCK","DYNAMIC_AGENT_CONTRACT_REQUIRED");
  if(subjectContractId&&!dynAgent&&!dynComponent)addReason(state,"BLOCK","DYNAMIC_SUBJECT_CONTRACT_NOT_FOUND");
  if(dynamicComponentClaim&&!dynComponent)addReason(state,"BLOCK","DYNAMIC_COMPONENT_CONTRACT_NOT_FOUND");

  if(!actorContract)addReason(state,"BLOCK","ACTOR_CONTRACT_MISSING");
  else{
    const allowed=arr(actorContract.allowed_actions_json),forbidden=arr(actorContract.forbidden_actions_json);
    if(forbidden.includes(action))addReason(state,"CRITICAL","ACTOR_ACTION_FORBIDDEN");
    else if(!allows(allowed,action))addReason(state,"BLOCK","ACTOR_ACTION_OUTSIDE_ROLE");
  }

  if(!roleContract)addReason(state,"BLOCK","SUBJECT_ROLE_CONTRACT_MISSING");
  else{
    const allowed=arr(roleContract.allowed_actions_json),forbidden=arr(roleContract.forbidden_actions_json);
    const perms=arr(roleContract.allowed_permissions_json);
    if(forbidden.includes(action))addReason(state,"CRITICAL","SUBJECT_ACTION_FORBIDDEN");
    else if(!allows(allowed,action))addReason(state,"BLOCK","SUBJECT_ACTION_OUTSIDE_ROLE");
    if(!allows(perms,permission))addReason(state,"BLOCK","PERMISSION_OUTSIDE_ROLE");
    if(Number(roleContract.unknown_role||0)===1){
      if(["read","plan"].includes(permission))addReason(state,"WARNING","UNKNOWN_ROLE_LOW_RISK");
      else addReason(state,"BLOCK","UNKNOWN_ROLE_WRITE_FORBIDDEN");
    }
    if(phase==="POST_ACTION"&&action==="FINAL_ARCHITECTURE_DECISION"){
      for(const key of arr(roleContract.required_evidence_json))
        if(!truthyEvidence(evidence,key))addReason(state,"BLOCK","REQUIRED_EVIDENCE_MISSING:"+key);
    }
    if(dynAgent){
      if(String(dynAgent.agent_id)!==subjectRole)addReason(state,"CRITICAL","DYNAMIC_AGENT_IDENTITY_MISMATCH");
      if(String(dynAgent.project_id)!==String(event.project_id||""))addReason(state,"CRITICAL","DYNAMIC_AGENT_PROJECT_SCOPE_MISMATCH");
      if(subjectContractVersion&&String(dynAgent.version)!==subjectContractVersion)addReason(state,"BLOCK","DYNAMIC_AGENT_CONTRACT_VERSION_MISMATCH");
      const allowedCaps=new Set(arr(dynAgent.allowed_capabilities_json));
      const requestedCaps=Array.isArray(event.capabilities)?event.capabilities.map(String):[];
      for(const cap of requestedCaps)if(!allowedCaps.has(cap))addReason(state,"BLOCK","CAPABILITY_OUTSIDE_AGENT_MISSION:"+cap);
      const eventDomain=String((event.context||{}).domain||"");
      if(eventDomain&&String(dynAgent.domain)!==eventDomain)addReason(state,"BLOCK","DOMAIN_OUTSIDE_AGENT_MISSION");
      const eventPackage=String((event.context||{}).package_id||"");
      if(eventPackage&&String(dynAgent.package_id)!==eventPackage)addReason(state,"BLOCK","PACKAGE_OUTSIDE_AGENT_MISSION");
    }
    if(dynComponent){
      if(String(dynComponent.component_id)!==subjectRole)addReason(state,"CRITICAL","DYNAMIC_COMPONENT_IDENTITY_MISMATCH");
      if(String(dynComponent.project_id)!==String(event.project_id||""))addReason(state,"CRITICAL","DYNAMIC_COMPONENT_PROJECT_SCOPE_MISMATCH");
      if(subjectContractVersion&&String(dynComponent.version)!==subjectContractVersion)addReason(state,"BLOCK","DYNAMIC_COMPONENT_CONTRACT_VERSION_MISMATCH");
      const allowedCaps=new Set(arr(dynComponent.allowed_capabilities_json));
      const requestedCaps=Array.isArray(event.capabilities)?event.capabilities.map(String):[];
      for(const cap of requestedCaps)if(!allowedCaps.has(cap))addReason(state,"BLOCK","CAPABILITY_OUTSIDE_COMPONENT_MISSION:"+cap);
      const eventDomain=String((event.context||{}).domain||"");
      if(eventDomain&&String(dynComponent.domain)!==eventDomain)addReason(state,"BLOCK","DOMAIN_OUTSIDE_COMPONENT_MISSION");
      const eventPackage=String((event.context||{}).package_id||"");
      if(eventPackage&&String(dynComponent.package_id)!==eventPackage)addReason(state,"BLOCK","PACKAGE_OUTSIDE_COMPONENT_MISSION");
    }
  }

  if(phase==="PRE_ACTION"&&SENSITIVE.has(permission)&&!truthyEvidence(evidence,"human_approval"))
    addReason(state,"CRITICAL","SENSITIVE_ACTION_WITHOUT_HUMAN_APPROVAL");
  if(phase==="PRE_ACTION"&&["heavy","very-heavy"].includes(String(context.resource_class||""))&&!truthyEvidence(evidence,"storage_preflight"))
    addReason(state,"BLOCK","HEAVY_ACTION_WITHOUT_STORAGE_PREFLIGHT");
  if(truthyEvidence(evidence,"emergency_stop_active"))addReason(state,"CRITICAL","EMERGENCY_STOP_ACTIVE");
  if(actor==="run-controller"&&phase==="PRE_ACTION"&&!truthyEvidence(evidence,"adapter_binding_valid"))
    addReason(state,"BLOCK","ADAPTER_BINDING_NOT_VALIDATED");
  if(actor==="run-controller"&&action==="DISPATCH_TASK"){
    const bindingDigest=String(context.guardian_binding_digest||"");
    const claimedPolicy=String(context.guardian_policy_contract_ref||"");
    if(!bindingDigest)addReason(state,"BLOCK","TASK_GUARDIAN_BINDING_DIGEST_MISSING");
    if(dynAgent&&claimedPolicy&&claimedPolicy!==String(dynAgent.template_contract_id||""))
      addReason(state,"BLOCK","TASK_GUARDIAN_POLICY_CONTRACT_DRIFT");
    if(dynComponent&&claimedPolicy&&claimedPolicy!==String(dynComponent.template_contract_id||""))
      addReason(state,"BLOCK","TASK_GUARDIAN_POLICY_CONTRACT_DRIFT");
    if(!dynAgent&&!dynComponent&&claimedPolicy&&roleContract&&claimedPolicy!==String(roleContract.contract_id||""))
      addReason(state,"BLOCK","TASK_GUARDIAN_STATIC_ROLE_CONTRACT_DRIFT");
  }

  for(const binding of (Array.isArray(event.adapters)?event.adapters:[])){
    if(!binding||!binding.adapter){addReason(state,"BLOCK","ADAPTER_ID_MISSING");continue;}
    const ac=await contractById(env,"adapter:"+String(binding.adapter));
    if(!ac){addReason(state,SENSITIVE.has(permission)?"CRITICAL":"BLOCK","ADAPTER_CONTRACT_MISSING:"+String(binding.adapter));continue;}
    if(!allows(arr(ac.allowed_permissions_json),permission))
      addReason(state,"CRITICAL","ADAPTER_PERMISSION_OUTSIDE_CONTRACT:"+String(binding.adapter));
  }

  if(action==="FINAL_ARCHITECTURE_DECISION"&&phase==="POST_ACTION"){
    for(const key of ["technology_watch_pre","technology_watch_final","reuse_memory","architecture_memory",
      "architecture_portfolio","branch_foundry","agent_foundry","capability_foundry","constraint_policy"])
      if(!truthyEvidence(evidence,key))addReason(state,"BLOCK","ARCHITECTURE_COUNCIL_EVIDENCE_MISSING:"+key);
  }

  const verdict=verdictFromSeverity(state.severity);
  return {verdict,severity:state.severity,reason_codes:[...new Set(state.reasons)],
          actor_contract_id:actorContract?actorContract.contract_id:null,
          subject_contract_id:roleContract?roleContract.contract_id:null};
}

async function actionLease(event,env,current){
  const phase=String(event.phase||"");
  const actionId=String(event.action_id||"");
  const permission=String(event.permission||"read");
  const isDispatch=String(event.actor||"")==="run-controller"&&String(event.action||"")==="DISPATCH_TASK";
  const bindingDigest=String((event.context||{}).guardian_binding_digest||"");
  const subjectContractId=String(event.subject_contract_id||"");
  const subjectContractVersion=String(event.subject_contract_version||"");
  if(!actionId){
    return {severity:"BLOCK",reason_codes:["ACTION_ID_REQUIRED"]};
  }
  if(phase==="PRE_ACTION"){
    const existing=await env.DB.prepare("SELECT status FROM action_leases WHERE action_id=?1").bind(actionId).first();
    if(existing)return {severity:"BLOCK",reason_codes:["ACTION_ID_REUSED"]};
    if(!["PASS","WARNING"].includes(current.verdict))
      return {severity:"INFO",reason_codes:[]};
    const deadline=Math.max(30,Math.min(3600,Number((event.context||{}).deadline_seconds||300)));
    await env.DB.prepare(
      `INSERT INTO action_leases(action_id,pre_event_id,actor,subject_role,action,permission,project_id,run_id,opened_at,deadline_at,status,last_verdict)
       VALUES(?1,?2,?3,?4,?5,?6,?7,?8,datetime('now'),datetime('now',?9),'OPEN',?10)`
    ).bind(actionId,String(event.event_id),String(event.actor||""),String(event.subject_role||""),String(event.action||""),
           permission,event.project_id?String(event.project_id):null,event.run_id?String(event.run_id):null,
           "+"+deadline+" seconds",current.verdict).run();
    if(isDispatch&&["PASS","WARNING"].includes(current.verdict)){
      await env.DB.prepare(
        `INSERT OR REPLACE INTO task_contract_leases(action_id,subject_role,subject_contract_id,subject_contract_version,binding_digest,opened_at,closed_at,status)
         VALUES(?1,?2,?3,?4,?5,datetime('now'),NULL,'OPEN')`
      ).bind(actionId,String(event.subject_role||""),subjectContractId||null,subjectContractVersion||null,bindingDigest).run();
    }
    return {severity:"INFO",reason_codes:[]};
  }
  if(phase==="POST_ACTION"){
    const row=await env.DB.prepare("SELECT * FROM action_leases WHERE action_id=?1").bind(actionId).first();
    if(!row)return {severity:"BLOCK",reason_codes:["POST_WITHOUT_PRE_ACTION"]};
    if(row.status!=="OPEN")return {severity:"BLOCK",reason_codes:["ACTION_LEASE_NOT_OPEN:"+String(row.status)]};
    const mismatch=
      String(row.actor)!==String(event.actor||"")||
      String(row.subject_role)!==String(event.subject_role||"")||
      String(row.permission)!==permission||
      String(row.project_id||"")!==String(event.project_id||"")||
      String(row.run_id||"")!==String(event.run_id||"");
    await env.DB.prepare(
      "UPDATE action_leases SET post_event_id=?2,closed_at=datetime('now'),status='CLOSED',last_verdict=?3 WHERE action_id=?1"
    ).bind(actionId,String(event.event_id),current.verdict).run();
    if(isDispatch){
      const lease=await env.DB.prepare("SELECT * FROM task_contract_leases WHERE action_id=?1").bind(actionId).first();
      if(!lease)return {severity:"CRITICAL",reason_codes:["TASK_CONTRACT_LEASE_MISSING"]};
      const contractMismatch=
        String(lease.subject_role||"")!==String(event.subject_role||"")||
        String(lease.subject_contract_id||"")!==subjectContractId||
        String(lease.subject_contract_version||"")!==subjectContractVersion||
        String(lease.binding_digest||"")!==bindingDigest;
      await env.DB.prepare(
        "UPDATE task_contract_leases SET closed_at=datetime('now'),status=?2 WHERE action_id=?1"
      ).bind(actionId,contractMismatch?"MISMATCH":"CLOSED").run();
      if(contractMismatch)return {severity:"CRITICAL",reason_codes:["TASK_CONTRACT_IDENTITY_DRIFT"]};
    }
    return mismatch?{severity:"CRITICAL",reason_codes:["ACTION_IDENTITY_DRIFT"]}:{severity:"INFO",reason_codes:[]};
  }
  return {severity:"INFO",reason_codes:[]};
}

function remediationPlan(reasons,severity,payload){
  const rs=(reasons||[]).map(String);
  let requiredAction="RELOAD_CONTRACT_AND_REPLAN";
  if(rs.some(x=>x.includes("BINDING")||x.includes("TASK_CONTRACT")))requiredAction="RESTORE_AUTHORITATIVE_TASK_BINDING";
  else if(rs.some(x=>x.startsWith("ADAPTER_")))requiredAction="REBIND_REGISTERED_ADAPTER";
  else if(rs.some(x=>x.includes("COVERAGE")||x.includes("GUARDIAN_HOOK")))requiredAction="RESTORE_GUARDIAN_HOOK";
  else if(rs.some(x=>x.includes("POST_ACTION_MISSING")))requiredAction="RECONCILE_ACTION_STATE";
  else if(rs.some(x=>x.includes("HUMAN_APPROVAL")))requiredAction="REQUEST_HUMAN_APPROVAL";
  else if(rs.some(x=>x.includes("EMERGENCY_STOP")))requiredAction="HALT_AND_ESCALATE";
  else if(rs.some(x=>x.includes("PRODUCTION_ANOMALY")))requiredAction="INVESTIGATE_REPLAN_PATCH_AND_VERIFY_PRODUCTION_ANOMALY";
  else if(rs.some(x=>x.includes("PROJECT_SCOPE")||x.includes("CAPABILITY_OUTSIDE")||x.includes("DOMAIN_OUTSIDE")||x.includes("PACKAGE_OUTSIDE")))requiredAction="REPLAN_WITHIN_AUTHORIZED_SCOPE";
  const p=payload&&typeof payload==="object"?payload:{};
  const actor=String(p.actor||p.component_id||"central-orchestrator");
  const subject=String(p.subject_role||p.component_id||actor);
  const adapterRelated=rs.some(x=>x.startsWith("ADAPTER_")||x.includes("BINDING"));
  const target=adapterRelated?actor:subject;
  return {
    target_actor:target,target_role:target,
    project_id:p.project_id?String(p.project_id):null,
    run_id:p.run_id?String(p.run_id):null,
    required_action:requiredAction,
    instructions:[
      "RELOAD_AUTHORITATIVE_ROLE_CONTRACT",
      requiredAction,
      "RETRY_ONLY_WITHIN_DECLARED_PROJECT_DOMAIN_CAPABILITIES_AND_PERMISSIONS",
      severity==="CRITICAL"?"DO_NOT_RESUME_UNTIL_GUARDIAN_ACCEPTS_CORRECTED_ACTION":"RESUBMIT_CORRECTED_ACTION_TO_GUARDIAN"
    ]
  };
}

async function createRemediation(env,{alertId,eventId,severity,reasons,payload}){
  if(payload&&payload.suppress_remediation===true)return null;
  const plan=remediationPlan(reasons,severity,payload);
  const directiveId="remed-"+String(alertId);
  await env.DB.prepare(
    `INSERT OR IGNORE INTO remediation_directives
      (directive_id,source_alert_id,source_event_id,target_actor,target_role,project_id,run_id,severity,required_action,rule_codes_json,instructions_json,status,attempt_count,max_attempts,created_at)
      VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,'OPEN',0,3,datetime('now'))`
  ).bind(directiveId,String(alertId),String(eventId),plan.target_actor,plan.target_role,
         plan.project_id,plan.run_id,String(severity),plan.required_action,
         JSON.stringify(reasons||[]),JSON.stringify(plan.instructions)).run();
  if(["BLOCK","CRITICAL"].includes(String(severity))){
    const holdKey=[plan.target_actor,plan.project_id||"*"].join("|");
    await env.DB.prepare(
      `INSERT OR IGNORE INTO remediation_holds
        (hold_key,directive_id,target_actor,target_role,project_id,run_id,severity,active,created_at)
        VALUES(?1,?2,?3,?4,?5,?6,?7,1,datetime('now'))`
    ).bind(holdKey,directiveId,plan.target_actor,plan.target_role,plan.project_id,plan.run_id,String(severity)).run();
  }
  return directiveId;
}

async function activeRemediationHold(event,env){
  const actor=String(event.actor||""),subject=String(event.subject_role||""),project=String(event.project_id||"");
  return env.DB.prepare(
    `SELECT * FROM remediation_holds
      WHERE active=1 AND (target_actor=?1 OR target_role=?2)
        AND (project_id IS NULL OR project_id='' OR project_id=?3)
      ORDER BY created_at ASC LIMIT 1`
  ).bind(actor,subject,project).first();
}

async function applyRemediationProgress(event,env,evaluation,hold){
  const rid=String((event.context||{}).remediation_directive_id||"");
  if(!rid||!hold||rid!==String(hold.directive_id||"")||String(event.phase||"")!=="PRE_ACTION")return {applied:false,escalated:false};
  if(["PASS","WARNING"].includes(String(evaluation.verdict))){
    await env.DB.prepare(
      "UPDATE remediation_directives SET status='APPLIED',applied_at=datetime('now'),resolution_evidence_json=?2 WHERE directive_id=?1"
    ).bind(rid,stable({event_id:event.event_id,action_id:event.action_id,verdict:evaluation.verdict})).run();
    await env.DB.prepare("UPDATE remediation_holds SET active=0,cleared_at=datetime('now') WHERE directive_id=?1").bind(rid).run();
    return {applied:true,escalated:false};
  }
  const row=await env.DB.prepare("SELECT attempt_count,max_attempts FROM remediation_directives WHERE directive_id=?1").bind(rid).first();
  const attempt=Number((row&&row.attempt_count)||0)+1,max=Number((row&&row.max_attempts)||3);
  await env.DB.prepare("UPDATE remediation_directives SET attempt_count=?2 WHERE directive_id=?1").bind(rid,attempt).run();
  if(attempt>=max){
    await env.DB.prepare("UPDATE remediation_directives SET status='ESCALATED' WHERE directive_id=?1").bind(rid).run();
    await createAlert(env,{
      alertId:"remediation-escalated-"+rid,eventId:String(event.event_id||rid),severity:"CRITICAL",
      summary:"Guardian remediation failed repeatedly: "+rid,
      reasons:["REMEDIATION_MAX_ATTEMPTS_EXCEEDED"],
      payload:{actor:event.actor,subject_role:event.subject_role,project_id:event.project_id,run_id:event.run_id,suppress_remediation:true}
    });
    return {applied:false,escalated:true};
  }
  return {applied:false,escalated:false};
}

async function createAlert(env,{alertId,eventId,severity,summary,reasons,payload}){
  await env.DB.prepare(
    `INSERT OR REPLACE INTO guardian_alerts
      (alert_id,event_id,created_at,severity,status,summary,reason_codes_json,payload_json)
      VALUES(?1,?2,datetime('now'),?3,'OPEN',?4,?5,?6)`
  ).bind(alertId,eventId,severity,summary,JSON.stringify(reasons||[]),stable(payload||{})).run();
  return createRemediation(env,{alertId,eventId,severity,reasons,payload});
}

async function storeEvent(env,event,evaluation){
  const payload=stable(event);
  await env.DB.prepare(
    `INSERT OR REPLACE INTO governance_events
      (event_id,received_at,phase,actor,subject_role,action,task_kind,permission,project_id,run_id,verdict,severity,contract_id,reason_codes_json,payload_json)
      VALUES(?1,datetime('now'),?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14)`
  ).bind(String(event.event_id),String(event.phase||""),String(event.actor||""),String(event.subject_role||""),
         String(event.action||""),event.task_kind?String(event.task_kind):null,event.permission?String(event.permission):null,
         event.project_id?String(event.project_id):null,event.run_id?String(event.run_id):null,evaluation.verdict,
         evaluation.severity,evaluation.subject_contract_id,JSON.stringify(evaluation.reason_codes),payload).run();
  let directiveId=null;
  if(evaluation.severity!=="INFO"){
    directiveId=await createAlert(env,{
      alertId:"alert-"+String(event.event_id),eventId:String(event.event_id),severity:evaluation.severity,
      summary:evaluation.severity+" "+String(event.actor||"")+" -> "+String(event.subject_role||"")+" / "+String(event.action||""),
      reasons:evaluation.reason_codes,payload:event
    });
  }
  return directiveId;
}

async function registerDynamicContract(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let x;try{x=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(!x||x.schema!=="chacha.dev/dynamic-agent-role-contract/v1")return json({error:"dynamic_contract_schema_invalid"},400);
  if(String(x.issued_by||"")!=="agent-foundry")return json({error:"dynamic_contract_issuer_invalid"},409);
  if(String(x.template_contract_id||"")!=="role:__agent__")return json({error:"dynamic_contract_template_invalid"},409);
  const contractId=String(x.contract_id||""),version=String(x.version||""),agentId=String(x.agent_id||"");
  const projectId=String(x.project_id||""),domain=String(x.domain||""),packageId=String(x.package_id||"");
  if(!contractId.startsWith("agent:")||!version||!agentId||!projectId||!domain||!packageId)
    return json({error:"dynamic_contract_identity_incomplete"},400);
  if(contractId!=="agent:"+agentId)return json({error:"dynamic_contract_id_agent_mismatch"},409);

  const template=await contractById(env,"role:__agent__");
  if(!template)return json({error:"dynamic_contract_template_missing"},503);
  const allowedActions=Array.isArray(x.allowed_actions)?x.allowed_actions.map(String):[];
  const forbiddenActions=Array.isArray(x.forbidden_actions)?x.forbidden_actions.map(String):[];
  const permissions=Array.isArray(x.allowed_permissions)?x.allowed_permissions.map(String):[];
  const capabilities=Array.isArray(x.allowed_capabilities)?x.allowed_capabilities.map(String):[];
  const tools=Array.isArray(x.allowed_tools)?x.allowed_tools:[];
  const templateActions=arr(template.allowed_actions_json),templateForbidden=arr(template.forbidden_actions_json),templatePerms=arr(template.allowed_permissions_json);
  if(allowedActions.some(v=>!allows(templateActions,v)))return json({error:"dynamic_contract_action_escalation"},409);
  if(permissions.some(v=>!allows(templatePerms,v)))return json({error:"dynamic_contract_permission_escalation"},409);
  if(templateForbidden.some(v=>!forbiddenActions.includes(v)))return json({error:"dynamic_contract_forbidden_rule_removed"},409);
  if(permissions.some(v=>["production-deploy","production-data-write","secret-change","destructive-operation"].includes(v)))
    return json({error:"dynamic_contract_production_permission_forbidden"},409);
  if(x.production_permissions_allowed!==false)return json({error:"dynamic_contract_production_boundary_invalid"},409);

  const digestInput={...x};delete digestInput.version;delete digestInput.contract_digest;
  const actualDigest=await sha256Hex(stable(digestInput));
  if(String(x.contract_digest||"")!==actualDigest||version!=="v1-"+actualDigest.slice(0,12))
    return json({error:"dynamic_contract_digest_invalid"},409);

  await env.DB.prepare(
    "UPDATE dynamic_role_contracts SET status='RETIRED',retired_at=datetime('now') WHERE contract_id=?1 AND status='ACTIVE' AND version<>?2"
  ).bind(contractId,version).run();
  await env.DB.prepare(
    `INSERT INTO dynamic_role_contracts
      (contract_id,version,status,template_contract_id,agent_id,project_id,domain,package_id,allowed_actions_json,forbidden_actions_json,allowed_permissions_json,allowed_capabilities_json,allowed_tools_json,source_digest,created_at,retired_at)
      VALUES(?1,?2,'ACTIVE',?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,datetime('now'),NULL)
      ON CONFLICT(contract_id,version) DO UPDATE SET status='ACTIVE',retired_at=NULL,source_digest=excluded.source_digest`
  ).bind(contractId,version,String(x.template_contract_id),agentId,projectId,domain,packageId,
         JSON.stringify(allowedActions),JSON.stringify(forbiddenActions),JSON.stringify(permissions),
         JSON.stringify(capabilities),JSON.stringify(tools),actualDigest).run();
  return json({
    schema:"chacha.dev/dynamic-agent-role-contract-registration/v1",
    status:"PASS",contract_id:contractId,version,agent_id:agentId,project_id:projectId,
    immutable_template:"role:__agent__",privilege_escalation_allowed:false,registered_at:new Date().toISOString()
  });
}

async function registerDynamicComponentContract(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let x;try{x=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(!x||x.schema!=="chacha.dev/dynamic-component-role-contract/v1")return json({error:"dynamic_component_contract_schema_invalid"},400);
  const kind=String(x.component_kind||"");
  if(!["branch","orchestrator"].includes(kind))return json({error:"dynamic_component_kind_invalid"},409);
  const expectedTemplate=kind==="branch"?"role:__branch__":"role:__dynamic-orchestrator__";
  if(String(x.template_contract_id||"")!==expectedTemplate)return json({error:"dynamic_component_template_invalid"},409);
  const issuer=String(x.issued_by||"");
  if(!["branch-foundry","capability-foundry"].includes(issuer))return json({error:"dynamic_component_issuer_invalid"},409);
  const contractId=String(x.contract_id||""),version=String(x.version||""),componentId=String(x.component_id||"");
  const projectId=String(x.project_id||""),domain=String(x.domain||""),packageId=String(x.package_id||"");
  const prefix=kind+":";
  if(!contractId.startsWith(prefix)||!version||!componentId||!projectId||!domain||!packageId)
    return json({error:"dynamic_component_identity_incomplete"},400);
  if(contractId!==prefix+componentId)return json({error:"dynamic_component_id_mismatch"},409);
  const template=await contractById(env,expectedTemplate);
  if(!template)return json({error:"dynamic_component_template_missing"},503);
  const allowedActions=Array.isArray(x.allowed_actions)?x.allowed_actions.map(String):[];
  const forbiddenActions=Array.isArray(x.forbidden_actions)?x.forbidden_actions.map(String):[];
  const permissions=Array.isArray(x.allowed_permissions)?x.allowed_permissions.map(String):[];
  const capabilities=Array.isArray(x.allowed_capabilities)?x.allowed_capabilities.map(String):[];
  const templateActions=arr(template.allowed_actions_json),templateForbidden=arr(template.forbidden_actions_json),templatePerms=arr(template.allowed_permissions_json);
  if(allowedActions.some(v=>!allows(templateActions,v)))return json({error:"dynamic_component_action_escalation"},409);
  if(permissions.some(v=>!allows(templatePerms,v)))return json({error:"dynamic_component_permission_escalation"},409);
  if(templateForbidden.some(v=>!forbiddenActions.includes(v)))return json({error:"dynamic_component_forbidden_rule_removed"},409);
  if(permissions.some(v=>["production-deploy","production-data-write","secret-change","destructive-operation"].includes(v)))
    return json({error:"dynamic_component_production_permission_forbidden"},409);
  if(x.production_permissions_allowed!==false)return json({error:"dynamic_component_production_boundary_invalid"},409);
  const digestInput={...x};delete digestInput.version;delete digestInput.contract_digest;
  const actualDigest=await sha256Hex(stable(digestInput));
  if(String(x.contract_digest||"")!==actualDigest||version!=="v1-"+actualDigest.slice(0,12))
    return json({error:"dynamic_component_contract_digest_invalid"},409);
  await env.DB.prepare(
    "UPDATE dynamic_component_contracts SET status='RETIRED',retired_at=datetime('now') WHERE contract_id=?1 AND status='ACTIVE' AND version<>?2"
  ).bind(contractId,version).run();
  await env.DB.prepare(
    `INSERT INTO dynamic_component_contracts
      (contract_id,version,status,template_contract_id,component_kind,component_id,project_id,domain,package_id,allowed_actions_json,forbidden_actions_json,allowed_permissions_json,allowed_capabilities_json,source_digest,created_at,retired_at)
      VALUES(?1,?2,'ACTIVE',?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,datetime('now'),NULL)
      ON CONFLICT(contract_id,version) DO UPDATE SET status='ACTIVE',retired_at=NULL,source_digest=excluded.source_digest`
  ).bind(contractId,version,expectedTemplate,kind,componentId,projectId,domain,packageId,
         JSON.stringify(allowedActions),JSON.stringify(forbiddenActions),JSON.stringify(permissions),
         JSON.stringify(capabilities),actualDigest).run();
  return json({
    schema:"chacha.dev/dynamic-component-role-contract-registration/v1",
    status:"PASS",contract_id:contractId,version,component_kind:kind,component_id:componentId,project_id:projectId,
    immutable_template:expectedTemplate,privilege_escalation_allowed:false,registered_at:new Date().toISOString()
  });
}

async function reportLearningAnomaly(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let x;try{x=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(!x||x.schema!=="chacha.dev/production-learning-anomaly/v1")return json({error:"anomaly_schema_invalid"},400);
  const severity=String(x.severity||"").toLowerCase();
  if(!["high","critical"].includes(severity))return json({error:"anomaly_severity_not_actionable"},409);
  const deltaId=String(x.delta_id||"");
  const projectId=String(x.project_id||"");
  const sourceId=String(x.source_id||"");
  const deploymentId=String(x.deployment_id||"");
  if(!deltaId||!projectId||!sourceId||!deploymentId)return json({error:"anomaly_identity_incomplete"},400);
  const guardianSeverity=severity==="critical"?"CRITICAL":"BLOCK";
  const alertId="learning-anomaly-"+deltaId;
  const eventId="learning-anomaly-event-"+deltaId;
  const payload={
    actor:"runtime-monitor",subject_role:"central-orchestrator",
    project_id:projectId,run_id:"production-learning:"+deltaId,
    action:"REPORT_PRODUCTION_ANOMALY",source_id:sourceId,deployment_id:deploymentId,
    delta_id:deltaId,anomaly:x.anomaly||{},evidence_refs:x.evidence_refs||[]
  };
  const directiveId=await createAlert(env,{
    alertId,eventId,severity:guardianSeverity,
    summary:guardianSeverity+" production anomaly "+projectId+" / "+sourceId,
    reasons:["PRODUCTION_ANOMALY_"+severity.toUpperCase()],
    payload
  });
  return json({
    schema:"chacha.dev/production-learning-anomaly-guardian-ack/v1",
    status:"DIRECTIVE_ISSUED",alert_id:alertId,directive_id:directiveId,
    project_id:projectId,source_id:sourceId,deployment_id:deploymentId,
    severity:guardianSeverity,guardian:"external-worker",
    production_mutation_performed:false,checked_at:new Date().toISOString()
  },202);
}

async function check(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let event;try{event=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(!event||typeof event!=="object")return json({error:"event_invalid"},400);
  const hold=await activeRemediationHold(event,env);
  const claimedDirective=String((event.context||{}).remediation_directive_id||"");
  let evaluation=await evaluate(event,env);
  if(hold&&claimedDirective!==String(hold.directive_id||"")){
    evaluation=mergeEval(evaluation,{
      severity:String(hold.severity)==="CRITICAL"?"CRITICAL":"BLOCK",
      reason_codes:["REMEDIATION_REQUIRED:"+String(hold.directive_id)]
    });
  }
  evaluation=mergeEval(evaluation,await actionLease(event,env,evaluation));
  const progress=await applyRemediationProgress(event,env,evaluation,hold);
  if(progress.escalated){
    evaluation=mergeEval(evaluation,{severity:"CRITICAL",reason_codes:["REMEDIATION_MAX_ATTEMPTS_EXCEEDED"]});
  }
  const createdDirectiveId=await storeEvent(env,event,evaluation);
  return json({
    schema:"chacha.dev/guardian-verdict/v3",event_id:String(event.event_id||""),action_id:String(event.action_id||""),
    verdict:evaluation.verdict,severity:evaluation.severity,reason_codes:evaluation.reason_codes,
    actor_contract_id:evaluation.actor_contract_id,subject_contract_id:evaluation.subject_contract_id,
    remediation_required:Boolean(hold||createdDirectiveId),
    remediation_directive_id:hold?String(hold.directive_id):createdDirectiveId,
    remediation_applied:progress.applied===true,
    remediation_escalated:progress.escalated===true,
    stop_recommended:evaluation.severity==="CRITICAL",guardian:"external-worker",
    action_lease_protocol:true,corrective_enforcement:true,checked_at:new Date().toISOString()
  },["PASS","WARNING"].includes(evaluation.verdict)?200:409);
}

async function coverage(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let payload;try{payload=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  if(payload.schema!=="chacha.dev/guardian-coverage-heartbeat/v1")return json({error:"coverage_schema_invalid"},400);
  const snapshotId=String(payload.snapshot_id||"");
  if(!snapshotId)return json({error:"snapshot_id_required"},400);
  const components=Array.isArray(payload.components)?payload.components:[];
  const got=new Map(components.filter(x=>x&&x.component_id).map(x=>[String(x.component_id),x]));
  const expected=(await env.DB.prepare("SELECT * FROM expected_components ORDER BY component_id").all()).results||[];
  const missing=[],inactive=[],unknown=[];
  let severity="INFO";
  for(const e of expected){
    const c=got.get(String(e.component_id));
    if(!c){
      missing.push(String(e.component_id));
      if(order(String(e.criticality))>order(severity))severity=String(e.criticality);
      await createAlert(env,{alertId:"coverage-missing-"+String(e.component_id),eventId:"coverage:"+snapshotId,
        severity:String(e.criticality),summary:"Guardian coverage missing: "+String(e.component_id),
        reasons:["EXPECTED_COMPONENT_MISSING"],payload:{snapshot_id:snapshotId,component_id:e.component_id}});
      continue;
    }
    const active=c.hook_active===true;
    await env.DB.prepare(
      `INSERT INTO coverage_heartbeats(component_id,snapshot_id,last_seen,hook_active,details_json)
       VALUES(?1,?2,datetime('now'),?3,?4)
       ON CONFLICT(component_id) DO UPDATE SET snapshot_id=excluded.snapshot_id,last_seen=datetime('now'),
       hook_active=excluded.hook_active,details_json=excluded.details_json`
    ).bind(String(e.component_id),snapshotId,active?1:0,stable(c)).run();
    if(!active){
      inactive.push(String(e.component_id));
      if(order(String(e.criticality))>order(severity))severity=String(e.criticality);
      await createAlert(env,{alertId:"coverage-inactive-"+String(e.component_id),eventId:"coverage:"+snapshotId,
        severity:String(e.criticality),summary:"Guardian hook inactive: "+String(e.component_id),
        reasons:["GUARDIAN_HOOK_INACTIVE"],payload:c});
    }
  }
  for(const id of got.keys())if(!expected.some(e=>String(e.component_id)===id))unknown.push(id);
  if(unknown.length&&order("WARNING")>order(severity))severity="WARNING";
  const verdict=verdictFromSeverity(severity);
  return json({schema:"chacha.dev/guardian-coverage-verdict/v1",snapshot_id:snapshotId,verdict,severity,
    expected_count:expected.length,reported_count:components.length,missing,inactive,unknown,
    coverage_ratio:expected.length?Number(((expected.length-missing.length-inactive.length)/expected.length).toFixed(4)):1,
    checked_at:new Date().toISOString()},["PASS","WARNING"].includes(verdict)?200:409);
}

async function remediations(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),status=String(u.searchParams.get("status")||"OPEN").toUpperCase();
  const limit=Math.max(1,Math.min(100,Number(u.searchParams.get("limit")||50)));
  const rows=await env.DB.prepare(
    `SELECT directive_id,source_alert_id,source_event_id,target_actor,target_role,project_id,run_id,severity,required_action,
            rule_codes_json,instructions_json,status,attempt_count,max_attempts,created_at,delivered_at,applied_at,resolution_evidence_json
       FROM remediation_directives WHERE status=?1 ORDER BY created_at ASC LIMIT ?2`
  ).bind(status,limit).all();
  return json({schema:"chacha.dev/guardian-remediation-batch/v1",items:(rows.results||[]).map(r=>({
    directive_id:r.directive_id,source_alert_id:r.source_alert_id,source_event_id:r.source_event_id,
    target_actor:r.target_actor,target_role:r.target_role,project_id:r.project_id,run_id:r.run_id,
    severity:r.severity,required_action:r.required_action,rule_codes:JSON.parse(r.rule_codes_json||"[]"),
    instructions:JSON.parse(r.instructions_json||"[]"),status:r.status,attempt_count:r.attempt_count,max_attempts:r.max_attempts,
    created_at:r.created_at,delivered_at:r.delivered_at,applied_at:r.applied_at,
    resolution_evidence:r.resolution_evidence_json?JSON.parse(r.resolution_evidence_json):null
  }))});
}

async function markRemediationsDelivered(req,env){
  const body=await req.text();const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let payload;try{payload=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  const ids=Array.isArray(payload.directive_ids)?payload.directive_ids.map(String).slice(0,100):[];
  if(!ids.length)return json({error:"directive_ids_required"},400);
  let count=0;
  for(const id of ids){
    const r=await env.DB.prepare(
      "UPDATE remediation_directives SET status='DELIVERED',delivered_at=datetime('now') WHERE directive_id=?1 AND status='OPEN'"
    ).bind(id).run();
    count+=r.meta.changes||0;
  }
  return json({schema:"chacha.dev/guardian-remediation-delivery/v1",status:"DELIVERED",count});
}

async function alerts(req,env){
  const auth=await requireCentral(req,env);if(!auth.ok)return auth.response;
  const u=new URL(req.url),status=String(u.searchParams.get("status")||"OPEN").toUpperCase();
  const limit=Math.max(1,Math.min(100,Number(u.searchParams.get("limit")||25)));
  const rows=await env.DB.prepare(
    "SELECT alert_id,event_id,created_at,severity,status,summary,reason_codes_json,payload_json FROM guardian_alerts WHERE status=?1 ORDER BY created_at DESC LIMIT ?2"
  ).bind(status,limit).all();
  return json({schema:"chacha.dev/guardian-alert-batch/v1",items:(rows.results||[]).map(r=>({
    alert_id:r.alert_id,event_id:r.event_id,created_at:r.created_at,severity:r.severity,status:r.status,
    summary:r.summary,reason_codes:JSON.parse(r.reason_codes_json||"[]"),event:JSON.parse(r.payload_json||"{}")
  }))});
}
async function ackAlerts(req,env){
  const body=await req.text();const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  let payload;try{payload=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
  const ids=Array.isArray(payload.alert_ids)?payload.alert_ids.map(String).slice(0,100):[];
  if(!ids.length)return json({error:"alert_ids_required"},400);
  let count=0;
  for(const id of ids){
    const r=await env.DB.prepare("UPDATE guardian_alerts SET status='ACKED' WHERE alert_id=?1 AND status='OPEN'").bind(id).run();
    count+=r.meta.changes||0;
  }
  return json({schema:"chacha.dev/guardian-alert-ack/v1",status:"ACKED",count});
}

async function sweep(env){
  let expiredCount=0, staleCoverageCount=0;
  const expired=(await env.DB.prepare(
    "SELECT * FROM action_leases WHERE status='OPEN' AND deadline_at < datetime('now') LIMIT 100"
  ).all()).results||[];
  for(const row of expired){
    expiredCount++;
    const severity=SENSITIVE.has(String(row.permission||""))?"CRITICAL":"BLOCK";
    await env.DB.prepare("UPDATE action_leases SET status='EXPIRED',last_verdict=?2 WHERE action_id=?1").bind(row.action_id,severity).run();
    await createAlert(env,{alertId:"lease-expired-"+String(row.action_id),eventId:String(row.pre_event_id),severity,
      summary:"Guardian action lease expired without POST: "+String(row.actor)+" / "+String(row.action),
      reasons:["POST_ACTION_MISSING"],payload:row});
  }
  const stale=(await env.DB.prepare(
    `SELECT e.component_id,e.criticality,h.last_seen,h.hook_active
     FROM expected_components e LEFT JOIN coverage_heartbeats h ON h.component_id=e.component_id
     WHERE h.component_id IS NULL OR h.hook_active=0 OR h.last_seen < datetime('now','-180 seconds') LIMIT 100`
  ).all()).results||[];
  for(const row of stale){
    staleCoverageCount++;
    await createAlert(env,{alertId:"coverage-stale-"+String(row.component_id),eventId:"coverage-sweep",
      severity:String(row.criticality),summary:"Guardian coverage stale: "+String(row.component_id),
      reasons:["COVERAGE_HEARTBEAT_STALE"],payload:row});
  }
  return {expired_action_leases:expiredCount,stale_coverage_components:staleCoverageCount};
}

async function watchdogSweep(req,env){
  const body=await req.text();
  const auth=await requireCentral(req,env,body);if(!auth.ok)return auth.response;
  const result=await sweep(env);
  return json({
    schema:"chacha.dev/guardian-watchdog-sweep/v1",
    status:"PASS",
    external_guardian:true,
    scheduled_watchdog_remains_enabled:true,
    ...result,
    swept_at:new Date().toISOString()
  });
}

export default {
  async fetch(req,env){
    const u=new URL(req.url);
    if(req.method==="GET"&&u.pathname==="/healthz")return json({
      status:"ok",service:"chacha-dev-guardian",external_governance_plane:true,
      runtime_contract_mutation_api:false,dynamic_instance_contract_registration:true,
      dynamic_component_contract_registration:true,dynamic_contract_policy_escalation_allowed:false,
      dynamic_component_policy_escalation_allowed:false,tunnel_required:false,action_lease_protocol:true,
      task_contract_binding_protocol:true,task_contract_identity_lease:true,coverage_watch:true,
      authenticated_watchdog_sweep:true,scheduled_watchdog:true,
      corrective_enforcement:true,remediation_holds:true,remediation_retry_limit:3,
      production_learning_anomaly_bridge:true,production_anomaly_direct_mutation:false
    });
    if(req.method==="POST"&&u.pathname==="/v1/check")return check(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/learning-anomalies/report")return reportLearningAnomaly(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/dynamic-contracts/register")return registerDynamicContract(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/dynamic-components/register")return registerDynamicComponentContract(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/coverage")return coverage(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/watchdog/sweep")return watchdogSweep(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/remediations")return remediations(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/remediations/delivered")return markRemediationsDelivered(req,env);
    if(req.method==="GET"&&u.pathname==="/v1/alerts")return alerts(req,env);
    if(req.method==="POST"&&u.pathname==="/v1/alerts/ack")return ackAlerts(req,env);
    return json({error:"not_found"},404);
  },
  async scheduled(controller,env,ctx){ctx.waitUntil(sweep(env));}
};
