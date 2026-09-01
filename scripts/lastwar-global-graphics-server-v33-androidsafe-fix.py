#!/usr/bin/env python3
from __future__ import annotations

"""WfGg V33 Android runtime compatibility fix.

The Last War Android bundles parsed by UnityPy 1.25.x can expose m_TextureFormat
as a raw integer (for example 50) instead of an IntEnum.  The direct decoder
expects canonical names (ASTC_RGB_6x6, ETC2_RGBA8, ...), so numeric values must
be normalized before decoding.

This wrapper keeps the proven Android-safe renderer and changes only runtime
format normalization.  No generated geometry, no network fallback, no fake
asset substitution.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import importlib.util
import os
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "scripts/lastwar-global-graphics-server-v33-androidsafe.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


srv = _load("wfgg_v33_androidsafe_server", SERVER_PATH)
direct = srv.direct
core = srv.core

# Canonical Unity TextureFormat values used by Last War / Unity 2019.
# Keep an explicit table so the runtime remains robust even when UnityPy returns
# a bare int instead of its TextureFormat IntEnum.
UNITY_TEXTURE_FORMAT_NAMES = {
    1: "Alpha8", 2: "ARGB4444", 3: "RGB24", 4: "RGBA32", 5: "ARGB32",
    6: "ARGBFloat", 7: "RGB565", 8: "BGR24", 9: "R16", 10: "DXT1",
    11: "DXT3", 12: "DXT5", 13: "RGBA4444", 14: "BGRA32", 15: "RHalf",
    16: "RGHalf", 17: "RGBAHalf", 18: "RFloat", 19: "RGFloat", 20: "RGBAFloat",
    21: "YUY2", 22: "RGB9e5Float", 23: "RGBFloat", 24: "BC6H", 25: "BC7",
    26: "BC4", 27: "BC5", 28: "DXT1Crunched", 29: "DXT5Crunched",
    30: "PVRTC_RGB2", 31: "PVRTC_RGBA2", 32: "PVRTC_RGB4", 33: "PVRTC_RGBA4",
    34: "ETC_RGB4", 35: "ATC_RGB4", 36: "ATC_RGBA8",
    41: "EAC_R", 42: "EAC_R_SIGNED", 43: "EAC_RG", 44: "EAC_RG_SIGNED",
    45: "ETC2_RGB", 46: "ETC2_RGBA1", 47: "ETC2_RGBA8",
    48: "ASTC_RGB_4x4", 49: "ASTC_RGB_5x5", 50: "ASTC_RGB_6x6",
    51: "ASTC_RGB_8x8", 52: "ASTC_RGB_10x10", 53: "ASTC_RGB_12x12",
    54: "ASTC_RGBA_4x4", 55: "ASTC_RGBA_5x5", 56: "ASTC_RGBA_6x6",
    57: "ASTC_RGBA_8x8", 58: "ASTC_RGBA_10x10", 59: "ASTC_RGBA_12x12",
    60: "ETC_RGB4_3DS", 61: "ETC_RGBA8_3DS", 62: "RG16", 63: "R8",
    64: "ETC_RGB4Crunched", 65: "ETC2_RGBA8Crunched",
    66: "ASTC_HDR_4x4", 67: "ASTC_HDR_5x5", 68: "ASTC_HDR_6x6",
    69: "ASTC_HDR_8x8", 70: "ASTC_HDR_10x10", 71: "ASTC_HDR_12x12",
    72: "RG32", 73: "RGB48", 74: "RGBA64", 75: "R8_SIGNED",
    76: "RG16_SIGNED", 77: "RGB24_SIGNED", 78: "RGBA32_SIGNED",
    79: "R16_SIGNED", 80: "RG32_SIGNED", 81: "RGB48_SIGNED", 82: "RGBA64_SIGNED",
}


def fixed_fmt_name(tex) -> str:
    value = getattr(tex, "m_TextureFormat", None)
    name = getattr(value, "name", None)
    if name:
        return str(name)
    try:
        ivalue = int(value)
    except Exception:
        return str(value)

    # Prefer UnityPy's own enum when available, then the stable Unity table.
    try:
        from UnityPy.enums.TextureFormat import TextureFormat
        return TextureFormat(ivalue).name
    except Exception:
        return UNITY_TEXTURE_FORMAT_NAMES.get(ivalue, str(ivalue))


direct._fmt_name = fixed_fmt_name

# Runtime contract self-check.  This is the exact failure visible on the phone:
# 50 must be ASTC_RGB_6x6, not the string "50".
class _FmtProbe:
    m_TextureFormat = 50

if fixed_fmt_name(_FmtProbe()) != "ASTC_RGB_6x6":
    raise RuntimeError("V33 texture format normalization self-test failed for Unity format 50")


if __name__ == "__main__":
    url = f"http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html"
    print("=== WFGG LAST WAR GLOBAL GRAPHICS V33 — ANDROID FORMAT FIX ===", flush=True)
    print("V33_TEXTURE_FORMAT 50=ASTC_RGB_6x6 numeric-normalization=ON", flush=True)
    print("V33_RENDERER texture=texture2ddecoder-direct mesh=MeshHandler-direct", flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(("127.0.0.1", core.PORT), core.Handler).serve_forever()
