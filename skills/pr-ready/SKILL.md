---
name: pr-ready
description: Take one or more PRs from "code written" to "green and ready to merge" in one run, without stopping to ask. Syncs the base, answers every open review comment, runs the review passes (code-review, simplify, jonathan-review) plus a check against the project's shape tab and invariants, fixes what holds up, runs every local gate the way CI runs it, pushes, and watches CI until green. Reports once at the end: what was fixed, what needs Meri, what can wait. Use when she says "make it green", "make it mergeable", "run the reviews and fix the findings", "/review /simplify /jonathan-review and fix", "address the comments", "get this ready", or pastes PR links with any of those. Merges only when she says merge.
---

# PR ready

One command for the chore loop: review, fix, gate, push, wait for CI, fix again. It runs to
the end without asking and stops early only for the cases under **Stop only for**.

## Input

- PR URLs, or nothing (the current branch's PR). `gh` resolves bare numbers from the cwd's
  repo, so turn numbers into URLs first.
- Words she may add: "and merge" (merge when green), "review only" (report, fix nothing),
  "quick" (one review round).

Several PRs: one background agent per PR, each in its own worktree, with this file as its
brief. A stacked PR waits until its parent is pushed, then runs on top of it.

## 0. Look before working

1. `scripts/pr.py status <url>`: one line. Exit 3 means merged, closed or conflicting. Run it
   again right before every push.
2. Work in a worktree no other live session is using: another session editing the same
   checkout makes every gate result meaningless (seen 2026-09-24). Reuse the branch's own
   worktree only if nothing else is in it; otherwise make one next to the others in
   `~/Desktop/root_repo` as `<short>-wt`. Never under `/tmp`: it gets reaped.
3. If a `doc-project` doc tracks this PR (`~/.claude/skills/doc-project/scripts/bookmark.py
   list`, then its PRs and tickets tab), read the feature's shape tab, its Invariants and
   Workbench's Standing rules. They are the bar for step 3.

## 1. Sync the base

Merge the PR's base branch in. A conflicting PR gets no CI at all, so this comes first.
Resolve mechanical conflicts. A conflict that needs a design call goes to Needs you, and the
run continues on everything else.

## 2. Answer open review comments

`scripts/pr.py threads <url>` lists the unresolved inline threads (which still need a reply)
and the top-level review comments. Every one, human or bot: fix it, or reply why not (already handled, wrong, out
of scope and where it is tracked). Reply in the thread with what changed. Never resolve a
person's thread. A request for a design change beyond this PR goes to Needs you.

## 3. Review passes

On the diff against the PR's base (its parent branch for a stacked PR, not main):

1. `/code-review high`
2. `/simplify`
3. `/jonathan-review` (pacific-server, nerfguard, pacific-gateway)
4. **Shape and invariants**, when a doc tracks the PR: does the diff match the shape tab
   (services, entrypoints, types, what was to be deleted)? Does every Invariants row this PR
   touches still hold? Collect evidence for each.

Read-only passes can run in parallel as background agents; fixes are applied here.

For each finding:
- **Verify it** against the code before touching anything. A finding is a claim.
- **Tag it**: we caused it or already there; needed now or can wait.
- **Fix** what is ours and needed now. List already-there and can-wait findings; do not fix
  them on this branch.
- A finding that contradicts a Decided behavior, Standing rules or shape row is not fixed. It
  goes to Needs you.

**Round 2**: rerun `/code-review` on the fixes alone, because a review fix is often the next
bug. One more round only if round 2 found something real. "Quick" skips round 2.

## 4. Gates, the way CI runs them

Commit, then `scripts/run_gates.py` from the worktree. It refuses a dirty tree, finds every
gate in the branch's own Makefile or package.json, runs each by exit code (baseline scans one
at a time, type check last), and prints only the failures with their log tails. After a fix,
commit and rerun just the failures with `--only '<regex>'`. Site: add `--tests`, and
`--build` when pages or routing changed. Tests, known flakes and repo notes:
`references/gates.md`.

- **Red on main too?** Prove it on a main worktree. Then it is already there: note it, don't
  fix it here.
- **Per-commit gates**: fold a small fix into the commit it fixes rather than adding a
  follow-up commit the gate grades alone.

## 5. Push and watch CI

Push, using `--force-with-lease` only when history was rewritten. Then run
`scripts/pr.py wait <url>` in the background. It reruns a known flake once, stops on
conflicts, and calls green only when every check on the head commit has finished and the same
green count shows on two polls in a row. Exit codes: 0 green, 1 failed (it prints each failing
check and its link), 2 timed out, 3 merged, closed or conflicting. On 1: reproduce the failure
locally, fix, push, wait again.

## 6. Report

**A doc tracks the project:** update its PR map row, add Findings rows, put Needs you items
in Overview, move Invariants rows (with evidence) and the Running row. Chat gets one line
with the link.

**No doc:** one short chat report in doc-project's Voice (answer first, plain words, our
names):

```
<PR link>: green | red on <check>
Fixed: N, one line each (up to 5, then "and N more")
Needs you: numbered, plain words, what it affects, my lean
Can wait / already there: one line each
Not checked: what was skipped and why
```

"And merge": after the report, `~/.claude/bin/merge-when-green <url>`; report its exit
(0 merged, 1 a check failed, 2 timed out, 3 unusable PR).

## Stop only for

- The PR merged or closed during the run.
- A fix needs a design change the shape tab does not cover. Park it in Needs you and finish
  the rest.
- A prod write, a migration against a shared database, or a message to a person. Never done
  here.

Everything else: make the call, log it (the doc's Claude decided, check me, or the report),
and keep going.

## Rules

- Never resolve a person's thread. A push to main is refused by a hook
  (`~/.claude/hooks/block-push-main.py`).
- Code comments follow her CLAUDE.md: short, present tense, what the code does, no history.
