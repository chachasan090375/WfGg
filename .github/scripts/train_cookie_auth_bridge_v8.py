from pathlib import Path

p = Path('frontend/_worker.js')
s = p.read_text(encoding='utf-8')
old = """          headers.set('X-WfGg-Portal-Token', cookiePortalTrainToken);\n          apiRequest = new Request(request, { headers });"""
new = """          /* WFGG_TRAIN_API_COOKIE_AUTH_DUAL_TRANSPORT_V8\n             Le cookie HttpOnly validé par le Portail est transporté au Worker\n             Train par le header dédié et, en secours strictement marqué, par\n             Authorization. Le backend n'accepte ce fallback que lorsque le\n             marqueur cookie-auth-v6 est présent. */\n          headers.set('X-WfGg-Portal-Token', cookiePortalTrainToken);\n          headers.set('X-WfGg-Portal-Bridge', 'cookie-auth-v6');\n          headers.set('Authorization', 'Bearer ' + cookiePortalTrainToken);\n          apiRequest = new Request(request, { headers });"""
if old not in s:
    raise SystemExit('anchor not found')
s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')
