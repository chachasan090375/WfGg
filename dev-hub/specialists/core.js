const enc=new TextEncoder();

function json(x,status=200){return new Response(JSON.stringify(x),{status,headers:{"content-type":"application/json; charset=utf-8"}});}
function b64bytes(s){const b=atob(String(s||""));return Uint8Array.from(b,c=>c.charCodeAt(0));}
function b64urlbytes(s){s=String(s||"").replace(/-/g,"+").replace(/_/g,"/");while(s.length%4)s+="=";return b64bytes(s);}
function stable(v){
  if(v===null||typeof v!=="object")return JSON.stringify(v);
  if(Array.isArray(v))return "["+v.map(stable).join(",")+"]";
  return "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+stable(v[k])).join(",")+"}";
}
async function sha256Hex(s){
  const d=await crypto.subtle.digest("SHA-256",enc.encode(String(s)));
  return [...new Uint8Array(d)].map(x=>x.toString(16).padStart(2,"0")).join("");
}
function requestMessage(req,ts,body=""){
  const u=new URL(req.url);return ts+"\n"+req.method.toUpperCase()+"\n"+u.pathname+(u.search||"")+"\n"+body;
}
async function verifyEd25519(spki,sig,msg){
  try{
    const key=await crypto.subtle.importKey("spki",b64bytes(spki),{name:"Ed25519"},false,["verify"]);
    return await crypto.subtle.verify({name:"Ed25519"},key,b64urlbytes(sig),enc.encode(msg));
  }catch{return false;}
}
async function requireSigned(req,env,table,body="",projectId=null){
  const keyId=req.headers.get("x-chacha-key-id")||"",ts=req.headers.get("x-chacha-timestamp")||"",sig=req.headers.get("x-chacha-signature")||"";
  const millis=Date.parse(ts);
  if(!keyId||!sig||!Number.isFinite(millis)||Math.abs(Date.now()-millis)>120000)return {ok:false,response:json({error:"authority_auth_invalid"},401)};
  const sql=projectId
    ?`SELECT project_id,public_key_spki_b64 FROM ${table} WHERE key_id=?1 AND status='ACTIVE'`
    :`SELECT public_key_spki_b64 FROM ${table} WHERE key_id=?1 AND status='ACTIVE'`;
  const row=await env.DB.prepare(sql).bind(keyId).first();
  if(!row)return {ok:false,response:json({error:"authority_identity_unknown"},403)};
  if(projectId&&String(row.project_id||"")!==String(projectId))return {ok:false,response:json({error:"authority_identity_project_mismatch"},403)};
  const ok=await verifyEd25519(row.public_key_spki_b64,sig,requestMessage(req,ts,body));
  return ok?{ok:true,keyId}:{ok:false,response:json({error:"authority_signature_invalid"},403)};
}
function privacyOk(e){
  const p=e&&e.privacy&&typeof e.privacy==="object"?e.privacy:{};
  return p.raw_user_content===false&&p.credentials===false&&p.secrets===false&&e.direct_mutation===false;
}
function severityRank(s){return ({INFO:0,WARNING:1,BLOCK:2,CRITICAL:3})[String(s||"INFO")]??0;}
function verdictFor(config,events,implementationVerified){
  if(!implementationVerified)return {verdict:"REVISE",hard:["IMPLEMENTATION_NOT_VERIFIED"],soft:[]};
  if(!events.length)return {verdict:"REVISE",hard:["NO_SPECIALIST_EVIDENCE"],soft:[]};
  let max=0;for(const e of events)max=Math.max(max,severityRank(e.severity));
  const blockSet=new Set(config.blockSeverities),reviseSet=new Set(config.reviseSeverities);
  const severities=[...new Set(events.map(e=>String(e.severity||"INFO")))];
  if(severities.some(x=>blockSet.has(x)))return {verdict:"BLOCK",hard:severities.filter(x=>blockSet.has(x)).map(x=>"UNRESOLVED_"+x),soft:[]};
  if(severities.some(x=>reviseSet.has(x)))return {verdict:"REVISE",hard:[],soft:severities.filter(x=>reviseSet.has(x)).map(x=>"REVIEW_"+x)};
  return {verdict:"ACCEPT",hard:[],soft:severities.includes("WARNING")?["WARNING_EVIDENCE_REVIEWED"]:[]};
}
async function publishReviewRef(env,role,receiptId){
  if(!env.ASSURANCE_EXCHANGE_SERVICE)return {status:"NOT_CONFIGURED"};
  const body=JSON.stringify({schema:"chacha.dev/specialist-review-ref/v1",source:role,receipt_id:receiptId});
  let r;try{
    r=await env.ASSURANCE_EXCHANGE_SERVICE.fetch(new Request("https://assurance-exchange.internal/v1/specialist-reviews",{
      method:"POST",headers:{"content-type":"application/json"},body
    }));
  }catch{return {status:"DEFERRED",reason:"EXCHANGE_UNAVAILABLE"};}
  return {status:r.ok?"DELIVERED":"DEFERRED",http_status:r.status};
}
function bastionAction(eventType,severity){
  const s=String(severity||"INFO"),t=String(eventType||"");
  if(s==="CRITICAL")return "QUARANTINE";
  if(s==="BLOCK")return "QUARANTINE";
  if(s==="WARNING"&&["auth-anomaly","permission-drift","security-regression","unexpected-public-surface"].includes(t))return "CONTAIN";
  return "OBSERVE";
}
async function createBastionIncident(env,e,projectId,revision){
  const fields=e.fields||{},severity=String(fields.severity||"INFO"),eventType=String(fields.event_type||"");
  const action=bastionAction(eventType,severity);
  if(action==="OBSERVE"&&severity==="INFO")return null;
  const incidentId="inc-"+await sha256Hex(projectId+"|"+revision+"|"+e.event_id+"|"+action);
  await env.DB.prepare(`INSERT OR IGNORE INTO security_incidents
    (incident_id,project_id,revision,event_id,event_type,severity,response_action,status,corroboration_count,scope,e_stop_eligible,created_at)
    VALUES(?1,?2,?3,?4,?5,?6,?7,'OPEN',0,'PROJECT',0,datetime('now'))`)
    .bind(incidentId,projectId,revision,String(e.event_id),eventType,severity,action).run();
  if(action!=="OBSERVE"){
    const directiveId="dir-"+await sha256Hex(incidentId+"|"+action);
    await env.DB.prepare(`INSERT OR IGNORE INTO response_directives
      (directive_id,incident_id,project_id,action,status,reason,created_at)
      VALUES(?1,?2,?3,?4,'OPEN',?5,datetime('now'))`)
      .bind(directiveId,incidentId,projectId,action,eventType+":"+severity).run();
  }
  return {incident_id:incidentId,response_action:action};
}

export function makeAuthority(config){
  return {
    async fetch(req,env){
      const u=new URL(req.url);
      if(req.method==="GET"&&u.pathname==="/healthz")return json({
        status:"ok",authority:config.role,scope:config.scope,external_authority:true,
        project_scoped_identity:true,local_probe_ingest:true,exact_revision_reviews:true,
        assurance_exchange_publish:Boolean(env.ASSURANCE_EXCHANGE_SERVICE),
        direct_application_mutation:false,direct_architecture_mutation:false,
        central_orchestrator_owns_remediation:true,
        bastion_incident_response:config.role==="bastion",
        failover_status:config.role==="bastion"?"RESERVED_INACTIVE":"NOT_APPLICABLE"
      });

      if(req.method==="POST"&&u.pathname==="/v1/project-assurance-identities/register"){
        const body=await req.text();const auth=await requireSigned(req,env,"authority_identities",body);if(!auth.ok)return auth.response;
        let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
        if(p.schema!=="chacha.dev/project-assurance-identity-registration/v1")return json({error:"project_assurance_identity_schema_invalid"},400);
        const projectId=String(p.project_id||""),keyId=String(p.key_id||""),pub=String(p.public_key_spki_b64||"");
        if(!projectId||!/^project-[a-f0-9]{16}$/.test(keyId)||!pub)return json({error:"project_assurance_identity_invalid"},400);
        await env.DB.prepare(`INSERT INTO project_assurance_identities(key_id,project_id,status,public_key_spki_b64,created_at)
          VALUES(?1,?2,'ACTIVE',?3,datetime('now'))
          ON CONFLICT(key_id) DO UPDATE SET project_id=excluded.project_id,status='ACTIVE',public_key_spki_b64=excluded.public_key_spki_b64,revoked_at=NULL`)
          .bind(keyId,projectId,pub).run();
        return json({schema:"chacha.dev/project-assurance-identity-registration-result/v1",status:"PASS",project_id:projectId,key_id:keyId,authority:config.role});
      }

      if(req.method==="POST"&&u.pathname==="/v1/project-events"){
        const body=await req.text();let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
        if(p.schema!=="chacha.dev/project-assurance-event-batch/v1")return json({error:"project_event_batch_schema_invalid"},400);
        const projectId=String(p.project_id||"");if(!projectId)return json({error:"project_event_batch_project_required"},400);
        const auth=await requireSigned(req,env,"project_assurance_identities",body,projectId);if(!auth.ok)return auth.response;
        const events=Array.isArray(p.events)?p.events:[];if(!events.length||events.length>50)return json({error:"project_event_batch_size_invalid"},400);
        let accepted=0;const incidents=[];
        for(const e of events){
          if(!e||e.schema!=="chacha.dev/project-assurance-event/v1")return json({error:"project_event_schema_invalid"},400);
          if(String(e.project_id||"")!==projectId||String(e.assurance_role||"")!==config.role)return json({error:"project_event_role_or_project_mismatch"},403);
          if(!privacyOk(e))return json({error:"project_event_privacy_invalid"},400);
          const fields=e.fields&&typeof e.fields==="object"&&!Array.isArray(e.fields)?e.fields:{};
          const eventType=String(fields.event_type||""),severity=String(fields.severity||"INFO"),revision=String(e.application_version||"");
          if(!e.event_id||!revision||!eventType)return json({error:"project_event_identity_invalid"},400);
          await env.DB.prepare(`INSERT OR IGNORE INTO project_events
            (event_id,project_id,revision,event_type,severity,component_id,component_version,event_digest,fields_json,observed_at,ingested_at)
            VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,?10,datetime('now'))`)
            .bind(String(e.event_id),projectId,revision,eventType,severity,String(fields.component_id||"")||null,
              String(fields.component_version||"")||null,String(e.event_digest||await sha256Hex(stable(e))),stable(fields),
              String(e.observed_at||new Date().toISOString())).run();
          accepted++;
          if(config.role==="bastion"){const inc=await createBastionIncident(env,e,projectId,revision);if(inc)incidents.push(inc);}
        }
        return json({schema:"chacha.dev/specialist-event-ingest/v1",status:"PASS",authority:config.role,project_id:projectId,accepted,incidents,
          raw_user_content:false,direct_mutation:false});
      }

      if(req.method==="POST"&&u.pathname==="/v1/review"){
        const body=await req.text();const auth=await requireSigned(req,env,"authority_identities",body);if(!auth.ok)return auth.response;
        let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
        if(p.schema!=="chacha.dev/specialist-review-request/v1")return json({error:"review_schema_invalid"},400);
        const projectId=String(p.project_id||""),revision=String(p.revision||""),compromise=String(p.compromise_digest||"");
        if(!projectId||!revision||!compromise)return json({error:"review_identity_invalid"},400);
        const rows=(await env.DB.prepare(`SELECT event_id,event_type,severity,component_id,component_version,event_digest,observed_at
          FROM project_events WHERE project_id=?1 AND revision=?2 ORDER BY observed_at ASC`).bind(projectId,revision).all()).results||[];
        const result=verdictFor(config,rows,p.implementation_verified===true);
        const reviewId=config.role+"-"+await sha256Hex(projectId+"|"+revision+"|"+compromise+"|"+stable(rows)+"|"+result.verdict);
        const evidence=rows.map(x=>"event:"+x.event_id+":"+x.event_digest);
        await env.DB.prepare(`INSERT OR REPLACE INTO specialist_reviews
          (review_id,project_id,revision,compromise_digest,verdict,hard_objections_json,soft_objections_json,evidence_refs_json,implementation_verified,created_at)
          VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,datetime('now'))`)
          .bind(reviewId,projectId,revision,compromise,result.verdict,JSON.stringify(result.hard),JSON.stringify(result.soft),JSON.stringify(evidence),
            p.implementation_verified===true?1:0).run();
        const publication=await publishReviewRef(env,config.role,reviewId);
        return json({schema:"chacha.dev/compromise-agent-review/v1",receipt_id:reviewId,agent:config.role,project_id:projectId,revision,
          compromise_digest:compromise,verdict:result.verdict,hard_objections:result.hard,soft_objections:result.soft,evidence_refs:evidence,
          implementation_verified:p.implementation_verified===true,source_authority:"EXTERNAL",reviewed_at:new Date().toISOString(),
          assurance_exchange_delivery:publication,direct_mutation:false},result.verdict==="BLOCK"?409:200);
      }

      if(req.method==="GET"&&u.pathname.startsWith("/v1/reviews/")){
        const id=decodeURIComponent(u.pathname.slice("/v1/reviews/".length));
        const r=await env.DB.prepare("SELECT * FROM specialist_reviews WHERE review_id=?1").bind(id).first();
        if(!r)return json({error:"review_not_found"},404);
        return json({schema:"chacha.dev/compromise-agent-review/v1",receipt_id:r.review_id,agent:config.role,project_id:r.project_id,revision:r.revision,
          compromise_digest:r.compromise_digest,verdict:r.verdict,hard_objections:JSON.parse(r.hard_objections_json||"[]"),
          soft_objections:JSON.parse(r.soft_objections_json||"[]"),evidence_refs:JSON.parse(r.evidence_refs_json||"[]"),
          implementation_verified:Boolean(r.implementation_verified),source_authority:"EXTERNAL",reviewed_at:r.created_at,direct_mutation:false});
      }

      if(config.role==="bastion"&&req.method==="POST"&&u.pathname==="/v1/incidents/escalate"){
        const body=await req.text();const auth=await requireSigned(req,env,"authority_identities",body);if(!auth.ok)return auth.response;
        let p;try{p=JSON.parse(body);}catch{return json({error:"invalid_json"},400);}
        const id=String(p.incident_id||""),scope=String(p.scope||"PROJECT"),corr=Number(p.independent_corroborations||0);
        const row=await env.DB.prepare("SELECT * FROM security_incidents WHERE incident_id=?1").bind(id).first();
        if(!row)return json({error:"incident_not_found"},404);
        let action=String(row.response_action||"OBSERVE"),eligible=false;
        if(String(row.severity)==="CRITICAL"&&["PLATFORM","CORE"].includes(scope)&&corr>=2){action="E_STOP";eligible=true;}
        else if(["PLATFORM","CORE"].includes(scope)&&severityRank(row.severity)>=2){action="SURVIVAL";}
        const directiveId="dir-"+await sha256Hex(id+"|"+action+"|"+scope+"|"+corr);
        await env.DB.prepare("UPDATE security_incidents SET corroboration_count=?2,scope=?3,e_stop_eligible=?4,response_action=?5 WHERE incident_id=?1")
          .bind(id,corr,scope,eligible?1:0,action).run();
        await env.DB.prepare(`INSERT OR IGNORE INTO response_directives(directive_id,incident_id,project_id,action,status,reason,created_at)
          VALUES(?1,?2,?3,?4,'OPEN',?5,datetime('now'))`).bind(directiveId,id,row.project_id,action,"CORROBORATED_ESCALATION").run();
        return json({schema:"chacha.dev/bastion-incident-escalation/v1",status:"PASS",incident_id:id,action,e_stop_eligible:eligible,
          independent_corroborations:corr,scope,failover_status:"RESERVED_INACTIVE",direct_mutation:false});
      }

      if(config.role==="bastion"&&req.method==="GET"&&u.pathname==="/v1/incidents/directives"){
        const auth=await requireSigned(req,env,"authority_identities");if(!auth.ok)return auth.response;
        const rows=(await env.DB.prepare("SELECT * FROM response_directives WHERE status='OPEN' ORDER BY created_at ASC LIMIT 100").all()).results||[];
        return json({schema:"chacha.dev/bastion-response-directive-batch/v1",items:rows,count:rows.length,
          failover_status:"RESERVED_INACTIVE",direct_application_mutation:false});
      }

      return json({error:"not_found"},404);
    }
  };
}
