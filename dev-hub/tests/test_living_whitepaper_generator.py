#!/usr/bin/env python3
import importlib.util,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; p=ROOT/'dev-hub/bin/living_whitepaper_generator.py';s=importlib.util.spec_from_file_location('lwg',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
with tempfile.TemporaryDirectory() as td:
 out=Path(td)/'wp'; snap=m.generate(ROOT,Path('/opt/chacha-dev/runtime'),out)
 assert snap['status']=='PASS'; text=(out/'index.html').read_text()
 for token in ['Cartographie L0','Improvement Intelligence','Business plan','Scénarios de valorisation','Concurrence et inspirations']:
  assert token in text,token
 assert (out/'metadata.json').is_file()
print('CHACHA_DEV_LIVING_WHITEPAPER_TEST=PASS')
