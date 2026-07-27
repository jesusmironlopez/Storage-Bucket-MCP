"""
Tribble MCP Server (local SQLite version)
------------------------------------------
Reads meeting transcripts, summaries, and notes directly from Tribble
Desktop's local SQLite database. No API key needed.

SETUP
1.  pip install mcp
2.  Set TRIBBLE_DB_PATH to the full path of your local Tribble .db file, e.g.:
        setx TRIBBLE_DB_PATH "C:\\Users\\YourName\\AppData\\Roaming\\Tribble\\tribble.db"
    (or pass it via the "env" block in claude_desktop_config.json - see README)
3.  Run directly to sanity check: python tribble_server.py

NOTES
- Opens the db in read-only mode so it won't conflict with Tribble Desktop
  writing to it while it's running.
- If Tribble Desktop is actively mid-recording, `has_summary` may be 0 and
  `summary_text` may be empty for that meeting - that's expected, not a bug.
"""

import os
import sqlite3
import sys
import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from account_utils import load_known_accounts, match_account, discover_candidate_tokens

TRIBBLE_DB_PATH = os.environ.get("TRIBBLE_DB_PATH", "")

if not TRIBBLE_DB_PATH:
    print(
        "WARNING: TRIBBLE_DB_PATH is not set. Set it to the full path of your "
        "Tribble Desktop .db file before running this server.",
        file=sys.stderr,
    )

mcp = FastMCP("tribble")


def _connect() -> sqlite3.Connection:
    """Open the Tribble db read-only so we never write to or lock the file
    the desktop app is using."""
    if not TRIBBLE_DB_PATH or not os.path.exists(TRIBBLE_DB_PATH):
        raise FileNotFoundError(
            f"Tribble db not found at TRIBBLE_DB_PATH='{TRIBBLE_DB_PATH}'. "
            "Check the env var / config."
        )
    # forward slashes required in sqlite URI even on Windows
    uri_path = TRIBBLE_DB_PATH.replace("\\", "/")
    conn = sqlite3.connect(f"file:/{uri_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _safe_json(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


@mcp.tool()
def list_meetings(limit: int = 10, query: str = "") -> str:
    """List recent meetings captured by Tribble, most recent first.

    Args:
        limit: max number of meetings to return (default 10)
        query: optional text filter matched against title/description
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return str(e)

    try:
        cur = conn.cursor()
        if query:
            cur.execute(
                """
                SELECT id, title, description, date, platform, has_summary, participants_json
                FROM meetings
                WHERE title LIKE ? OR description LIKE ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", limit),
            )
        else:
            cur.execute(
                """
                SELECT id, title, description, date, platform, has_summary, participants_json
                FROM meetings
                ORDER BY date DESC
                LIMIT ?
                """,
                (limit,),
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return "No meetings found."

    lines = []
    for r in rows:
        participants = _safe_json(r["participants_json"]) or []
        if isinstance(participants, list):
            names = ", ".join(
                p.get("name", p.get("email", "unknown")) if isinstance(p, dict) else str(p)
                for p in participants
            )
        else:
            names = str(participants)
        summary_flag = "✓ summarized" if r["has_summary"] else "no summary yet"
        lines.append(
            f"- [{r['id']}] {r['title'] or 'Untitled'} — {r['date']} "
            f"({r['platform'] or 'unknown platform'}) — {summary_flag}\n"
            f"    participants: {names or 'unknown'}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_meeting_transcript(meeting_id: str) -> str:
    """Fetch the full transcript for a meeting, in order, with speaker labels.

    Args:
        meeting_id: the meeting id, as returned by list_meetings
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return str(e)

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT speaker, text
            FROM transcript_entries
            WHERE meeting_id = ?
            ORDER BY seq ASC
            """,
            (meeting_id,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return f"No transcript entries found for meeting_id='{meeting_id}'."

    lines = [f"{r['speaker'] or 'Unknown'}: {r['text']}" for r in rows]
    return "\n".join(lines)


@mcp.tool()
def get_meeting_summary(meeting_id: str) -> str:
    """Fetch the AI summary, user notes, and action items for a meeting.

    Args:
        meeting_id: the meeting id, as returned by list_meetings
    """
    try:
        conn = _connect()
    except FileNotFoundError as e:
        return str(e)

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT d.summary_text, d.user_notes_content, m.action_items_json, m.title, m.date
            FROM meetings m
            LEFT JOIN meeting_details d ON d.meeting_id = m.id
            WHERE m.id = ?
            """,
            (meeting_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        return f"No meeting found with id='{meeting_id}'."

    out = [f"# {row['title'] or 'Untitled'} ({row['date']})\n"]

    if row["summary_text"]:
        out.append("## Summary\n" + row["summary_text"])

    if row["user_notes_content"]:
        out.append("\n## User notes\n" + row["user_notes_content"])

    action_items = _safe_json(row["action_items_json"])
    if action_items:
        out.append("\n## Action items")
        if isinstance(action_items, list):
            for item in action_items:
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content") or str(item)
                else:
                    text = str(item)
                out.append(f"- {text}")
        else:
            out.append(str(action_items))

    if len(out) == 1:
        out.append("(no summary, notes, or action items recorded for this meeting yet)")

    return "\n".join(out)


@mcp.tool()
def list_accounts() -> str:
    """List accounts/customers Claude can recognize from your Tribble meetings.

    If accounts.json has a curated list, shows exactly those account names
    plus how many meetings match each. If accounts.json is empty, falls back
    to a heuristic discovery mode: extracts candidate account-name tokens
    from meeting titles and ranks them by frequency, so you can review and
    copy the real ones into accounts.json.
    """
    known_accounts = load_known_accounts()

    try:
        conn = _connect()
    except FileNotFoundError as e:
        return str(e)

    try:
        cur = conn.cursor()
        cur.execute("SELECT title FROM meetings")
        titles = [r["title"] for r in cur.fetchall()]
    finally:
        conn.close()

    if known_accounts:
        lines = ["Curated accounts (from accounts.json):\n"]
        for account in known_accounts:
            count = sum(1 for t in titles if match_account(t, [account]))
            alias_note = f" (aliases: {', '.join(account['aliases'])})" if account["aliases"] else ""
            lines.append(f"- {account['name']}{alias_note}: {count} meeting(s)")
        return "\n".join(lines)

    # Discovery mode
    candidates = discover_candidate_tokens(titles)
    if not candidates:
        return "No candidate account names found in meeting titles."

    top = candidates.most_common(30)
    lines = [
        "No curated account list yet (accounts.json is empty). Here are "
        "candidate account names discovered from your meeting titles, "
        "ranked by frequency. Review these and copy the real ones into "
        "accounts.json's \"accounts\" list for reliable matching:\n"
    ]
    for token, count in top:
        lines.append(f"- {token}: appears in {count} title(s)")
    return "\n".join(lines)


@mcp.tool()
def get_account_context(account: str, limit: int = 20) -> str:
    """Pull combined context for a specific account: every matching meeting's
    date, summary, notes, and action items, most recent first.

    Args:
        account: account/customer name to match against meeting titles
                 (should match an entry in accounts.json for reliable results;
                 aliases from accounts.json are also searched automatically)
        limit: max number of meetings to include (default 20)
    """
    # If this account name has aliases curated in accounts.json, search all
    # of them too (e.g. "Prudential" -> also matches "Pru", "CyberArk", "qBotica")
    known_accounts = load_known_accounts()
    search_terms = [account]
    for known in known_accounts:
        if known["name"].lower() == account.lower():
            search_terms.extend(known.get("aliases", []))
            break

    try:
        conn = _connect()
    except FileNotFoundError as e:
        return str(e)

    try:
        cur = conn.cursor()
        placeholders = " OR ".join(["m.title LIKE ?"] * len(search_terms))
        cur.execute(
            f"""
            SELECT m.id, m.title, m.date, d.summary_text, d.user_notes_content, m.action_items_json
            FROM meetings m
            LEFT JOIN meeting_details d ON d.meeting_id = m.id
            WHERE {placeholders}
            ORDER BY m.date DESC
            LIMIT ?
            """,
            tuple(f"%{term}%" for term in search_terms) + (limit,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return (
            f"No meetings found matching account='{account}'. "
            "Try list_accounts to see available/candidate account names."
        )

    out = [f"# Account context: {account} ({len(rows)} meeting(s))\n"]
    for row in rows:
        out.append(f"## {row['title']} — {row['date']} [{row['id']}]")
        if row["summary_text"]:
            out.append(row["summary_text"])
        if row["user_notes_content"]:
            out.append(f"\nNotes: {row['user_notes_content']}")
        action_items = row["action_items_json"]
        if action_items:
            try:
                items = json.loads(action_items)
                if items:
                    out.append("Action items:")
                    for item in items:
                        text = item.get("text") or item.get("content") or str(item) if isinstance(item, dict) else str(item)
                        out.append(f"  - {text}")
            except (json.JSONDecodeError, TypeError):
                pass
        if not row["summary_text"] and not row["user_notes_content"]:
            out.append("(no summary/notes recorded yet for this meeting)")
        out.append("")  # blank line between meetings

    return "\n".join(out)


if __name__ == "__main__":
    mcp.run()
