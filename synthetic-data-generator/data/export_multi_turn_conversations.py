"""Export saved Pi JSONL sessions into a readable three-column CSV."""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterator, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SESSIONS_DIR = PROJECT_ROOT / "sessions"
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().with_name(
    "multi-turn-conversation.csv"
)
CSV_COLUMNS = ("user_request", "agent_response", "tool_output")


class ConversationTurn(TypedDict):
    user_request: str
    agent_response: list[str]
    tool_output: list[str]


class ConversationRow(TypedDict):
    user_request: str
    agent_response: str
    tool_output: str


def _content_text(content: Any) -> str:
    """Extract readable text blocks from a Pi message or tool result."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"].strip()
        for block in content
        if isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
        and block["text"].strip()
    )


def _format_value(value: Any, indent: int = 0) -> list[str]:
    """Render JSON values as key/value text without JSON punctuation."""
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}{key}:")
                child_lines = _format_value(item, indent + 2)
                lines.extend(child_lines or [f"{' ' * (indent + 2)}(empty)"])
            else:
                lines.append(f"{prefix}{key}: {item}")
        return lines
    if isinstance(value, list):
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}-")
                lines.extend(_format_value(item, indent + 2))
            else:
                lines.append(f"{prefix}- {item}")
        return lines
    return [f"{prefix}{value}"]


def _readable_tool_text(text: str) -> str:
    """Convert JSON tool payloads, including JSON appended to prose, to text."""
    stripped = text.strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for index, character in enumerate(stripped):
            if character not in "[{" or (
                index > 0 and not stripped[index - 1].isspace()
            ):
                continue
            try:
                value, end = decoder.raw_decode(stripped, index)
            except json.JSONDecodeError:
                continue
            if not stripped[end:].strip():
                prefix = stripped[:index].strip()
                rendered = "\n".join(_format_value(value))
                return f"{prefix}\n{rendered}".strip() if prefix else rendered
        return stripped

    while isinstance(value, str):
        try:
            nested_value = json.loads(value)
        except json.JSONDecodeError:
            break
        if isinstance(nested_value, str):
            break
        value = nested_value
    return "\n".join(_format_value(value))


def _tool_output(event: dict[str, Any]) -> str:
    result = event.get("result")
    if isinstance(result, dict):
        text = _content_text(result.get("content"))
    else:
        text = _content_text(result)
    if not text:
        return ""

    tool_name = event.get("toolName")
    label = str(tool_name) if isinstance(tool_name, str) else "tool"
    if event.get("isError") is True:
        label = f"{label} (error)"
    return f"{label}:\n{_readable_tool_text(text)}"


def _new_row(request: str) -> ConversationTurn:
    return {
        "user_request": request,
        "agent_response": [],
        "tool_output": [],
    }


def _finish_row(row: ConversationTurn) -> ConversationRow:
    return {
        "user_request": row["user_request"],
        "agent_response": "\n\n".join(row["agent_response"]),
        "tool_output": "\n\n".join(row["tool_output"]),
    }


def iter_session_rows(session_path: Path) -> Iterator[ConversationRow]:
    """Yield one row per user message, joining its assistant and tool outputs."""
    current_row: ConversationTurn | None = None
    with session_path.open("r", encoding="utf-8") as session_file:
        for line_number, line in enumerate(session_file, start=1):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"Invalid JSON on line {line_number} of {session_path}."
                ) from error
            if not isinstance(event, dict):
                raise ValueError(
                    f"Expected a JSON object on line {line_number} of {session_path}."
                )

            event_type = event.get("type")
            if event_type == "message_end":
                message = event.get("message")
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                text = _content_text(message.get("content"))
                if role == "user":
                    if current_row is not None:
                        yield _finish_row(current_row)
                    current_row = _new_row(text)
                elif role == "assistant" and current_row is not None and text:
                    current_row["agent_response"].append(text)
            elif event_type == "tool_execution_end" and current_row is not None:
                output = _tool_output(event)
                if output:
                    current_row["tool_output"].append(output)

    if current_row is not None:
        yield _finish_row(current_row)


def export_sessions(sessions_dir: Path, output_path: Path) -> int:
    """Export all JSONL files from a directory and return the row count."""
    session_paths = sorted(sessions_dir.glob("*.jsonl"))
    if not session_paths:
        raise FileNotFoundError(f"No JSONL session files found in {sessions_dir}.")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with output_path.open("w", encoding="utf-8-sig", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for session_path in session_paths:
            for row in iter_session_rows(session_path):
                writer.writerow(row)
                row_count += 1
    return row_count


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export saved Pi JSONL sessions to a readable conversation CSV."
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_SESSIONS_DIR,
        help=f"directory containing session JSONL files (default: {DEFAULT_SESSIONS_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"CSV output path (default: {DEFAULT_OUTPUT_PATH})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        row_count = export_sessions(args.sessions_dir, args.output)
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Exported {row_count} conversation turns to {args.output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
