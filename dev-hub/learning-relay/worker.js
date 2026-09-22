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
  return crypto.subtle.verify(
    { name: "Ed25519" },
    key,
    b64uToBytes(signatureB64),
    enc.encode(message)
  );
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
    return { ok: false, response: json({ error: "central_auth_invalid" }, 401) };
  }
  const row = await env.DB
    .prepare("SELECT public_key_spki_b64 FROM identities WHERE key_id=?1 AND role='CENTRAL' AND status='ACTIVE'")
    .bind(keyId)
    .first();
  if (!row) return { ok: false, response: json({ error: "central_identity_unknown" }, 403) };
  const ok = await verifyEd25519(row.public_key_spki_b64, sig, requestMessage(req, ts, body));
  return ok ? { ok: true, keyId } : { ok: false, response: json({ error: "central_signature_invalid" }, 403) };
}

async function requireProducer(packet, env) {
  if (
    packet?.schema !== "chacha.dev/learning-uplink-packet/v2" ||
    packet?.algorithm !== "Ed25519" ||
    !packet?.key_id ||
    !packet?.signature ||
    !packet?.delta
  ) {
    return { ok: false, error: "packet_invalid" };
  }
  const row = await env.DB
    .prepare("SELECT public_key_spki_b64,project_id,deployment_id FROM identities WHERE key_id=?1 AND role='PRODUCER' AND status='ACTIVE'")
    .bind(String(packet.key_id))
    .first();
  if (!row) return { ok: false, error: "producer_identity_unknown" };
  const delta = packet.delta;
  if (String(delta.project_id || "") !== row.project_id || String(delta.deployment_id || "") !== row.deployment_id) {
    return { ok: false, error: "producer_scope_mismatch" };
  }
  const ok = await verifyEd25519(row.public_key_spki_b64, String(packet.signature), stable(delta));
  return ok ? { ok: true, keyId: String(packet.key_id) } : { ok: false, error: "producer_signature_invalid" };
}

async function ingest(req, env) {
  let packet;
  try { packet = await req.json(); }
  catch { return json({ error: "invalid_json" }, 400); }

  const auth = await requireProducer(packet, env);
  if (!auth.ok) return json({ error: auth.error }, 403);

  const d = packet.delta;
  if (!d.delta_id || !Array.isArray(d.changes) || d.changes.length === 0) {
    return json({ error: "delta_invalid" }, 400);
  }

  const res = await env.DB.prepare(
    `INSERT OR IGNORE INTO learning_deltas
      (delta_id,project_id,source_id,deployment_id,sequence,observed_at,severity,payload_json,producer_key_id,received_at,status)
      VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,datetime('now'),'PENDING')`
  ).bind(
    String(d.delta_id),
    String(d.project_id || ""),
    String(d.source_id || ""),
    String(d.deployment_id || ""),
    Number(d.sequence || 0),
    String(d.observed_at || ""),
    String((d.anomaly || {}).severity || ""),
    stable(d),
    auth.keyId
  ).run();

  return json({
    schema: "chacha.dev/learning-relay-ack/v1",
    status: res.meta.changes === 1 ? "RECORDED" : "DEDUPLICATED",
    delta_id: String(d.delta_id)
  }, res.meta.changes === 1 ? 202 : 200);
}

async function pull(req, env) {
  const auth = await requireCentral(req, env);
  if (!auth.ok) return auth.response;
  const u = new URL(req.url);
  const limit = Math.max(1, Math.min(100, Number(u.searchParams.get("limit") || 25)));
  const rows = await env.DB
    .prepare("SELECT delta_id,payload_json,received_at FROM learning_deltas WHERE status='PENDING' ORDER BY received_at,delta_id LIMIT ?1")
    .bind(limit)
    .all();
  return json({
    schema: "chacha.dev/learning-relay-batch/v1",
    items: (rows.results || []).map(r => ({
      delta_id: r.delta_id,
      delta: JSON.parse(r.payload_json),
      received_at: r.received_at
    }))
  });
}

async function ack(req, env) {
  const body = await req.text();
  const auth = await requireCentral(req, env, body);
  if (!auth.ok) return auth.response;
  let payload;
  try { payload = JSON.parse(body); }
  catch { return json({ error: "invalid_json" }, 400); }
  const ids = Array.isArray(payload.delta_ids) ? payload.delta_ids.map(String).slice(0, 100) : [];
  if (!ids.length) return json({ error: "delta_ids_required" }, 400);
  let count = 0;
  for (const id of ids) {
    const r = await env.DB
      .prepare("UPDATE learning_deltas SET status='ACKED',acked_at=datetime('now') WHERE delta_id=?1 AND status='PENDING'")
      .bind(id)
      .run();
    count += r.meta.changes || 0;
  }
  return json({ status: "ACKED", count });
}

async function upsertIdentity(req, env) {
  const body = await req.text();
  const auth = await requireCentral(req, env, body);
  if (!auth.ok) return auth.response;
  let payload;
  try { payload = JSON.parse(body); }
  catch { return json({ error: "invalid_json" }, 400); }

  if (!["PRODUCER", "CENTRAL"].includes(payload.role) || !payload.key_id || !payload.public_key_spki_b64) {
    return json({ error: "identity_invalid" }, 400);
  }
  if (payload.role === "PRODUCER" && (!payload.project_id || !payload.deployment_id)) {
    return json({ error: "producer_scope_required" }, 400);
  }

  await env.DB.prepare(
    `INSERT INTO identities(key_id,role,status,public_key_spki_b64,project_id,deployment_id,created_at)
     VALUES(?1,?2,'ACTIVE',?3,?4,?5,datetime('now'))
     ON CONFLICT(key_id) DO UPDATE SET
       status='ACTIVE',
       public_key_spki_b64=excluded.public_key_spki_b64,
       project_id=excluded.project_id,
       deployment_id=excluded.deployment_id`
  ).bind(
    String(payload.key_id),
    String(payload.role),
    String(payload.public_key_spki_b64),
    payload.project_id ? String(payload.project_id) : null,
    payload.deployment_id ? String(payload.deployment_id) : null
  ).run();

  return json({ status: "REGISTERED", key_id: String(payload.key_id), role: String(payload.role) }, 201);
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (req.method === "GET" && u.pathname === "/healthz") {
      return json({
        status: "ok",
        service: "chacha-dev-learning-relay",
        architecture: "worker-mailbox",
        tunnel_required: false
      });
    }
    if (req.method === "POST" && u.pathname === "/v1/learning-deltas") return ingest(req, env);
    if (req.method === "GET" && u.pathname === "/v1/central/pull") return pull(req, env);
    if (req.method === "POST" && u.pathname === "/v1/central/ack") return ack(req, env);
    if (req.method === "POST" && u.pathname === "/v1/central/identities") return upsertIdentity(req, env);
    return json({ error: "not_found" }, 404);
  }
};
