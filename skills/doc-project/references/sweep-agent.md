# Sweep agent brief

You run one sweep of a doc-project doc in the background, so the main session's context stays
small. `S` = `~/.claude/skills/doc-project`, `B` = `python3 S/scripts/bookmark.py`,
`C` = `{"kind":"project","id":"<doc_id>"}`.

## 1. Check, cheaply (every sweep)

1. In one batch: `B plan <doc_id>`, `python3 S/scripts/prmap.py refresh <doc_id>` (it says so
   when there is no PR map), and `ToolSearch("select:mcp__claude_ai_Claude_Docs__query,mcp__claude_ai_Claude_Docs__create,mcp__claude_ai_Claude_Docs__read,mcp__claude_ai_Claude_Docs__update")`.
   If `plan` refuses (another sweep is running), return "skipped" and stop.
2. In ONE parallel batch, run every call that `plan` printed (the tab list and each tab's
   comment `query`). Do not call the docs `guide` and do not read tab contents yet. A tab in the
   list that `plan` did not name is new: `B tab <doc_id> <tab_id> --name "<name>" --body
   <body_id>`, then query its comments from seq 0.
3. A hook appends a sorted work list to each query result and moves the bookmark itself on a
   quiet tab. If every tab is quiet, `prmap` printed no change and no Running row is overdue:
   run `B swept <doc_id>` and return `quiet`. Nothing else.

## 2. Load the context (only when something is new)

Answer from the doc as it stands now, never from a guess. In ONE parallel batch:

- **The project**: the Overview tab whole (Now, Needs you, Claude decided), and Workbench's
  Standing rules when a comment asks for a call.
- **What changed since the last sweep**, per tab with work:
  `read(ref={"object":"node","id":"<body_id>"}, engine="prose", container=C, payload={"kind":"view","sinceRev":<rev from plan>})`.
- **Where each comment points**, per thread root: `read(ref={"object":"utterance","id":"<root>"}, container=C)`
  gives the anchored `quote`, its `block` id and `state` (attached or detached).

Then, per tab with work, `read(... payload={"projection":"outline"})` once, to find each anchor
block's section (the heading above it). Read that section in full with
`payload={"kind":"view","parentId":"<block id>"}` for a table or list, or the blocks between the
heading and the next heading. Never re-read a whole tab.

**Check the context moved.** If the anchor is detached, or its block or section shows up in the
changes since the last sweep, the text the comment was written against has changed. Answer
against the current text, and say in the reply what changed if it affects the answer.

Then read `S/SKILL.md` (sections: What each kind of comment gets, How Meri works, Voice, Rules)
and `S/references/sweep.md` (sections 3 and 4, Editing traps).

## 3. Work

- **Quick items first**: answer each in its thread (`create` an utterance, parent = the root id).
- **Doc edits** only when a comment asks for one or an answer changes what the doc states.
  Read the target block fresh right before editing. Call `guide(["topic.editing"])` only if an
  edit needs a table, column or restore op.
- **Slow items** (a code dig, a data query, a web survey) that fit in about 20 minutes: after all
  quick replies are out, reply "Looking into this, I'll update this thread", investigate, then
  reply with the finding and its evidence.
- **Long runs** (an experiment, an eval, a big investigation): do not run them here. Write a
  handoff to `~/.claude/doc-projects/runs/<doc_id>-<root>.md` with:
  - the question word for word, the doc id and the thread root;
  - what the doc already says on it, and where to look (repos, paths, tables);
  - the limits: production read-only, no PRs, no messages;
  - what to post when done: the finding in the thread, with evidence and what was not checked,
    and the Running row in Overview marked landed or failed.

  Reply "Started a longer run for this; progress is on the Running line in Overview", add a
  Running row (what, started, running), and list the handoff path in your return.
- **Actions outside the doc** (a prod write, a PR, a message): never. List them for the main
  session as "waiting on Meri's yes".
- A hook blocks dashes, history wording and secrets in doc writes, and blocks resolves. If a
  write is refused, fix the text and resend.

## 4. Close out

1. For each tab that had work, re-list its comments so your replies are included, then run
   `B tab <doc_id> <tab_id> --rev <latest rev you saw> --seq observed`.
2. If anything changed: update the Overview header, Needs you and the PR map, and add one
   Activity row.
3. `B swept <doc_id>`.

## 5. Return

At most 80 words, for the main session:
- counts: answered, verified, edits, still open;
- `long run: <handoff path>`, one line each;
- any item "waiting on Meri's yes";
- anything that failed.

No thread text: Meri reads it in the doc.
