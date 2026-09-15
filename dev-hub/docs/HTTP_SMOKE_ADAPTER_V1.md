# ChaCha DEV HUB — HTTP Smoke Adapter V1

`http-smoke-adapter` is the first concrete runtime bridge implementing the DEV HUB adapter protocol end to end.

It consumes `chacha.dev/dispatch-envelope/v1` on stdin and emits `chacha.dev/task-result/v1` on stdout. It is deliberately read-only and supports only HTTP `GET` and `HEAD` smoke checks.

## Safety properties

The adapter:

- requires task permission `read`;
- requires the `http-smoke` / `http-smoke-adapter` binding;
- requires an explicit `CHACHA_HTTP_SMOKE_ALLOWED_HOSTS` allowlist;
- rejects inline URL credentials;
- disables environment HTTP proxies for the request;
- does not follow redirects;
- caps timeout and response bytes;
- never emits response bodies;
- strips query strings and fragments from evidence sources;
- never self-verifies its result: task results remain `UNVERIFIED` until the independent verification layer handles them;
- invokes no shell and accepts no arbitrary command.

## Dispatch metadata

The adapter reads `metadata.http_smoke`:

```json
{
  "url": "https://example.test/health",
  "method": "GET",
  "expected_status": [200],
  "max_bytes": 4096
}
```

The configured host must be present in `CHACHA_HTTP_SMOKE_ALLOWED_HOSTS`.

## Certification path

The repository fixture `dev-hub/examples/http-smoke.dispatch.v1.json` targets a loopback-only sandbox. CI starts a local HTTP server, executes the real adapter, runs the generic Adapter Contract Harness against a temporary `CONTRACT_OK` registry copy, then uses `adapter-certification.py` to derive promotion evidence from the actual artifacts.

That evidence proves:

1. `static-contract-pass`;
2. `runtime-contract-pass`;
3. `sandbox-only`.

The resulting evidence is fed to the Adapter Promotion Engine in **plan-only** mode for both `DESIGNED -> CONTRACT_OK` and `CONTRACT_OK -> PILOT`.

The real `provider-adapters.v1.json` remains `DESIGNED` and unmodified. Runtime certification is therefore proof of eligibility, not an implicit promotion.

## Promotion boundary

Moving the real adapter to `CONTRACT_OK` or `PILOT` remains a separate explicit action. The runtime executable path on the actual DEV HUB host must exist and be provisioned before a real PILOT promotion is applied.
