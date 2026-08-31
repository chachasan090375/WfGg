#!/usr/bin/env python3
import ipaddress, json, re, sys
from pathlib import Path

p = Path(sys.argv[1])
d = json.loads(p.read_text(encoding='utf-8'))

infra_re = re.compile(r'(?i)(FORMATION_STRACE_DEPLOY_PROBE|REMOTE_STRACE|STRACE_PREP|WFGG_OMNITRACE|ADB_DEVICE|ADB_CONNECTED|device=\d{1,3}(?:\.\d{1,3}){3}:\d+)')

def infra_candidate(r):
    examples = r.get('examples') or []
    texts = [str(e.get('text','')) for e in examples]
    if texts and all(infra_re.search(t) for t in texts):
        return True
    tok = str(r.get('token',''))
    m = re.fullmatch(r'((?:\d{1,3}\.){3}\d{1,3}):(\d{2,5})', tok)
    if m and any(infra_re.search(t) for t in texts):
        return True
    return False

orig = d.get('candidates') or []
bad_tokens = {str(r.get('token','')) for r in orig if infra_candidate(r)}
clean = [r for r in orig if not infra_candidate(r)]

# Recompute all candidate-derived views after removing our own probes.
d['candidates'] = clean
d['candidateCount'] = len(clean)
d['strong'] = [r for r in clean if r.get('confidence') == 'FORTE'][:80]
d['strongCount'] = len([r for r in clean if r.get('confidence') == 'FORTE'])
d['crossSource'] = [r for r in clean if int(r.get('sourceCount') or 0) >= 2][:120]
d['crossSourceCount'] = len([r for r in clean if int(r.get('sourceCount') or 0) >= 2])
d['paths'] = [r for r in clean if '/' in str(r.get('token','')) or re.search(r'(?i)(\.bundle$|\.ab$|gamers_)', str(r.get('token','')))][:150]

# Exact endpoints that were discovered only through our deployment probe are infrastructure, not game traffic.
d['network'] = [n for n in (d.get('network') or []) if str(n.get('endpoint','')) not in bad_tokens]
d['networkCount'] = len(d['network'])

# Diagnostic/preparation logs are useful for method health but never runtime evidence.
def good_ev(e):
    f = str(e.get('file',''))
    t = str(e.get('text',''))
    if f.startswith(('strace-prep','strace-start','perfetto-start','simpleperf-start')):
        return False
    if infra_re.search(t):
        return False
    return True

d['evidence'] = [e for e in (d.get('evidence') or []) if good_ev(e)]
d['noiseEvidence'] = [e for e in (d.get('noiseEvidence') or []) if good_ev(e)]
d['evidenceCount'] = len(d['evidence']) + len(d['noiseEvidence'])

strong = d['strongCount']
cross = d['crossSourceCount']
d['verdict'] = ('CROSS_SOURCE_STRONG_EVIDENCE' if strong and cross else
                'LOW_LEVEL_EVIDENCE' if strong else
                'MULTI_SOURCE_SIGNALS' if cross else
                'CAPTURED_NO_STRONG_CORRELATION')
d['sanitizerVersion'] = 2
d['excludedInfrastructureTokens'] = sorted(t for t in bad_tokens if t)

p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
print(f"OMNITRACE_SANITIZED_V2 excluded={len(bad_tokens)} strong={d['strongCount']} cross={d['crossSourceCount']} candidates={d['candidateCount']} verdict={d['verdict']}")
