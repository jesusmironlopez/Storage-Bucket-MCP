"""Manually smoke-test every non-destructive UiPath Storage Buckets tool."""

import json
import os
import sys
from pathlib import Path


CONFIG_ENV_KEYS = (
    "UIPATH_CLIENT_ID",
    "UIPATH_CLIENT_SECRET",
    "UIPATH_ORG_NAME",
    "UIPATH_TENANT_NAME",
)


def _is_error(result: str) -> bool:
    """Return whether a tool result contains a server/API error."""
    return result.startswith((
        "Missing required",
        "UiPath authentication failed",
        "UiPath API request failed",
        "Unable to ",
    ))


def _load_credentials(config_path: Path) -> int:
    """Load Claude Desktop credentials into the process environment."""
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        print(f"ERROR: Claude Desktop config not found: {config_path}")
        return 1
    except json.JSONDecodeError as e:
        print(f"ERROR: Could not parse {config_path}: {e}")
        return 1
    except OSError as e:
        print(f"ERROR: Could not read {config_path}: {e}")
        return 1

    try:
        env = config["mcpServers"]["uipath-storage-buckets"]["env"]
        if not isinstance(env, dict):
            raise TypeError("the env block is not an object")

        missing = [key for key in CONFIG_ENV_KEYS if not env.get(key)]
        if missing:
            raise KeyError(f"missing required env value(s): {', '.join(missing)}")

        for key in CONFIG_ENV_KEYS:
            os.environ[key] = str(env[key])
    except (KeyError, TypeError) as e:
        print(
            "ERROR: Could not find the UiPath credentials in "
            f"mcpServers['uipath-storage-buckets']['env']: {e}"
        )
        return 1

    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    config_path = Path(__file__).resolve().parent / "claude_desktop_config.json"
    if _load_credentials(config_path):
        return 1

    try:
        # Import only after the config credentials have been placed in os.environ.
        from storage_bucket_server import (  # noqa: PLC0415
            _api_request,
            _get_access_token,
            list_files,
            list_storage_buckets,
            read_file,
        )

        token = _get_access_token()
        if _is_error(token):
            print(f"AUTHENTICATION: FAILED\n{token}")
            return 1
        print("AUTHENTICATION: PASSED")

        failures = 0

        print("\nLIST_STORAGE_BUCKETS:")
        bucket_response = list_storage_buckets()
        print(bucket_response)
        if _is_error(bucket_response):
            failures += 1
            return failures

        bucket_payload = _api_request("GET", "/odata/Buckets")
        if isinstance(bucket_payload, str):
            print(f"\nBUCKET LOOKUP: FAILED\n{bucket_payload}")
            return 1

        buckets = bucket_payload.get("value", []) if isinstance(bucket_payload, dict) else []
        if not buckets:
            print("\nNo buckets are available for file-operation tests.")
            return failures

        bucket_name = os.environ.get("TEST_BUCKET_NAME") or buckets[0].get("Name")
        folder_path = os.environ.get("TEST_FOLDER_PATH", "/")
        if not bucket_name:
            print("\nFILE TESTS: FAILED\nNo bucket name was available.")
            return 1

        print(f"\nLIST_FILES ({bucket_name}, {folder_path}):")
        files_response = list_files(bucket_name, folder_path)
        print(files_response)
        if _is_error(files_response):
            failures += 1

        test_file_path = os.environ.get("TEST_FILE_PATH", "")
        if test_file_path:
            print(f"\nREAD_FILE ({bucket_name}, {test_file_path}):")
            read_response = read_file(bucket_name, test_file_path)
            print(read_response)
            if _is_error(read_response):
                failures += 1
        else:
            print(
                "\nREAD_FILE: SKIPPED (set TEST_FILE_PATH to a file path "
                "such as /reports/example.pdf)"
            )

        # upload_file is currently disabled in storage_bucket_server.py.
        print("\nUPLOAD_FILE: DISABLED")

        return 1 if failures else 0
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: Storage bucket smoke test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
