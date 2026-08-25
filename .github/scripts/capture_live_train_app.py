# Capture focused boot/auth snippets from the exact JavaScript served by WfGg preview.
from pathlib import Path
import re
import urllib.request

url = 'https://train-bridge-phase3.wfgg.pages.dev/train/app.js'
request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 WfGg-Diagnostic/1.0'})
source = urllib.request.urlopen(request, timeout=25).read().decode('utf-8', 'replace')

needles = [
    'const API_BASE',
    'let state',
    'const state',
    'currentUserId',
    'function user(',
    'function saveState(',
    'function loadState(',
    'function api(',
    'async function api(',
    'function syncSnapshot(',
    'async function syncSnapshot(',
    'function refreshRoster(',
    'function bootApp(',
    'async function init(',
]

out = []
for needle in needles:
    out.append(f'===== {needle} =====')
    m = re.search(re.escape(needle), source, flags=re.I)
    if not m:
        out.append('NOT FOUND')
        continue
    start = max(0, m.start() - 1800)
    end = min(len(source), m.start() + 9000)
    out.append(source[start:end])
    out.append('\n---\n')

Path('.debug').mkdir(exist_ok=True)
Path('.debug/train_app_snippets.txt').write_text('\n'.join(out), encoding='utf-8')
print('captured', len(source), 'bytes')
