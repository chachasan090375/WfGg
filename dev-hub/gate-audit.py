#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CHACHA_DEV_ROOT", "/opt/chacha-dev"))
REGISTRY = ROOT / "registry" / "manifests"
AUDITS = ROOT / "audits"
GATES = [
    "product", "frontend", "backend", "data", "security", "integrations",
    "testing", "build", "ci_cd", "observability", "performance",
    "backup_recovery", "documentation", "operations",
]

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".cache", ".wrangler", "vendor", "__pycache__"}
TEXT_EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".html", ".css", ".scss", ".json", ".jsonc", ".toml", ".yaml", ".yml", ".md", ".txt", ".sh"}


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def iter_files(base, max_files=8000):
    count = 0
    if not base.exists():
        return
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            yield Path(root) / name
            count += 1
            if count >= max_files:
                return


def rel(path, base):
    try:
        return str(path.relative_to(base))
    except Exception:
        return str(path)


def names(files):
    return {p.name.lower() for p in files}


def paths_lower(files, base):
    return [rel(p, base).lower() for p in files]


def read_small(path, limit=350_000):
    try:
        if path.suffix.lower() not in TEXT_EXTS or path.stat().st_size > limit:
            return ""
        return path.read_text(errors="ignore")
    except Exception:
        return ""


def grep_evidence(files, base, patterns, max_hits=8):
    compiled = [re.compile(x, re.I) for x in patterns]
    hits = []
    for p in files:
        txt = read_small(p)
        if not txt:
            continue
        if any(rx.search(txt) for rx in compiled):
            hits.append(rel(p, base))
            if len(hits) >= max_hits:
                break
    return hits


def pkg_scripts(base):
    out = {}
    for p in iter_files(base, 1500) or []:
        if p.name != "package.json":
            continue
        data = load_json(p)
        if isinstance(data, dict):
            out[rel(p, base)] = data.get("scripts", {}) or {}
    return out


def command_exists(cmd):
    return bool(shutil.which(cmd))


def git_tracked_sensitive(workspace):
    if not (workspace / ".git").exists() or not command_exists("git"):
        return []
    try:
        p = subprocess.run(["git", "-C", str(workspace), "ls-files"], text=True, capture_output=True, timeout=15)
        if p.returncode != 0:
            return []
        risky = []
        for x in p.stdout.splitlines():
            low = x.lower()
            if low.endswith((".pem", ".key", ".p12", ".pfx")) or low in {".env", ".env.production", ".env.prod"}:
                risky.append(x)
        return risky[:20]
    except Exception:
        return []


def gate(status, score, evidence=None, missing=None, notes=None):
    return {
        "status": status,
        "score": max(0, min(100, int(score))),
        "evidence": evidence or [],
        "missing": missing or [],
        "notes": notes or [],
    }


def assess(project, manifest, workspace):
    files = list(iter_files(workspace) or [])
    fnames = names(files)
    plower = paths_lower(files, workspace)
    scripts = pkg_scripts(workspace)
    components = manifest.get("components", [])
    ctypes = " ".join(str(c.get("type", "")).lower() for c in components)
    cnames = " ".join(str(c.get("name", "")).lower() for c in components)
    has_front = any(x in (ctypes + " " + cnames) for x in ["frontend", "web-frontend", "static", "pwa"])
    has_back = any(x in (ctypes + " " + cnames) for x in ["backend", "api", "worker", "server"])
    has_data = any(x in (ctypes + " " + cnames) for x in ["database", "d1", "r2", "storage", "sql"])
    out = {}

    # Product
    req = manifest.get("requirements", {})
    product_ev = []
    if any(req.get(k) for k in ("functional", "non_functional", "constraints")):
        product_ev.append("manifest:requirements")
    product_ev += [p for p in plower if any(k in p for k in ["roadmap", "spec", "requirements", "product", "acceptance"])][:5]
    out["product"] = gate("OK" if len(product_ev) >= 2 else "PARTIAL" if product_ev else "MISSING", 85 if len(product_ev) >= 2 else 50 if product_ev else 10, product_ev, [] if len(product_ev) >= 2 else ["explicit requirements and acceptance criteria"])

    # Frontend
    if not has_front:
        out["frontend"] = gate("NOT_APPLICABLE", 100, notes=["no frontend component declared"])
    else:
        ev = [p for p in plower if p.endswith(("index.html", "manifest.webmanifest", "manifest.json"))][:4]
        ev += grep_evidence(files, workspace, [r"<meta[^>]+viewport", r"aria-", r"serviceWorker", r"@media"], 6)
        score = min(100, 25 + 12 * len(set(ev)))
        out["frontend"] = gate("OK" if score >= 75 else "PARTIAL" if ev else "MISSING", score, sorted(set(ev)), [] if score >= 75 else ["responsive/accessibility/PWA evidence"])

    # Backend
    if not has_back:
        out["backend"] = gate("NOT_APPLICABLE", 100, notes=["no backend/API component declared"])
    else:
        ev = [p for p in plower if p.endswith(("wrangler.toml", "wrangler.json", "wrangler.jsonc")) or "/worker/" in ("/" + p)][:5]
        ev += grep_evidence(files, workspace, [r"fetch\s*\(", r"addEventListener\s*\(\s*['\"]fetch", r"Response\s*\(", r"try\s*\{"], 6)
        score = min(100, 20 + 10 * len(set(ev)))
        out["backend"] = gate("OK" if score >= 75 else "PARTIAL" if ev else "MISSING", score, sorted(set(ev)), [] if score >= 75 else ["API validation/error handling/contract evidence"])

    # Data
    if not has_data:
        out["data"] = gate("NOT_APPLICABLE", 100, notes=["no data component declared"])
    else:
        ev = [p for p in plower if "migration" in p or p.endswith(".sql")][:8]
        data_cfg = manifest.get("data", {})
        if any(data_cfg.get(k) for k in ("databases", "object_storage", "cache", "queues")):
            ev.append("manifest:data")
        score = min(100, 30 + 12 * len(set(ev))) if ev else 15
        out["data"] = gate("OK" if score >= 75 else "PARTIAL" if ev else "MISSING", score, sorted(set(ev)), [] if score >= 75 else ["schema lifecycle, retention, restore evidence"])

    # Security
    risky = git_tracked_sensitive(workspace)
    sec_ev = grep_evidence(files, workspace, [r"authorization", r"bearer\s+", r"cors", r"content-security-policy", r"x-frame-options", r"oauth", r"jwt", r"session"], 8)
    sec_manifest = manifest.get("security", {})
    if any(sec_manifest.get(k) for k in ("authn", "authz", "secrets", "threat_model", "audit")):
        sec_ev.append("manifest:security")
    score = min(100, 35 + 8 * len(set(sec_ev))) if sec_ev else 20
    missing = []
    if risky:
        score = min(score, 35)
        missing.append("tracked sensitive files detected: " + ",".join(risky[:5]))
    if not any("depend" in p and ("workflow" in p or "audit" in p) for p in plower):
        missing.append("dependency/security scanning evidence")
    out["security"] = gate("OK" if score >= 75 and not risky else "PARTIAL" if sec_ev else "MISSING", score, sorted(set(sec_ev)), missing)

    # Integrations
    integ = manifest.get("integrations", {})
    iev = []
    for k in ("source_control", "mcp", "external_apis", "webhooks"):
        if integ.get(k):
            iev.append("manifest:integrations." + k)
    iev += grep_evidence(files, workspace, [r"https://", r"fetch\s*\(", r"webhook"], 4)
    score = min(100, 35 + 12 * len(set(iev))) if iev else 15
    out["integrations"] = gate("OK" if score >= 75 else "PARTIAL" if iev else "MISSING", score, sorted(set(iev)), [] if score >= 75 else ["integration contracts/timeouts/retries evidence"])

    # Testing
    tev = [p for p in plower if any(x in p for x in ["/test/", "/tests/", ".test.", ".spec.", "playwright", "vitest", "jest"]][:12]
    for pkg, sc in scripts.items():
        if any(k in sc for k in ("test", "check", "test:e2e", "lint")):
            tev.append(pkg + ":scripts")
    score = min(100, 20 + 12 * len(set(tev))) if tev else 5
    out["testing"] = gate("OK" if score >= 75 else "PARTIAL" if tev else "MISSING", score, sorted(set(tev)), [] if score >= 75 else ["unit/integration/E2E coverage evidence"])

    # Build
    bev = []
    for pkg, sc in scripts.items():
        if any(k in sc for k in ("build", "deploy", "check")):
            bev.append(pkg + ":scripts")
    bev += [p for p in plower if any(x in p for x in ["wrangler", "vite.config", "webpack", "rollup", "cloudflare"]][:6]
    score = min(100, 30 + 15 * len(set(bev))) if bev else 10
    out["build"] = gate("OK" if score >= 75 else "PARTIAL" if bev else "MISSING", score, sorted(set(bev)), [] if score >= 75 else ["repeatable build/deploy command evidence"])

    # CI/CD
    cev = [p for p in plower if p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))][:12]
    score = min(100, 35 + 20 * len(cev)) if cev else 10
    out["ci_cd"] = gate("OK" if score >= 75 else "PARTIAL" if cev else "MISSING", score, cev, [] if cev else ["CI workflow and protected deployment evidence"])

    # Observability
    oev = grep_evidence(files, workspace, [r"console\.(log|error|warn)", r"logger", r"metrics", r"trace", r"health(check)?", r"sentry", r"telemetry"], 8)
    ops = manifest.get("operations", {})
    if any(ops.get(k) for k in ("health_checks", "logging", "metrics", "alerts")):
        oev.append("manifest:operations")
    score = min(100, 25 + 10 * len(set(oev))) if oev else 10
    out["observability"] = gate("OK" if score >= 75 else "PARTIAL" if oev else "MISSING", score, sorted(set(oev)), [] if score >= 75 else ["health/structured logs/metrics/alerts evidence"])

    # Performance
    pev = [p for p in plower if any(x in p for x in ["lighthouse", "benchmark", "perf", "load-test", "k6", "web-vitals"]][:8]
    pev += grep_evidence(files, workspace, [r"cache-control", r"caches\.default", r"performance\.", r"web-vitals"], 4)
    score = min(100, 20 + 14 * len(set(pev))) if pev else 10
    out["performance"] = gate("OK" if score >= 75 else "PARTIAL" if pev else "MISSING", score, sorted(set(pev)), [] if score >= 75 else ["performance budget/load test/cache strategy evidence"])

    # Backup/recovery
    brev = []
    data_cfg = manifest.get("data", {})
    storage = manifest.get("storage", {})
    if data_cfg.get("backup_restore"):
        brev.append("manifest:data.backup_restore")
    if storage.get("backups"):
        brev.append("manifest:storage.backups")
    brev += [p for p in plower if any(x in p for x in ["backup", "restore", "export", "disaster", "recovery"]][:8]
    score = min(100, 30 + 15 * len(set(brev))) if brev else 5
    out["backup_recovery"] = gate("OK" if score >= 75 else "PARTIAL" if brev else "MISSING", score, sorted(set(brev)), [] if score >= 75 else ["tested restore/RPO/RTO evidence"])

    # Documentation
    dev = [p for p in plower if p.startswith("readme") or p.startswith("docs/") or "/docs/" in ("/" + p) or any(x in p for x in ["architecture", "runbook", "adr-"])][:12]
    score = min(100, 30 + 10 * len(set(dev))) if dev else 10
    out["documentation"] = gate("OK" if score >= 75 else "PARTIAL" if dev else "MISSING", score, sorted(set(dev)), [] if score >= 75 else ["architecture/runbook/ADR evidence"])

    # Operations
    op_ev = []
    if manifest.get("release", {}).get("rollback"):
        op_ev.append("manifest:release.rollback")
    if any(ops.get(k) for k in ("health_checks", "alerts", "cost_quota")):
        op_ev.append("manifest:operations")
    op_ev += [p for p in plower if any(x in p for x in ["runbook", "rollback", "deploy", "health", "incident"]][:8]
    score = min(100, 30 + 12 * len(set(op_ev))) if op_ev else 10
    out["operations"] = gate("OK" if score >= 75 else "PARTIAL" if op_ev else "MISSING", score, sorted(set(op_ev)), [] if score >= 75 else ["runbook/rollback/incident/cost-quota evidence"])

    return out, len(files)


def print_report(report):
    print("=== CHACHA ARCHITECTURE GATE AUDIT V4.4 ===")
    print(f"PROJECT={report['project']}")
    print(f"WORKSPACE={report['workspace']}")
    print(f"FILES_SCANNED={report['files_scanned']}")
    print(f"TIME={report['time']}")
    print()
    for name in GATES:
        g = report["gates"][name]
        print(f"=== GATE {name.upper()} ===")
        print(f"STATUS={g['status']}")
        print(f"SCORE={g['score']}")
        for e in g["evidence"][:10]:
            print(f"EVIDENCE={e}")
        for m in g["missing"][:10]:
            print(f"MISSING={m}")
        for n in g["notes"][:5]:
            print(f"NOTE={n}")
        print()
    statuses = [report["gates"][x]["status"] for x in GATES]
    avg = round(sum(report["gates"][x]["score"] for x in GATES) / len(GATES))
    print("=== SUMMARY ===")
    for s in ("OK", "PARTIAL", "MISSING", "NOT_APPLICABLE"):
        print(f"GATES_{s}={statuses.count(s)}")
    print(f"ARCHITECTURE_EVIDENCE_SCORE={avg}")
    print(f"ACTION_ITEMS={sum(len(report['gates'][x]['missing']) for x in GATES)}")
    print("GATE_AUDIT=OK")


def main():
    ap = argparse.ArgumentParser(prog="gate-audit")
    ap.add_argument("project")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    mp = REGISTRY / f"{args.project}.json"
    manifest = load_json(mp)
    if not manifest:
        raise SystemExit(f"MANIFEST_NOT_FOUND_OR_INVALID={mp}")
    if manifest.get("schema") != "chacha.dev/project-manifest/v2":
        raise SystemExit("GATE_AUDIT_REQUIRES_MANIFEST_V2")

    w = manifest.get("workspace", {})
    workspace = Path(w.get("local") or w.get("path") or "")
    if not str(workspace):
        raise SystemExit("WORKSPACE_NOT_DECLARED")
    if not workspace.exists():
        raise SystemExit(f"WORKSPACE_NOT_FOUND={workspace}")

    gates, scanned = assess(args.project, manifest, workspace)
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "schema": "chacha.dev/architecture-gate-audit/v1",
        "version": "4.4",
        "project": args.project,
        "workspace": str(workspace),
        "time": now,
        "files_scanned": scanned,
        "gates": gates,
    }
    dest = AUDITS / args.project
    hist = dest / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (dest / "latest.json").write_text(json.dumps(report, indent=2) + "\n")
    (hist / f"{stamp}.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
