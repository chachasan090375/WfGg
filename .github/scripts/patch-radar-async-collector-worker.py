#!/usr/bin/env python3
import runpy
import subprocess
import sys

# Preserve the already-qualified async/email-auth/account-control patch exactly,
# then layer the V6.10 Collector index search bridge and V6.10.1 immutable
# D1 observation-writer bundle fix on top.
runpy.run_path('.github/scripts/patch-radar-async-collector-worker-vpre610.py', run_name='__main__')
subprocess.run([sys.executable, '.github/scripts/patch-radar-worker-collector-index-v610.py'], check=True)
print('RADAR_ASYNC_COLLECTOR_WORKER_V6101=READY')
