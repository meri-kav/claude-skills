#!/usr/bin/env python3
"""Per-doc sweep bookmarks for the doc-project skill.

State lives in ~/.claude/doc-projects/<doc_id>.json. Revs and comment seqs only move forward.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path.home() / ".claude" / "doc-projects"
LOCK_SECONDS = 45 * 60


def _path(doc_id: str) -> Path:
    return STATE_DIR / f"{doc_id}.json"


def _load(doc_id: str) -> dict:
    p = _path(doc_id)
    if not p.exists():
        sys.exit(f"no state for {doc_id}; run init first")
    return json.loads(p.read_text())


def _save(doc_id: str, state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path(doc_id).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def cmd_init(a: argparse.Namespace) -> None:
    p = _path(a.doc_id)
    state = json.loads(p.read_text()) if p.exists() else {"doc_id": a.doc_id, "tabs": {}}
    state["url"] = a.url or state.get("url")
    state["title"] = a.title or state.get("title")
    _save(a.doc_id, state)
    print(json.dumps(state, indent=2))


def cmd_show(a: argparse.Namespace) -> None:
    print(json.dumps(_load(a.doc_id), indent=2))


def cmd_tab(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    tab = state["tabs"].setdefault(a.tab_id, {"rev": 0, "seq": 0})
    if a.name:
        tab["name"] = a.name
    if a.body:
        tab["body_id"] = a.body
    if a.rev is not None:
        tab["rev"] = max(tab.get("rev", 0), a.rev)
    if a.seq is not None:
        observed = tab.get("observed_seq", 0)
        seq = observed if a.seq == "observed" else int(a.seq)
        if seq < observed and not a.force:
            sys.exit(f"refused: seq {seq} is below {observed}, the highest seq a tab-wide listing returned; "
                     "use --seq observed, or --force")
        tab["seq"] = max(tab.get("seq", 0), seq)
    _save(a.doc_id, state)
    print(json.dumps({a.tab_id: tab}))


def cmd_set(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    for pair in a.pairs:
        key, _, value = pair.partition("=")
        state[key] = None if value == "" else value
    _save(a.doc_id, state)
    print(json.dumps({k: state.get(k) for k in (p.partition("=")[0] for p in a.pairs)}))


def cmd_plan(a: argparse.Namespace) -> None:
    """Claims the sweep lock and prints every call a sweep needs, so all tabs are queried in one parallel batch."""
    state = _load(a.doc_id)
    now = datetime.now(timezone.utc)
    running = state.get("sweep_running")
    if running and (now - datetime.fromisoformat(running)).total_seconds() < LOCK_SECONDS and not a.force:
        sys.exit(f"another sweep started at {running} and has not finished; skip this one")
    state["sweep_running"] = now.isoformat(timespec="seconds")
    _save(a.doc_id, state)
    container = {"kind": "project", "id": a.doc_id}
    print(f"Sweep {state.get('title')} ({state.get('url')}). Run all of these in ONE parallel batch:")
    print(f"- tab list: read(ref={json.dumps({'object': 'project', 'id': a.doc_id})})")
    for tab_id, tab in state.get("tabs", {}).items():
        payload = {"under": {"object": "file", "id": tab_id}, "afterSeq": tab.get("seq", 0)}
        print(f"- {tab.get('name', tab_id)} (body {tab.get('body_id')}, last read at rev {tab.get('rev', 0)}): "
              f"query(object=\"utterance\", container={json.dumps(container)}, payload={json.dumps(payload)})")
    for tid, d in state.get("deferred", {}).items():
        print(f"Pending agent: thread {tid} since {d['since']}: {d['what']}")
    if state.get("prs"):
        print(f"PR map: run prmap.py refresh {a.doc_id} in the same batch.")


def cmd_unlock(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    print("released" if state.pop("sweep_running", None) else "not locked")
    _save(a.doc_id, state)


def cmd_swept(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    state.pop("sweep_running", None)
    state["last_sweep"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save(a.doc_id, state)
    print(state["last_sweep"])


def cmd_mine(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    mine = set(state.get("my_replies", []))
    mine.update(a.reply_ids)
    state["my_replies"] = sorted(mine)
    _save(a.doc_id, state)
    print(f"{len(a.reply_ids)} recorded, {len(mine)} total")


def cmd_whose(a: argparse.Namespace) -> None:
    mine = set(_load(a.doc_id).get("my_replies", []))
    for rid in a.reply_ids:
        print(f"{rid} {'mine' if rid in mine else 'other-session'}")


def cmd_defer(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    pending = state.setdefault("deferred", {})
    pending[a.thread_id] = {
        "agent": a.agent,
        "tab": a.tab,
        "what": a.what,
        "since": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _save(a.doc_id, state)
    print(json.dumps({a.thread_id: pending[a.thread_id]}))


def cmd_landed(a: argparse.Namespace) -> None:
    state = _load(a.doc_id)
    gone = state.setdefault("deferred", {}).pop(a.thread_id, None)
    _save(a.doc_id, state)
    print("cleared" if gone else "not deferred")


def cmd_pending(a: argparse.Namespace) -> None:
    for tid, d in _load(a.doc_id).get("deferred", {}).items():
        print(f"{tid} | agent {d['agent']} | tab {d['tab']} | since {d['since']} | {d['what']}")


def cmd_list(_: argparse.Namespace) -> None:
    for p in sorted(STATE_DIR.glob("*.json")):
        s = json.loads(p.read_text())
        watch = f"cron={s['cron_id']}" if s.get("cron_id") else "not watched"
        print(f"{s.get('title') or s['doc_id']} | {s.get('url')} | last sweep {s.get('last_sweep')} | {watch}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(required=True)
    p = sub.add_parser("init"); p.add_argument("doc_id"); p.add_argument("--url"); p.add_argument("--title"); p.set_defaults(fn=cmd_init)
    p = sub.add_parser("show"); p.add_argument("doc_id"); p.set_defaults(fn=cmd_show)
    p = sub.add_parser("tab"); p.add_argument("doc_id"); p.add_argument("tab_id")
    p.add_argument("--name"); p.add_argument("--body"); p.add_argument("--rev", type=int)
    p.add_argument("--seq", help="a seq, or 'observed' for the highest one the docs hook saw"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_tab)
    p = sub.add_parser("set"); p.add_argument("doc_id"); p.add_argument("pairs", nargs="+", help="key=value; empty value clears"); p.set_defaults(fn=cmd_set)
    p = sub.add_parser("plan", help="claim the sweep lock and print the sweep's calls"); p.add_argument("doc_id")
    p.add_argument("--force", action="store_true"); p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("unlock", help="release the sweep lock without stamping a sweep"); p.add_argument("doc_id")
    p.set_defaults(fn=cmd_unlock)
    p = sub.add_parser("swept", help="release the sweep lock and stamp the time"); p.add_argument("doc_id"); p.set_defaults(fn=cmd_swept)
    p = sub.add_parser("mine", help="record reply ids this session posted"); p.add_argument("doc_id"); p.add_argument("reply_ids", nargs="+"); p.set_defaults(fn=cmd_mine)
    p = sub.add_parser("whose", help="label Claude reply ids as mine or other-session"); p.add_argument("doc_id"); p.add_argument("reply_ids", nargs="+"); p.set_defaults(fn=cmd_whose)
    p = sub.add_parser("defer", help="record a thread handed to a background agent"); p.add_argument("doc_id"); p.add_argument("thread_id")
    p.add_argument("--agent", required=True); p.add_argument("--tab", required=True); p.add_argument("--what", required=True); p.set_defaults(fn=cmd_defer)
    p = sub.add_parser("landed", help="clear a deferred thread once its answer is in the doc"); p.add_argument("doc_id"); p.add_argument("thread_id"); p.set_defaults(fn=cmd_landed)
    p = sub.add_parser("pending", help="list deferred threads still waiting on an agent"); p.add_argument("doc_id"); p.set_defaults(fn=cmd_pending)
    p = sub.add_parser("list"); p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
