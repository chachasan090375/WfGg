# Capture focused boot/auth functions from the exact JavaScript served by WfGg preview.
from pathlib import Path
import urllib.request

url = 'https://train-bridge-phase3.wfgg.pages.dev/train/app.js'
request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 WfGg-Diagnostic/1.0'})
source = urllib.request.urlopen(request, timeout=25).read().decode('utf-8', 'replace')

Path('.debug').mkdir(exist_ok=True)

def capture(name, needle, before=1200, after=6500):
    pos = source.find(needle)
    if pos < 0:
        text = 'NOT FOUND: ' + needle
    else:
        text = source[max(0,pos-before):min(len(source),pos+after)]
    Path('.debug', name).write_text(text, encoding='utf-8')

capture('train_api.txt', 'async function api(', 600, 5200)
capture('train_sync.txt', 'async function syncSnapshot(', 900, 7600)
capture('train_init.txt', 'async function init(', 900, 8500)
capture('train_state.txt', 'function loadState(', 900, 5200)
print('captured', len(source), 'bytes')
