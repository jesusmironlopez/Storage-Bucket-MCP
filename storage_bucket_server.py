"""
UiPath Storage Buckets MCP Servers
---------------------------------
Provides the authenticated server skeleton for UiPath Orchestrator Storage
Buckets. Tools can be added below once the authentication and API helpers are
configured.

SETUP
1.  pip install mcp requests pdfplumber pandas python-docx
2.  Set UIPATH_CLIENT_ID, UIPATH_CLIENT_SECRET, UIPATH_ORG_NAME, and
    UIPATH_TENANT_NAME in the environment.
3.  Run directly to sanity check: python storage_bucket_server.py
"""

import os
import tempfile
import time
from typing import Any
from urllib.parse import quote

import requests
from mcp.server.fastmcp import FastMCP

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from docx import Document
except ImportError:
    Document = None


UIPATH_CLIENT_ID = os.environ.get("UIPATH_CLIENT_ID", "")
UIPATH_CLIENT_SECRET = os.environ.get("UIPATH_CLIENT_SECRET", "")
UIPATH_ORG_NAME = os.environ.get("UIPATH_ORG_NAME", "")
UIPATH_TENANT_NAME = os.environ.get("UIPATH_TENANT_NAME", "DefaultTenant")

TOKEN_URL = "https://staging.uipath.com/identity_/connect/token"
API_BASE_URL = (
    f"https://staging.uipath.com/{UIPATH_ORG_NAME}/{UIPATH_TENANT_NAME}/orchestrator_"
)

# Cached token state. The small safety window prevents using a token that is
# about to expire while a request is in flight.
_access_token: str | None = None
_token_expires_at: float = 0.0

mcp = FastMCP("uipath-storage-buckets")

MAX_EXTRACTED_TEXT_CHARS = 100_000
TEXT_EXTENSIONS = {".txt", ".json", ".csv", ".md", ".py", ".yaml", ".xml"}


def _save_to_temp_file(file_path: str, content: bytes) -> str:
    """Save downloaded content to a temporary file and return its path."""
    temp_dir = tempfile.mkdtemp(prefix="uipath_storage_")
    file_name = os.path.basename(file_path) or "downloaded_file"
    local_path = os.path.join(temp_dir, file_name)
    with open(local_path, "wb") as output_file:
        output_file.write(content)
    return local_path


def _decode_text(content: bytes) -> str:
    """Decode text as UTF-8, falling back to latin-1 when necessary."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1")


def _truncate_text(text: str) -> str:
    """Limit extracted text to a safe response size and mark truncation."""
    if len(text) <= MAX_EXTRACTED_TEXT_CHARS:
        return text
    return (
        text[:MAX_EXTRACTED_TEXT_CHARS]
        + "\n\n[Content truncated because it exceeded the maximum response size.]"
    )


def _table_to_markdown(table: list[list[Any]]) -> str:
    """Convert a pdfplumber table into a markdown table."""
    rows = [
        [str(cell or "").replace("|", "\\|").replace("\n", " ").strip() for cell in row]
        for row in table
        if row and any(cell not in (None, "") for cell in row)
    ]
    if not rows:
        return ""

    column_count = max(len(row) for row in rows)
    rows = [row + [""] * (column_count - len(row)) for row in rows]
    headers = rows[0]
    if not any(headers):
        headers = [f"Column {index}" for index in range(1, column_count + 1)]
    separator = ["---"] * column_count
    markdown_rows = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    markdown_rows.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(markdown_rows)


def _get_bucket_context(bucket_name: str) -> tuple[int, int] | str:
    """Resolve a bucket name to its ID and one accessible folder ID."""
    bucket_result = _api_request("GET", "/odata/Buckets")
    if isinstance(bucket_result, str):
        return bucket_result

    bucket_records = (
        bucket_result.get("value", [])
        if isinstance(bucket_result, dict)
        else bucket_result
    )
    bucket = next(
        (
            record
            for record in bucket_records
            if str(record.get("Name", "")).lower() == bucket_name.lower()
        ),
        None,
    )
    if not bucket:
        return f"No storage bucket found with name='{bucket_name}'."

    bucket_id = bucket.get("Id") or bucket.get("Identifier")
    if bucket_id is None:
        return f"Storage bucket '{bucket_name}' has no usable ID."

    folders_result = _api_request(
        "GET",
        "/odata/Buckets/UiPath.Server.Configuration.OData.GetFoldersForBucket"
        f"(id={bucket_id})",
    )
    if isinstance(folders_result, str):
        return folders_result

    folders = (
        folders_result.get("AccessibleFolders", [])
        if isinstance(folders_result, dict)
        else []
    )
    if not folders:
        return (
            f"No accessible Orchestrator folder found for storage bucket "
            f"'{bucket_name}'."
        )

    folder_id = folders[0].get("Id")
    if folder_id is None:
        return f"Accessible folder for bucket '{bucket_name}' has no ID."

    return int(bucket_id), int(folder_id)


def get_access_token() -> str:
    """Get an OAuth2 client-credentials token, reusing it until it expires."""
    global _access_token, _token_expires_at

    if _access_token and time.time() < (_token_expires_at - 60):
        return _access_token

    missing = [
        name
        for name, value in (
            ("UIPATH_CLIENT_ID", UIPATH_CLIENT_ID),
            ("UIPATH_CLIENT_SECRET", UIPATH_CLIENT_SECRET),
            ("UIPATH_ORG_NAME", UIPATH_ORG_NAME),
            ("UIPATH_TENANT_NAME", UIPATH_TENANT_NAME),
        )
        if not value
    ]
    if missing:
        return f"Missing required environment variable(s): {', '.join(missing)}"

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": UIPATH_CLIENT_ID,
                "client_secret": UIPATH_CLIENT_SECRET,
                "scope": "OR.Default",
            },
            timeout=30,
        )
        response.raise_for_status()
        token_data = response.json()
        token = token_data.get("access_token")
        if not token:
            return "UiPath authentication failed: response did not include an access token."

        _access_token = token
        _token_expires_at = time.time() + int(token_data.get("expires_in", 3600))
        return _access_token
    except requests.HTTPError as e:
        response = e.response
        status = response.status_code if response is not None else "unknown"
        body = response.text if response is not None else str(e)
        return f"UiPath authentication failed: HTTP {status}: {body}"
    except (requests.RequestException, ValueError) as e:
        return f"UiPath authentication failed: {e}"


# Compatibility alias used by the manual sanity-check script.
_get_access_token = get_access_token


def _api_request(
    method: str,
    path: str,
    **kwargs: Any,
) -> dict[str, Any] | list[Any] | str:
    """Make an authenticated UiPath Orchestrator API request and return JSON."""
    token = get_access_token()
    if token.startswith("Missing required") or token.startswith("UiPath authentication failed"):
        return token

    url = f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    headers = dict(kwargs.pop("headers", {}) or {})
    headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Accept", "application/json")

    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            timeout=30,
            **kwargs,
        )
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()
    except requests.HTTPError as e:
        response = e.response
        status = response.status_code if response is not None else "unknown"
        body = response.text if response is not None else str(e)
        return f"UiPath API request failed: HTTP {status}: {body}"
    except (requests.RequestException, ValueError) as e:
        return f"UiPath API request failed: {e}"


@mcp.tool()
def list_storage_buckets() -> str:
    """List all storage buckets configured in the UiPath Orchestrator tenant.

    Returns each bucket's ID, name, description, and storage provider as a
    clean markdown bullet list.
    """
    result = _api_request("GET", "/odata/Buckets")
    if isinstance(result, str):
        return result

    buckets = result.get("value", []) if isinstance(result, dict) else result
    if not buckets:
        return "No storage buckets found."

    lines = []
    for bucket in buckets:
        lines.append(
            f"- **{bucket.get('Name', 'Unnamed')}** — "
            f"Id: `{bucket.get('Id', 'N/A')}`; "
            f"Description: {bucket.get('Description') or 'None'}; "
            f"StorageProvider: {bucket.get('StorageProvider', 'N/A')}"
        )
    return "\n".join(lines)


@mcp.tool()
def list_files(bucket_name: str, folder_path: str = "/") -> str:
    """List files in a specific UiPath Storage Bucket folder.

    Args:
        bucket_name: name of the storage bucket to search
        folder_path: folder path within the bucket (default "/")

    Returns each file's ID, name, folder path, size, and last-modified time as
    a markdown list.
    """
    try:
        context = _get_bucket_context(bucket_name)
        if isinstance(context, str):
            return context
        bucket_id, folder_id = context

        encoded_directory = quote(folder_path or "/", safe="")
        result = _api_request(
            "GET",
            f"/odata/Buckets({bucket_id})/"
            "UiPath.Server.Configuration.OData.GetFiles"
            f"?directory={encoded_directory}&recursive=false",
            headers={"X-UIPATH-OrganizationUnitId": str(folder_id)},
        )
    except (TypeError, ValueError) as e:
        return f"Unable to list files: {e}"

    if isinstance(result, str):
        return result

    files = result.get("value", []) if isinstance(result, dict) else result
    if not files:
        return "No files found in this path."

    lines = []
    for file in files:
        file_path = file.get("FullPath") or file.get("Name", "Unnamed")
        lines.append(
            f"- **{file_path}** — "
            f"Id: `{file.get('Id', 'N/A')}`; "
            f"FolderPath: `{file.get('FolderPath') or folder_path}`; "
            f"Size: {file.get('Size', 'N/A')}; "
            f"LastModified: {file.get('LastModified', 'N/A')}"
        )
    return "\n".join(lines)


@mcp.tool()
def read_file(bucket_name: str, file_path: str) -> str:
    """Read or download a file from a UiPath Storage Bucket.

    Args:
        bucket_name: name of the storage bucket containing the file
        file_path: path of the file within the bucket, such as
            "/folder/file.pdf"

    Text files are returned directly. PDFs, Excel workbooks, and Word
    documents are parsed when possible. Other binary files are downloaded to
    a local temporary directory and the saved path is returned.
    """
    try:
        context = _get_bucket_context(bucket_name)
        if isinstance(context, str):
            return context
        bucket_id, folder_id = context

        encoded_file_path = quote(file_path, safe="")
        result = _api_request(
            "GET",
            f"/odata/Buckets({bucket_id})/"
            "UiPath.Server.Configuration.OData.GetReadUri"
            f"?path={encoded_file_path}",
            headers={"X-UIPATH-OrganizationUnitId": str(folder_id)},
        )
    except (TypeError, ValueError) as e:
        return f"Unable to get file download URL: {e}"

    if isinstance(result, str):
        return result

    download_url = None
    if isinstance(result, dict):
        value = result.get("value")
        if isinstance(value, str):
            download_url = value
        elif isinstance(value, dict):
            download_url = value.get("Uri") or value.get("Url") or value.get("url")
        download_url = (
            download_url
            or result.get("Uri")
            or result.get("Url")
            or result.get("url")
        )

    if not download_url:
        return "Unable to get file download URL: response did not include a URL."

    try:
        response = requests.get(download_url, timeout=60)
        response.raise_for_status()
    except requests.RequestException as e:
        return f"Unable to download file: {e}"

    extension = os.path.splitext(file_path)[1].lower()
    try:
        if extension in TEXT_EXTENSIONS:
            return _decode_text(response.content)

        local_path = _save_to_temp_file(file_path, response.content)

        if extension == ".pdf":
            if pdfplumber is None:
                return (
                    "Unable to extract text from PDF: pdfplumber is not installed. "
                    f"File saved to: {local_path}"
                )
            try:
                pages = []
                with pdfplumber.open(local_path) as pdf:
                    for page_number, page in enumerate(pdf.pages, start=1):
                        table = page.extract_table()
                        if table:
                            table_markdown = _table_to_markdown(table)
                            if table_markdown:
                                pages.append(f"## Page {page_number}\n{table_markdown}")
                                continue

                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            pages.append(f"## Page {page_number}\n{page_text}")
                extracted_text = "\n\n".join(pages).strip()
            except Exception as e:  # noqa: BLE001
                return f"Unable to extract text from PDF: {e}. File saved to: {local_path}"

            if len(extracted_text) < 50:
                return (
                    "PDF appears to contain mostly images or scanned content. "
                    f"File saved to: {local_path}. Please upload it directly to "
                    "the chat for visual analysis."
                )
            return _truncate_text(extracted_text)

        if extension in {".xlsx", ".xls"}:
            if pd is None:
                return (
                    "Unable to read Excel file: pandas is not installed. "
                    f"File saved to: {local_path}"
                )
            try:
                sheets = pd.read_excel(local_path, sheet_name=None)
                sections = []
                for sheet_name, data_frame in sheets.items():
                    if data_frame is None or data_frame.empty:
                        continue
                    sections.append(f"## Sheet: {sheet_name}")
                    sections.append(data_frame.head(100).to_markdown(index=False))
                if not sections:
                    return "Excel file appears empty or corrupted."
                return _truncate_text("\n\n".join(sections))
            except Exception as e:  # noqa: BLE001
                return f"Unable to read Excel file: {e}. File saved to: {local_path}"

        if extension == ".docx":
            if Document is None:
                return (
                    "Unable to read Word document: python-docx is not installed. "
                    f"File saved to: {local_path}"
                )
            try:
                document = Document(local_path)
                paragraphs = [
                    paragraph.text.strip()
                    for paragraph in document.paragraphs
                    if paragraph.text.strip()
                ]
                if not paragraphs:
                    return "Word document appears empty or contains only images."
                return _truncate_text("\n".join(paragraphs))
            except Exception as e:  # noqa: BLE001
                return f"Unable to read Word document: {e}. File saved to: {local_path}"

        return (
            f"Binary file saved to: {local_path}. Claude cannot read this file "
            "type directly. Please upload it to the chat manually if needed."
        )
    except OSError as e:
        return f"Unable to save or process file: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Unable to process file: {e}"


# @mcp.tool()
# def upload_file(bucket_name: str, file_path: str, local_file_path: str) -> str:
#     """Upload a local file to a UiPath Storage Bucket.
#
#     Args:
#         bucket_name: name of the storage bucket to receive the file
#         file_path: destination path in the bucket, such as
#             "/reports/Q3.xlsx"
#         local_file_path: absolute path to the local file to upload
#
#     Returns a confirmation containing the destination path and uploaded file
#     size in bytes.
#     """
#     try:
#         escaped_bucket_name = bucket_name.replace("'", "''")
#         encoded_file_path = quote(file_path.replace("'", "''"), safe="")
#         filter_expression = f"StorageBucketName eq '{escaped_bucket_name}'"
#         encoded_filter = quote(filter_expression, safe="")
#         result = _api_request(
#             "GET",
#             "/odata/StorageBucketFiles("
#             f"'{encoded_file_path}'"
#             ")/UiPath.Server.Configuration.OData.GetWriteUrl"
#             f"?$filter={encoded_filter}",
#         )
#     except (TypeError, ValueError) as e:
#         return f"Unable to get file upload URL: {e}"
#
#     if isinstance(result, str):
#         return result
#
#     upload_url = None
#     required_headers = {}
#     if isinstance(result, dict):
#         value = result.get("value")
#         if isinstance(value, str):
#             upload_url = value
#         elif isinstance(value, dict):
#             upload_url = value.get("Uri") or value.get("Url") or value.get("url")
#             required_headers = value.get("RequiredHeaders", {}) or {}
#         upload_url = upload_url or result.get("Uri") or result.get("Url") or result.get("url")
#         required_headers = required_headers or result.get("RequiredHeaders", {}) or {}
#
#     if not upload_url:
#         return "Unable to get file upload URL: response did not include a URL."
#
#     try:
#         with open(local_file_path, "rb") as input_file:
#             file_content = input_file.read()
#         file_size = len(file_content)
#
#         response = requests.put(
#             upload_url,
#             data=file_content,
#             headers=required_headers,
#             timeout=60,
#         )
#         response.raise_for_status()
#         return f"File uploaded successfully to: {file_path} ({file_size} bytes)"
#     except (OSError, requests.RequestException) as e:
#         return f"Unable to upload file: {e}"


if __name__ == "__main__":
    mcp.run()
