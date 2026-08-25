# Capture the exact JavaScript served through the WfGg preview, not the protected upstream.
from pathlib import Path
import re
import urllib.request

url = 'https://train-bridge-phase3.wfgg.pages.dev/train/app.js'
request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 WfGg-Diagnostic/1.0'})
source = urllib.request.urlopen(request, timeout=25).read().decode('utf-8', 'replace')

needles = [
    'wfgg_train_session',
    'showTrainEntry',
    'bootApp',
    'appView',
    '/api/snapshot',
    'DOMContentLoaded',
    'localStorage',
    'loginView',
    'portalView',
]

out = []
separator_count = 0
for needle in needles:
    out.append(f'===== {needle} =====')
    found = False
    for m in re.finditer(re.escape(needle), source, flags=re.I):
        found = True
        start = max(0, m.start() - 2200)
        end = min(len(source), m.end() + 3200)
        out.append(source[start:end])
        out.append('\n---\n')
        separator_count += 1
        if separator_count >= 40:
            break
    if not found:
        out.append('NOT FOUND')

Path('.debug').mkdir(exist_ok=True)
Path('.debug/train_app_snippets.txt').write_text('\n'.join(out), encoding='utf-8')
print('captured', len(source), 'bytes')
