#!/data/data/com.termux/files/usr/bin/bash
set -u
ROOT="$HOME/wfgg-lastwar-preview"
cd "$ROOT" || exit 1

echo "AUDIE_ASTC_V21_RUNNER_START"

# On Android/Termux, UnityPy may be able to expose raw ASTC bytes while its bundled
# native decoder is unavailable.  Prefer a locally-built texture2ddecoder.
python - <<'PY'
try:
 import texture2ddecoder
 print('TEXTURE2DDECODER_OK', texture2ddecoder.__file__)
except Exception as e:
 print('TEXTURE2DDECODER_MISSING', type(e).__name__, e)
PY

if ! python -c 'import texture2ddecoder' >/dev/null 2>&1; then
  echo "TEXTURE2DDECODER_BUILD_ATTEMPT"
  pkg install -y clang make python >/dev/null 2>&1 || true
  python -m pip install --no-cache-dir --force-reinstall --no-binary=:all: texture2ddecoder || true
fi

python scripts/lastwar-audie-astc-v21.py "$ROOT"
