#!/usr/bin/env python3
"""Wait for Meri's next comment on tracked docs, print one line and exit. No LLM calls.

Usage: doc_watch.py <doc_id> [<doc_id> ...] [--interval 20]

Talks to the Claude Docs connector directly with the CLI's own login (unofficial route).
Wakes only on comments typed in the doc page (via "frame"); replies written by any Claude
session (via "mcp") and resolves are ignored. Prints no comment text.
Exit 0: "NEW ..." line. Exit 1: "WATCH FAILING ..." line after repeated errors.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

DOCS_MCP = "https://mcp-proxy.anthropic.com/v1/mcp/mcpsrv_014Fj7srWvLMyCuRCS8J9W3d"
BOOKMARKS = Path.home() / ".claude" / "doc-projects"
MAX_FAILURES = 5


def token() -> str:
    raw = subprocess.check_output(
        ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"]
    ).decode()
    return json.loads(raw)["claudeAiOauth"]["accessToken"]


class Docs:
    """Minimal MCP client for the docs connector."""

    def __init__(self) -> None:
        self.client_session = str(uuid.uuid4())
        self.session = None
        self.next_id = 0
        self.token = token()
        self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "doc-watch", "version": "1"}})
        self._rpc("notifications/initialized", notify=True)

    def _rpc(self, method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        body: dict = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            self.next_id += 1
            body["id"] = self.next_id
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "anthropic-version": "2023-06-01",
            "User-Agent": "claude-code/2.1.0 (cli)",
            "X-Mcp-Client-Session-Id": self.client_session,
        }
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(DOCS_MCP, data=json.dumps(body).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            self.session = resp.headers.get("Mcp-Session-Id") or self.session
            text = resp.read().decode()
        if notify or not text.strip():
            return None
        if text.lstrip().startswith("{"):
            return json.loads(text)
        for line in text.splitlines():
            if line.startswith("data:"):
                msg = json.loads(line[5:])
                if msg.get("id") == body["id"]:
                    return msg
        raise RuntimeError("no response in event stream")

    def rows_after(self, doc_id: str, tab_id: str, after_seq: int) -> list[dict]:
        msg = self._rpc("tools/call", {"name": "query", "arguments": {
            "object": "utterance",
            "container": {"kind": "project", "id": doc_id},
            "payload": {"under": {"object": "file", "id": tab_id}, "afterSeq": after_seq, "limit": 20},
        }})
        decoder = json.JSONDecoder()
        for part in (msg or {}).get("result", {}).get("content", []):
            text = part.get("text", "")
            if text.startswith("{"):
                result = decoder.raw_decode(text)[0]
                if result.get("verdict") != "allow":
                    raise RuntimeError(f"query refused: {result.get('reason')}")
                return result.get("rows", [])
        raise RuntimeError("query returned no rows payload")


def tabs_and_seq(doc_id: str) -> tuple[dict[str, str], int]:
    state = json.loads((BOOKMARKS / f"{doc_id}.json").read_text())
    tabs = state.get("tabs", {})
    seq = max([max(t.get("seq", 0), t.get("observed_seq", 0)) for t in tabs.values()] or [0])
    return {tab_id: t.get("name", tab_id) for tab_id, t in tabs.items()}, seq


def is_meris_comment(row: dict) -> bool:
    value = row.get("payload", {}).get("value", {})
    return row.get("actor", {}).get("via") == "frame" and value.get("kind") != "resolve"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("doc_ids", nargs="+")
    parser.add_argument("--interval", type=float, default=20)
    args = parser.parse_args()

    seen = {doc_id: tabs_and_seq(doc_id)[1] for doc_id in args.doc_ids}
    docs = None
    failures = 0
    while True:
        try:
            docs = docs or Docs()
            for doc_id in args.doc_ids:
                tabs, bookmark_seq = tabs_and_seq(doc_id)
                seen[doc_id] = max(seen[doc_id], bookmark_seq)
                newest = seen[doc_id]
                for tab_id, name in tabs.items():
                    rows = docs.rows_after(doc_id, tab_id, seen[doc_id])
                    newest = max([newest] + [r["seq"] for r in rows])
                    hits = [r for r in rows if is_meris_comment(r)]
                    if hits:
                        to_claude = sum(1 for r in hits if r["payload"]["value"].get("to"))
                        print(f"NEW doc={doc_id} tab={name!r} comments={len(hits)} "
                              f"to_claude={to_claude} seq={hits[-1]['seq']}", flush=True)
                        return 0
                seen[doc_id] = newest
            failures = 0
        except (urllib.error.URLError, RuntimeError, OSError, ValueError, KeyError) as exc:
            failures += 1
            docs = None
            if failures >= MAX_FAILURES:
                print(f"WATCH FAILING after {failures} tries: {exc}", flush=True)
                return 1
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())
