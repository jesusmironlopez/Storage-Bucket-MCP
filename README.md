# UiPath Storage Buckets MCP Server

Connects Claude Desktop to UiPath Orchestrator Storage Buckets through a
local MCP server. You can list buckets, browse files, read text files,
download binary files.

## What you get

- A local MCP server Claude Desktop can query for UiPath Storage Buckets
- OAuth2 client-credentials authentication with cached access tokens
- Tools for listing buckets, listing files, and reading files
- PDF, Excel, Word, text, and binary-file handling

The server is currently read-only. Upload and delete operations are not exposed
as active MCP tools.

Large extracted responses are truncated to protect the MCP response size. The
complete downloaded file is saved in a local temporary directory and its path
is included in the response.

## Setup

### 1. Prerequisites

- Python 3.10+ installed (Windows: check with `python --version` in
  PowerShell; if that fails, install from python.org and enable **Add Python
  to PATH**)
- A UiPath external application with client-credentials access
- Claude Desktop installed

### 2. Install dependencies

```powershell
python -m pip install mcp requests pdfplumber pandas openpyxl xlrd tabulate python-docx
```

These packages provide the MCP server, HTTP calls, PDF extraction, Excel
conversion, and Word document extraction. `openpyxl` reads modern `.xlsx`
workbooks, `xlrd` supports legacy `.xls` workbooks, and `tabulate` formats
Excel data as Markdown tables. Verify the parser packages:

```powershell
python -c "import pdfplumber, pandas, openpyxl, xlrd, tabulate, docx; print('Parser dependencies installed')"
```

If `pip` or `python` resolves to the wrong interpreter, find the exact path
with `where.exe python` and use that full `python.exe` path in the commands and
Claude Desktop configuration below.

### 3. Configure UiPath credentials

This setup passes credentials directly through Claude Desktop's MCP
configuration; system-wide environment variables are not required. Replace
the placeholder values in the `env` block of `claude_desktop_config.json`:

```json
"env": {
  "UIPATH_CLIENT_ID": "your-client-id",
  "UIPATH_CLIENT_SECRET": "your-client-secret",
  "UIPATH_ORG_NAME": "your-org-name",
  "UIPATH_TENANT_NAME": "DefaultTenant"
}
```

### 4. Add it to Claude Desktop

Open or create Claude Desktop's configuration file:

- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

If Claude was installed through the Microsoft Store or an MSIX installer,
also check:
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`

Merge the contents of this project's `claude_desktop_config.json` into the
existing configuration. Use the full path to `python.exe` if Claude cannot
resolve the bare `python` command:

```json
{
  "mcpServers": {
    "uipath-storage-buckets": {
      "command": "C:\\full\\path\\to\\python.exe",
      "args": [
        "C:\\Tools\\storage-buckets-mcp\\storage_bucket_server.py"
      ],
      "env": {
        "UIPATH_CLIENT_ID": "your-client-id",
        "UIPATH_CLIENT_SECRET": "your-client-secret",
        "UIPATH_ORG_NAME": "your-org-name",
        "UIPATH_TENANT_NAME": "DefaultTenant"
      }
    }
  }
}
```

Fully quit and reopen Claude Desktop after changing its configuration. Check
**Settings → Developer** to confirm the server is connected.

### 5. Test the server

```powershell
python storage_bucket_server.py
```

The server should start and wait for MCP input. Press `Ctrl+C` to stop it.
Because the credentials are supplied by Claude Desktop, use Claude Desktop
to test an authenticated tool call. For direct authenticated testing, set the
four variables in the current PowerShell session before running the command.

To smoke-test the available tools using credentials from the Claude Desktop
config, run:

```powershell
python test_server.py
```

The script tests authentication, bucket listing, and file listing. Set these
optional variables to test reading a specific file:

```powershell
$env:TEST_BUCKET_NAME = "Bank"
$env:TEST_FOLDER_PATH = "/"
$env:TEST_FILE_PATH = "/reports/example.pdf"
python test_server.py
```

### 6. Generate Project instructions

Generate one ready-to-paste Claude Project instructions file for the complete
`storage_bucket_server.py` MCP server:

```powershell
python generate_project_instructions.py
```

This project-specific generator fills `project_instructions/TEMPLATE.md` and
writes one project-wide Markdown file to
`project_instructions/storage_bucket_server_instructions.md`. The generated
instructions cover all active tools, bucket/path usage, file extraction
behavior, authentication, limitations, and error handling. It does not create
one file per bucket.

### 7. Create the Projects in claude.ai

For the generated project instruction file:

1. Create a Claude Project for the Storage Buckets MCP server.
2. Paste `project_instructions/storage_bucket_server_instructions.md` into the
   Project instructions.
3. Use the Project with the MCP tools to browse and read files from any
   accessible bucket.

## Tools exposed by the MCP server

| Tool | Description |
|---|---|
| `list_storage_buckets()` | List available storage buckets |
| `list_files(bucket_name, folder_path)` | List files in a bucket folder |
| `read_file(bucket_name, file_path)` | Return text content or download a binary file locally |

## Common issues

| Symptom | Likely cause |
|---|---|
| Server disconnected | Claude resolved a different Python than the one with `mcp` installed; use the full `python.exe` path |
| Authentication failed | Check all four UiPath environment values and the external application's permissions |
| Config file will not parse | A comma is missing while merging JSON; validate with `python -m json.tool claude_desktop_config.json` |
| No buckets or files returned | Confirm the UiPath organization, tenant, and storage-bucket permissions |
