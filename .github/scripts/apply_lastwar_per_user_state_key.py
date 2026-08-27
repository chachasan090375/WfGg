from pathlib import Path

ROOT = Path('.')


def replace_once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return False
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one anchor, found {count}: {old[:80]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')
    return True


def replace_all_exact(path: Path, old: str, new: str, expected: int):
    text = path.read_text(encoding='utf-8')
    if new in text and old not in text:
        return False
    count = text.count(old)
    if count != expected:
        raise SystemExit(f'{path}: expected {expected} anchors, found {count}: {old!r}')
    path.write_text(text.replace(old, new), encoding='utf-8')
    return True


go = ROOT / 'lastwar-broker/go/wfgg-broker-main.go'
replace_once(go, 'if state, err := unsealState(sealed); err == nil && state.LinkedUID == uid {',
             'if state, err := unsealState(sealed, stateSecret(r)); err == nil && state.LinkedUID == uid {')
replace_once(go, 'sealed, err := sealState(state)', 'sealed, err := sealState(state, stateSecret(r))')
replace_once(go, 'state, err := unsealState(sealed)', 'state, err := unsealState(sealed, stateSecret(r))')
replace_once(go, 'freshSealed, err := sealState(freshState)', 'freshSealed, err := sealState(freshState, stateSecret(r))')
replace_once(
    go,
    'func sealState(state sealedState) (string, error) {\n\tsecret := os.Getenv("WFGG_STATE_KEY")\n\tif len(secret) < 16 {',
    'func stateSecret(r *http.Request) string {\n'
    '\tif r != nil {\n'
    '\t\tif secret := strings.TrimSpace(r.Header.Get("X-WfGg-State-Key")); len(secret) >= 16 {\n'
    '\t\t\treturn secret\n'
    '\t\t}\n'
    '\t}\n'
    '\treturn os.Getenv("WFGG_STATE_KEY")\n'
    '}\n\n'
    'func sealState(state sealedState, secret string) (string, error) {\n'
    '\tif len(secret) < 16 {'
)
replace_once(
    go,
    'func unsealState(sealed string) (sealedState, error) {\n\tvar state sealedState\n\tsecret := os.Getenv("WFGG_STATE_KEY")\n\tif len(secret) < 16 || !strings.HasPrefix(sealed, "wfgs1.") {',
    'func unsealState(sealed string, secret string) (sealedState, error) {\n'
    '\tvar state sealedState\n'
    '\tif len(secret) < 16 || !strings.HasPrefix(sealed, "wfgs1.") {'
)

identity = ROOT / 'worker/src/lastwar-identity.js'
replace_all_exact(identity, 'containerCall(env, ctx.id,', 'containerCall(env, ctx,', 4)
replace_once(
    identity,
    'async function containerCall(env, userId, path, payload, sha256Text, fail) {\n'
    "  if (!env.LASTWAR_USER) fail('LASTWAR_BROKER_NOT_CONFIGURED', 503);\n"
    '  const instanceKey = `u-${(await sha256Text(userId)).slice(0, 48)}`;\n'
    '  const instance = getContainer(env.LASTWAR_USER, instanceKey);',
    'async function containerCall(env, ctx, path, payload, sha256Text, fail) {\n'
    "  if (!env.LASTWAR_USER) fail('LASTWAR_BROKER_NOT_CONFIGURED', 503);\n"
    "  const privateSeed = cleanText(ctx?.auth_code_key, 256);\n"
    "  if (!privateSeed) fail('LASTWAR_STATE_KEY_SOURCE_MISSING', 500);\n"
    '  const userId = String(ctx.id);\n'
    '  const stateKey = await sha256Text(`wfgg-lastwar-state:v1:${userId}:${privateSeed}`);\n'
    '  const instanceKey = `u-${(await sha256Text(userId)).slice(0, 48)}`;\n'
    '  const instance = getContainer(env.LASTWAR_USER, instanceKey);'
)
replace_once(
    identity,
    "      headers: { 'Content-Type': 'application/json' },",
    "      headers: { 'Content-Type': 'application/json', 'X-WfGg-State-Key': stateKey },"
)

container = ROOT / 'worker/src/lastwar-container.js'
replace_once(
    container,
    "  envVars = {\n    WFGG_STATE_KEY: env.APP_SECRET || '',\n    WFGG_UPSTREAM_REVISION: env.LASTWAR_BROKER_REVISION || ''\n  };",
    "  envVars = {\n    WFGG_UPSTREAM_REVISION: env.LASTWAR_BROKER_REVISION || ''\n  };"
)

print('Per-user Last War state encryption key integration applied')
