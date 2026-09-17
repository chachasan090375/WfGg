# Radar V6.10 — Collector Index Search Bridge

## Search order

1. D1 `radar_observations` cache.
2. Signed read-only VPS Collector index (`GET /v1/collector/index/search`).
3. Lazy D1 cache of only the matching Collector rows.
4. OWNER-only read-only Last War lookup as the final fallback.

The accumulated VPS Collector remains the canonical player index. V6.10 deliberately does not bulk-copy the Collector database into D1.

## Privacy and safety

The Connector index route projects only player search fields needed by Radar and does not expose Collector internals, credentials, tokens, hashes or cycle metadata. The production live probe uses a guaranteed-miss synthetic query and validates only route/signature/response shape; it never logs returned player rows.

## Qualification

Final pre-merge qualification must pass reconstruction, Go tests, `go vet`, Linux build, Worker syntax/tests, search-order assertions and read-only/probe-privacy checks on the exact PR head.
