#!/usr/bin/env python3
"""Runs a repo's local gates the way CI does and prints only the failures.

Refuses a dirty tree (diff-scoped gates grade commits), enumerates gates from the branch's own
Makefile or package.json, judges each by exit code, and runs the type check last.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MUTATING = {"run-ruff-format", "run-ruff-check", "run-yamlfix", "fix-yamllint"}
SITE_CHECKS = ["lint", "check-prose-blocks", "check:semgrep", "check:patch-coverage"]


def sh(cmd: str, cwd: Path, env: dict | None = None, timeout: int = 1800) -> tuple[int, str]:
    try:
        out = subprocess.run(cmd, shell=True, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return out.returncode, out.stdout + out.stderr
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"


def pr_base(repo: Path) -> str:
    code, out = sh("gh pr view --json baseRefName -q .baseRefName", repo)
    return out.strip() if code == 0 and out.strip() else "main"


def baseline_targets(mk: str) -> set[str]:
    """Targets whose recipe diffs against a baseline commit; semgrep resets the checkout for those, so they run alone."""
    found, target = set(), None
    for line in mk.splitlines():
        m = re.match(r"^([a-z][a-z0-9-]*):", line)
        if m:
            target = m.group(1)
        elif target and "baseline" in line and line.startswith("\t"):
            found.add(target)
    return found


def server_plan(repo: Path, base: str, changed: list[str]) -> tuple[list, list, list, dict]:
    mk = (repo / "Makefile").read_text()
    recipe = re.search(r"^fmt-lint:.*?(?=^\S)", mk, re.S | re.M).group(0)
    members = sorted(set(re.findall(r"\b((?:run|check|lint)-[a-z0-9-]+)", recipe)) - MUTATING - {"run-pyright"})
    extra = [t for t in ("check-semgrep-security", "check-black", "check-isort") if re.search(rf"^{t}:", mk, re.M)]
    if any(f.startswith("alembic/") for f in changed):
        extra.append("lint-migrations")
    targets = sorted(set(members + extra))
    ref = f"origin/{base}"
    vars_ = {v: ref for v in re.findall(r"^([A-Z_]*BASE)\s*\?=", mk, re.M)}
    vars_.update({"BASE": ref, "COMMENT_RATIO_BASE": ref})
    make_vars = " ".join(f"{k}={v}" for k, v in vars_.items())
    env = {**os.environ, "PYTHONPATH": str(repo)}
    serial = baseline_targets(mk)
    first = [("ruff check", "uv run ruff check .")]
    middle = [(t, f"make {t} {make_vars}") for t in targets if t not in serial]
    last = [(t, f"make {t} {make_vars}") for t in targets if t in serial]
    last.append(("type check (pyrefly)", "make run-pyright"))
    return first, middle, last, env


def site_plan(repo: Path, tests: bool, build: bool) -> tuple[list, list, list, dict]:
    scripts = json.loads((repo / "package.json").read_text()).get("scripts", {})
    first = [("check-format", "npm run check-format")] if "check-format" in scripts else []
    middle = [(s, f"npm run {s}") for s in SITE_CHECKS if s in scripts]
    if tests and "test" in scripts:
        middle.append(("test", "npm test -- --silent"))
    last = [("type-check", "npm run type-check")]
    if build:
        last.append(("build", "npm run build"))
    return first, middle, last, dict(os.environ)


def generic_plan(repo: Path) -> tuple[list, list, list, dict]:
    mk = (repo / "Makefile").read_text()
    names = re.findall(r"^([a-z][a-z0-9-]*):", mk, re.M)
    middle = [(n, f"make {n}") for n in names if re.fullmatch(r"(lint|fmt-check|format-check|check(-[a-z0-9-]+)?|test)", n)]
    last = [(n, f"make {n}") for n in names if n in ("typecheck", "type-check", "mypy", "pyright")]
    return [], middle, last, dict(os.environ)


def run_phase(steps: list, repo: Path, env: dict, logs: Path, jobs: int) -> list[dict]:
    def one(step):
        name, cmd = step
        t0 = time.time()
        code, out = sh(cmd, repo, env)
        log = logs / (re.sub(r"[^a-z0-9]+", "-", name.lower()) + ".log")
        log.write_text(f"$ {cmd}\n{out}")
        return {"name": name, "exit": code, "secs": round(time.time() - t0), "log": str(log), "tail": out}
    with ThreadPoolExecutor(jobs) as pool:
        return list(pool.map(one, steps))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=".", help="repo or worktree root")
    ap.add_argument("--base", help="PR base branch (default: the PR's base via gh, else main)")
    ap.add_argument("--tests", action="store_true", help="also run the test suite (site)")
    ap.add_argument("--build", action="store_true", help="also run the production build (site)")
    ap.add_argument("--only", help="regex on gate names, to rerun just those")
    ap.add_argument("--allow-dirty", action="store_true")
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args()

    repo = Path(sh("git rev-parse --show-toplevel", Path(a.repo))[1].strip())
    dirty = sh("git status --porcelain --untracked-files=no", repo)[1].strip()
    if dirty and not a.allow_dirty:
        sys.exit("refused: uncommitted changes. Diff-scoped gates grade commits; commit first.\n" + dirty)
    head = sh("git rev-parse HEAD", repo)[1].strip()
    base = a.base or pr_base(repo)
    sh(f"git fetch -q origin {base}", repo)
    changed = sh(f"git diff --name-only origin/{base}...HEAD", repo)[1].split()
    branch = sh("git rev-parse --abbrev-ref HEAD", repo)[1].strip()

    if (repo / "Makefile").exists() and "check-comment-ratio:" in (repo / "Makefile").read_text():
        kind, plan = "pacific-server", server_plan(repo, base, changed)
    elif (repo / "package.json").exists() and '"next"' in (repo / "package.json").read_text():
        kind, plan = "pacific-site", site_plan(repo, a.tests, a.build)
    elif (repo / "Makefile").exists():
        kind, plan = "generic", generic_plan(repo)
    else:
        sys.exit("no Makefile or package.json to enumerate gates from")
    first, middle, last, env = plan
    if a.only:
        keep = re.compile(a.only)
        first, middle, last = ([s for s in phase if keep.search(s[0])] for phase in (first, middle, last))

    logs = Path.home() / ".claude" / "pr-ready-logs" / re.sub(r"[^A-Za-z0-9._-]+", "_", branch)
    logs.mkdir(parents=True, exist_ok=True)
    print(f"{kind} @ {branch} vs origin/{base}: {len(first) + len(middle) + len(last)} gates, logs in {logs}")
    results = run_phase(first, repo, env, logs, 1) + run_phase(middle, repo, env, logs, a.jobs)
    results += run_phase(last, repo, env, logs, 1)

    now_dirty = sh("git status --porcelain --untracked-files=no", repo)[1].strip()
    now_head = sh("git rev-parse HEAD", repo)[1].strip()
    if now_dirty != dirty or now_head != head:
        print("WARNING: the checkout changed during the run (another session editing it?). These results may not "
              "describe HEAD; use a worktree no other session touches and rerun.\n" + now_dirty)
    failed = [r for r in results if r["exit"] != 0]
    for r in failed:
        tail = "\n    ".join(r["tail"].strip().splitlines()[-25:])
        print(f"\nFAIL {r['name']} (exit {r['exit']}, {r['secs']}s) {r['log']}\n    {tail}")
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed: "
          + (", ".join(r["name"] for r in failed) if failed else "all green"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
