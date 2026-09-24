#!/usr/bin/env python3
"""PreToolUse hook on Bash: denies any git push that would land on main or master."""
import json
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "master"}


def _branch(path: str) -> str:
    out = subprocess.run(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip()


def _dest(refspec: str) -> str:
    ref = refspec.lstrip("+").split(":")[-1]
    return re.sub(r"^refs/heads/", "", ref)


def check(command: str, cwd: str) -> str | None:
    where = cwd
    for seg in re.split(r"&&|\|\||;|\n|\|", command):
        try:
            tokens = shlex.split(seg)
        except ValueError:
            tokens = seg.split()
        if len(tokens) >= 2 and tokens[0] == "cd":
            where = tokens[1] if tokens[1].startswith("/") else f"{where}/{tokens[1]}"
            continue
        if "git" not in tokens or "push" not in tokens:
            continue
        repo = where
        if "-C" in tokens:
            repo = tokens[tokens.index("-C") + 1]
        args = tokens[tokens.index("push") + 1:]
        if {"--all", "--mirror"} & set(args):
            return "push --all/--mirror includes main"
        positional = [t for t in args if not t.startswith("-")]
        refspecs = positional[1:]
        if refspecs:
            hit = [r for r in refspecs if _dest(r) in PROTECTED or (_dest(r) == "HEAD" and _branch(repo) in PROTECTED)]
            if hit:
                return f"push to {', '.join(hit)}"
        elif _branch(repo) in PROTECTED:
            return f"push from {_branch(repo)} with no refspec"
    return None


def main() -> None:
    evt = json.load(sys.stdin)
    reason = check((evt.get("tool_input") or {}).get("command", ""), evt.get("cwd") or ".")
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": f"Blocked: {reason}. Never push to main; push a branch and open a PR."}}))


if __name__ == "__main__":
    main()
