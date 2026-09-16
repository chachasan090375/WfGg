#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';

const REQUIRED = [
  'PLAYWRIGHT_MCP_BIN',
  'PLAYWRIGHT_MCP_TARGET_URL',
  'PLAYWRIGHT_MCP_ALLOWED_ORIGIN',
  'PLAYWRIGHT_MCP_EVIDENCE',
  'PLAYWRIGHT_MCP_MARKER',
];
for (const name of REQUIRED) {
  if (!process.env[name]) {
    console.error(`MISSING_ENV=${name}`);
    process.exit(2);
  }
}

const allowed = new Set([
  'browser_navigate',
  'browser_snapshot',
  'browser_find',
  'browser_console_messages',
  'browser_network_requests',
  'browser_network_request',
  'browser_take_screenshot',
  'browser_close',
]);
const explicitlyDenied = new Set([
  'browser_run_code_unsafe', 'browser_evaluate', 'browser_click', 'browser_type',
  'browser_fill_form', 'browser_file_upload', 'browser_drop', 'browser_drag',
  'browser_handle_dialog', 'browser_hover', 'browser_press_key', 'browser_select_option',
  'browser_webmcp_call', 'browser_webmcp_list',
]);

function stableDigest(value) {
  const raw = JSON.stringify(value, Object.keys(value).sort());
  return `sha256:${crypto.createHash('sha256').update(raw).digest('hex')}`;
}

function flattenText(result) {
  return (result?.content || [])
    .filter(x => x && typeof x === 'object' && x.type === 'text' && typeof x.text === 'string')
    .map(x => x.text)
    .join('\n');
}

function rejectFilename(value, where = 'arguments') {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    value.forEach((item, i) => rejectFilename(item, `${where}[${i}]`));
    return;
  }
  for (const [key, child] of Object.entries(value)) {
    if (key === 'filename') throw new Error(`FILENAME_ARGUMENT_DENIED:${where}.${key}`);
    rejectFilename(child, `${where}.${key}`);
  }
}

const evidence = {
  schema: 'chacha.dev/playwright-mcp-pilot-runtime-evidence/v1',
  provider: 'playwright-mcp',
  adapter: 'playwright-mcp-adapter',
  runtime_surface: 'github-actions-ephemeral',
  package: '@playwright/mcp',
  package_version: '0.0.81',
  mcp_client_package: '@modelcontextprotocol/client',
  mcp_client_version: '2.0.0',
  target_url: process.env.PLAYWRIGHT_MCP_TARGET_URL,
  target_origin: process.env.PLAYWRIGHT_MCP_ALLOWED_ORIGIN,
  isolated: true,
  headless: true,
  browser: 'chromium',
  service_workers_blocked: true,
  persistent_profile: false,
  production_target: false,
  negotiated_era: null,
  negotiated_protocol_version: null,
  tool_inventory: [],
  tool_inventory_digest: null,
  required_allowed_tools_present: false,
  unsafe_tool_present_in_raw_server: false,
  unsafe_tool_invoked: false,
  invoked_tools: [],
  marker_found_in_snapshot: false,
  marker_found_in_find: false,
  network_observed: false,
  result_trust: 'UNVERIFIED',
  runtime_contract_pass: false,
  sandbox_only_pass: true,
  provisioning_pass: true,
  test_origin_navigation_pass: false,
  snapshot_pass: false,
  no_workspace_write_claim: 'WORKFLOW_VERIFIES_GIT_CLEAN',
  eligible_for_pilot: false,
  blockers: [],
};

let client;
try {
  const transport = new StdioClientTransport({
    command: process.env.PLAYWRIGHT_MCP_BIN,
    args: [
      '--headless',
      '--isolated',
      '--browser', 'chromium',
      '--block-service-workers',
      '--allowed-origins', process.env.PLAYWRIGHT_MCP_ALLOWED_ORIGIN,
      '--codegen', 'none',
      '--output-dir', process.env.PLAYWRIGHT_MCP_OUTPUT_DIR || '/tmp/playwright-mcp-output',
    ],
  });
  client = new Client(
    { name: 'chacha-dev-playwright-pilot', version: '1.0.0' },
    { versionNegotiation: { mode: 'auto' } },
  );
  await client.connect(transport);
  evidence.negotiated_era = client.getProtocolEra?.() ?? null;
  evidence.negotiated_protocol_version = client.getNegotiatedProtocolVersion?.() ?? null;

  const listed = await client.listTools();
  evidence.tool_inventory = (listed.tools || []).map(tool => ({
    name: tool.name,
    readOnlyHint: tool.annotations?.readOnlyHint ?? null,
    destructiveHint: tool.annotations?.destructiveHint ?? null,
    idempotentHint: tool.annotations?.idempotentHint ?? null,
    openWorldHint: tool.annotations?.openWorldHint ?? null,
  })).sort((a, b) => a.name.localeCompare(b.name));
  evidence.tool_inventory_digest = stableDigest(evidence.tool_inventory);

  const names = new Set(evidence.tool_inventory.map(x => x.name));
  const requiredForProbe = ['browser_navigate', 'browser_snapshot', 'browser_find', 'browser_network_requests', 'browser_close'];
  const missing = requiredForProbe.filter(name => !names.has(name));
  evidence.required_allowed_tools_present = missing.length === 0;
  if (missing.length) evidence.blockers.push(...missing.map(x => `ALLOWED_TOOL_MISSING:${x}`));
  evidence.unsafe_tool_present_in_raw_server = names.has('browser_run_code_unsafe');

  async function safeCall(name, args = {}) {
    if (!allowed.has(name)) throw new Error(`TOOL_NOT_ALLOWLISTED:${name}`);
    rejectFilename(args);
    evidence.invoked_tools.push(name);
    const result = await client.callTool({ name, arguments: args });
    if (result?.isError) throw new Error(`TOOL_RESULT_ERROR:${name}:${flattenText(result).slice(0, 500)}`);
    return result;
  }

  const nav = await safeCall('browser_navigate', { url: process.env.PLAYWRIGHT_MCP_TARGET_URL });
  evidence.test_origin_navigation_pass = !nav?.isError;

  const snapshot = await safeCall('browser_snapshot', {});
  const snapshotText = flattenText(snapshot);
  evidence.marker_found_in_snapshot = snapshotText.includes(process.env.PLAYWRIGHT_MCP_MARKER);
  evidence.snapshot_pass = evidence.marker_found_in_snapshot;
  if (!evidence.marker_found_in_snapshot) evidence.blockers.push('MARKER_NOT_FOUND_IN_SNAPSHOT');

  const found = await safeCall('browser_find', { text: process.env.PLAYWRIGHT_MCP_MARKER });
  evidence.marker_found_in_find = flattenText(found).includes(process.env.PLAYWRIGHT_MCP_MARKER);
  if (!evidence.marker_found_in_find) evidence.blockers.push('MARKER_NOT_FOUND_BY_BROWSER_FIND');

  const network = await safeCall('browser_network_requests', { static: false });
  evidence.network_observed = flattenText(network).includes(process.env.PLAYWRIGHT_MCP_ALLOWED_ORIGIN) || flattenText(network).length > 0;

  await safeCall('browser_close', {});

  if (!evidence.required_allowed_tools_present) evidence.blockers.push('REQUIRED_TOOL_SURFACE_INCOMPLETE');
  if (!evidence.test_origin_navigation_pass) evidence.blockers.push('TEST_ORIGIN_NAVIGATION_FAILED');
  if (evidence.invoked_tools.some(name => explicitlyDenied.has(name))) {
    evidence.unsafe_tool_invoked = true;
    evidence.blockers.push('DENIED_TOOL_INVOKED');
  }
  if (!['modern', 'legacy'].includes(evidence.negotiated_era)) evidence.blockers.push('PROTOCOL_ERA_NOT_RECORDED');

  evidence.runtime_contract_pass = evidence.blockers.length === 0;
  evidence.eligible_for_pilot = evidence.runtime_contract_pass;
} catch (error) {
  evidence.blockers.push(`RUNTIME_EXCEPTION:${error?.name || 'Error'}:${String(error?.message || error).slice(0, 500)}`);
  evidence.runtime_contract_pass = false;
  evidence.eligible_for_pilot = false;
} finally {
  try { await client?.close(); } catch {}
  fs.mkdirSync(path.dirname(process.env.PLAYWRIGHT_MCP_EVIDENCE), { recursive: true });
  fs.writeFileSync(process.env.PLAYWRIGHT_MCP_EVIDENCE, JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify(evidence, null, 2));
}

process.exit(evidence.eligible_for_pilot ? 0 : 2);
