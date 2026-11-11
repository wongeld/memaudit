"""Run the redactors on example texts and show the results in the terminal.

Examples:
    python demo.py                              all samples, with none, presidio and ner
    python demo.py --lang am                    Amharic samples only
    python demo.py --text "..." --lang sw       your own text
    python demo.py --file my.jsonl              one {"lang", "text"} object per line
    python demo.py --gemini                     add Gemini, model from GEMINI_MODEL in .env
    python demo.py --gemini gemini-2.5-pro      add Gemini, with this model instead
    python demo.py --spans --save out.jsonl     list every span, save results
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from redactors.base import LANGUAGES, NoRedaction, RedactionResult, Redactor
from redactors.env import load_env

SAMPLES = Path(__file__).resolve().parent / "examples" / "samples.jsonl"

# One colour per label, used to highlight masks and spans.
COLOURS = {
    "PERSON": "bold magenta", "LOCATION": "bold green", "ORGANIZATION": "bold blue",
    "DATE": "bold yellow", "PHONE": "bold red", "EMAIL": "bold cyan",
    "ID_NUMBER": "bold white on red", "ADDRESS": "bold white on blue",
}


def load_samples(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_redactors(names: list[str], gemini: str | None, open_model: str | None) -> list[Redactor]:
    """Create the requested redactors. NER and Presidio share one model loader."""
    from redactors.ner import NerDetector, NerRedactor
    from redactors.presidio_redactor import PresidioRedactor

    detector = NerDetector()
    redactors: list[Redactor] = []
    for name in names:
        if name == "none":
            redactors.append(NoRedaction())
        elif name == "presidio":
            redactors.append(PresidioRedactor(detector))
        elif name == "ner":
            redactors.append(NerRedactor(detector))
        else:
            raise SystemExit(f"unknown redactor {name!r}")

    # None means the flag was not used. An empty string means the flag was used
    # without a model, so the client reads the model from .env.
    if gemini is not None:
        from redactors.llm import GeminiClient, LLMRedactor
        redactors.append(LLMRedactor(GeminiClient(gemini or None), name="gemini"))
    if open_model is not None:
        from redactors.llm import LLMRedactor, OpenAICompatibleClient
        redactors.append(LLMRedactor(OpenAICompatibleClient(open_model or None), name="open"))
    return redactors


def warm_up(redactors: list[Redactor], langs: set[str]) -> None:
    """Run each local redactor once per language so model loading is not counted in the timings.

    LLM redactors are skipped, because a warm-up call would cost an API request.
    """
    from redactors.llm import LLMRedactor

    for redactor in redactors:
        if isinstance(redactor, LLMRedactor):
            continue
        for lang in langs:
            redactor.redact("warm up", lang)


def highlight_masks(redacted: str) -> Text:
    """Colour every [LABEL] mask in a redacted text."""
    out = Text(redacted)
    for label, style in COLOURS.items():
        out.highlight_words([f"[{label}]"], style=style)
    return out


def highlight_spans(result: RedactionResult) -> Text:
    """Show the original text with the masked parts underlined in their label colour."""
    out = Text(result.original)
    for span in result.spans:
        out.stylize(f"{COLOURS[span.label]} underline", span.start, span.end)
    return out


def check_expected(result: RedactionResult, expected: list[dict]) -> tuple[int, list[str]]:
    """Count expected identifiers that ended up fully inside a masked span."""
    caught, missed = 0, []
    for item in expected:
        piece = item["text"]
        start = result.original.find(piece)
        end = start + len(piece)
        covered = start >= 0 and any(s.start <= start and end <= s.end for s in result.spans)
        if covered:
            caught += 1
        else:
            missed.append(f"{piece} ({item['label']})")
    return caught, missed


def show_sample(console: Console, sample: dict, results: list[RedactionResult], show_spans: bool) -> None:
    console.rule(f"[bold]{sample.get('id', '')}  ·  {sample['lang']}")
    console.print(Text("Original: ", style="dim") + Text(sample["text"]))
    console.print()

    expected = sample.get("expected")
    table = Table(show_lines=True, expand=True)
    table.add_column("Redactor", style="bold", no_wrap=True)
    table.add_column("Redacted text", ratio=1)
    table.add_column("Masks", justify="right")
    if expected:
        table.add_column("Expected caught", no_wrap=True)
    table.add_column("Time", justify="right", no_wrap=True)

    for result in results:
        row = [result.redactor, highlight_masks(result.redacted), str(len(result.spans))]
        if expected:
            caught, missed = check_expected(result, expected)
            cell = Text(f"{caught}/{len(expected)}", style="green" if not missed else "yellow")
            for m in missed:
                cell.append(f"\nmissed: {m}", style="dim")
            row.append(cell)
        row.append(f"{result.seconds:.2f}s")
        table.add_row(*row)
    console.print(table)

    for result in results:
        for w in result.warnings:
            console.print(f"[yellow]warning[/] {result.redactor}: {w}")

    if show_spans:
        for result in results:
            if not result.spans:
                continue
            console.print(Text(f"{result.redactor}: ", style="bold") + highlight_spans(result))
            spans = Table(box=None, padding=(0, 2), show_header=True, header_style="dim")
            spans.add_column("label")
            spans.add_column("text")
            spans.add_column("offsets", justify="right")
            spans.add_column("score", justify="right")
            for s in result.spans:
                score = "" if s.score is None else f"{s.score:.2f}"
                spans.add_row(Text(s.label, style=COLOURS[s.label]), s.text, f"{s.start}-{s.end}", score)
            console.print(spans)
            console.print()


def show_summary(console: Console, rows: list[tuple[dict, RedactionResult]]) -> None:
    """Expected identifiers caught per redactor and language, over all samples shown."""
    totals: dict[tuple[str, str], list[int]] = {}
    for sample, result in rows:
        expected = sample.get("expected")
        if not expected:
            continue
        caught, _ = check_expected(result, expected)
        cell = totals.setdefault((result.redactor, result.lang), [0, 0])
        cell[0] += caught
        cell[1] += len(expected)
    if not totals:
        return

    redactors = list(dict.fromkeys(r for r, _ in totals))
    langs = [lang for lang in LANGUAGES if any(lg == lang for _, lg in totals)]
    table = Table()
    table.add_column("Redactor", style="bold")
    for lang in langs:
        table.add_column(lang, justify="right")
    for name in redactors:
        cells = []
        for lang in langs:
            caught, total = totals.get((name, lang), [0, 0])
            cells.append(f"{caught}/{total}" if total else "-")
        table.add_row(name, *cells)
    console.rule()
    console.print("[bold]Expected identifiers caught[/]")
    console.print(table)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Show what each redactor masks.")
    parser.add_argument("--redactors", default="none,presidio,ner",
                        help="comma-separated: none, presidio, ner (default: all three)")
    parser.add_argument("--gemini", metavar="MODEL", nargs="?", const="",
                        help="also run the Gemini redactor (model from GEMINI_MODEL in .env unless given)")
    parser.add_argument("--open", metavar="MODEL", dest="open_model", nargs="?", const="",
                        help="also run the open-weight redactor (model from OPEN_WEIGHT_MODEL in .env)")
    parser.add_argument("--text", help="redact this text instead of the samples (needs --lang)")
    parser.add_argument("--file", type=Path, help="JSONL file with one {\"lang\", \"text\"} per line")
    parser.add_argument("--lang", choices=LANGUAGES, help="language of --text, or filter the samples")
    parser.add_argument("--spans", action="store_true", help="also list every masked span")
    parser.add_argument("--save", type=Path, help="write all results to this JSONL file")
    parser.add_argument("--debug", action="store_true", help="show full tracebacks for errors")
    args = parser.parse_args(argv)

    if args.text:
        if not args.lang:
            parser.error("--text needs --lang")
        samples = [{"id": "input", "lang": args.lang, "text": args.text}]
    else:
        samples = load_samples(args.file or SAMPLES)
        if args.lang:
            samples = [s for s in samples if s["lang"] == args.lang]

    console = Console()
    load_env()
    names = [n.strip() for n in args.redactors.split(",") if n.strip()]
    with console.status("Loading redactors (the first NER run downloads about 2.6 GB of models)..."):
        try:
            redactors = build_redactors(names, args.gemini, args.open_model)
        except RuntimeError as error:
            raise SystemExit(f"Error: {error}") from None
        warm_up(redactors, {s["lang"] for s in samples})

    rows: list[tuple[dict, RedactionResult]] = []
    for sample in samples:
        results = []
        with console.status(f"Redacting {sample.get('id', '')}..."):
            for redactor in redactors:
                # An API error (bad key, unknown model, rate limit) stops the run with
                # one readable line. --debug shows the full traceback instead.
                try:
                    results.append(redactor.redact(sample["text"], sample["lang"]))
                except Exception as error:
                    if args.debug:
                        raise
                    raise SystemExit(f"Error from the {redactor.name} redactor: {error}") from None
        show_sample(console, sample, results, args.spans)
        rows.extend((sample, r) for r in results)

    show_summary(console, rows)

    if args.save:
        with open(args.save, "w", encoding="utf-8") as f:
            for sample, result in rows:
                record = {"id": sample.get("id"), **asdict(result)}
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        console.print(f"Saved {len(rows)} results to {args.save}")


if __name__ == "__main__":
    main()
