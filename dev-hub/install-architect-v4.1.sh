#!/bin/bash
set -euo pipefail

ROOT="${CHACHA_DEV_ROOT:-/opt/chacha-dev}"
BIN="$ROOT/platform/bin"
CFG="$ROOT/platform/config"
DOC="$ROOT/platform/docs"
AGENT="$ROOT/agents/chacha-dev-architect"
BASE="https://raw.githubusercontent.com/chachasan090375/WfGg/dev-hub-v4.1/dev-hub"

mkdir -p "$BIN" "$CFG" "$DOC" "$AGENT"

curl -fsSL "$BASE/architectctl.py" -o "$BIN/architectctl.py"
curl -fsSL "$BASE/technology-radar.json" -o "$CFG/technology-radar.json"
curl -fsSL "$BASE/tech-watch-sources.json" -o "$CFG/tech-watch-sources.json"
curl -fsSL "$BASE/ARCHITECTURE_BLUEPRINT_V4_1.md" -o "$DOC/ARCHITECTURE_BLUEPRINT_V4_1.md"
curl -fsSL "$BASE/agents/chacha-dev-architect.md" -o "$AGENT/AGENT.md"
curl -fsSL "$BASE/project-manifest-v2.example.json" -o "$DOC/project-manifest-v2.example.json"

chmod 755 "$BIN/architectctl.py"
chmod 644 "$CFG/technology-radar.json" "$CFG/tech-watch-sources.json"
chmod 644 "$DOC/ARCHITECTURE_BLUEPRINT_V4_1.md" "$DOC/project-manifest-v2.example.json" "$AGENT/AGENT.md"
ln -sfn "$BIN/architectctl.py" /usr/local/bin/architectctl

python3 -m py_compile "$BIN/architectctl.py"
python3 -m json.tool "$CFG/technology-radar.json" >/dev/null
python3 -m json.tool "$CFG/tech-watch-sources.json" >/dev/null
python3 -m json.tool "$DOC/project-manifest-v2.example.json" >/dev/null

echo "ARCHITECT_INSTALL=OK"
echo "ARCHITECT_BIN=/usr/local/bin/architectctl"
echo "ARCHITECT_AGENT=$AGENT/AGENT.md"
echo "ARCHITECT_BLUEPRINT=$DOC/ARCHITECTURE_BLUEPRINT_V4_1.md"
echo "TECH_RADAR=$CFG/technology-radar.json"
echo "TECH_WATCH=$CFG/tech-watch-sources.json"

echo
echo "=== ARCHITECT STATUS ==="
architectctl status || true

echo
echo "=== RADAR ==="
architectctl radar || true

echo
echo "=== WATCH PLAN ==="
architectctl watch-plan || true

echo
echo "=== CHACHA DEV ARCHITECT READY ==="
