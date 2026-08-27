#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding='utf-8')

old_line = '\tlistenAddr      = ":8080"\n'
if old_line not in text:
    raise SystemExit('expected listenAddr constant not found')
text = text.replace(old_line, '', 1)

marker = '\tstateAAD        = "wfgg-lastwar-state:v1"\n)\n\n'
insert = '''\tstateAAD        = "wfgg-lastwar-state:v1"\n)\n\nvar listenAddr = func() string {\n\tport := strings.TrimSpace(os.Getenv("PORT"))\n\tif port == "" {\n\t\tport = "18080"\n\t}\n\treturn "127.0.0.1:" + port\n}()\n\n'''
if marker not in text:
    raise SystemExit('expected const block marker not found')
text = text.replace(marker, insert, 1)

path.write_text(text, encoding='utf-8')
print('patched broker child runtime for loopback dynamic PORT')
