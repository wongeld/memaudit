# memaudit

**Evaluating Privacy Preservation in Multilingual Assistant Memory via Post-Redaction Inference Audits**


This repository holds the code for the study. Right now it contains the **redactors**:
the tools that mask personal information in English, Swahili and Amharic text before it
is saved as assistant memory. Data generation, memory summaries and the attacker come next.

## Quick start

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# 2. Run
python demo.py
```

The first run downloads the NER models (about 2.6 GB) to `~/.cache/huggingface`.

## Running the demo

```bash
# All example texts
python demo.py

# Amharic examples only
python demo.py --lang am

# Your own text
python demo.py --lang sw --text "Habari, mimi ni Amina kutoka Kisumu."

# Also list every masked span
python demo.py --spans

# Add the LLM redactors (needs .env, see below)
python demo.py --gemini
python demo.py --open

# Your own file, results saved
python demo.py --file my_texts.jsonl --save results.jsonl
```

For each text you get a table with each redactor's output, how many masks it made, which expected
identifiers it caught or missed, and the time taken. A summary table at the end gives totals per
redactor and language.

`--file` takes one `{"lang": "...", "text": "..."}` per line. Add an `"expected"` list (see
`examples/samples.jsonl`) to get the caught/missed column.

## The redactors

| ID | Name | What it does |
|---|---|---|
| C0 | `none` | Masks nothing. The baseline. |
| C1 | `presidio` | Presidio's pattern rules (email, phone, date) plus the NER model below. |
| C2 | `ner` | NER model only. MasakhaNER for Swahili and Amharic, a CoNLL-03 model for English. |
| C3 | `gemini` | Gemini lists the exact text to mask; we mask it. |
| C4 | `open` | Same prompt as C3, with an open-weight model on any OpenAI-compatible server. |

Using them from your own script in this folder:

```python
from redactors import PresidioRedactor

result = PresidioRedactor().redact("Mimi ni Amina Wanjiru, nipigie 0712 345 678.", "sw")
print(result.redacted)
print(result.spans)
```

```
Mimi ni [PERSON], nipigie [PHONE].
[Span(start=8, end=21, label='PERSON', text='Amina Wanjiru', ...), Span(start=31, end=43, label='PHONE', ...)]
```

### Models

| Language | NER model (C1 and C2) | Pinned revision |
|---|---|---|
| English | [`dslim/bert-base-NER`](https://huggingface.co/dslim/bert-base-NER) | `d1a3e8f` |
| Swahili, Amharic | [`masakhane/afroxlmr-large-ner-masakhaner-1.0_2.0`](https://huggingface.co/masakhane/afroxlmr-large-ner-masakhaner-1.0_2.0) | `d15d8ba` |

C1 and C2 use the same NER model, so the difference between them is only Presidio's pattern rules.

### Labels

`PERSON`, `LOCATION`, `ORGANIZATION`, `DATE`, `PHONE`, `EMAIL`, `ID_NUMBER`, `ADDRESS`.
Occupation, age, education, family and health are left in on purpose: those are what the
attacker will try to infer later.

Known gaps, which are part of what we measure:

- NER alone cannot find phone numbers, emails, ID numbers or addresses.
- The English NER model has no DATE label, and Presidio's date rules only catch numeric dates
  such as `14/03/2027`, so "14 March 2027" is missed in English.
- Neither Presidio nor the NER models find `ID_NUMBER` or `ADDRESS` for Kenya or Ethiopia.

## Settings for the LLM redactors (.env)

Copy `.env.example` to `.env` and fill it in. `demo.py` reads it automatically.

| Setting | What it is |
|---|---|
| `GEMINI_API_KEY` | Key from [Google AI Studio](https://aistudio.google.com) |
| `GEMINI_MODEL` | Gemini model ID, e.g. `gemini-2.5-flash` |
| `OPEN_WEIGHT_BASE_URL` | OpenAI-compatible server, e.g. `http://localhost:11434/v1` for Ollama |
| `OPEN_WEIGHT_MODEL` | Model name on that server |
| `OPEN_WEIGHT_API_KEY` | Only for hosted servers; leave empty for local ones |

A model given on the command line (`--gemini gemini-2.5-pro`) overrides `.env`.
Keep `GEMINI_MODEL` the same for everyone running the experiment. `.env` is never committed.

## Tests

```bash
# A few seconds; fake models, no downloads or API keys
pytest

# Also runs the real NER models
RUN_MODEL_TESTS=1 pytest
```

## Files

```
demo.py                   the script you run
redactors/
    base.py               Span, RedactionResult, shared masking, the no-redaction baseline
    ner.py                NER-only redactor and the NER model loader shared with Presidio
    presidio_redactor.py  Presidio redactor
    llm.py                LLM redactor, Gemini client, OpenAI-compatible client, the prompt
    env.py                reads settings from .env
examples/samples.jsonl    example texts with the identifiers each should lose
tests/                    tests
requirements.txt          what to pip install
```

The Swahili and Amharic example texts should be checked by a fluent speaker before they are used
for anything beyond testing.

## Licence

MIT. See `LICENSE`.
