#!/usr/bin/env python3
from __future__ import annotations

"""V33 LAB server with the proven Android-safe direct decode path.

This is a thin runtime layer over V33-resolved:
- keeps physical availability / exact slice resolution / Unity version detection;
- replaces high-level UnityPy image/mesh exporters with direct Texture2D + MeshHandler;
- streams more real bundles from the selected logical subfolder without retaining them;
- keeps diagnostics when a prefab has no locally available mesh dependency.
"""

from http.server import ThreadingHTTPServer
from pathlib import Path
import importlib.util, json, os, sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
RESOLVED_PATH = ROOT / "scripts/lastwar-global-graphics-server-v33-resolved.py"
DIRECT_PATH = ROOT / "scripts/lastwar-android-safe-render-v33.py"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


resolved = _load("wfgg_v33_resolved", RESOLVED_PATH)
direct = _load("wfgg_v33_androidsafe", DIRECT_PATH)
core = resolved.core

# The old mobile cache remains tiny; these bundles are streamed one by one. Increasing
# this number therefore broadens the exact subfolder search without keeping 48 bundles RAM-resident.
core.MAX_MODEL_BUNDLES = int(os.environ.get("WFGG_V33_MODEL_BUNDLES", "48"))
core.MAX_ASSEMBLY_ASSETS = int(os.environ.get("WFGG_V33_ASSEMBLY_ASSETS", "800"))
core.MAX_MESHES = int(os.environ.get("WFGG_V33_MESHES", "48"))
core.MAX_TEXTURES = int(os.environ.get("WFGG_V33_TEXTURES", "96"))

_original_render_asset = core.v31.render_asset
_original_build_model = core.build_model


def _direct_export_bundle_objects(UnityPy, bundle, outdir, bi, terms, exported, errors):
    """Drop-in replacement for V33's high-level bundle exporter."""
    result = direct.scan_bundle(
        UnityPy, bundle, outdir, bi, terms, core.score_name, core.safe_name,
        max_meshes=core.MAX_MESHES, max_textures=core.MAX_TEXTURES,
    )
    exported.extend(result.get("meshes", []))
    # Texture files are useful to the model viewer even when they are not yet bound to a material.
    exported.extend(result.get("textures", []))
    errors.extend(result.get("errors", []))
    try:
        (outdir / f"diagnostic-b{bi}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
        )
    except Exception:
        pass
    return bool(result.get("loaded"))


# build_model() resolves this global at call time, so monkey-patching it is enough.
core.export_bundle_objects = _direct_export_bundle_objects


def _direct_render_asset(a):
    """2D path: real local bundle -> direct Texture2D/Sprite bytes -> PNG."""
    try:
        import UnityPy
    except Exception as exc:
        raise RuntimeError("UnityPy indisponible: " + str(exc)) from exc

    out = core.v31.RENDER_CACHE / (a["stable_id"] + "-androidsafe.png")
    if out.is_file() and out.stat().st_size > 32:
        return out, {"mode": "android-safe-cache", "stableId": a["stable_id"]}

    bundle, source = core.v31.materialize_bundle(a)
    terms = core.target_terms(a)
    try:
        path, meta = direct.best_raster_from_bundle(UnityPy, bundle, out, terms, core.score_name)
        meta.update({
            "stableId": a["stable_id"],
            "source": source,
            "modeV33": "android-safe-direct-texture",
        })
        return path, meta
    except Exception as direct_error:
        # Keep the legacy path only as a diagnostic fallback. It must never hide the direct error.
        try:
            return _original_render_asset(a)
        except Exception as legacy_error:
            raise RuntimeError(
                "Android-safe direct decode failed: " + str(direct_error) +
                " | legacy fallback: " + str(legacy_error)
            ) from legacy_error


core.v31.render_asset = _direct_render_asset


def _build_model_with_diagnostics(a):
    try:
        model = _original_build_model(a)
        model["rendererMode"] = "android-safe-mesh-handler"
        model["guardrails"] = {
            "generatedGeometry": False,
            "highLevelUnityPyExporter": False,
            "sameLogicalSubfolderAssembly": True,
        }
        return model
    except Exception as exc:
        outdir = core.MODEL_CACHE / a["stable_id"]
        diag = []
        if outdir.is_dir():
            for fp in sorted(outdir.glob("diagnostic-b*.json"))[:16]:
                try:
                    d = json.loads(fp.read_text("utf-8"))
                    diag.append({
                        "bundle": fp.stem,
                        "objects": d.get("objects", {}),
                        "meshes": len(d.get("meshes", [])),
                        "textures": len(d.get("textures", [])),
                        "errors": d.get("errors", [])[:5],
                    })
                except Exception:
                    continue
        raise RuntimeError(
            str(exc) + " | Android-safe diagnostics=" +
            json.dumps(diag, ensure_ascii=False, separators=(",", ":"))[:5000]
        ) from exc


core.build_model = _build_model_with_diagnostics


if __name__ == "__main__":
    url = f"http://127.0.0.1:{core.PORT}/lab/lastwar-global-graphics-viewer-v33.html"
    print("=== WFGG LAST WAR GLOBAL GRAPHICS V33 — ANDROID SAFE DIRECT RENDER ===", flush=True)
    print("V33_RENDERER texture=texture2ddecoder-direct mesh=MeshHandler-direct", flush=True)
    print("V33_MODEL_BUNDLES", core.MAX_MODEL_BUNDLES, "streamed-one-by-one", flush=True)
    print(url, flush=True)
    ThreadingHTTPServer(("127.0.0.1", core.PORT), core.Handler).serve_forever()
