#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import math
import os
import re
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
UA = "ChaCha-DEV-HUB-Tech-Watch/4.3"
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
        "fork": bool(data.get("fork")),
        "stars": int(data.get("stargazers_count") or 0),
        "forks": int(data.get("forks_count") or 0),
        "open_issues": int(data.get("open_issues_count") or 0),
        "pushed_at": data.get("pushed_at"),
        "updated_at": data.get("updated_at"),
        "default_branch": data.get("default_branch"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "topics": data.get("topics") or [],
        "description": data.get("description") or "",
        "latest_release": release.get("tag_name"),
        "release_published_at": release.get("published_at"),
        "html_url": data.get("html_url"),
    }


def signal_score(item):
    if not item.get("ok") or item.get("archived"):
        return 0
    stars = max(0, int(item.get("stars") or 0))
    star_score = min(35, int(math.log10(stars + 1) * 9))
    push_age = age_days(item.get("pushed_at"))
    freshness = 0 if push_age is None else 30 if push_age <= 14 else 24 if push_age <= 60 else 16 if push_age <= 180 else 8 if push_age <= 365 else 0
    release_age = age_days(item.get("release_published_at"))
    release_score = 5 if release_age is None else 20 if release_age <= 30 else 14 if release_age <= 180 else 8 if release_age <= 365 else 2
    license_score = 10 if item.get("license") and item.get("license") != "NOASSERTION" else 0
    return min(100, star_score + freshness + release_score + license_score)


def decision(role, info, policy):
    if not info.get("ok"):
        return "WATCH"
    if info.get("archived"):
        return "URGENT" if role == "installed" else "HOLD"
    if role == "installed":
        pushed = age_days(info.get("pushed_at"))
        return "WATCH" if pushed is not None and pushed > 730 else "KEEP"
    score = int(info.get("signal_score") or 0)
    if score >= int(policy.get("candidate_watch_score", 80)):
        return "WATCH"
    if score >= int(policy.get("candidate_assess_score", 60)):
        return "ASSESS"
    return "HOLD"


def inspect_targets(cfg):
    policy = cfg.get("policy", {})
    out = []
    for group in ("installed", "candidates"):
        for target in cfg.get(group, []):
            info = github_repo(target["github"])
            info.update({k: v for k, v in target.items() if k != "github"})
            info["role"] = "installed" if group == "installed" else "candidate"
            info["confidence"] = target.get("confidence", "curated")
            info["signal_score"] = signal_score(info)
            info["decision"] = decision(info["role"], info, policy)
            out.append(info)
            time.sleep(0.12)
    return out


def normalize_text(repo):
    parts = [repo.get("full_name") or "", repo.get("name") or "", repo.get("description") or ""]
    parts.extend(repo.get("topics") or [])
    return " ".join(parts).lower()


def relevant(repo, query_cfg, policy):
    if repo.get("archived") or repo.get("fork"):
        return False, "archived_or_fork"
    stars = int(repo.get("stargazers_count") or 0)
    if stars < int(policy.get("market_min_stars", 750)):
        return False, "stars"
    age = age_days(repo.get("pushed_at"))
    if age is not None and age > int(policy.get("market_max_push_age_days", 365)):
        return False, "stale"
    text = normalize_text(repo)
    excludes = [x.lower() for x in query_cfg.get("exclude_any", [])]
    if any(x in text for x in excludes):
        return False, "excluded_term"
    includes = [x.lower() for x in query_cfg.get("include_any", [])]
    if includes and not any(x in text for x in includes):
        return False, "irrelevant"
    return True, "ok"


def market_scan(cfg):
    policy = cfg.get("policy", {})
    request_max = int(policy.get("maximum_market_results_per_query", 12))
    keep_max = int(policy.get("maximum_market_results_per_category", 5))
    discoveries = []
    for entry in cfg.get("market_queries", []):
        q = urllib.parse.quote(entry.get("query", ""))
        url = f"https://api.github.com/search/repositories?q={q}&sort=updated&order=desc&per_page={request_max}"
        status, data, err = get_json(url)
        if status != 200 or not isinstance(data, dict):
            discoveries.append({"category": entry.get("category"), "ok": False, "http": status, "error": err})
            continue
        kept = 0
        for repo in data.get("items", []):
            ok, reason = relevant(repo, entry, policy)
            if not ok:
                continue
            discoveries.append({
                "category": entry.get("category"),
                "ok": True,
                "name": repo.get("full_name"),
                "description": repo.get("description"),
                "stars": int(repo.get("stargazers_count") or 0),
                "pushed_at": repo.get("pushed_at"),
                "archived": bool(repo.get("archived")),
                "fork": bool(repo.get("fork")),
                "html_url": repo.get("html_url"),
                "confidence": "discovery",
                "decision": "ASSESS",
                "relevance": reason,
            })
            kept += 1
            if kept >= keep_max:
                break
        time.sleep(0.35)
    return discoveries


def load_previous():
    try:
        return json.loads(LATEST.read_text()) if LATEST.exists() else None
    except Exception:
        return None


def changes(previous, current_targets):
    if not previous:
        return []
    old = {x.get("github"): x for x in previous.get("targets", [])}
    result = []
    for cur in current_targets:
        prev = old.get(cur.get("github"))
        if not prev:
            result.append({"type":"TARGET_ADDED","target":cur.get("name"),"github":cur.get("github")})
            continue
        if cur.get("latest_release") and cur.get("latest_release") != prev.get("latest_release"):
            result.append({"type":"NEW_RELEASE","target":cur.get("name"),"from":prev.get("latest_release"),"to":cur.get("latest_release")})
        if cur.get("archived") and not prev.get("archived"):
            result.append({"type":"ARCHIVED","target":cur.get("name"),"severity":"URGENT"})
        if cur.get("decision") != prev.get("decision"):
            result.append({"type":"DECISION_CHANGED","target":cur.get("name"),"from":prev.get("decision"),"to":cur.get("decision")})
    return result


def report_text(snapshot):
    lines = ["=== CHACHA TECHNOLOGY WATCH V4.3 ===", f"TIME={snapshot['generated_at']}", f"TARGETS={len(snapshot['targets'])}", f"DISCOVERIES={len([x for x in snapshot['market'] if x.get('ok')])}", f"CHANGES={len(snapshot['changes'])}", "", "=== INSTALLED / CURATED CANDIDATES ==="]
    for x in snapshot["targets"]:
        lines.append(f"{x.get('decision','?'):9} | {x.get('role','?'):9} | {x.get('category','?'):24} | {x.get('name','?')} | score={x.get('signal_score',0)} | confidence={x.get('confidence','?')} | release={x.get('latest_release') or '-'}")
    lines += ["", "=== MATERIAL CHANGES ==="]
    lines.extend(json.dumps(x, ensure_ascii=False) for x in snapshot["changes"]) if snapshot["changes"] else lines.append("NO_MATERIAL_CHANGE")
    lines += ["", "=== FILTERED MARKET DISCOVERY ==="]
    seen = set()
    for x in snapshot["market"]:
        if not x.get("ok"):
            lines.append(f"SOURCE_ERROR category={x.get('category')} http={x.get('http')} error={x.get('error')}")
            continue
        key = x.get("name")
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"ASSESS    | {x.get('category','?'):24} | {key} | stars={x.get('stars',0)} | confidence=discovery")
    lines += ["", "POLICY=Discovery is not recommendation. PILOT/RECOMMEND require comparative engineering evidence and explicit approval. No production replacement is automatic."]
    return "\n".join(lines) + "\n"


def run_watch(args):
    if not TARGETS.exists():
        print(f"TECH_WATCH_CONFIG_MISSING={TARGETS}", file=sys.stderr)
        return 2
    cfg = json.loads(TARGETS.read_text())
    previous = load_previous()
    targets = inspect_targets(cfg)
    market = market_scan(cfg) if args.market else []
    snapshot = {"schema":"chacha.dev/technology-watch-snapshot/v3","generated_at":iso_now(),"policy":cfg.get("policy",{}),"targets":targets,"market":market,"changes":changes(previous, targets)}
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
    r = sp.add_parser("run"); r.add_argument("--market", action="store_true"); r.set_defaults(func=run_watch)
    s = sp.add_parser("status"); s.set_defaults(func=show_status)
    q = sp.add_parser("report"); q.set_defaults(func=show_report)
    args = p.parse_args(); raise SystemExit(args.func(args))

if __name__ == "__main__":
    main()
