#!/usr/bin/env python3
"""Build full-context Stage 4 links with Gemini explicit context caching."""

import argparse
import json
from pathlib import Path
import sys

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from mirrulations_markdown.gemini_reference_linker import (  # noqa: E402
    DEFAULT_GEMINI_MODEL, GeminiReferenceLinkerPipeline,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown-db", default="data/markdown_db")
    parser.add_argument("--model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--source-object-key", action="append", default=[])
    parser.add_argument("--source-object-keys-json")
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--maximum-concurrency", type=int, default=3)
    parser.add_argument("--maximum-api-calls", type=int)
    parser.add_argument("--cache-ttl-seconds", type=int, default=14400)
    parser.add_argument("--retry-count", type=int, default=2)
    parser.add_argument("--retain-cache", action="store_true")
    parser.add_argument("--dotenv", help="Ignored local credential file to load.")
    arguments = parser.parse_args()
    try:
        for name, value in (
            ("batch-size", arguments.batch_size),
            ("maximum-concurrency", arguments.maximum_concurrency),
            ("cache-ttl-seconds", arguments.cache_ttl_seconds),
        ):
            if value < 1:
                raise ValueError(f"--{name} must be at least 1")
        if arguments.maximum_api_calls is not None and arguments.maximum_api_calls < 1:
            raise ValueError("--maximum-api-calls must be at least 1")
        if arguments.retry_count < 0:
            raise ValueError("--retry-count cannot be negative")
        if arguments.dotenv:
            dotenv_path = Path(arguments.dotenv).expanduser().resolve()
            if not dotenv_path.is_file():
                raise ValueError(f"credential file does not exist: {dotenv_path}")
            load_dotenv(dotenv_path=dotenv_path, override=False)
        source_object_keys = list(arguments.source_object_key)
        if arguments.source_object_keys_json:
            source_object_keys.extend(json.loads(
                Path(arguments.source_object_keys_json).expanduser().resolve().read_text(
                    encoding="utf-8"
                )
            ))
        result = GeminiReferenceLinkerPipeline.run(
            markdown_db_path=Path(arguments.markdown_db).expanduser().resolve(),
            model=arguments.model, source_object_keys=source_object_keys,
            batch_size=arguments.batch_size,
            maximum_concurrency=arguments.maximum_concurrency,
            maximum_api_calls=arguments.maximum_api_calls,
            cache_ttl_seconds=arguments.cache_ttl_seconds,
            retry_count=arguments.retry_count, retain_cache=arguments.retain_cache,
            progress_callback=lambda event: print(
                f"Batch {event['batch_number']}/{event['batch_count']} complete "
                f"({event['reference_count']} references, attempt {event['attempt']})",
                flush=True,
            ),
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"gemini_reference_linker.py Error: {error}\n")
    except Exception as error:
        if error.__class__.__module__.startswith("google.genai"):
            parser.exit(
                1,
                f"gemini_reference_linker.py Provider Error: "
                f"{type(error).__name__}: {error}\n",
            )
        raise
    print(json.dumps(result, indent=2))
    if result["failed_batch_count"]:
        parser.exit(1, "gemini_reference_linker.py Error: requested work is incomplete\n")


if __name__ == "__main__":
    main()