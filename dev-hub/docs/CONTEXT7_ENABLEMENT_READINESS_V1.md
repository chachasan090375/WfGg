# Context7 MCP — PILOT to ENABLED readiness

This branch evaluates Context7 enablement readiness only. It does not promote the adapter to ENABLED.

Required gates are derived from `adapter-enablement.v1.json` and `adapter-enable-readiness.py`:

- at least three concrete Task Results from `context7-mcp-adapter`
- each result status `OK`
- producer verification remains `UNVERIFIED`
- stable project/task identity
- distinct `observed_at` timestamps and distinct result digests
- fresh normalized provider health in `HEALTHY` state (maximum age 300 seconds)
- machine-readable rollback to `DISABLED`
- evidence generation must not mutate the adapter registry
- final promotion still requires an explicit promotion action; this branch performs readiness only

No production mutation is permitted.
