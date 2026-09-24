#!/usr/bin/env python3
"""PR helpers for pr-ready: one-line status, unresolved review comments, and waiting on CI.

Exit codes: 0 ok or green, 1 a check failed, 2 timed out, 3 merged, closed or conflicting.
"""
import argparse
import json
import re
import subprocess
import sys
import time

# Check names that fail for infrastructure reasons; one rerun, then treated as real.
KNOWN_FLAKES = [r"connector-policy", r"check-connector-safeguards", r"build-base"]
FAILED = {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "STARTUP_FAILURE"}
PASSED = {"SUCCESS", "NEUTRAL", "SKIPPED"}


def gh(*args: str) -> str:
    out = subprocess.run(["gh", *args], capture_output=True, text=True)
    if out.returncode:
        sys.exit(f"gh {' '.join(args[:3])}: {out.stderr.strip()}")
    return out.stdout


def parse(url: str) -> tuple[str, str, int]:
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not m:
        sys.exit(f"not a PR url: {url}")
    return m.group(1), m.group(2), int(m.group(3))


def view(url: str) -> dict:
    return json.loads(gh("pr", "view", url, "--json",
                         "number,state,isDraft,baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus,"
                         "reviewDecision,statusCheckRollup"))


def verdict(check: dict) -> str:
    v = (check.get("conclusion") or check.get("state") or "").upper()
    return "pass" if v in PASSED else "fail" if v in FAILED else "pending"


def cmd_status(a: argparse.Namespace) -> None:
    d = view(a.url)
    checks = [verdict(c) for c in d.get("statusCheckRollup") or []]
    counts = {k: checks.count(k) for k in ("pass", "fail", "pending") if checks.count(k)}
    print(f"#{d['number']} {d['state'].lower()}{' draft' if d['isDraft'] else ''} | {d['headRefName']} -> "
          f"{d['baseRefName']} | {d['mergeable'].lower()} ({d['mergeStateStatus'].lower()}) | review "
          f"{(d.get('reviewDecision') or 'none').lower()} | checks {counts or 'none'} | head {d['headRefOid'][:10]}")
    if d["state"] != "OPEN":
        sys.exit(3)
    if d["mergeable"] == "CONFLICTING":
        print("CONFLICTING: CI runs nothing until the base is merged in")
        sys.exit(3)


THREADS = """query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){
reviewThreads(first:100){nodes{id isResolved isOutdated path line comments(first:20){nodes{author{login} body url}}}}
reviews(last:50){nodes{author{login} state body url}}
comments(last:50){nodes{author{login} body url}}}}}"""


def cmd_threads(a: argparse.Namespace) -> None:
    owner, repo, num = parse(a.url)
    me = gh("api", "user", "-q", ".login").strip()
    pr = json.loads(gh("api", "graphql", "-f", f"query={THREADS}", "-F", f"o={owner}", "-F", f"r={repo}",
                       "-F", f"n={num}"))["data"]["repository"]["pullRequest"]
    open_threads = [t for t in pr["reviewThreads"]["nodes"] if not t["isResolved"]]
    print(f"{len(open_threads)} unresolved inline threads")
    for t in open_threads:
        c = t["comments"]["nodes"]
        last = c[-1]["author"]["login"] if c else "?"
        waiting = "answered by me" if last == me else "needs a reply"
        print(f"- {t['path']}:{t['line'] or '?'}{' (outdated)' if t['isOutdated'] else ''} | {c[0]['author']['login']} "
              f"| {len(c)} comments, {waiting} | thread {t['id']}\n    {_one(c[0]['body'])}\n    {c[0]['url']}")
    tops = [r for r in pr["reviews"]["nodes"] if r["body"].strip() and r["author"]["login"] != me]
    tops += [c for c in pr["comments"]["nodes"] if c["author"]["login"] != me]
    print(f"{len(tops)} top-level review comments by others")
    for r in tops:
        print(f"- {r['author']['login']}{' ' + r['state'].lower() if r.get('state') else ''}: {_one(r['body'])}\n    {r['url']}")


def _one(body: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip()[:220]


def cmd_wait(a: argparse.Namespace) -> None:
    deadline = time.time() + a.timeout
    rerun: set[str] = set()
    last_green = None
    while True:
        d = view(a.url)
        if d["state"] != "OPEN":
            print(f"PR is {d['state'].lower()}")
            sys.exit(3)
        checks = d.get("statusCheckRollup") or []
        if not checks and d["mergeable"] == "CONFLICTING":
            print("no checks: the PR is CONFLICTING, so CI runs nothing. Merge the base in first.")
            sys.exit(3)
        by = {"pass": [], "fail": [], "pending": []}
        for c in checks:
            by[verdict(c)].append(c)
        flaky = [c for c in by["fail"] if _name(c) not in rerun and any(re.search(p, _name(c)) for p in KNOWN_FLAKES)]
        for c in flaky:
            rerun.add(_name(c))
            run_id = re.search(r"/actions/runs/(\d+)", c.get("detailsUrl") or "")
            if run_id:
                subprocess.run(["gh", "run", "rerun", run_id.group(1), "--failed", "--repo",
                                "/".join(parse(a.url)[:2])], capture_output=True)
                print(f"known flake, rerunning once: {_name(c)}")
            else:
                print(f"known flake, cannot rerun from here (not a GitHub Actions run): {_name(c)} {c.get('detailsUrl', '')}")
        real = [c for c in by["fail"] if c not in flaky]
        if real and not by["pending"]:
            for c in real:
                print(f"FAIL {_name(c)} {c.get('detailsUrl') or c.get('targetUrl') or ''}")
            print(f"{len(by['pass'])} passed, {len(real)} failed")
            sys.exit(1)
        if checks and not by["pending"] and not by["fail"]:
            if last_green == (d["headRefOid"], len(by["pass"])):
                print(f"green: {len(by['pass'])} checks on {d['headRefOid'][:10]}, same count on two polls")
                sys.exit(0)
            last_green = (d["headRefOid"], len(by["pass"]))
        else:
            last_green = None
        if time.time() > deadline:
            print(f"timed out: {len(by['pending'])} pending, {len(by['fail'])} failed")
            sys.exit(2)
        time.sleep(a.interval)


def _name(c: dict) -> str:
    return c.get("name") or c.get("context") or "?"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    for name, fn in (("status", cmd_status), ("threads", cmd_threads), ("wait", cmd_wait)):
        p = sub.add_parser(name)
        p.add_argument("url")
        p.set_defaults(fn=fn)
        if name == "wait":
            p.add_argument("--interval", type=int, default=120)
            p.add_argument("--timeout", type=int, default=7200)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
