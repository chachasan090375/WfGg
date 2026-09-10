from pathlib import Path

path = Path('frontend/_worker.js')
text = path.read_text()

old = """        let apiRequest = request;
        if (apiRoute === UPSTREAMS.trainApi && cookiePortalTrainToken) {
          const headers = new Headers(request.headers);
          headers.set('X-WfGg-Portal-Token', cookiePortalTrainToken);
          apiRequest = new Request(request, { headers });
        }
"""

new = """        let apiRequest = request;
        if (apiRoute === UPSTREAMS.trainApi && cookiePortalTrainToken) {
          const headers = new Headers(request.headers);
          /* WFGG_TRAIN_API_COOKIE_AUTH_DUAL_TRANSPORT_V6
             Le cookie Portail HttpOnly a déjà été validé avant l'accès au module.
             Pour le saut serveur Portail -> Worker Train, le même jeton est
             transmis par le header historique ET par Authorization. Le backend
             n'accepte ce fallback Authorization qu'avec ce marqueur v6. */
          headers.set('X-WfGg-Portal-Token', cookiePortalTrainToken);
          headers.set('Authorization', 'Bearer ' + cookiePortalTrainToken);
          headers.set('X-WfGg-Portal-Bridge', 'cookie-auth-v6');
          apiRequest = new Request(request, { headers });
        }
"""

if 'WFGG_TRAIN_API_COOKIE_AUTH_DUAL_TRANSPORT_V6' not in text:
    assert old in text, 'Train cookie auth bridge anchor not found'
    text = text.replace(old, new, 1)

path.write_text(text)
