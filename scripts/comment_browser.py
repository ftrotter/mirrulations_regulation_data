#!/usr/bin/env python3
"""Start a simple local-only browser for reading comment documents."""

import argparse
import os
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.comment_browser import CommentBrowserServer  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start"])
    parser.add_argument("--markdown-db")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    arguments = parser.parse_args()

    try:
        environment_path = REPOSITORY_ROOT / ".env"
        if environment_path.is_file():
            load_dotenv(dotenv_path=environment_path, override=False)

        markdown_db = arguments.markdown_db or os.getenv(
            "COMMENT_BROWSER_MARKDOWN_DB"
        )
        if not markdown_db:
            raise ValueError(
                "provide --markdown-db or set COMMENT_BROWSER_MARKDOWN_DB"
            )
        host = arguments.host or os.getenv("COMMENT_BROWSER_HOST", "127.0.0.1")
        port_value = arguments.port or int(
            os.getenv("COMMENT_BROWSER_PORT", "8765")
        )
        markdown_db_path = Path(markdown_db).expanduser()
        if not markdown_db_path.is_absolute():
            markdown_db_path = REPOSITORY_ROOT / markdown_db_path
        markdown_db_path = markdown_db_path.resolve()

        server = CommentBrowserServer(
            markdown_db_path=markdown_db_path, host=host, port=port_value,
        )
    except (OSError, ValueError) as error:
        parser.exit(1, f"comment_browser.py Error: {error}\n")

    url = f"http://{host}:{port_value}/comments/"
    print(f"Comment browser is running:", flush=True)
    print(f"  {url}", flush=True)
    print(flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        return


if __name__ == "__main__":
    main()
