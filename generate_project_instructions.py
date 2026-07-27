"""Generate Claude Project instructions for the UiPath Storage Buckets MCP server.

USAGE
    python generate_project_instructions.py

The script fills project_instructions/TEMPLATE.md and writes one ready-to-paste
Markdown file describing the complete storage_bucket_server.py project.
"""

from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR / "project_instructions" / "TEMPLATE.md"
OUTPUT_DIR = SCRIPT_DIR / "project_instructions"
OUTPUT_PATH = OUTPUT_DIR / "storage_bucket_server_instructions.md"


def main() -> int:
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(template, encoding="utf-8")
        print(f"Wrote {OUTPUT_PATH}")
        return 0
    except FileNotFoundError as e:
        print(f"ERROR: Required file not found: {e}")
        return 1
    except OSError as e:
        print(f"ERROR: Could not generate project instructions: {e}")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: Project instruction generation failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
