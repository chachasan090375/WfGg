from pathlib import Path

p=Path('worker/src/index.js')
s=p.read_text(encoding='utf-8')
original=s

s=s.replace(
    "response = json({ ok: true, service: 'wfgg-api', version: '0.4.1' });",
    "response = json({ ok: true, service: 'wfgg-api', version: '0.4.2', admin_gate: 'R4_R5_ONLY' });",
    1,
)
s=s.replace(
    "const admin = isOwner(ctx) || ADMIN_RANKS.has(ctx.rank);",
    "const admin = ADMIN_RANKS.has(ctx.rank);",
    1,
)
s=s.replace(
    "if (!isOwner(ctx) && !ADMIN_RANKS.has(ctx.rank)) fail('FORBIDDEN', 403);",
    "if (!ADMIN_RANKS.has(ctx.rank)) fail('FORBIDDEN', 403);",
    1,
)

if s==original:
    print('PORTAL_R4_R5_GATE=ALREADY_APPLIED')
else:
    p.write_text(s,encoding='utf-8')
    print('PORTAL_R4_R5_GATE=OK')

assert "admin_gate: 'R4_R5_ONLY'" in s
assert "const admin = ADMIN_RANKS.has(ctx.rank);" in s
assert "if (!ADMIN_RANKS.has(ctx.rank)) fail('FORBIDDEN', 403);" in s
