const enc = new TextEncoder();

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function stable(v) {
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(stable).join(",") + "]";
  return "{" + Object.keys(v).sort().map(k => JSON.stringify(k) + ":" + stable(v[k])).join(",") + "}";
}

function b64uToBytes(s) {
  s = String(s).replace(/-/g, "+").replace(/_/g, "/");
  while (s.length % 4) s += "=";
  return Uint8Array.from(atob(s), c => c.charCodeAt(0));
}

async function importEd25519Spki(b64) {
  return crypto.subtle.importKey("spki", b64uToBytes(b64), { name: "Ed25519" }, false, ["verify"]);
}

async function verifyEd25519(publicKeyB64, signatureB64, message) {
  const key = await importEd25519Spki(publicKeyB64);
  return crypto.subtle.verify({ name: "Ed25519" }, key, b64uToBytes(signatureB64), enc.encode(message));
}

function requestMessage(req, ts, body = "") {
  const u = new URL(req.url);
  return ts + "\n" + req.method + "\n" + u.pathname + u.search + "\n" + body;
}

async function requireCentral(req, env, body = "") {
  const keyId = req.headers.get("x-chacha-key-id") || "";
  const ts = req.headers.get("x-chacha-timestamp") || "";
  const sig = req.headers.get("x-chacha-signature") || "";
  const millis = Date.parse(ts);
  if (!keyId || !sig || !Number.isFinite(millis) || Math.abs(Date.now() - millis) > 120000) {
    return { ok: false, response: json({ error: "guardian_auth_invalid" }, 401) };
  }
  const row = await env.DB
    .prepare("SELECT public_key_spki_b64 FROM guardian_identities WHERE key_id=?1 AND status='ACTIVE'")
    .bind(keyId)
    .first();
  if (!row) return { ok: false, response: json({ error: "guardian_identity_unknown" }, 403) };
  const ok = await verifyEd25519(row.public_key_spki_b64, sig, requestMessage(req, ts, body));
  return ok ? { ok: true, keyId } : { ok: false, response: json({ error: "guardian_signature_invalid" }, 403) };
}

function arr(v) {
  try {
    const x = typeof v === "string" ? JSON.parse(v) : v;
    return Array.isArray(x) ? x.map(String) : [];
  } catch {
    return [];
  }
}

function allows(list, value) {
  return list.includes("*") || list.includes(String(value || ""));
}

function truthyEvidence(evidence, key) {
  const v = (evidence || {})[key];
  return v === true || v === "PASS" || v === "YES" || v === "OK" || v === "VERIFIED";
}

async function contractById(env, id) {
  if (!id) return null;
  return env.DB.prepare("SELECT * FROM role_contracts WHERE contract_id=?1").bind(id).first();
}

async function resolveRoleContract(env, role) {
  role = String(role || "");
  let row = await contractById(env, "role:" + role);
  if (row) return row;
  const lower = role.toLowerCase();
  if (lower.includes("foundry")) return contractById(env, "role:__foundry__");
  if (lower.endsWith("-agent") || lower === "agent") return contractById(env, "role:__agent__");
  if (lower.includes("orchestrator")) return contractById(env, "role:__orchestrator__");
  return contractById(env, "role:__unknown__");
}

function addReason(state, severity, code) {
  const order = { INFO: 0, WARNING: 1, BLOCK: 2, CRITICAL: 3 };
  state.reasons.push(code);
  if (order[severity] > order[state.severity]) state.severity = severity;
}

function verdictFromSeverity(severity) {
  if (severity === "CRITICAL") return "CRITICAL";
  if (severity === "BLOCK") return "BLOCK";
  if (severity === "WARNING") return "WARNING";
  return "PASS";
}

async function evaluate(event, env) {
  const state = { severity: "INFO", reasons: [] };
  const actor = String(event.actor || "");
  const subjectRole = String(event.subject_role || "");
  const action = String(event.action || "");
  const permission = String(event.permission || "read");
  const phase = String(event.phase || "");
  const evidence = event.evidence || {};
  const context = event.context || {};

  if (event.schema !== "chacha.dev/governance-action/v1") addReason(state, "BLOCK", "EVENT_SCHEMA_INVALID");
  if (!event.event_id) addReason(state, "BLOCK", "EVENT_ID_MISSING");
  if (!["PRE_ACTION", "POST_ACTION"].includes(phase)) addReason(state, "BLOCK", "EVENT_PHASE_INVALID");
  if (!actor) addReason(state, "BLOCK", "ACTOR_MISSING");
  if (!subjectRole) addReason(state, "BLOCK", "SUBJECT_ROLE_MISSING");
  if (!action) addReason(state, "BLOCK", "ACTION_MISSING");

  const actorContract = await contractById(env, "component:" + actor) || await resolveRoleContract(env, actor);
  const roleContract = await resolveRoleContract(env, subjectRole);

  if (!actorContract) {
    addReason(state, "BLOCK", "ACTOR_CONTRACT_MISSING");
  } else {
    const allowedActions = arr(actorContract.allowed_actions_json);
    const forbiddenActions = arr(actorContract.forbidden_actions_json);
    if (forbiddenActions.includes(action)) addReason(state, "CRITICAL", "ACTOR_ACTION_FORBIDDEN");
    else if (!allows(allowedActions, action)) addReason(state, "BLOCK", "ACTOR_ACTION_OUTSIDE_ROLE");
  }

  if (!roleContract) {
    addReason(state, "BLOCK", "SUBJECT_ROLE_CONTRACT_MISSING");
  } else {
    const allowedActions = arr(roleContract.allowed_actions_json);
    const forbiddenActions = arr(roleContract.forbidden_actions_json);
    const allowedPermissions = arr(roleContract.allowed_permissions_json);
    if (forbiddenActions.includes(action)) addReason(state, "CRITICAL", "SUBJECT_ACTION_FORBIDDEN");
    else if (!allows(allowedActions, action)) addReason(state, "BLOCK", "SUBJECT_ACTION_OUTSIDE_ROLE");
    if (!allows(allowedPermissions, permission)) addReason(state, "BLOCK", "PERMISSION_OUTSIDE_ROLE");

    if (Number(roleContract.unknown_role || 0) === 1) {
      if (["read", "plan"].includes(permission)) addReason(state, "WARNING", "UNKNOWN_ROLE_LOW_RISK");
      else addReason(state, "BLOCK", "UNKNOWN_ROLE_WRITE_FORBIDDEN");
    }

    if (phase === "POST_ACTION" && action === "FINAL_ARCHITECTURE_DECISION") {
      for (const key of arr(roleContract.required_evidence_json)) {
        if (!truthyEvidence(evidence, key)) addReason(state, "BLOCK", "REQUIRED_EVIDENCE_MISSING:" + key);
      }
    }
  }

  const sensitive = new Set([
    "production-deploy", "production-data-write",
    "secret-change", "destructive-operation", "technology-replacement"
  ]);
  if (phase === "PRE_ACTION" && sensitive.has(permission) && !truthyEvidence(evidence, "human_approval")) {
    addReason(state, "CRITICAL", "SENSITIVE_ACTION_WITHOUT_HUMAN_APPROVAL");
  }

  if (phase === "PRE_ACTION" && ["heavy", "very-heavy"].includes(String(context.resource_class || "")) &&
      !truthyEvidence(evidence, "storage_preflight")) {
    addReason(state, "BLOCK", "HEAVY_ACTION_WITHOUT_STORAGE_PREFLIGHT");
  }

  if (truthyEvidence(evidence, "emergency_stop_active")) {
    addReason(state, "CRITICAL", "EMERGENCY_STOP_ACTIVE");
  }

  if (actor === "run-controller" && phase === "PRE_ACTION" && !truthyEvidence(evidence, "adapter_binding_valid")) {
    addReason(state, "BLOCK", "ADAPTER_BINDING_NOT_VALIDATED");
  }

  const adapters = Array.isArray(event.adapters) ? event.adapters : [];
  for (const binding of adapters) {
    if (!binding || !binding.adapter) {
      addReason(state, "BLOCK", "ADAPTER_ID_MISSING");
      continue;
    }
    const ac = await contractById(env, "adapter:" + String(binding.adapter));
    if (!ac) {
      addReason(state, sensitive.has(permission) ? "CRITICAL" : "BLOCK", "ADAPTER_CONTRACT_MISSING:" + String(binding.adapter));
      continue;
    }
    if (!allows(arr(ac.allowed_permissions_json), permission)) {
      addReason(state, "CRITICAL", "ADAPTER_PERMISSION_OUTSIDE_CONTRACT:" + String(binding.adapter));
    }
  }

  if (action === "FINAL_ARCHITECTURE_DECISION" && phase === "POST_ACTION") {
    for (const key of [
      "technology_watch_pre", "technology_watch_final", "reuse_memory", "architecture_memory",
      "architecture_portfolio", "branch_foundry", "agent_foundry", "capability_foundry", "constraint_policy"
    ]) {
      if (!truthyEvidence(evidence, key)) addReason(state, "BLOCK", "ARCHITECTURE_COUNCIL_EVIDENCE_MISSING:" + key);
    }
  }

  const verdict = verdictFromSeverity(state.severity);
  return {
    verdict,
    severity: state.severity,
    reason_codes: [...new Set(state.reasons)],
    actor_contract_id: actorContract ? actorContract.contract_id : null,
    subject_contract_id: roleContract ? roleContract.contract_id : null
  };
}

async function storeEvent(env, event, evaluation) {
  const payload = stable(event);
  await env.DB.prepare(
    `INSERT OR REPLACE INTO governance_events
      (event_id,received_at,phase,actor,subject_role,action,task_kind,permission,project_id,run_id,verdict,severity,contract_id,reason_codes_json,payload_json)
      VALUES(?1,datetime('now'),?2,?3,?4,?5,?6,?7,?8,?9,?10,?11,?12,?13,?14)`
  ).bind(
    String(event.event_id),
    String(event.phase || ""),
    String(event.actor || ""),
    String(event.subject_role || ""),
    String(event.action || ""),
    event.task_kind ? String(event.task_kind) : null,
    event.permission ? String(event.permission) : null,
    event.project_id ? String(event.project_id) : null,
    event.run_id ? String(event.run_id) : null,
    evaluation.verdict,
    evaluation.severity,
    evaluation.subject_contract_id,
    JSON.stringify(evaluation.reason_codes),
    payload
  ).run();

  if (evaluation.severity !== "INFO") {
    const alertId = "alert-" + String(event.event_id);
    const summary = evaluation.severity + " " + String(event.actor || "") + " -> " + String(event.subject_role || "") + " / " + String(event.action || "");
    await env.DB.prepare(
      `INSERT OR REPLACE INTO guardian_alerts
        (alert_id,event_id,created_at,severity,status,summary,reason_codes_json,payload_json)
        VALUES(?1,?2,datetime('now'),?3,'OPEN',?4,?5,?6)`
    ).bind(alertId,String(event.event_id),evaluation.severity,summary,JSON.stringify(evaluation.reason_codes),payload).run();
  }
}

async function check(req, env) {
  const body = await req.text();
  const auth = await requireCentral(req, env, body);
  if (!auth.ok) return auth.response;
  let event;
  try { event = JSON.parse(body); }
  catch { return json({ error: "invalid_json" }, 400); }
  if (!event || typeof event !== "object") return json({ error: "event_invalid" }, 400);

  const evaluation = await evaluate(event, env);
  await storeEvent(env, event, evaluation);
  return json({
    schema: "chacha.dev/guardian-verdict/v1",
    event_id: String(event.event_id || ""),
    verdict: evaluation.verdict,
    severity: evaluation.severity,
    reason_codes: evaluation.reason_codes,
    actor_contract_id: evaluation.actor_contract_id,
    subject_contract_id: evaluation.subject_contract_id,
    stop_recommended: evaluation.severity === "CRITICAL",
    guardian: "external-worker",
    checked_at: new Date().toISOString()
  }, evaluation.verdict === "PASS" || evaluation.verdict === "WARNING" ? 200 : 409);
}

async function alerts(req, env) {
  const auth = await requireCentral(req, env);
  if (!auth.ok) return auth.response;
  const u = new URL(req.url);
  const status = String(u.searchParams.get("status") || "OPEN").toUpperCase();
  const limit = Math.max(1, Math.min(100, Number(u.searchParams.get("limit") || 25)));
  const rows = await env.DB.prepare(
    "SELECT alert_id,event_id,created_at,severity,status,summary,reason_codes_json,payload_json FROM guardian_alerts WHERE status=?1 ORDER BY created_at DESC LIMIT ?2"
  ).bind(status,limit).all();
  return json({
    schema:"chacha.dev/guardian-alert-batch/v1",
    items:(rows.results || []).map(r => ({
      alert_id:r.alert_id,event_id:r.event_id,created_at:r.created_at,severity:r.severity,status:r.status,
      summary:r.summary,reason_codes:JSON.parse(r.reason_codes_json || "[]"),event:JSON.parse(r.payload_json || "{}")
    }))
  });
}

async function ackAlerts(req, env) {
  const body = await req.text();
  const auth = await requireCentral(req, env, body);
  if (!auth.ok) return auth.response;
  let payload;
  try { payload = JSON.parse(body); }
  catch { return json({ error:"invalid_json" },400); }
  const ids = Array.isArray(payload.alert_ids) ? payload.alert_ids.map(String).slice(0,100) : [];
  if (!ids.length) return json({ error:"alert_ids_required" },400);
  let count=0;
  for (const id of ids) {
    const r=await env.DB.prepare("UPDATE guardian_alerts SET status='ACKED' WHERE alert_id=?1 AND status='OPEN'").bind(id).run();
    count += r.meta.changes || 0;
  }
  return json({schema:"chacha.dev/guardian-alert-ack/v1",status:"ACKED",count});
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (req.method === "GET" && u.pathname === "/healthz") {
      return json({
        status:"ok",
        service:"chacha-dev-guardian",
        external_governance_plane:true,
        runtime_contract_mutation_api:false,
        tunnel_required:false
      });
    }
    if (req.method === "POST" && u.pathname === "/v1/check") return check(req, env);
    if (req.method === "GET" && u.pathname === "/v1/alerts") return alerts(req, env);
    if (req.method === "POST" && u.pathname === "/v1/alerts/ack") return ackAlerts(req, env);
    return json({error:"not_found"},404);
  }
};
