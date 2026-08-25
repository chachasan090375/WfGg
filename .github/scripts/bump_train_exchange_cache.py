from pathlib import Path
p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
changes=[]
for old,new in [
    ('wfgg_bridge=v13','wfgg_bridge=v14'),
    ("wfgg_train_sw_reset_v1","wfgg_train_sw_reset_v2"),
    ("fresh.searchParams.set('wfgg_fresh','v13')","fresh.searchParams.set('wfgg_fresh','v14')"),
]:
    n=s.count(old)
    if n:
        s=s.replace(old,new)
        changes.append((old,new,n))
if not changes:
    required=['wfgg_bridge=v14','wfgg_train_sw_reset_v2',"fresh.searchParams.set('wfgg_fresh','v14')"]
    if all(x in s for x in required):
        print('WFGG_TRAIN_V14 already fully applied')
        raise SystemExit(0)
    raise SystemExit('v14 cache/reload markers incomplete')
p.write_text(s,encoding='utf-8')
print('WFGG_TRAIN_V14=PATCHED')
for old,new,n in changes:
    print(n,old,'->',new)
