#!/usr/bin/env python3
"""Claude Docs hook: guards doc writes before they land, records replies and sorts comment listings after."""
import json
import re
import sys
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "doc-projects"

SKIP_KEYS = {"target", "anchor", "to", "parent", "ref", "container", "ifHash", "ifRev", "opId", "user"}
TEXT_KEYS = {"content", "text", "body", "markdown", "name", "title", "intent"}

DASHES = re.compile(r"[—–]")
HISTORY = re.compile(
    r"\b(used to|we (?:switched|changed|moved|dropped|replaced|reverted)|previously|originally|"
    r"(?:an |the )?earlier (?:draft|version)|(?:i|we) (?:was|were) wrong|(?:had|got) (?:it|this|that) wrong|"
    r"(?:was|has been|have been) replaced (?:by|with)|the old (?:plan|design|approach)|instead of what)\b",
    re.I,
)
BASELINE = re.compile(
    r"\b(production|prod|today|currently|on main|existing behaviou?r|current behaviou?r|"
    r"before (?:this|our|the) change|as it (?:works|stands) now|as shipped)\b",
    re.I,
)
SECRETS = [
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{20,})")),
    ("API key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
    ("password in a URL", re.compile(r"\b[a-z][a-z0-9+.-]*://[^:/\s]+:[^@/\s]{3,}@")),
    ("secret assignment", re.compile(r"\b(?:password|passwd|pwd|secret|token|api[_ -]?key)\s*[:=]\s*[^\s,;]{6,}", re.I)),
]


def _payload(tool_input: dict) -> dict:
    p = tool_input.get("payload")
    if isinstance(p, str):
        try:
            return json.loads(p)
        except ValueError:
            return {}
    return p or {}


def _texts(node, key=None, out=None) -> list[str]:
    out = [] if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k not in SKIP_KEYS:
                _texts(v, k, out)
    elif isinstance(node, list):
        for v in node:
            _texts(v, key, out)
    elif isinstance(node, str) and key in TEXT_KEYS:
        out.append(node)
    return out


def _snip(text: str, start: int, end: int) -> str:
    return text[max(0, start - 30): end + 30].replace("\n", " ").strip()


def _sentences(text: str):
    for line in text.split("\n"):
        yield from re.split(r"(?<=[.!?])\s+", line)


def lint(texts: list[str], doc_body: bool) -> list[str]:
    found = []
    for t in texts:
        for m in DASHES.finditer(t):
            found.append(f"em or en dash: \"{_snip(t, m.start(), m.end())}\"")
        for label, rx in SECRETS:
            if rx.search(t):
                found.append(f"{label} in the text")
        if doc_body:
            for s in _sentences(t):
                m = HISTORY.search(s)
                if m and not BASELINE.search(s):
                    found.append(f"history wording \"{m.group(0)}\": \"{s.strip()[:120]}\"")
    return found


def _state_path(doc_id: str) -> Path | None:
    p = STATE_DIR / f"{doc_id}.json"
    if p.exists():
        return p
    for q in STATE_DIR.glob("*.json"):
        s = json.loads(q.read_text())
        if doc_id and (doc_id in (s.get("url") or "") or s.get("doc_id") == doc_id):
            return q
    return None


def _response_json(resp) -> dict:
    parts = resp if isinstance(resp, list) else [resp]
    for part in parts:
        text = part.get("text") if isinstance(part, dict) else part
        if isinstance(text, str) and text.lstrip().startswith("{"):
            try:
                return json.JSONDecoder().raw_decode(text.lstrip())[0]
            except ValueError:
                continue
    return {}


def pre(tool: str, tool_input: dict) -> dict | None:
    payload = _payload(tool_input)
    value = payload.get("value") if isinstance(payload.get("value"), dict) else {}
    is_comment = tool == "create" and tool_input.get("object") == "utterance"
    if is_comment and value.get("kind") == "resolve":
        return _deny("Never resolve a thread: Meri resolves. Reply in the thread instead.")
    if tool not in ("update", "batch", "create"):
        return None
    texts = _texts(value) if is_comment else _texts(payload) + _texts(tool_input.get("batch")) + _texts(
        (tool_input.get("container") or {}).get("create"))
    found = lint(texts, doc_body=not is_comment)
    if not found:
        return None
    return _deny(
        "Doc write blocked:\n- " + "\n- ".join(found[:8])
        + "\nFix: commas, colons or periods instead of dashes. State the current plan; history wording is"
        " allowed only in a sentence that compares against production or today's behavior (\"In production"
        " today, ...\"). Keep secrets out; say where they live. If the dash is in the user's own words, target"
        " your edit narrowly with find instead of rewriting their text."
    )


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


ITEM = re.compile(r"(?:^|(?<=\s))(\d{1,2})(?:\s*[.:)=-])?\s+(?=[^\d\s])")


def numbered_answers(body: str) -> list[tuple[str, str, str]]:
    marks, want = [], 1
    for m in ITEM.finditer(body):
        if int(m.group(1)) == want:
            marks.append(m)
            want += 1
    if len(marks) < 2:
        return []
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(body)
        n, text = m.group(1), body[m.end():end]
        t = text.strip().lower()
        if re.match(r"(yes|yep|yeah|ok|sure|do it|agree|go)\b", t):
            action = "yes: record in Decided behavior"
        elif re.match(r"(no|nope|don't|dont)\b", t):
            action = "no: record in Decided behavior"
        elif re.search(r"\b(later|not now|ask (me )?again|park)\b", t):
            action = "later: move to Later"
        elif re.search(r"\b(check yourself|idk|you decide|your call|whatever)\b", t):
            action = "check yourself: investigate, decide, log in Claude decided, check me"
        else:
            action = "her words: act on them"
        out.append((n, text.strip()[:80], action))
    return out


def post(tool: str, tool_input: dict, resp) -> dict | None:
    container = (tool_input.get("container") or {}).get("id", "")
    path = _state_path(container)
    if path is None or tool_input.get("object") != "utterance":
        return None
    state = json.loads(path.read_text())
    payload = _payload(tool_input)
    data = _response_json(resp)
    if tool == "create" and data.get("minted"):
        mine = set(state.get("my_replies", []))
        mine.add(data["minted"])
        state["my_replies"] = sorted(mine)
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        return None
    if tool != "query":
        return None
    under = payload.get("under") or {}
    rows = sorted(data.get("rows") or [], key=lambda r: r.get("seq", 0))
    note, quiet = sort_rows(rows, set(state.get("my_replies", [])))
    if under.get("object") == "file":
        tab = state.setdefault("tabs", {}).setdefault(under["id"], {"rev": 0, "seq": 0})
        if rows:
            tab["observed_seq"] = max(tab.get("observed_seq", 0), rows[-1]["seq"])
        name = tab.get("name", under["id"])
        if quiet and not data.get("truncated"):
            tab["seq"] = max(tab.get("seq", 0), tab.get("observed_seq", 0))
            note = f"Tab {name}: quiet, bookmark moved to seq {tab['seq']}. " + note
        else:
            note = f"Tab {name}: when done, bookmark with --seq observed ({tab.get('observed_seq', 0)}).\n" + note
        path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": note}}


def sort_rows(rows: list[dict], mine: set[str]) -> tuple[str, bool]:
    """Returns the work list as text, and whether nothing needs work."""
    threads: dict[str, list[dict]] = {}
    resolved, deleted = set(), []
    for r in rows:
        if r.get("verb") == "delete":
            deleted.append(r.get("id"))
            continue
        value = (r.get("payload") or {}).get("value") or {}
        parent = value.get("parent") or {}
        root = parent.get("id") if parent.get("object") == "utterance" else r.get("id")
        if value.get("kind") == "resolve":
            if (r.get("actor") or {}).get("via") == "frame":
                resolved.add(root)
            continue
        threads.setdefault(root, []).append(r)
    answer, verify, done = [], [], 0
    for root, rs in threads.items():
        if root in resolved:
            continue
        last = rs[-1]
        via = (last.get("actor") or {}).get("via")
        body = ((last.get("payload") or {}).get("value") or {}).get("body", "")
        if via == "frame":
            line = f"- {root}: \"{body[:100]}\""
            nums = numbered_answers(body)
            if nums:
                line += "\n" + "\n".join(f"    {n}. \"{t}\" -> {a}" for n, t, a in nums)
            answer.append(line)
        elif last.get("id") in mine:
            done += 1
        else:
            verify.append(f"- reply {last.get('id')} in {root}: \"{body[:80]}\"")
    if not (answer or verify):
        return f"Nothing new to work ({done} handled, {len(resolved)} resolved by Meri).", True
    parts = []
    if answer:
        parts.append(f"Needs an answer ({len(answer)}):\n" + "\n".join(answer))
    if verify:
        parts.append(f"Other-session replies to verify ({len(verify)}):\n" + "\n".join(verify))
    parts.append(f"Already handled: {done}. Resolved by Meri: {len(resolved)}. Deleted: {len(deleted)}.")
    return "\n".join(parts), False


def main() -> None:
    try:
        evt = json.load(sys.stdin)
        tool = evt.get("tool_name", "").rsplit("__", 1)[-1]
        if evt.get("hook_event_name") == "PreToolUse":
            out = pre(tool, evt.get("tool_input") or {})
        else:
            out = post(tool, evt.get("tool_input") or {}, evt.get("tool_response"))
    except Exception as e:  # a broken hook must never block the doc
        out = {"systemMessage": f"docs_hook error: {e}"}
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
