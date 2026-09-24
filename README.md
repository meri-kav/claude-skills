# Claude Code skills

| Skill | What it does |
|---|---|
| `doc-project` | Runs a project through a Claude Doc. It sweeps comments in a background agent, answers in threads, and keeps the Overview (Now, Running, Needs you), Invariants, code-shape tabs and the PR map current. |
| `pr-ready` | Takes PRs from written to green. It answers review comments, runs the reviews and fixes what holds up, runs every local gate the way CI does, pushes, and waits on CI. |

## Install

```sh
cp -R skills/doc-project skills/pr-ready ~/.claude/skills/
cp hooks/block-push-main.py ~/.claude/hooks/
chmod +x ~/.claude/skills/*/scripts/*.py ~/.claude/hooks/block-push-main.py
```

## Hooks

These go under `hooks` in `~/.claude/settings.json`, merged with any hooks already there:

```json
{
  "PreToolUse": [
    {"matcher": "mcp__claude_ai_Claude_Docs__(update|batch|create)",
     "hooks": [{"type": "command", "command": "~/.claude/skills/doc-project/scripts/docs_hook.py", "timeout": 10}]},
    {"matcher": "Bash",
     "hooks": [{"type": "command", "command": "~/.claude/hooks/block-push-main.py", "timeout": 10}]}
  ],
  "PostToolUse": [
    {"matcher": "mcp__claude_ai_Claude_Docs__(create|query)",
     "hooks": [{"type": "command", "command": "~/.claude/skills/doc-project/scripts/docs_hook.py", "timeout": 10}]}
  ]
}
```

- **`docs_hook.py`, before a doc write:** refuses dashes, history wording and secrets in doc text, and refuses resolving a thread.
- **`docs_hook.py`, after a docs call:** records Claude's replies, sorts comment listings into a work list, and moves a quiet tab's bookmark.
- **`block-push-main.py`:** refuses any git push that would land on main or master.

Bookmarks and the PR map live in `~/.claude/doc-projects/`. Gate logs go to `~/.claude/pr-ready-logs/`.
