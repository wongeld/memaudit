# memaudit

**Evaluating Privacy Preservation in Multilingual Assistant Memory via Post-Redaction Inference Audits**

Synthetic users talk to an assistant in English, Swahili or Amharic. Each session is redacted,
turned into a memory note, and an attacker model then tries to recover the user's attributes
and pick the user out of all 40 profiles after reading 1, 3, 5 or 10 notes.

## Quick start

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt # then fill in the API key and model IDs
```

Then run the four steps in order, from this folder:

```bash
python step1_redact.py      # sessions/  -> redacted/
python step2_memory.py      # redacted/  -> memory/
python step3_attack.py      # memory/    -> results/attacks/
python step4_evaluate.py    # everything -> results/paper_tables.md, results/report.md
```

Every step can be stopped and run again: it skips what is already done. Steps 2 and 3 have
`--dry-run` (show the plan and one prompt, no API calls) and `--limit 3` (a pilot on the first
3 profiles of each language). Try those first.

## What each step does

| Step | Reads | Writes | Model |
|---|---|---|---|
| 1. Redact | `sessions/*.jsonl`, `profiles/profiles.csv` | `redacted/<profile>_s01_<redactor>.txt` and `.spans.json` | Gemini, for the LLM redactor only |
| 2. Memory notes | `redacted/` | `memory/<profile>_s01_<redactor>.txt` | Summarizer |
| 3. Attacks | `memory/`, `profiles/profiles.csv` | `results/attacks/attributes.jsonl`, `identify.jsonl` | Attacker |
| 4. Evaluate | all of the above | `results/paper_tables.md`, `report.md`, `tables/*.csv`, `figures/*.png` | none |

**Step 1** cuts each profile's history into sessions, replaces every `profile_id` with
`[PROFILE_ID]` (it is a generator key, not something a user would say), and runs each redactor:

| Name | Paper name | What it does |
|---|---|---|
| `none` | No redaction | Baseline. |
| `presidio` | Presidio based redactor | Presidio pattern rules (email, phone, date) plus the NER model. |
| `ner` | NER / MasakhaNER based redactor | NER model only: MasakhaNER for Swahili and Amharic, `dslim/bert-base-NER` for English. |
| `gemini` | LLM Data Anonymization | Gemini lists the exact text to mask; we mask it. |
| `open` | (optional) | Same prompt as `gemini`, on an open-weight model. |

The language of each profile comes from its country in `profiles.csv` (Kenya and Tanzania:
Swahili; Ethiopia: Amharic; United States: English). Step 1 warns if a session's text does not
look like that language.

**Step 2** writes one memory note per session from the redacted text only.

**Step 3** runs two attacks for every profile, redactor and memory length k, each as a separate
API call with no shared history:

- *Attribute recovery*: from the first k notes, pick one option or "unknown" for each of age
  group, location (city), occupation, education, family status and health condition.
- *Profile identification*: from the same notes, pick the right person from a shuffled,
  numbered list of all 40 profiles (chance = 2.5%). Profile IDs are never shown.

**Step 4** fills in the three paper tables and writes a fuller report with 95% confidence
intervals (profile-level bootstrap), the change from 1 to k sessions, each redactor compared with
no redaction, what guessing would score, and figures.

## Running only what the paper tables need

Table 1 needs step 1 only. Tables 2 and 3 need memory notes and attacks for `none` and
`presidio`, which halves steps 2 and 3:

```bash
python step2_memory.py --redactors none,presidio
python step3_attack.py --redactors none,presidio
```

## Free models

The three model roles are set in `.env`. One Gemini API key from
[Google AI Studio](https://aistudio.google.com) can serve all of them. Free daily quotas are
per model and per project, and AI Studio shows yours. In October 2026 a third-party check
reported about 20 requests a day for the Flash models, about 500 for the Flash-Lite models,
and over 14,000 for Gemma models, so:

- **Redactor** (`GEMINI_MODEL`): a Flash-Lite model.
- **Summarizer** (`SUMMARIZER_MODEL`): a Gemma model; it makes the most calls.
- **Attacker** (`ATTACKER_MODEL`): a different Flash-Lite model from the redactor, so the
  attacker is independent and has its own quota. Mistral's free API is another option
  (`ATTACKER_PROVIDER=openai`, see `.env.example`).

`<ROLE>_RPM` keeps calls under the per-minute limit. If a daily quota runs out, the step stops
with a message; run the same command the next day and it continues. On the free tier Google may
use prompts to improve its products, which is acceptable here only because all data is synthetic.

## Settings

Everything about the experiment is in `config.py`: folders, how sessions are cut, memory lengths,
redactors, the language for each country, the candidate pool and what a candidate card shows.

**How sessions are cut** (`SESSION_SIZE`). Each file in `sessions/` is one profile's whole history.

- `SESSION_SIZE = 5` (default): every 5 user messages is one session(10 sessions of 5 turns = 50 turns).
- A profile with 45 user messages has 9 sessions.
- `SESSION_SIZE = None`: a session starts where the user introduces themselves with
  `profile_id: ...`.

Memory lengths a profile does not have are skipped and shown as n/a. If you change
`SESSION_SIZE`, rerun every step with `--force` for step 1 and empty `memory/` and `results/`.

## How redaction is scored (Table 1)

Precision, recall and F1 are computed on spans, against reference spans found automatically:
the profile's name, phone, email, national ID, city, country and neighbourhood, plus places the
user asked to search for and coordinates the user gave. In this synthetic data every identifier
comes from one of those, and names and places are written in Latin script in all three languages.
The reference spans are not hand-annotated, which the methodology describes; say so in the paper,
or check a sample by hand.

A reference span counts as found only if all its letters and digits are masked. A mask counts
as correct if it overlaps a reference span. Masks on other things (for example a shop name the
assistant mentioned) count as incorrect, so precision is conservative.

## Files

```
config.py                experiment settings
step1_redact.py ... step4_evaluate.py
demo.py                  try the redactors on examples/samples.jsonl
pipeline/
    profiles.py          read profiles/profiles.csv; look-alike profiles
    sessions.py          read session files, cut them into sessions, detect language
    reference.py         reference spans for scoring the redactors
    memory.py            summarizer prompt; memory sets of 1, 3, 5, 10 notes
    attacks.py           the two attacks and their prompts
    metrics.py           span precision/recall/F1, accuracy, bootstrap intervals
redactors/               the redaction methods
sessions/  profiles/     input data
redacted/  memory/  results/   outputs of steps 1 to 4
```
