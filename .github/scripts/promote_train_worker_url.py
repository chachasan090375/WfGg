from pathlib import Path

OLD='https://portal-auth-phase1-wfgg-train.chachasan090375.workers.dev'
NEW='https://wfgg-train.chachasan090375.workers.dev'

paths=[
    Path('frontend/_worker.js'),
    Path('frontend/portal-v070.js'),
]

changed=[]
for p in paths:
    s=p.read_text(encoding='utf-8')
    n=s.count(OLD)
    if n:
        s=s.replace(OLD,NEW)
        p.write_text(s,encoding='utf-8')
        changed.append((str(p),n))

if not changed:
    raise SystemExit('production Worker URL already applied or old URL missing')

print('PROMOTE_TRAIN_WORKER_URL=OK')
for path,n in changed:
    print(path,n)
