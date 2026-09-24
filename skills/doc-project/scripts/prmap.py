#!/usr/bin/env python3
"""PR map state for a doc-project doc: prints only the PRs whose state changed since the last refresh.

State lives under "prs" in ~/.claude/doc-projects/<doc_id>.json, keyed by PR url.
"""
import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "doc-projects"
FIELDS = "number,title,state,isDraft,reviewDecision,mergeable,headRefOid,baseRefName,statusCheckRollup"


def _load(doc_id: str) -> tuple[Path, dict]:
    p = STATE_DIR / f"{doc_id}.json"
    if not p.exists():
        sys.exit(f"no state for {doc_id}; run bookmark.py init first")
    return p, json.loads(p.read_text())


def _gh(*args: str) -> dict | list:
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(out.stderr.strip())
    return json.loads(out.stdout)


def _checks(rollup: list[dict]) -> str:
    counts = {"pass": 0, "fail": 0, "pending": 0}
    for c in rollup or []:
        verdict = (c.get("conclusion") or c.get("state") or "").upper()
        if verdict in ("SUCCESS", "NEUTRAL", "SKIPPED"):
            counts["pass"] += 1
        elif verdict in ("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"):
            counts["fail"] += 1
        else:
            counts["pending"] += 1
    if not any(counts.values()):
        return "no checks"
    return ", ".join(f"{n} {k}" for k, n in counts.items() if n)


def snapshot(url: str) -> dict:
    d = _gh("pr", "view", url, "--json", FIELDS)
    state = "draft" if d["isDraft"] and d["state"] == "OPEN" else d["state"].lower()
    return {
        "number": d["number"], "title": d["title"], "state": state, "base": d["baseRefName"],
        "review": (d.get("reviewDecision") or "none").lower(), "mergeable": d.get("mergeable", "").lower(),
        "checks": _checks(d.get("statusCheckRollup")), "head": d["headRefOid"][:10],
    }


def cmd_add(a: argparse.Namespace) -> None:
    p, s = _load(a.doc_id)
    prs = s.setdefault("prs", {})
    for url in a.urls:
        if not re.match(r"https://github\.com/[^/]+/[^/]+/pull/\d+", url):
            sys.exit(f"not a PR url: {url}")
        prs.setdefault(url, {})
    p.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n")
    print(f"{len(prs)} PRs in the map")


def cmd_refresh(a: argparse.Namespace) -> None:
    p, s = _load(a.doc_id)
    prs = s.get("prs", {})
    if not prs:
        sys.exit("no PRs in the map; add them with prmap.py add")
    with ThreadPoolExecutor(8) as pool:
        fresh = dict(zip(prs, pool.map(lambda u: _try(snapshot, u), prs)))
    changed = 0
    for url, new in fresh.items():
        old = prs[url]
        if "error" in new:
            print(f"{url}: could not read ({new['error']})")
            continue
        diffs = [f"{k} {old.get(k, '?')} -> {new[k]}" for k in ("state", "review", "mergeable", "checks", "base")
                 if old.get(k) != new[k] and "unknown" not in (old.get(k), new[k])]
        if old.get("head") and old["head"] != new["head"]:
            diffs.append("new commits: move Invariants rows whose Evidence points here to Recheck")
        if new["mergeable"] == "conflicting":
            diffs.append("CONFLICTING: CI runs nothing until the base is merged in")
        if diffs:
            changed += 1
            print(f"#{new['number']} {new['title'][:60]} ({url})\n  " + "\n  ".join(diffs))
        prs[url] = new
    p.write_text(json.dumps(s, indent=2, sort_keys=True) + "\n")
    print(f"{changed} of {len(prs)} PRs changed" if changed else f"no change across {len(prs)} PRs")


def cmd_discover(a: argparse.Namespace) -> None:
    _, s = _load(a.doc_id)
    known = set(s.get("prs", {}))
    repos = sorted({re.match(r"https://github\.com/([^/]+/[^/]+)/", u).group(1) for u in known})
    for repo in repos:
        for pr in _gh("pr", "list", "--repo", repo, "--author", "@me", "--state", "open",
                      "--json", "url,title,headRefName"):
            if pr["url"] not in known:
                print(f"not in the map: {pr['url']} {pr['title'][:60]} ({pr['headRefName']})")


def _try(fn, arg):
    try:
        return fn(arg)
    except Exception as e:
        return {"error": str(e)[:120]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("add"); p.add_argument("doc_id"); p.add_argument("urls", nargs="+"); p.set_defaults(fn=cmd_add)
    p = sub.add_parser("refresh"); p.add_argument("doc_id"); p.set_defaults(fn=cmd_refresh)
    p = sub.add_parser("discover", help="open PRs of mine in the map's repos that the map lacks")
    p.add_argument("doc_id"); p.set_defaults(fn=cmd_discover)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
