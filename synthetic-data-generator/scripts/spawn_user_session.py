"""Run a synthetic user's question bank through Pi's JSON output mode."""

import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUESTION_BANK_PATH = PROJECT_ROOT / "data" / "synthetic_conversation_starter.json"
CATEGORIES = (
    "work",
    "travel",
    "school",
    "shopping",
    "family interactions",
    "daily planning",
)
DEFAULT_MODEL = "google/gemini-2.5-flash"


def _load_question_bank(path: Path = QUESTION_BANK_PATH) -> list[dict[str, object]]:
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Question bank is not valid JSON: {path}") from error

    if not isinstance(records, list):
        raise ValueError(f"Question bank must contain a JSON array: {path}")
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise ValueError(f"Question-bank record {index} must be a JSON object.")
        if not isinstance(record.get("user_id"), str):
            raise ValueError(f"Question-bank record {index} has an invalid user_id.")
        for category in CATEGORIES:
            questions = record.get(category)
            if not isinstance(questions, list) or not all(
                isinstance(question, str) for question in questions
            ):
                raise ValueError(
                    f"Question-bank record {index} category {category!r} "
                    "must be an array of strings."
                )
    return records


def _pi_command_args(pi_command: str) -> list[str]:
    """Resolve npm's Windows shim to Node so prompts remain safe argv values."""
    executable = shutil.which(pi_command)
    if executable is None:
        raise FileNotFoundError(f"Could not find Pi command {pi_command!r}.")

    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        npm_directory = Path(executable).parent
        cli_path = (
            npm_directory
            / "node_modules"
            / "@earendil-works"
            / "pi-coding-agent"
            / "dist"
            / "bundle"
            / "cli.js"
        )
        if not cli_path.is_file():
            raise FileNotFoundError(f"Could not find Pi's Node entry point: {cli_path}")
        local_node = npm_directory / "node.exe"
        node = str(local_node) if local_node.is_file() else shutil.which("node")
        if node is None:
            raise FileNotFoundError("Could not find Node.js to start Pi.")
        return [node, str(cli_path)]

    return [executable]


def resolve_session_dir(session_dir: Path | None = None) -> Path:
    """Resolve the output directory shared by the runner and resume checks."""
    configured_session_dir = session_dir
    if configured_session_dir is None:
        session_dir_value = os.environ.get("PI_CODING_AGENT_SESSION_DIR")
        configured_session_dir = (
            Path(session_dir_value) if session_dir_value else Path("sessions")
        )
    configured_session_dir = configured_session_dir.expanduser()
    if not configured_session_dir.is_absolute():
        configured_session_dir = PROJECT_ROOT / configured_session_dir
    return configured_session_dir.resolve()


def _successful_user_prompts(session_log: Path) -> list[str]:
    """Read user prompts whose Pi turns completed successfully from a JSONL log."""
    if not session_log.exists():
        return []

    completed: list[str] = []
    pending_prompt: str | None = None
    with session_log.open("r", encoding="utf-8") as log_file:
        for line_number, line in enumerate(log_file, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                if not line.endswith("\n"):
                    break
                raise ValueError(
                    f"Session log contains invalid JSON on line {line_number}: "
                    f"{session_log}"
                ) from error
            if not isinstance(event, dict):
                raise ValueError(
                    f"Session log contains a non-object event on line {line_number}: "
                    f"{session_log}"
                )

            if event.get("type") == "message_end":
                message = event.get("message")
                if isinstance(message, dict) and message.get("role") == "user":
                    pending_prompt = None
                    content = message.get("content", [])
                    if isinstance(content, list):
                        pending_prompt = "".join(
                            item.get("text", "")
                            for item in content
                            if isinstance(item, dict)
                            and item.get("type") == "text"
                            and isinstance(item.get("text"), str)
                        )
            elif event.get("type") == "turn_end" and pending_prompt is not None:
                message = event.get("message")
                if isinstance(message, dict) and message.get("role") == "assistant":
                    stop_reason = message.get("stopReason")
                    if stop_reason == "stop" or stop_reason == "length":
                        completed.append(pending_prompt)
                        pending_prompt = None
                    elif stop_reason == "error" or stop_reason == "aborted":
                        pending_prompt = None
    return completed


def _completed_prompt_prefix(prompts: Sequence[str], completed: Sequence[str]) -> int:
    """Return the longest prompt prefix found in a contiguous completed-log segment."""
    longest_prefix = 0
    for start in range(len(completed)):
        matched = 0
        while (
            matched < len(prompts)
            and start + matched < len(completed)
            and completed[start + matched] == prompts[matched]
        ):
            matched += 1
        longest_prefix = max(longest_prefix, matched)
    return longest_prefix


def run_user_question_bank(
    user_id: str,
    *,
    categories: Sequence[str] | None = None,
    model: str = DEFAULT_MODEL,
    pi_command: str = "pi",
    api_key_env: str = "GEMINI_API_KEY",
    timeout: float = 0,
    session_dir: Path | None = None,
    resume: bool = False,
) -> dict[str, list[str]]:
    """Run a user's selected questions in one Pi JSON-mode process.

    Pi emits JSONL events to stdout. The same events are appended to a
    per-user file in PI_CODING_AGENT_SESSION_DIR (or the project sessions
    directory if that variable is unset). With resume enabled, successfully
    completed prompts in that file are skipped.
    """
    selected_categories = tuple(CATEGORIES if categories is None else categories)
    if not selected_categories:
        raise ValueError("Select at least one category.")
    if len(set(selected_categories)) != len(selected_categories):
        raise ValueError("Categories must not contain duplicates.")
    unknown_categories = set(selected_categories) - set(CATEGORIES)
    if unknown_categories:
        raise ValueError(f"Unknown categories: {', '.join(sorted(unknown_categories))}.")
    if timeout < 0:
        raise ValueError("timeout cannot be negative.")

    records = _load_question_bank()
    user_record = next(
        (record for record in records if record["user_id"] == user_id),
        None,
    )
    if user_record is None:
        raise ValueError(f"User {user_id!r} was not found in the question bank.")

    questions_by_category = {
        category: list(user_record[category]) for category in selected_categories
    }
    prompts = [
        question
        for questions in questions_by_category.values()
        for question in questions
    ]
    if not prompts:
        print(f"No questions found for user {user_id}.", file=sys.stderr, flush=True)
        return questions_by_category

    configured_session_dir = resolve_session_dir(session_dir)
    configured_session_dir.mkdir(parents=True, exist_ok=True)
    session_log = configured_session_dir / f"{user_id}.jsonl"

    if resume:
        completed_count = _completed_prompt_prefix(
            prompts,
            _successful_user_prompts(session_log),
        )
        if completed_count == len(prompts):
            print(
                f"All {len(prompts)} selected questions are already complete for "
                f"user {user_id}.",
                file=sys.stderr,
                flush=True,
            )
            return questions_by_category
        if completed_count:
            print(
                f"Resuming user {user_id} at question {completed_count + 1} "
                f"of {len(prompts)}.",
                file=sys.stderr,
                flush=True,
            )
        prompts = prompts[completed_count:]

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise ValueError(f"API key environment variable {api_key_env!r} is not set.")

    command = [
        *_pi_command_args(pi_command),
        "--mode",
        "json",
        "--model",
        model,
        "--api-key",
        api_key,
        "--session-id",
        user_id,
        *prompts,
    ]
    print(f"Saving JSONL conversation to {session_log}", file=sys.stderr, flush=True)

    try:
        log_file = session_log.open("ab")
    except OSError as error:
        raise OSError(f"Could not open session log {session_log}: {error}") from error

    try:
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
        )
    except OSError as error:
        log_file.close()
        raise RuntimeError(f"Could not start Pi: {error}") from error

    output_errors: list[OSError] = []
    output_bytes = 0

    def save_and_display_output() -> None:
        nonlocal output_bytes
        assert process.stdout is not None
        for line in process.stdout:
            try:
                log_file.write(line)
                log_file.flush()
                output_bytes += len(line)
            except OSError as error:
                output_errors.append(error)
            try:
                stdout_buffer = getattr(sys.stdout, "buffer", None)
                if stdout_buffer is not None:
                    stdout_buffer.write(line)
                    stdout_buffer.flush()
                else:
                    sys.stdout.write(line.decode("utf-8", errors="replace"))
                    sys.stdout.flush()
            except OSError as error:
                output_errors.append(error)

    output_thread = threading.Thread(target=save_and_display_output)
    output_thread.start()
    try:
        process.wait(timeout=timeout or None)
    except subprocess.TimeoutExpired as error:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        output_thread.join()
        process.stdout.close()
        log_file.close()
        raise TimeoutError(
            f"Pi exceeded {timeout} seconds while running questions for user "
            f"{user_id}; partial output is in {session_log}."
        ) from error
    except BaseException:
        process.terminate()
        process.wait()
        output_thread.join()
        process.stdout.close()
        log_file.close()
        raise
    output_thread.join()
    process.stdout.close()
    log_file.close()

    if output_errors:
        raise OSError(f"Could not write Pi output to {session_log}: {output_errors[0]}")
    if process.returncode != 0:
        raise RuntimeError(
            f"Pi exited with status {process.returncode}; output is in {session_log}."
        )
    if output_bytes == 0:
        raise RuntimeError(
            f"Pi returned no JSONL output; check its stderr. "
            f"The session log is empty: {session_log}."
        )
    return questions_by_category


def run_category_questions(
    user_id: str,
    category: str,
    *,
    model: str = DEFAULT_MODEL,
    pi_command: str = "pi",
    api_key_env: str = "GEMINI_API_KEY",
    timeout: float = 0,
    session_dir: Path | None = None,
    resume: bool = False,
) -> dict[str, list[str]]:
    """Run a single category for a user."""
    return run_user_question_bank(
        user_id,
        categories=[category],
        model=model,
        pi_command=pi_command,
        api_key_env=api_key_env,
        timeout=timeout,
        session_dir=session_dir,
        resume=resume,
    )
