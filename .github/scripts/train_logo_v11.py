from pathlib import Path

p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
original=s

s=s.replace('/assets/wfgg-logo-vector.svg','/assets/wfgg-logo-mini.svg')
s=s.replace('wfgg_bridge=v10','wfgg_bridge=v11')
s=s.replace("wfgg_fresh','v10'","wfgg_fresh','v11'")

if s==original:
    print('TRAIN_LOGO_V11=ALREADY_APPLIED')
else:
    p.write_text(s,encoding='utf-8')
    print('TRAIN_LOGO_V11=OK')
