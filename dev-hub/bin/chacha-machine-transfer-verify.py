#!/usr/bin/env python3
import hashlib,sys
from pathlib import Path

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

src,dst=map(sha,sys.argv[1:3])
print("SOURCE_SHA256="+src)
print("DESTINATION_SHA256="+dst)

if src != dst:
    raise SystemExit("TRANSFER_VERIFY=BLOCK")

print("TRANSFER_VERIFY=PASS")
