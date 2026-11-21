import csv
import json
import tempfile
import unittest
from pathlib import Path

from data.export_multi_turn_conversations import (
    export_sessions,
    iter_session_rows,
)


class ConversationExportTests(unittest.TestCase):
    def test_extracts_turn_text_and_formats_tool_json_as_readable_text(self) -> None:
        events = [
            {
                "type": "message_end",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "Please save this activity."}],
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "thinking", "thinking": "internal thought"},
                        {"type": "text", "text": "I can help with that."},
                    ],
                },
            },
            {
                "type": "tool_execution_end",
                "toolName": "record_user_activity",
                "isError": False,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Canceled. No activity was saved.\n"
                                '{\n  "theme": "school",\n  "title": "Prepare lessons"\n}'
                            ),
                        }
                    ]
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Nothing was saved."}],
                },
            },
            {
                "type": "message_end",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": "What happened?"}],
                },
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            session_path = Path(directory) / "session.jsonl"
            session_path.write_text(
                "".join(json.dumps(event) + "\n" for event in events),
                encoding="utf-8",
            )

            rows = list(iter_session_rows(session_path))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["user_request"], "Please save this activity.")
        self.assertEqual(
            rows[0]["agent_response"],
            "I can help with that.\n\nNothing was saved.",
        )
        self.assertIn("record_user_activity:", rows[0]["tool_output"])
        self.assertIn("theme: school", rows[0]["tool_output"])
        self.assertNotIn('"theme"', rows[0]["tool_output"])
        self.assertEqual(rows[1]["user_request"], "What happened?")

    def test_exports_all_sessions_with_expected_csv_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sessions_dir = root / "sessions"
            sessions_dir.mkdir()
            session_path = sessions_dir / "user.jsonl"
            session_path.write_text(
                json.dumps(
                    {
                        "type": "message_end",
                        "message": {
                            "role": "user",
                            "content": [{"type": "text", "text": "Hello"}],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            output_path = root / "data" / "multi-turn-conversation.csv"

            row_count = export_sessions(sessions_dir, output_path)

            with output_path.open(encoding="utf-8-sig", newline="") as output_file:
                reader = csv.DictReader(output_file)
                rows = list(reader)

        self.assertEqual(row_count, 1)
        self.assertEqual(
            reader.fieldnames,
            ["user_request", "agent_response", "tool_output"],
        )
        self.assertEqual(rows[0]["user_request"], "Hello")


if __name__ == "__main__":
    unittest.main()
