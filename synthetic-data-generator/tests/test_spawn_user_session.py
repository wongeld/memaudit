import json
import tempfile
import unittest
from pathlib import Path

from scripts.spawn_user_session import (
    _completed_prompt_prefix,
    _successful_user_prompts,
)


def _user_prompt(text: str) -> dict[str, object]:
    return {
        "type": "message_end",
        "message": {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        },
    }


def _turn_end(stop_reason: str) -> dict[str, object]:
    return {
        "type": "turn_end",
        "message": {"role": "assistant", "stopReason": stop_reason},
    }


class SessionResumeTests(unittest.TestCase):
    def test_only_successfully_completed_user_prompts_are_recovered(self) -> None:
        events = [
            _user_prompt("first"),
            _turn_end("toolUse"),
            _turn_end("stop"),
            _user_prompt("failed"),
            _turn_end("error"),
            _user_prompt("interrupted"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            session_log = Path(directory) / "session.jsonl"
            session_log.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )

            self.assertEqual(_successful_user_prompts(session_log), ["first"])

    def test_resume_matches_the_longest_prompt_prefix_in_log_history(self) -> None:
        completed = ["old question", "first", "second", "later question"]

        self.assertEqual(
            _completed_prompt_prefix(["first", "second", "third"], completed),
            2,
        )

    def test_missing_session_log_has_no_completed_prompts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session_log = Path(directory) / "missing.jsonl"

            self.assertEqual(_successful_user_prompts(session_log), [])


if __name__ == "__main__":
    unittest.main()
