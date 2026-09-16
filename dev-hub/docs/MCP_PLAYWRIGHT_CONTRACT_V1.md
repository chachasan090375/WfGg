# Playwright MCP Contract V1 — design-only

## Decision

Playwright MCP is admitted as a **verification/diagnostic candidate**, not as a general-purpose browser with unrestricted interaction. The first DEV HUB stage is `DESIGNED` / `ASSESS` only.

Provider: `playwright-mcp`  
Adapter: `playwright-mcp-adapter`  
Catalog status during this PR: `CATALOG_ONLY`

No browser is downloaded or launched by this design PR.

## Why now

With multiple development agents, browser verification becomes more valuable because an implementation can be checked independently from the agent that produced it. Playwright MCP exposes structured accessibility snapshots, console/network information and screenshots that can become verification evidence.

## Execution surface

The initial runtime qualification is intentionally **GitHub Actions ephemeral**, not ChaChaVPS. Browser binaries are heavy and the DEV HUB Storage Governor already protects the small VPS from this class of installation.

Pilot requirements:
- Node.js 20+;
- exact `@playwright/mcp` version pinned for each qualification run;
- ephemeral GitHub Actions runner;
- Chromium headless;
- isolated browser session;
- no persistent browser profile;
- preview/test target only;
- no authenticated personal browser profile.

## Initial tool surface

Allowed for the first PILOT contract:
- `browser_navigate` — browser-session mutation only, limited to an approved preview/test origin;
- `browser_snapshot`;
- `browser_find`;
- `browser_console_messages`;
- `browser_network_requests`;
- `browser_network_request`;
- `browser_take_screenshot`;
- `browser_close`.

The `filename` argument is denied for read/inspection tools during the first pilot so they cannot write arbitrary workspace files.

Explicitly denied include:
- `browser_run_code_unsafe`;
- `browser_evaluate`;
- click/type/form/file-upload/drop/drag interactions;
- page WebMCP calls;
- any arbitrary JavaScript execution.

A later, separate contract may admit test-account interactions such as click/type/fill, but only after isolated preview environments and cleanup/rollback are proven.

## Network boundary

The browser must target explicit preview/test origins. Playwright's `allowed-origins` configuration is useful defense-in-depth but is **not treated as a security boundary**; redirect targets must be revalidated by the adapter. `file://` navigation and unrestricted filesystem access remain disabled. Service workers are blocked for the first pilot.

## Verification separation

Playwright MCP returns `chacha.dev/task-result/v1` as `UNVERIFIED`. It may collect machine evidence, but it does not self-certify the change it is examining. Verification Broker remains the authority that decides whether evidence satisfies a gate.

## Admission path

`CATALOG_ONLY / DESIGNED → CONTRACT_OK → PILOT → ENABLED`

`DESIGNED -> CONTRACT_OK` is static only. `CONTRACT_OK -> PILOT` must prove an ephemeral runner can provision the pinned package/browser, launch an isolated session, navigate only to an approved test origin, capture snapshot/diagnostic evidence, and leave the repository/workspace unchanged.

## Official references

- https://github.com/microsoft/playwright-mcp
- https://playwright.dev/mcp/introduction
- https://playwright.dev/mcp/installation
