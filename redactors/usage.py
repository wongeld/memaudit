"""Persist provider-reported token usage and estimate paid-tier API costs."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

USAGE_FILE = Path(__file__).resolve().parents[1] / "results" / "llm_usage.jsonl"
USAGE_STAGES = (
    "Step 1 redaction",
    "Step 2 summarization",
    "Step 3 attacks",
    "Step 4 evaluation",
    "Step 5 synthetic test",
    "Other/standalone",
)


@dataclass(frozen=True)
class ModelRates:
    input_per_million: float
    output_per_million: float
    cached_input_per_million: float


@dataclass(frozen=True)
class UsageSummary:
    stage: str
    provider: str
    model: str
    calls: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int
    cost_usd: float | None


def _rates_for(provider: str, model: str, when: date) -> ModelRates | None:
    if provider.lower() != "gemini":
        return None

    model = model.removeprefix("models/").lower()
    if model == "gemini-3.1-flash-lite":
        return ModelRates(0.25, 1.50, 0.025)
    if model == "gemini-3.8-flash":
        if when >= date(2027, 1, 1):
            return ModelRates(1.50, 7.50, 0.15)
        return ModelRates(0.75, 3.75, 0.075)
    if model == "gemini-4-argon":
        if when >= date(2026, 12, 1):
            return ModelRates(4.00, 20.00, 0.20)
        return ModelRates(2.00, 10.00, 0.10)
    return None


def _token_count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def record_usage(
    *,
    stage: str,
    provider: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_input_tokens: int | None = 0,
    path: Path = USAGE_FILE,
    occurred_at: datetime | None = None,
) -> None:
    occurred_at = occurred_at or datetime.now(timezone.utc)
    cached_count = cached_input_tokens or 0
    rates = _rates_for(provider, model, occurred_at.date())
    cost = None
    if input_tokens is not None and output_tokens is not None and rates is not None:
        cached_count = min(cached_count, input_tokens)
        if cached_count == 0 or rates.cached_input_per_million is not None:
            cost = (
                (input_tokens - cached_count) * rates.input_per_million
                + cached_count * rates.cached_input_per_million
                + output_tokens * rates.output_per_million
            ) / 1_000_000

    event = {
        "timestamp": occurred_at.isoformat(),
        "stage": stage,
        "provider": provider,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "input_rate_per_million_usd": rates.input_per_million if rates else None,
        "output_rate_per_million_usd": rates.output_per_million if rates else None,
        "cached_input_rate_per_million_usd": rates.cached_input_per_million if rates else None,
        "estimated_cost_usd": cost,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as usage_file:
        usage_file.write(json.dumps(event) + "\n")


def record_gemini_usage(
    stage: str, model: str, response: object, path: Path = USAGE_FILE
) -> None:
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        record_usage(
            stage=stage, provider="gemini", model=model, input_tokens=None,
            output_tokens=None, cached_input_tokens=None, path=path,
        )
        return

    input_tokens = _token_count(getattr(metadata, "prompt_token_count", None))
    candidates = _token_count(getattr(metadata, "candidates_token_count", None))
    thoughts = _token_count(getattr(metadata, "thoughts_token_count", None))
    output_tokens = None if candidates is None and thoughts is None else (candidates or 0) + (thoughts or 0)
    cached_tokens = _token_count(getattr(metadata, "cached_content_token_count", None))
    record_usage(
        stage=stage,
        provider="gemini",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        path=path,
    )


def record_openai_usage(
    stage: str, model: str, response: object, path: Path = USAGE_FILE
) -> None:
    usage = getattr(response, "usage", None)
    input_tokens = _token_count(getattr(usage, "prompt_tokens", None))
    output_tokens = _token_count(getattr(usage, "completion_tokens", None))
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    cached_tokens = _token_count(getattr(prompt_details, "cached_tokens", None))
    record_usage(
        stage=stage,
        provider="openai-compatible",
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_input_tokens=cached_tokens,
        path=path,
    )


def summarize_usage(path: Path = USAGE_FILE) -> list[UsageSummary]:
    groups: dict[tuple[str, str, str], dict[str, int | float | bool]] = defaultdict(
        lambda: {
            "calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "missing_input": False,
            "missing_output": False,
            "unpriced": False,
            "cost_usd": 0.0,
        }
    )
    if path.exists():
        with path.open(encoding="utf-8") as usage_file:
            for line in usage_file:
                if not line.strip():
                    continue
                event = json.loads(line)
                key = (event["stage"], event["provider"], event["model"])
                group = groups[key]
                group["calls"] = int(group["calls"]) + 1
                input_tokens = event["input_tokens"]
                output_tokens = event["output_tokens"]
                if input_tokens is None:
                    group["missing_input"] = True
                else:
                    group["input_tokens"] = int(group["input_tokens"]) + input_tokens
                if output_tokens is None:
                    group["missing_output"] = True
                else:
                    group["output_tokens"] = int(group["output_tokens"]) + output_tokens
                group["cached_input_tokens"] = int(group["cached_input_tokens"]) + (
                    event.get("cached_input_tokens") or 0
                )
                cost = event["estimated_cost_usd"]
                if cost is None:
                    group["unpriced"] = True
                else:
                    group["cost_usd"] = float(group["cost_usd"]) + cost

    summaries = []
    for stage in (*USAGE_STAGES, *(s for s, _, _ in groups if s not in USAGE_STAGES)):
        stage_groups = sorted((key, value) for key, value in groups.items() if key[0] == stage)
        if not stage_groups:
            summaries.append(UsageSummary(stage, "-", "-", 0, 0, 0, 0, 0.0))
            continue
        for (_, provider, model), group in stage_groups:
            input_tokens = None if group["missing_input"] else int(group["input_tokens"])
            output_tokens = None if group["missing_output"] else int(group["output_tokens"])
            cost = None if group["unpriced"] else float(group["cost_usd"])
            summaries.append(
                UsageSummary(
                    stage=stage,
                    provider=provider,
                    model=model,
                    calls=int(group["calls"]),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=int(group["cached_input_tokens"]),
                    cost_usd=cost,
                )
            )
    return summaries
