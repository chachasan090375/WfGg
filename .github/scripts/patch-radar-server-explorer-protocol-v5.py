#!/usr/bin/env python3
from pathlib import Path

P = Path('/tmp/wfgg-radar/connector-go/internal/protocol/region_scan.go')
s = P.read_text(encoding='utf-8')
if 'redirectPresent' not in s:
    old = '"mapPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "MAP_PACKET_RX"))'
    new = '"mapPacket", serverExplorerNativeStageSeen(stderr.Bytes(), "MAP_PACKET_RX"), "redirectPresent", serverExplorerNativeStageSeen(stderr.Bytes(), "LOGIN_SERVERINFO_REDIRECT_PRESENT"), "redirectDialOK", serverExplorerNativeStageSeen(stderr.Bytes(), "LOGIN_SERVERINFO_REDIRECT_DIAL_OK"), "redirectLoginSent", serverExplorerNativeStageSeen(stderr.Bytes(), "LOGIN_SERVERINFO_REDIRECT_LOGIN_SENT"))'
    n = s.count(old)
    if n != 2:
        raise SystemExit(f'PROTOCOL_V5_ANCHOR expected 2 matches, got {n}')
    s = s.replace(old, new)
    P.write_text(s, encoding='utf-8')
print('SERVER_EXPLORER_PROTOCOL_V5=PATCHED')
print('SERVER_EXPLORER_PROTOCOL_V5_DATA=SAFE_REDIRECT_BOOLEANS_ONLY')
