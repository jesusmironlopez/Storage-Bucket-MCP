"""Manually smoke-test the UiPath Storage Buckets tools."""

import argparse
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


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse optional runtime arguments for mutating smoke tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-folder-id",
        type=int,
        required=True,
        help="Orchestrator folder ID used by the list-storage-buckets test.",
    )
    parser.add_argument(
        "--file-list-bucket-name",
        help="Bucket name used by the file-listing test.",
    )
    parser.add_argument(
        "--file-list-folder-path",
        default="/",
        help="Folder path used by the file-listing test (default: /).",
    )
    # parser.add_argument(
    #     "--bucket-name",
    #     help="Existing bucket to use for the upload test.",
    # )
    # parser.add_argument(
    #     "--folder-path",
    #     default="/",
    #     help="Folder path used by the list-files test (default: /).",
    # )
    # parser.add_argument(
    #     "--file-path",
    #     help="Path of a bucket file to read.",
    # )
    # parser.add_argument(
    #     "--upload-file-path",
    #     help="Local file path to upload during the smoke test.",
    # )
    # parser.add_argument(
    #     "--upload-destination-path",
    #     help="Destination path for the uploaded file; defaults to /<filename>.",
    # )
    # parser.add_argument(
    #     "--upload-folder-id",
    #     type=int,
    #     help="Optional Orchestrator folder ID containing the upload bucket.",
    # )
    # parser.add_argument(
    #     "--create-bucket-name",
    #     help="Create a bucket with this name during the smoke test.",
    # )
    # parser.add_argument(
    #     "--create-bucket-description",
    #     default="",
    #     help="Description for the bucket created by the smoke test.",
    # )
    # parser.add_argument(
    #     "--create-bucket-folder-id",
    #     type=int,
    #     help="Optional Orchestrator folder ID for the new bucket.",
    # )
    return parser.parse_args(argv)


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


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_args(argv)

    config_path = Path(__file__).resolve().parent / "claude_desktop_config.json"
    if _load_credentials(config_path):
        return 1

    try:
        # Import only after the config credentials have been placed in os.environ.
        from storage_bucket_server import (  # noqa: PLC0415
            # _api_request,
            _get_access_token,
            list_storage_buckets,
            list_files,
            # read_file,
            # create_storage_bucket,
            # upload_file,
        )

        token = _get_access_token()
        if _is_error(token):
            print(f"AUTHENTICATION: FAILED\n{token}")
            return 1
        print("AUTHENTICATION: PASSED")

        failures = 0

        print("\nLIST_STORAGE_BUCKETS:")
        bucket_response = list_storage_buckets(args.list_folder_id)
        print(bucket_response)
        if _is_error(bucket_response):
            failures += 1

        if args.file_list_bucket_name:
            print(
                f"\nLIST_FILES ({args.file_list_bucket_name}, "
                f"{args.file_list_folder_path}):"
            )
            files_response = list_files(
                args.file_list_bucket_name,
                args.file_list_folder_path,
                args.list_folder_id,
            )
            print(files_response)
            if _is_error(files_response):
                failures += 1

        # create_bucket_name = args.create_bucket_name
        # if create_bucket_name:
        #     print(f"\nCREATE_STORAGE_BUCKET ({create_bucket_name}):")
        #     create_response = create_storage_bucket(
        #         create_bucket_name,
        #         args.create_bucket_description,
        #         args.create_bucket_folder_id,
        #     )
        #     print(create_response)
        #     if _is_error(create_response):
        #         failures += 1

        # bucket_payload = _api_request("GET", "/odata/Buckets")
        # if isinstance(bucket_payload, str):
        #     print(f"\nBUCKET LOOKUP: FAILED\n{bucket_payload}")
        #     return 1

        # buckets = (
        #     bucket_payload.get("value", [])
        #     if isinstance(bucket_payload, dict)
        #     else []
        # )
        # if not buckets:
        #     print("\nNo buckets are available for file-operation tests.")
        #     return failures

        # bucket_name = args.bucket_name or buckets[0].get("Name")
        # folder_path = args.folder_path
        # if not bucket_name:
        #     print("\nFILE TESTS: FAILED\nNo bucket name was available.")
        #     return 1

        # print(f"\nLIST_FILES ({bucket_name}, {folder_path}):")
        # files_response = list_files(bucket_name, folder_path)
        # print(files_response)
        # if _is_error(files_response):
        #     failures += 1

        # test_file_path = args.file_path
        # if test_file_path:
        #     print(f"\nREAD_FILE ({bucket_name}, {test_file_path}):")
        #     read_response = read_file(bucket_name, test_file_path)
        #     print(read_response)
        #     if _is_error(read_response):
        #         failures += 1
        # else:
        #     print(
        #         "\nREAD_FILE: SKIPPED (pass --file-path with a path such as "
        #         "/reports/example.pdf)"
        #     )

        # upload_local_path = args.upload_file_path
        # if upload_local_path:
        #     bucket_name = args.bucket_name or create_bucket_name
        #     if not bucket_name:
        #         print(
        #             "\nUPLOAD_FILE: FAILED (pass --bucket-name or "
        #             "--create-bucket-name)"
        #         )
        #         return 1
        #     upload_destination = args.upload_destination_path or (
        #         f"/{Path(upload_local_path).name}"
        #     )
        #     print(
        #         f"\nUPLOAD_FILE ({bucket_name}, {upload_destination}, "
        #         f"{upload_local_path}):"
        #     )
        #     upload_response = upload_file(
        #         bucket_name,
        #         upload_destination,
        #         upload_local_path,
        #         args.upload_folder_id,
        #     )
        #     print(upload_response)
        #     if _is_error(upload_response):
        #         failures += 1
        # else:
        #     print(
        #         "\nUPLOAD_FILE: SKIPPED (pass --upload-file-path with a local "
        #         "file; optionally pass --upload-destination-path)"
        #     )

        return 1 if failures else 0
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: Storage bucket smoke test failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
