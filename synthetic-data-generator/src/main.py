"""CLI entry point for running synthetic-user conversation question banks."""

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.spawn_user_session import (  # noqa: E402
    CATEGORIES,
    DEFAULT_MODEL,
    QUESTION_BANK_PATH,
    resolve_session_dir,
    run_user_question_bank,
)


def load_user_ids(question_bank_path: Path = QUESTION_BANK_PATH) -> list[str]:
    """Return user IDs in question-bank order, rejecting invalid or duplicate IDs."""
    try:
        records = json.loads(question_bank_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Question bank is not valid JSON: {question_bank_path}") from error

    if not isinstance(records, list):
        raise ValueError(f"Question bank must contain a JSON array: {question_bank_path}")

    user_ids: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Question-bank record {index} must be a JSON object.")
        user_id = record.get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise ValueError(f"Question-bank record {index} has an invalid user_id.")
        if user_id in seen:
            raise ValueError(f"Question bank contains duplicate user_id {user_id!r}.")
        seen.add(user_id)
        user_ids.append(user_id)
    return user_ids


def _resume_start_index(user_ids: Sequence[str], session_dir: Path) -> tuple[int, str | None]:
    """Return the index of the last existing session log in user order."""
    for index in range(len(user_ids) - 1, -1, -1):
        current_user_id = user_ids[index]
        session_log = session_dir / f"{current_user_id}.jsonl"
        if session_log.is_file():
            return index, current_user_id
    return 0, None


def run_conversations(
    *,
    all_users: bool = False,
    user_id: str | None = None,
    categories: Sequence[str] | None = None,
    model: str = DEFAULT_MODEL,
    api_key_env: str = "GEMINI_API_KEY",
    pi_command: str = "pi",
    timeout: float = 0,
    session_dir: Path | None = None,
    resume: bool = False,
) -> dict[str, dict[str, list[str]]]:
    """Run selected question categories for one user or every bank user."""
    if all_users == (user_id is not None):
        raise ValueError("Choose exactly one of all_users=True or user_id.")

    selected_categories = tuple(CATEGORIES if categories is None else categories)
    if not selected_categories:
        raise ValueError("Select at least one category.")
    if len(set(selected_categories)) != len(selected_categories):
        raise ValueError("Categories must not contain duplicates.")
    unknown_categories = set(selected_categories) - set(CATEGORIES)
    if unknown_categories:
        raise ValueError(f"Unknown categories: {', '.join(sorted(unknown_categories))}.")

    if all_users:
        user_ids = load_user_ids()
    elif user_id is not None:
        user_ids = [user_id]
    else:
        raise ValueError("Provide all_users=True or a user_id.")

    start_index = 0
    if all_users and resume:
        start_index, last_session_user_id = _resume_start_index(
            user_ids,
            resolve_session_dir(session_dir),
        )
        if last_session_user_id is not None:
            print(
                f"Resuming at the last existing session in question-bank order for "
                f"user {last_session_user_id}; earlier users are skipped.",
                file=sys.stderr,
                flush=True,
            )

    results: dict[str, dict[str, list[str]]] = {}
    failed_sessions: list[str] = []
    for index, current_user_id in enumerate(user_ids[start_index:], start=start_index + 1):
        action = "Checking progress for" if resume else "Running"
        print(
            f"[{index}/{len(user_ids)}] {action} {', '.join(selected_categories)} "
            f"questions for user {current_user_id}",
            file=sys.stderr,
            flush=True,
        )
        try:
            results[current_user_id] = run_user_question_bank(
                current_user_id,
                categories=selected_categories,
                model=model,
                pi_command=pi_command,
                api_key_env=api_key_env,
                timeout=timeout,
                session_dir=session_dir,
                resume=resume,
            )
        except (OSError, RuntimeError, TimeoutError) as error:
            failed_sessions.append(f"{current_user_id}: {error}")
            print(
                f"Session failed for user {current_user_id}; continuing to the next user.",
                file=sys.stderr,
                flush=True,
            )

    if failed_sessions:
        completed_question_count = sum(
            len(responses)
            for categories_result in results.values()
            for responses in categories_result.values()
        )
        failures = "; ".join(failed_sessions)
        raise RuntimeError(
            f"Completed {completed_question_count} questions for {len(results)} "
            f"user(s); {len(failed_sessions)} session(s) failed: {failures}"
        )
    return results


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run synthetic users' stored conversation questions through Pi JSON mode."
    )
    user_selection = parser.add_mutually_exclusive_group(required=True)
    user_selection.add_argument(
        "--all-users",
        action="store_true",
        help="run the selected categories for every user in the question bank",
    )
    user_selection.add_argument(
        "--uuid",
        dest="user_id",
        help="run questions for one question-bank user_id",
    )
    parser.add_argument(
        "--category",
        dest="categories",
        action="append",
        choices=CATEGORIES,
        help=(
            "category to run; repeat to select multiple categories "
            "(default: all categories)"
        ),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Pi model ID")
    parser.add_argument(
        "--api-key-env",
        default="GEMINI_API_KEY",
        help="environment variable containing the API key (default: GEMINI_API_KEY)",
    )
    parser.add_argument("--pi-command", default="pi", help="Pi CLI command")
    parser.add_argument(
        "--session-dir",
        type=Path,
        help=(
            "directory for per-user JSONL output "
            "(default: PI_CODING_AGENT_SESSION_DIR or .\\sessions)"
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0,
        help="maximum seconds for each user's Pi process (default: no timeout)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="skip successfully completed questions found in the user's session log",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.timeout < 0:
        raise ValueError("--timeout cannot be negative.")
    if args.user_id is not None and args.user_id not in load_user_ids():
        raise ValueError(f"User {args.user_id!r} was not found in the question bank.")

    results = run_conversations(
        all_users=args.all_users,
        user_id=args.user_id,
        categories=args.categories,
        model=args.model,
        api_key_env=args.api_key_env,
        pi_command=args.pi_command,
        timeout=args.timeout,
        session_dir=args.session_dir,
        resume=args.resume,
    )
    question_count = sum(
        len(responses)
        for categories_result in results.values()
        for responses in categories_result.values()
    )
    print(
        f"Completed {question_count} questions for {len(results)} user(s).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from error