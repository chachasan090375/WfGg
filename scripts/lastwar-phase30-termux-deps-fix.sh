#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# WfGg Last War LAB — Phase 30 Termux dependency repair
# Installs native image headers required by Pillow, then resumes Phase 30.
# No Last War network connection. Package downloads only from Termux/PyPI.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHASE30="$ROOT/scripts/lastwar-phase30-unity-sprite-extraction.sh"
UNITYPY_VERSION="1.25.3"

fail(){ printf 'ERREUR: %s\n' "$*" >&2; exit 1; }
command -v pkg >/dev/null 2>&1 || fail "commande pkg Termux absente"
command -v python >/dev/null 2>&1 || fail "python Termux absent"
[[ -f "$PHASE30" ]] || fail "script Phase 30 introuvable: $PHASE30"

printf '=== WfGg Last War LAB · réparation dépendances Phase 30 ===\n'
printf 'Installation des bibliothèques natives nécessaires à Pillow…\n'

pkg install -y \
  libjpeg-turbo \
  libpng \
  freetype \
  littlecms \
  libwebp \
  openjpeg \
  libtiff \
  zlib

export CPPFLAGS="-I${PREFIX}/include ${CPPFLAGS:-}"
export CFLAGS="-I${PREFIX}/include ${CFLAGS:-}"
export LDFLAGS="-L${PREFIX}/lib ${LDFLAGS:-}"
export PKG_CONFIG_PATH="${PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH:-}"

if ! python - <<'PYTEST' >/dev/null 2>&1
from PIL import Image
PYTEST
then
  printf 'Pillow absent — compilation avec les en-têtes Termux maintenant disponibles…\n'
  python -m pip install --disable-pip-version-check --no-cache-dir Pillow
fi

if ! python - <<'PYTEST' >/dev/null 2>&1
import UnityPy
PYTEST
then
  printf 'UnityPy absent ou installation précédente incomplète — reprise…\n'
  python -m pip install --disable-pip-version-check --no-cache-dir "UnityPy==${UNITYPY_VERSION}"
fi

python - <<'PYTEST'
import UnityPy
from PIL import Image
print("DEPENDENCIES_OK", "UnityPy", getattr(UnityPy,"__version__","?"), "Pillow", getattr(Image,"__version__","?"))
PYTEST

printf 'Dépendances prêtes. Reprise automatique de la Phase 30…\n'
WFGG_PHASE30_NO_INSTALL=1 exec bash "$PHASE30"
