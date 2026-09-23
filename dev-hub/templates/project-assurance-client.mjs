const DEFAULT_RELAY="/__chacha/assurance/v1/events";
const ALLOW=new Set([
  "event_type","severity","code","component_id","component_version","deployment_id",
  "metric_name","metric_value","metric_unit","duration_ms","status_code",
  "evidence_digest","route_template","operation","observed_at","trace_id_hash"
]);
const FORBIDDEN=["content","body","prompt","message","email","password","secret","token","authorization","cookie"];

function forbiddenKey(key){
  const lower=String(key).toLowerCase();
  return FORBIDDEN.some(x=>lower.includes(x));
}
function sanitize(fields){
  const out={};
  for(const [key,value] of Object.entries(fields||{})){
    if(forbiddenKey(key))throw new Error("RAW_OR_SENSITIVE_FIELD_DENIED:"+key);
    if(!ALLOW.has(key))throw new Error("FIELD_NOT_ALLOWLISTED:"+key);
    if(value!==null&&typeof value==="object")throw new Error("NESTED_FIELD_DENIED:"+key);
    if(typeof value==="string"&&value.length>256)throw new Error("FIELD_TOO_LARGE:"+key);
    out[key]=value;
  }
  return out;
}
function uuid(){
  if(globalThis.crypto?.randomUUID)return globalThis.crypto.randomUUID();
  throw new Error("CRYPTO_RANDOM_UUID_REQUIRED");
}
function make(role,projectId,applicationVersion,relayUrl=DEFAULT_RELAY){
  if(!["guardian","sentinel"].includes(role))throw new Error("ASSURANCE_ROLE_INVALID");
  if(!projectId||!applicationVersion)throw new Error("ASSURANCE_IDENTITY_REQUIRED");
  return {
    async emit(eventType,severity="INFO",fields={}){
      const safe=sanitize(fields);
      safe.event_type=eventType;
      safe.severity=severity;
      const payload={
        schema:"chacha.dev/project-assurance-local-event/v1",
        event_id:"evt-"+uuid(),
        project_id:projectId,
        application_version:applicationVersion,
        assurance_role:role,
        observed_at:new Date().toISOString(),
        fields:safe,
        privacy:{raw_user_content:false,credentials:false,secrets:false},
        direct_mutation:false
      };
      const response=await fetch(relayUrl,{
        method:"POST",
        headers:{"content-type":"application/json"},
        body:JSON.stringify(payload),
        credentials:"same-origin",
        keepalive:true
      });
      if(!response.ok)throw new Error("ASSURANCE_RELAY_HTTP_"+response.status);
      return response.json().catch(()=>({status:"QUEUED"}));
    }
  };
}
export function createGuardianLocal(projectId,applicationVersion,relayUrl=DEFAULT_RELAY){
  return make("guardian",projectId,applicationVersion,relayUrl);
}
export function createSentinelLocal(projectId,applicationVersion,relayUrl=DEFAULT_RELAY){
  return make("sentinel",projectId,applicationVersion,relayUrl);
}
export const assurancePrivacy={
  raw_user_content:false,
  credentials:false,
  secrets:false,
  client_direct_to_central:false,
  direct_mutation:false
};
