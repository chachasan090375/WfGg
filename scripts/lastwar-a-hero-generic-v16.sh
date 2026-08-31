#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$HOME/wfgg-lastwar-preview"
python scripts/lastwar-a-hero-generic-v16.py
printf '\nVIEWER=http://127.0.0.1:8788/lab/lastwar-a-hero-generic-v16.html?v=16\n'
