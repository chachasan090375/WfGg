#!/usr/bin/env python3
import runpy
import subprocess
import sys

# Preserve the already-qualified async/email-auth/account-control patch exactly,
# then layer V6.10 persistence/search, followed by V6.11 fast identity lookup.
runpy.run_path('.github/scripts/patch-radar-async-collector-worker-vpre610.py', run_name='__main__')
subprocess.run([sys.executable, '.github/scripts/patch-radar-worker-collector-index-v610.py'], check=True)
subprocess.run([sys.executable, '.github/scripts/patch-radar-worker-fast-lookup-v611.py'], check=True)
subprocess.run([sys.executable, '.github/scripts/patch-live-radar-fast-lookup-v611.py'], check=True)
print('RADAR_ASYNC_COLLECTOR_WORKER_V611=READY')
