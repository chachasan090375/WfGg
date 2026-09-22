#!/usr/bin/env python3
from pathlib import Path
import shutil

ROOT=Path('/tmp/wfgg-radar')
MAIN=ROOT/'connector-go/cmd/radar-connector/main.go'
SRC=Path('.radar-release-src/v624-source/connector-go/cmd/radar-connector')
DST=ROOT/'connector-go/cmd/radar-connector'
marker='// WFGG_RADAR_MESSENGER_OUTBOX_BRIDGE_V624'

for name in ['messenger_outbox_v624.go','messenger_outbox_v624_test.go']:
    shutil.copy2(SRC/name,DST/name)

text=MAIN.read_text(encoding='utf-8')
if marker not in text:
    anchor='\tmux.HandleFunc("GET /v1/collector/search/status", s.signed(s.collectorSearchStatus))\n'
    if text.count(anchor)!=1:
        raise SystemExit(f'V624_CONNECTOR_ROUTE_ANCHOR_COUNT={text.count(anchor)}')
    add=(
        '\n\t'+marker+'\n'
        '\tmux.HandleFunc("POST /v1/messenger/outbox/create", s.signed(s.messengerOutboxCreateV624))\n'
        '\tmux.HandleFunc("POST /v1/messenger/outbox/queue", s.signed(s.messengerOutboxQueueV624))\n'
        '\tmux.HandleFunc("POST /v1/messenger/outbox/cancel", s.signed(s.messengerOutboxCancelV624))\n'
        '\tmux.HandleFunc("GET /v1/messenger/outbox/status", s.signed(s.messengerOutboxStatusV624))\n'
        '\tmux.HandleFunc("GET /v1/messenger/outbox/list", s.signed(s.messengerOutboxListV624))\n'
    )
    text=text.replace(anchor,anchor+add,1)
MAIN.write_text(text,encoding='utf-8')
print('RADAR_V624_CONNECTOR_OUTBOX_BRIDGE=READY')
print('RADAR_V624_LASTWAR_MUTATION=NO')
