import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from redactors.usage import record_gemini_usage, record_usage, summarize_usage
from step4_evaluate import usage_cost_table


class LLMUsageTests(unittest.TestCase):
    def test_gemini_usage_includes_thinking_and_cached_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            response = SimpleNamespace(
                usage_metadata=SimpleNamespace(
                    prompt_token_count=1_000,
                    candidates_token_count=20,
                    thoughts_token_count=5,
                    cached_content_token_count=100,
                )
            )

            record_gemini_usage("Step 3 attacks", "gemini-3.1-flash-lite", response, path)
            event = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(event["input_tokens"], 1_000)
        self.assertEqual(event["output_tokens"], 25)
        self.assertEqual(event["cached_input_tokens"], 100)
        self.assertAlmostEqual(event["estimated_cost_usd"], 0.000265)

    def test_unknown_model_is_not_reported_as_zero_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            record_usage(
                stage="Step 2 summarization",
                provider="gemini",
                model="unlisted-model",
                input_tokens=100,
                output_tokens=20,
                path=path,
            )

            summaries = summarize_usage(path)

        memory_summary = next(row for row in summaries if row.stage == "Step 2 summarization")
        self.assertEqual(memory_summary.calls, 1)
        self.assertIsNone(memory_summary.cost_usd)

    def test_missing_usage_has_zero_cost_and_unmetered_call_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            record_gemini_usage("Step 3 attacks", "gemini-3.1-flash-lite", object(), path)

            summaries = summarize_usage(path)

        attack_summary = next(row for row in summaries if row.stage == "Step 3 attacks")
        empty_redaction_summary = next(row for row in summaries if row.stage == "Step 1 redaction")
        self.assertEqual(attack_summary.calls, 1)
        self.assertIsNone(attack_summary.cost_usd)
        self.assertEqual(empty_redaction_summary.calls, 0)
        self.assertEqual(empty_redaction_summary.cost_usd, 0.0)

    def test_model_price_changes_apply_on_their_effective_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            for when in (
                datetime(2026, 11, 21, tzinfo=timezone.utc),
                datetime(2027, 1, 1, tzinfo=timezone.utc),
            ):
                record_usage(
                    stage="Step 3 attacks",
                    provider="gemini",
                    model="gemini-3.8-flash",
                    input_tokens=1_000_000,
                    output_tokens=1_000_000,
                    path=path,
                    occurred_at=when,
                )

            attack_summary = next(
                row for row in summarize_usage(path) if row.stage == "Step 3 attacks"
            )

        self.assertAlmostEqual(attack_summary.cost_usd or 0, 13.5)

    def test_step_four_table_displays_costs_and_zero_use_stages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.jsonl"
            record_usage(
                stage="Step 3 attacks",
                provider="gemini",
                model="gemini-3.1-flash-lite",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                path=path,
            )

            rows, total = usage_cost_table(path)

        attack_row = next(row for row in rows if row[0] == "Step 3 attacks")
        evaluation_row = next(row for row in rows if row[0] == "Step 4 evaluation")
        self.assertEqual(attack_row[-1], "$1.7500")
        self.assertEqual(evaluation_row[-1], "$0.00")
        self.assertEqual(total, "$1.7500")


if __name__ == "__main__":
    unittest.main()
