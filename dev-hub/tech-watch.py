#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("CHACHA_DEV_ROOT", "/opt/chacha-dev"))
CONFIG = ROOT / "platform" / "config"
RADAR = ROOT / "radar"
HISTORY = RADAR / "history"
LATEST = RADAR / "latest.json"
LATEST_TXT = RADAR / "latest.txt"
TARGETS = CONFIG / "tech-watch-targets.json"
UA = "ChaCha-DEV-HUB-Tech-Watch/4.2"
TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def iso_now():
    return now_utc().replace(microsecond=0).isoformat()


def parse_time(value):
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def age_days(value):
    t = parse_time(value)
    if not t:
        return None
    return max(0, (now_utc() - t).days)


def get_json(url, timeout=20):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:500]
        except Exception:
            body = ""
        return e.code, None, body or str(e)
    except Exception as e:
        return 0, None, str(e)


def github_repo(repo):
    status, data, err = get_json(f"https://api.github.com/repos/{repo}")
    if status != 200 or not isinstance(data, dict):
        return {"github": repo, "ok": False, "http": status, "error": err or "repo lookup failed"}

    release_status, release, _ = get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    if release_status != 200 or not isinstance(release, dict):
        release = {}

    return {
        "github": repo,
        "ok": True,
        "archived": bool(data.get("archived")),
        "stars": int(data.get("stargazers_count") or 0),
        "forks": int(data.get("forks_count") or 0),
        "open_issues": int(data.get("open_issues_count") or 0),
        "pushed_at": data.get("pushed_at"),
        "updated_at": data.get("updated_at"),
        "default_branch": data.get("default_branch"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "latest_release": release.get("tag_name"),
        "release_published_at": release.get("published_at"),
        "html_url": data.get("html_url"),
    }


def signal_score(item):
    if not item.get("ok"):
        return 0
    if item.get("archived"):
        return 0
    stars = max(0, int(item.get("stars") or 0))
    star_score = min(40, int(math.log10(stars + 1) * 10))
    push_age = age_days(item.get("pushed_at"))
    if push_age is None:
        freshness = 0
    elif push_age <= 14:
        freshness = 30
    elif push_age <= 60:
        freshness = 24
    elif push_age <= 180:
        freshness = 16
    elif push_age <= 365:
        freshness = 8
    else:
        freshness = 0
    release_age = age_days(item.get("release_published_at"))
    if release_age is None:
        release_score = 5
    elif release_age <= 30:
        release_score = 20
    elif release_age <= 180:
        release_score = 14
    elif release_age <= 365:
        release_score = 8
    else:
        release_score = 2
    license_score = 10 if item.get("license") and item.get("license") != "NOASSERTION" else 0
    return min(100, star_score + freshness + release_score + license_score)


def decision(role, info, policy):
    if not info.get("ok"):
        return "WATCH"
    if info.get("archived"):
        return "URGENT" if role == "installed" else "HOLD"
    if role == "installed":
        pushed = age_days(info.get("pushed_at"))
        if pushed is not None and pushed > 730:
            return "WATCH"
        return "KEEP"
    score = int(info.get("signal_score") or 0)
    if score >= int(policy.get("candidate_pilot_score", 80)):
        return "PILOT"
    if score >= int(policy.get("candidate_watch_score", 65)):
        return "WATCH"
    return "ASSESS"


def inspect_targets(cfg):
    policy = cfg.get("policy", {})
    out = []
    for role in ("installed", "candidates"):
        for target in cfg.get(role, []):
            info = github_repo(target["github"])
            info.update({k: v for k, v in target.items() if k != "github"})
            info["role"] = "installed" if role == "installed" else "candidate"
            info["signal_score"] = signal_score(info)
            info["decision"] = decision(info["role"], info, policy)
            out.append(info)
            time.sleep(0.15)
    return out


def market_scan(cfg):
    max_results = int(cfg.get("policy", {}).get("maximum_market_results_per_query", 5))
    discoveries = []
    for entry in cfg.get("market_queries", []):
        q = urllib.parse.quote(entry.get("query", ""))
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page={max_results}"
        status, data, err = get_json(url)
        if status != 200 or not isinstance(data, dict):
            discoveries.append({"category": entry.get("category"), "ok": False, "http": status, "error": err})
            continue
        for repo in data.get("items", [])[:max_results]:
            discoveries.append({
                "category": entry.get("category"),
                "ok": True,
                "name": repo.get("full_name"),
                "description": repo.get("description"),
                "stars": int(repo.get("stargazers_count") or 0),
                "pushed_at": repo.get("pushed_at"),
                "archived": bool(repo.get("archived")),
                "html_url": repo.get("html_url"),
                "decision": "ASSESS",
            })
        time.sleep(0.4)
    return discoveries


def load_previous():
    try:
        return json.loads(LATEST.read_text()) if LATEST.exists() else None
    except Exception:
        return None


def changes(previous, current_targets):
    old = {}
    if previous:
        for x in previous.get("targets", []):
            old[x.get("github")] = x
    result = []
    for cur in current_targets:
        prev = old.get(cur.get("github"))
        if not prev:
            result.append({"type": "NEW_TARGET", "target": cur.get("name"), "github": cur.get("github")})
            continue
        if cur.get("latest_release") and cur.get("latest_release") != prev.get("latest_release"):
            result.append({
                "type": "NEW_RELEASE",
                "target": cur.get("name"),
                "from": prev.get("latest_release"),
                "to": cur.get("latest_release"),
            })
        if cur.get("archived") and not prev.get("archived"):
            result.append({"type": "ARCHIVED", "target": cur.get("name"), "severity": "URGENT"})
        if cur.get("decision") != prev.get("decision"):
            result.append({
                "type": "DECISION_CHANGED",
                "target": cur.get("name"),
                "from": prev.get("decision"),
                "to": cur.get("decision"),
            })
    return result


def report_text(snapshot):
    lines = []
    lines.append("=== CHACHA TECHNOLOGY WATCH ===")
    lines.append(f"TIME={snapshot['generated_at']}")
    lines.append(f"TARGETS={len(snapshot['targets'])}")
    lines.append(f"DISCOVERIES={len([x for x in snapshot['market'] if x.get('ok')])}")
    lines.append(f"CHANGES={len(snapshot['changes'])}")
    lines.append("")
    lines.append("=== INSTALLED / CANDIDATES ===")
    for x in snapshot["targets"]:
        lines.append(
            f"{x.get('decision','?'):9} | {x.get('role','?'):9} | {x.get('category','?'):24} | "
            f"{x.get('name','?')} | score={x.get('signal_score',0)} | release={x.get('latest_release') or '-'}"
        )
    lines.append("")
    lines.append("=== CHANGES ===")
    if snapshot["changes"]:
        for x in snapshot["changes"]:
            lines.append(json.dumps(x, ensure_ascii=False))
    else:
        lines.append("NO_MATERIAL_CHANGE")
    lines.append("")
    lines.append("=== MARKET DISCOVERY ===")
    seen = set()
    for x in snapshot["market"]:
        if not x.get("ok"):
            lines.append(f"SOURCE_ERROR category={x.get('category')} http={x.get('http')} error={x.get('error')}")
            continue
        key = x.get("name")
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"ASSESS    | {x.get('category','?'):24} | {key} | stars={x.get('stars',0)}")
    lines.append("")
    lines.append("POLICY=No production technology is replaced automatically. PILOT/WATCH are evidence signals, not migration approval.")
    return "\n".join(lines) + "\n"


def run_watch(args):
    if not TARGETS.exists():
        print(f"TECH_WATCH_CONFIG_MISSING={TARGETS}", file=sys.stderr)
        return 2
    cfg = json.loads(TARGETS.read_text())
    previous = load_previous()
    targets = inspect_targets(cfg)
    market = market_scan(cfg) if args.market else []
    snapshot = {
        "schema": "chacha.dev/technology-watch-snapshot/v2",
        "generated_at": iso_now(),
        "policy": cfg.get("policy", {}),
        "targets": targets,
        "market": market,
        "changes": changes(previous, targets),
    }
    HISTORY.mkdir(parents=True, exist_ok=True)
    stamp = now_utc().strftime("%Y%m%dT%H%M%SZ")
    hist = HISTORY / f"technology-watch-{stamp}.json"
    hist.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    LATEST.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n")
    text = report_text(snapshot)
    LATEST_TXT.write_text(text)
    print(text, end="")
    print(f"TECH_WATCH_JSON={LATEST}")
    print(f"TECH_WATCH_REPORT={LATEST_TXT}")
    print(f"TECH_WATCH_HISTORY={hist}")
    print("TECH_WATCH_RUN=OK")
    return 0


def show_report(_args):
    if not LATEST_TXT.exists():
        print("TECH_WATCH_REPORT=NOT_YET_GENERATED")
        return 1
    print(LATEST_TXT.read_text(), end="")
    return 0


def show_status(_args):
    print("=== CHACHA TECH WATCH STATUS ===")
    print(f"CONFIG={'OK' if TARGETS.exists() else 'MISSING'}")
    print(f"LATEST={'OK' if LATEST.exists() else 'NONE'}")
    print(f"HISTORY_DIR={HISTORY}")
    if LATEST.exists():
        try:
            d = json.loads(LATEST.read_text())
            print(f"LAST_RUN={d.get('generated_at','?')}")
            print(f"LAST_CHANGES={len(d.get('changes', []))}")
            print(f"LAST_MARKET={len(d.get('market', []))}")
        except Exception:
            print("LATEST_PARSE=FAIL")
    return 0


def main():
    p = argparse.ArgumentParser(prog="techwatch")
    sp = p.add_subparsers(dest="cmd", required=True)
    r = sp.add_parser("run")
    r.add_argument("--market", action="store_true", help="also perform general GitHub market discovery")
    r.set_defaults(func=run_watch)
    s = sp.add_parser("status")
    s.set_defaults(func=show_status)
    q = sp.add_parser("report")
    q.set_defaults(func=show_report)
    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
