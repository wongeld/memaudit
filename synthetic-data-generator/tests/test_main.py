import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.main import run_conversations


class ContinueAfterSessionFailureTests(unittest.TestCase):
    def test_all_users_continues_after_a_session_process_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("src.main.load_user_ids", return_value=["first-user", "second-user"]),
                patch(
                    "src.main.run_user_question_bank",
                    side_effect=[
                        RuntimeError("Pi exited with status 1"),
                        {"school": ["A question"]},
                    ],
                ) as run_user,
            ):
                with self.assertRaisesRegex(RuntimeError, "1 session\\(s\\) failed"):
                    run_conversations(
                        all_users=True,
                        categories=["school"],
                        resume=True,
                        session_dir=Path(directory),
                    )

        self.assertEqual(run_user.call_count, 2)
        self.assertEqual(run_user.call_args_list[1].args, ("second-user",))


class ResumeSessionOrderTests(unittest.TestCase):
    def test_all_users_resume_starts_at_last_session_in_question_bank_order(self) -> None:
        user_ids = ["first-user", "last-session-user", "next-user"]
        with tempfile.TemporaryDirectory() as directory:
            session_dir = Path(directory)
            for user_id, timestamp in (
                ("first-user", 2_000_000_000),
                ("last-session-user", 1_000_000_000),
            ):
                session_log = session_dir / f"{user_id}.jsonl"
                session_log.write_text("", encoding="utf-8")
                os.utime(session_log, ns=(timestamp, timestamp))

            with (
                patch("src.main.load_user_ids", return_value=user_ids),
                patch(
                    "src.main.run_user_question_bank",
                    return_value={"school": ["A question"]},
                ) as run_user,
            ):
                run_conversations(
                    all_users=True,
                    categories=["school"],
                    resume=True,
                    session_dir=session_dir,
                )

        self.assertEqual(run_user.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in run_user.call_args_list],
            ["last-session-user", "next-user"],
        )


if __name__ == "__main__":
    unittest.main()
