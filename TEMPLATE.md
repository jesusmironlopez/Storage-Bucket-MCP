# Tribble → Claude Account Specialist Toolkit

Turns your local Tribble Desktop meeting history into live, queryable
context inside Claude — then organizes it into per-account "specialist"
Projects with four switchable roles: Project Manager, Solution Architect,
Account Executive, and Adoption & Enablement Lead.

No API key needed — this reads Tribble Desktop's local SQLite database
directly, read-only.

## What you get

- A local MCP server Claude Desktop can query for meeting transcripts,
  summaries, and account-level context — live, in any conversation
- A curated account list (`accounts.json`) so meetings get grouped by real
  customer name, not guesswork
- A script that exports one Markdown "account brief" per account, ready to
  upload into a Claude Project's knowledge base
- A script that generates ready-to-paste Project custom instructions
  defining all 4 roles for each of your accounts

## Setup

### 1. Prerequisites
- Tribble Desktop installed and has recorded at least one meeting
- Python 3.10+ installed (Windows: check with `python --version` in
  PowerShell; if that fails, install from python.org and make sure you
  check "Add to PATH" during install)
- Claude Desktop installed

### 2. Find your Tribble database
Windows (PowerShell):
```powershell
Get-ChildItem -Path $env:APPDATA,$env:LOCALAPPDATA -Recurse -Include *.db,*.sqlite -ErrorAction SilentlyContinue | Where-Object { $_.FullName -match "tribble" }
```
Ctrl+C to stop.

macOS/Linux:
```bash
find ~ -iname "*tribble*" -iname "*.db" 2>/dev/null
```
Ctrl+C to stop.

### 3. Install dependencies
```powershell
pip install mcp
```
If `pip`/`python` don't resolve the interpreter you expect, find the exact
path with `where.exe python` (Windows) or `which python3` (macOS/Linux) and
use that full path everywhere below instead of the bare word `python`.

### 4. Download this toolkit
Unzip it somewhere permanent, e.g. `C:\Tools\tribble-mcp\` or `~/tools/tribble-mcp/`.

### 5. Set your db path as an environment variable
Windows (PowerShell, persists across sessions):
```powershell
[Environment]::SetEnvironmentVariable("TRIBBLE_DB_PATH", "C:\full\path\to\your\tribble.db", "User")
```
Open a **new** terminal window afterward for it to take effect.

### 6. Sanity check
```powershell
python tribble_server.py
```
Should run silently with no "TRIBBLE_DB_PATH not set" warning. Ctrl+C to stop.

### 7. Connect it to Claude Desktop
Open (or create) your Claude Desktop config:
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
IMPORTANT: If you installed Claude via the Microsoft Store or an MSIX installer, Windows isolates the configuration file. Instead of standard AppData, look here: `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add (or merge into existing content — don't delete what's already there):
```json
{
  "mcpServers": {
    "tribble": {
      "command": "C:\\full\\path\\to\\python.exe",
      "args": ["C:\\full\\path\\to\\tribble-mcp\\tribble_server.py"],
      "env": {
        "TRIBBLE_DB_PATH": "C:\\full\\path\\to\\your\\tribble.db"
      }
    }
  }
}
```
Watch for a missing comma if you're merging into an existing file with
other keys already present — that's the #1 cause of "server disconnected."

Fully quit Claude Desktop (system tray (the small icon area located on the bottom-right corner of your taskbar (the notification area)) → Exit, not just closing the window) and reopen it. 

WARNING: DO NOT log out of Claude Desktop. This will cause the ~/claude_desktop_config.json file to be reset.

Check **Settings → Developer** or the 🔌 icon near the chat
box to confirm `tribble` is connected.

### 8. Discover your accounts
In a Claude Desktop chat, ask: **"list my Tribble accounts"** — this calls
the `list_accounts` tool, which (since `accounts.json` starts empty) surfaces
candidate account names pulled from your meeting titles. Review them and
add the real ones to `accounts.json`:

```json
{
  "accounts": [
    {"name": "Acme Corp", "aliases": ["ACME", "Acme Inc"], "domains": ["acme.com"]}
  ]
}
```
- `aliases`: other strings that show up in your meeting titles for the same
  account (e.g. a partner name that always co-occurs with that customer)
- `domains`: reference only — confirmed customer email domains, useful if
  you cross-check meetings against your Outlook calendar for ones Tribble
  couldn't identify participants for. Not used for automatic matching.

### 9. Generate account briefs
```powershell
python generate_account_briefs.py
```
Writes one `.md` file per account to `account_briefs/`.

### 10. Generate Project instructions
```powershell
python generate_project_instructions.py
```
Writes one ready-to-paste instructions file per account to
`project_instructions/`, each defining all 4 roles (PM, SA, AE, Adoption &
Enablement) scoped to that account.

### 11. Create the Projects in claude.ai
For each account:
1. Create a new Project named after the account
2. Paste that account's file from `project_instructions/` into Customs Instructions (**Instructions**)
3. Upload that account's file from `account_briefs/` to the Project's knowledge base (**Files**)
4. Start chatting — ask for a specific role ("SA view," "PM update," "AE risk
   read," "adoption check") or just ask naturally for an integrated view

### Keeping it current
- Re-run `generate_account_briefs.py` periodically and re-upload changed
  files — there's no API to auto-push into Project knowledge, so this step
  stays manual
- For anything more recent than your last upload, just ask inside the
  Project chat — the live Tribble MCP tools (`get_account_context`,
  `list_meetings`, `get_meeting_transcript`, `get_meeting_summary`) pull
  current data directly, no upload needed

## Tools exposed by the MCP server

| Tool | Description |
|---|---|
| `list_meetings(limit, query)` | Recent meetings, optionally filtered |
| `get_meeting_transcript(meeting_id)` | Full speaker-labeled transcript |
| `get_meeting_summary(meeting_id)` | AI summary + notes + action items |
| `list_accounts()` | Curated accounts + counts, or discovery candidates if accounts.json is empty |
| `get_account_context(account, limit)` | All matching meetings' summaries/notes/action items for one account |

## Common issues

| Symptom | Likely cause |
|---|---|
| "Server disconnected" | Bare `"python"` in config resolved to a different Python than the one with `mcp` installed — use the full `python.exe` path instead |
| "TRIBBLE_DB_PATH not set" warning | Env var not set, or you didn't open a new terminal after setting it |
| Config file won't parse | Missing comma when merging into existing JSON — validate with `python -m json.tool your_config.json` before saving |
| `list_accounts` results look noisy | Expected in discovery mode — curate `accounts.json` and it'll clean up immediately |
