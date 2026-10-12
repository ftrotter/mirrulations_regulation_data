"""Cross-provider full-context Stage 4 benchmark runner and premium adapters."""

import asyncio
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import time

from .full_context_linker import (
    FullContextLinkBatch, LINKING_INSTRUCTIONS, serialize_target_context,
    validate_link_batch,
)
from .gemini_reference_linker import (
    GeminiCachedContextAdapter, _batch_prompt, _link_record, _load_work,
    _target_record,
)
from .pipeline import _write_json


PREMIUM_LINKER_VERSION = 1
DEFAULT_MODELS = {
    "google": "gemini-3.1-pro-preview",
    "anthropic": "claude-opus-5-5",
    "openai": "gpt-6-astra",
}


def _checkpoint_root(*, markdown_db_path, provider, model, context_sha256):
    return (
        markdown_db_path / "metadata" / "reference_link_benchmarks"
        / provider / model.replace("/", "_") / context_sha256
    )


def _load_checkpoints(*, checkpoint_root):
    links = {}
    batch_root = checkpoint_root / "batches"
    for path in sorted(batch_root.glob("*.json")) if batch_root.is_dir() else []:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
        for link in checkpoint.get("links", []):
            links[link["reference_id"]] = link
    return links


def _normalized_batch_metadata(*, response):
    return {
        "latency_seconds": response["latency_seconds"],
        "usage": response["usage"],
        "response_id": response["response_id"],
        "model_version": response["model_version"],
    }


class AnthropicCachedContextAdapter:
    """Claude adapter with an explicit ephemeral breakpoint after target context."""

    provider = "anthropic"

    def __init__(self, *, model=DEFAULT_MODELS["anthropic"], cache_ttl_seconds=3600):
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("premium_linker.py Error: ANTHROPIC_API_KEY is not set")
        from anthropic import AsyncAnthropic
        self._client = AsyncAnthropic()
        self.model = model
        self.cache_ttl_seconds = cache_ttl_seconds

    def prepare_target_context(self, *, target_context):
        ttl = "1h" if self.cache_ttl_seconds > 300 else "5m"
        return {
            "cache_strategy": "explicit_prefix_breakpoint",
            "cache_ttl": ttl,
            "system": [
                {"type": "text", "text": LINKING_INSTRUCTIONS},
                {
                    "type": "text",
                    "text": target_context["serialized_context"],
                    "cache_control": {"type": "ephemeral", "ttl": ttl},
                },
            ],
        }

    async def submit_question_batch(self, *, prepared_context, questions):
        started_at = time.monotonic()
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=32768,
            system=prepared_context["system"],
            messages=[{"role": "user", "content": _batch_prompt(questions=questions)}],
            output_format=FullContextLinkBatch,
        ) as stream:
            response = await stream.get_final_message()
        parsed = response.parsed_output
        if not isinstance(parsed, FullContextLinkBatch):
            text = "".join(block.text for block in response.content if block.type == "text")
            parsed = FullContextLinkBatch.model_validate_json(text)
        usage = response.usage
        usage_record = {
            "input_tokens": usage.input_tokens,
            "cache_creation_input_tokens": usage.cache_creation_input_tokens,
            "cache_read_input_tokens": usage.cache_read_input_tokens,
            "output_tokens": usage.output_tokens,
            "total_tokens": (
                usage.input_tokens + usage.cache_creation_input_tokens
                + usage.cache_read_input_tokens + usage.output_tokens
            ),
        }
        return {
            "batch": parsed,
            "latency_seconds": round(time.monotonic() - started_at, 3),
            "usage": usage_record,
            "response_id": response.id,
            "model_version": response.model,
        }

    def release_target_context(self, *, prepared_context):
        return None

    async def aclose(self):
        await self._client.close()


class OpenAICachedContextAdapter:
    """OpenAI Responses adapter with an explicit breakpoint after target context."""

    provider = "openai"

    def __init__(self, *, model=DEFAULT_MODELS["openai"], cache_ttl_seconds=1800):
        if not os.getenv("OPENAI_API_KEY"):
            raise ValueError("premium_linker.py Error: OPENAI_API_KEY is not set")
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI()
        self.model = model
        self.cache_ttl_seconds = cache_ttl_seconds

    def prepare_target_context(self, *, target_context):
        return {
            "cache_strategy": "explicit_prefix_breakpoint",
            # OpenAI limits prompt_cache_key to 64 characters.
            "prompt_cache_key": "stage4-" + target_context["context_sha256"][:56],
            "input_prefix": [{
                "role": "developer",
                "content": [{
                    "type": "input_text",
                    "text": LINKING_INSTRUCTIONS + "\n\n" + target_context["serialized_context"],
                    "prompt_cache_breakpoint": {"mode": "explicit"},
                }],
            }],
        }

    async def submit_question_batch(self, *, prepared_context, questions):
        started_at = time.monotonic()
        response = await self._client.responses.parse(
            model=self.model,
            input=prepared_context["input_prefix"] + [{
                "role": "user", "content": _batch_prompt(questions=questions),
            }],
            text_format=FullContextLinkBatch,
            max_output_tokens=32768,
            reasoning={"effort": "high"},
            prompt_cache_key=prepared_context["prompt_cache_key"],
            prompt_cache_options={"mode": "explicit", "ttl": "30m"},
            store=False,
        )
        usage = response.usage
        input_details = usage.input_tokens_details if usage else None
        output_details = usage.output_tokens_details if usage else None
        usage_record = {
            "input_tokens": usage.input_tokens if usage else None,
            "cached_input_tokens": getattr(input_details, "cached_tokens", None),
            "cache_write_tokens": getattr(input_details, "cache_write_tokens", None),
            "output_tokens": usage.output_tokens if usage else None,
            "reasoning_tokens": getattr(output_details, "reasoning_tokens", None),
            "total_tokens": usage.total_tokens if usage else None,
        }
        return {
            "batch": response.output_parsed,
            "latency_seconds": round(time.monotonic() - started_at, 3),
            "usage": usage_record,
            "response_id": response.id,
            "model_version": response.model,
        }

    def release_target_context(self, *, prepared_context):
        return None

    async def aclose(self):
        await self._client.close()


def build_adapter(*, provider, model, cache_ttl_seconds):
    if provider == "google":
        adapter = GeminiCachedContextAdapter(
            model=model, cache_ttl_seconds=cache_ttl_seconds,
        )
        adapter.provider = "google"
        return adapter
    if provider == "anthropic":
        return AnthropicCachedContextAdapter(
            model=model, cache_ttl_seconds=cache_ttl_seconds,
        )
    if provider == "openai":
        return OpenAICachedContextAdapter(
            model=model, cache_ttl_seconds=cache_ttl_seconds,
        )
    raise ValueError("premium_linker.py Error: provider must be google, anthropic, or openai")


async def _submit_batches(
    *, adapter, prepared_context, batches, target_context, target_record,
    markdown_db_path, checkpoint_root, maximum_concurrency, retry_count,
    progress_callback,
):
    semaphore = asyncio.Semaphore(maximum_concurrency)

    async def submit(*, batch_number, items):
        questions = [{
            "reference_id": item["reference_id"],
            "source_block_id": item["source_block_id"],
            "source_text": item["source_text"],
            "search_description": item["search_description"],
        } for item in items]
        last_error = None
        for attempt in range(1, retry_count + 2):
            try:
                async with semaphore:
                    response = await adapter.submit_question_batch(
                        prepared_context=prepared_context, questions=questions,
                    )
                try:
                    validate_link_batch(
                        batch=response["batch"],
                        expected_reference_ids=[item["reference_id"] for item in items],
                        target_block_ids=[
                            block["block_id"] for block in target_context["target_blocks"]
                        ],
                        open_questions=target_context["open_questions"],
                    )
                except ValueError as validation_error:
                    rejected_key = hashlib.sha256("|".join(
                        item["reference_id"] for item in items
                    ).encode("utf-8")).hexdigest()[:20]
                    _write_json(
                        output_path=(
                            checkpoint_root / "rejected_batches"
                            / f"batch-{rejected_key}.json"
                        ),
                        value={
                            "schema_version": 1,
                            "provider": adapter.provider, "model": adapter.model,
                            "context_sha256": target_context["context_sha256"],
                            "validation_error": str(validation_error),
                            "response": response["batch"].model_dump(mode="json"),
                            "provider_metadata": _normalized_batch_metadata(
                                response=response
                            ),
                        },
                    )
                    raise
                metadata = _normalized_batch_metadata(response=response)
                result_by_id = {
                    result.reference_id: result for result in response["batch"].results
                }
                links = [
                    _link_record(
                        item=item, result=result_by_id[item["reference_id"]],
                        target_record=target_record, markdown_db_path=markdown_db_path,
                        batch_metadata=metadata,
                    )
                    for item in items
                ]
                batch_key = hashlib.sha256("|".join(
                    item["reference_id"] for item in items
                ).encode("utf-8")).hexdigest()[:20]
                _write_json(
                    output_path=(
                        checkpoint_root / "batches"
                        / f"batch-{batch_key}.json"
                    ),
                    value={
                        "schema_version": 1, "batch_number": batch_number,
                        "provider": adapter.provider, "model": adapter.model,
                        "context_sha256": target_context["context_sha256"],
                        "links": links,
                    },
                )
                if progress_callback:
                    progress_callback({
                        "event": "batch_completed", "batch_number": batch_number,
                        "batch_count": len(batches), "reference_count": len(items),
                        "attempt": attempt,
                    })
                return links, response, None
            except Exception as error:
                last_error = error
                if attempt <= retry_count:
                    await asyncio.sleep(min(2 ** attempt, 10))
        return [], None, last_error

    return await asyncio.gather(*[
        submit(batch_number=index, items=items)
        for index, items in enumerate(batches, start=1)
    ])


async def _submit_batches_and_close(**kwargs):
    """Keep async provider requests and client cleanup on one event loop."""
    adapter = kwargs["adapter"]
    try:
        return await _submit_batches(**kwargs)
    finally:
        if hasattr(adapter, "aclose"):
            await adapter.aclose()


def _public_cache_metadata(*, prepared_context):
    if prepared_context is None:
        return None
    private_keys = {"system", "input_prefix"}
    return {
        key: value for key, value in prepared_context.items()
        if key not in private_keys
    }


class PremiumReferenceLinkerPipeline:
    """Run one isolated, resumable premium-provider Stage 4 benchmark."""

    @staticmethod
    def run(
        *, markdown_db_path, provider, model=None, adapter=None,
        source_object_keys=None, batch_size=10, maximum_concurrency=3,
        maximum_api_calls=None, cache_ttl_seconds=3600, retry_count=2,
        retain_cache=False, progress_callback=None,
    ):
        selected_model = model or DEFAULT_MODELS[provider]
        work, block_records, _source_records = _load_work(
            markdown_db_path=markdown_db_path, source_object_keys=source_object_keys,
        )
        if not work:
            return {"provider": provider, "model": selected_model,
                    "references_requested": 0, "references_completed": 0,
                    "api_calls": 0, "failed_batch_count": 0, "failures": []}
        target_document_ids = {item["target_document_id"] for item in work}
        if len(target_document_ids) != 1:
            raise ValueError("premium_linker.py Error: one run requires one target document")
        target_document_id = next(iter(target_document_ids))
        target_record = _target_record(
            block_records=block_records, document_id=target_document_id,
        )
        serialized = serialize_target_context(
            document_id=target_document_id, target_blocks=target_record["blocks"],
        )
        target_context = {**serialized, "target_blocks": target_record["blocks"]}
        checkpoint_root = _checkpoint_root(
            markdown_db_path=markdown_db_path, provider=provider, model=selected_model,
            context_sha256=serialized["context_sha256"],
        )
        requested_reference_ids = {item["reference_id"] for item in work}
        all_existing = _load_checkpoints(checkpoint_root=checkpoint_root)
        existing = {
            reference_id: link for reference_id, link in all_existing.items()
            if reference_id in requested_reference_ids
        }
        pending = [item for item in work if item["reference_id"] not in existing]
        if maximum_api_calls is not None:
            pending = pending[:maximum_api_calls * batch_size]
        batches = [
            pending[index:index + batch_size]
            for index in range(0, len(pending), batch_size)
        ]
        selected_adapter = adapter or build_adapter(
            provider=provider, model=selected_model,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        prepared_context = None
        outcomes = []
        try:
            if batches:
                prepared_context = selected_adapter.prepare_target_context(
                    target_context=target_context,
                )
                submit_function = (
                    _submit_batches if adapter is not None else _submit_batches_and_close
                )
                outcomes = asyncio.run(submit_function(
                    adapter=selected_adapter, prepared_context=prepared_context,
                    batches=batches, target_context=target_context,
                    target_record=target_record, markdown_db_path=markdown_db_path,
                    checkpoint_root=checkpoint_root,
                    maximum_concurrency=maximum_concurrency, retry_count=retry_count,
                    progress_callback=progress_callback,
                ))
        finally:
            if prepared_context and not retain_cache:
                selected_adapter.release_target_context(
                    prepared_context=prepared_context,
                )
            if adapter is None and not hasattr(selected_adapter, "aclose"):
                selected_adapter.close()
        failures = []
        usage_totals = Counter()
        for _links, response, error in outcomes:
            if error is not None:
                failures.append({
                    "error": f"premium_linker.py Error: {type(error).__name__}: {error}"
                })
                continue
            usage_totals.update({
                key: value for key, value in response["usage"].items()
                if isinstance(value, int)
            })
        completed = {
            reference_id: link
            for reference_id, link in _load_checkpoints(
                checkpoint_root=checkpoint_root
            ).items()
            if reference_id in requested_reference_ids
        }
        statuses = Counter(link["status"] for link in completed.values())
        manifest = {
            "schema_version": 1, "linker_version": PREMIUM_LINKER_VERSION,
            "provider": provider, "model": selected_model,
            "target_document_id": target_document_id,
            "context_sha256": serialized["context_sha256"],
            "open_question_count": len(serialized["open_questions"]),
            "references_requested": len(work),
            "references_reused": len(existing),
            "references_completed": len(completed),
            "linked": statuses["linked"], "no_match": statuses["no-match"],
            "ambiguous": statuses["ambiguous"], "api_calls": len(outcomes),
            "usage_totals": dict(usage_totals),
            "cache": _public_cache_metadata(prepared_context=prepared_context),
            "failed_batch_count": len(failures), "failures": failures,
        }
        _write_json(output_path=checkpoint_root / "manifest.json", value=manifest)
        return manifest