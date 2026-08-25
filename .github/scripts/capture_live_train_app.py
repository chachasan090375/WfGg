from pathlib import Path
import re
import urllib.request

url = 'https://portal-only-auth.wfgg-train-app.pages.dev/app.js'
source = urllib.request.urlopen(url, timeout=25).read().decode('utf-8', 'replace')

needles = [
    'wfgg_train_session',
    'showTrainEntry',
    'bootApp',
    'appView',
    '/api/snapshot',
    'DOMContentLoaded',
    'localStorage',
]

out = []
for needle in needles:
    out.append(f'===== {needle} =====')
    found = False
    for m in re.finditer(re.escape(needle), source, flags=re.I):
        found = True
        start = max(0, m.start() - 1800)
        end = min(len(source), m.end() + 2600)
        out.append(source[start:end])
        out.append('\n---\n')
        if sum(1 for x in out if x == '\n---\n') >= 30:
            break
    if not found:
        out.append('NOT FOUND')

Path('.debug').mkdir(exist_ok=True)
Path('.debug/train_app_snippets.txt').write_text('\n'.join(out), encoding='utf-8')
print('captured', len(source), 'bytes')
