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
It also prints and writes estimated LLM token usage and paid-tier cost by step to
`results/report.md`. Usage tracking starts with calls made after this feature is installed; older
calls are not recoverable from saved answers. Steps with no tracked LLM calls show `$0.00`.

## Running only what the paper tables need

Table 1 needs step 1 only. Tables 2 and 3 need memory notes and attacks for `none` and
`presidio`, which halves steps 2 and 3:

```bash
python step2_memory.py --redactors none,presidio
python step3_attack.py --redactors none,presidio
```

## Step 5: synthetic privacy simulation

Step 5 asks **what would happen if the saved Step 3 attribute guesses were used to filter
the synthetic candidate pool**. It complements Step 4's attack evaluation; it does not
replay the Step 3 identification attack on the smaller pool.

The following commands are for PowerShell, run from the project root.
Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first if it is not available.

### 1. Prepare the environment and inputs

Install the analysis and test dependencies into the project's `.venv`:

```powershell
uv sync --extra analysis --extra dev --inexact
```

`--inexact` avoids removing other installed packages. Use `--no-sync` in the commands below
so that `uv run` does not change the selected extras.

For the reduction and geographic comparisons, check that these inputs exist:

```powershell
Test-Path .\profiles\profiles.csv
Test-Path .\results\attacks\attributes.jsonl
Test-Path .\pipeline\geodata\natural_earth_regions.geojson
```

Each should print `True`. The geographic data is needed for country maps, not for reduction.
`results/attacks/identify.jsonl` is optional; when present, the reduction output includes the
separate saved identification results. `memory/` is optional for Step 5, but allows its report
to compare available memory cases with saved answers. Step 4 is recommended for interpreting
attack accuracy, but is not a prerequisite for Step 5.

The saved Step 3 attribute cases must have been made from `memory/` with the full candidate pool
(`CANDIDATE_POOL = "all"` in `config.py`) and a pool size matching the current profiles.
Changing that setting now does not change existing records. Do not mix results from a different
pool or experiment; preserve them separately and generate matching answers if necessary.

**If saved answers already exist, skip to step 2 below.** If they do not, run the preceding
pipeline first. This requires synthetic sessions in `sessions/`, the full pipeline dependencies,
and configured model providers, model IDs and API keys in `.env`. For creating synthetic
sessions, see [Synthetic Data Generator](#synthetic-data-generator).

```powershell
uv sync --extra all --inexact
uv run --no-sync python step1_redact.py
uv run --no-sync python step2_memory.py --dry-run
uv run --no-sync python step2_memory.py
uv run --no-sync python step3_attack.py --dry-run
uv run --no-sync python step3_attack.py
uv run --no-sync python step4_evaluate.py
```

Steps 1–3 can make model calls, send synthetic input to the configured providers, take time and
incur charges. Review the Step 2 and Step 3 dry-run plans before the full commands. Step 3
normally runs both the attribute and identification attacks; `--task attributes` runs only the
attribute attack if identification results are not needed. Existing Step 2 notes and Step 3
answers are skipped on reruns, so review their provenance before reusing them.

### 2. Preview the saved cases

```powershell
uv run --no-sync python step5_test.py --dry-run
uv run --no-sync python step5_test.py --regional-maps --dry-run
```

The preview shows the candidate-pool size and selected saved-case count without writing outputs,
contacting map services or calling models. A case is one target profile, redactor and memory
length `k`; `k` is the number of notes, not the number of profiles. Coverage depends on which
answers were saved. For example, the current saved data has 40 candidates and 400 cases for
32 distinct targets, with only four cases per redactor at `k=10`. Check the generated reports
for the counts in your run rather than assuming all 40 targets are covered.

### 3. Run the reduction simulation

```powershell
uv run --no-sync python step5_test.py
```

For each saved case, the simulation starts with the **entire** synthetic pool and applies the
saved location, occupation and education guesses in that order. Matching is normalized; an
unknown or invalid answer applies no filter. For illustration, a case might go from 40 candidates
to 5, then 2, then 1. The target is used only to check retention: if a wrong guess removes it,
it is not put back. The reported reduction at each stage is relative to the original pool.

This command makes **no new model calls**, but it also generates a world map using OpenStreetMap.
The map uses public city and country names and, where needed, public neighborhood names to
disambiguate a city; it does not send profile identifiers or notes. It uses cached lookups and
tiles, and an uncached run requires internet access. Unresolved cities are reported rather than
guessed. If you do not want OpenStreetMap, skip this command and use the offline visualizations
below; there is currently no offline-only option for the reduction report itself.

Read `simulation/reduction/report.md` first. The main outputs are:

| Output | What it shows |
|---|---|
| `case_stages.csv` | Per-case candidates remaining, reduction, whether each filter applied, target retention and any saved Step 3 identification outcome. |
| `stage_summary.csv` | Counts, mean candidate reduction and target retention by redactor, k and stage. |
| `reduction.png` | Mean candidates remaining and target-retention percentage across the filtering stages. |
| `candidate_cities.csv`, `candidate_map.png` | Counts for the **original** pool at public city centers, not filtered survivors, homes or journeys. |
| `regional_heatmaps/` | Offline city-by-occupation categorical grids for the full pool. |

### 4. Generate the offline country comparisons

```powershell
uv run --no-sync python step5_test.py --regional-maps
```

Open `simulation/reduction/regional_maps/report.md` for links to the country images,
`coverage.csv` and `map_counts.csv`. There is one map per country, saved redactor and k.
Each figure has:

- **Left:** saved Step 3 location and occupation guesses. The city list gives the number of
  matching profiles in the full pool, how many cases made that guess, and how many guessed both
  attributes correctly for their target. Unknown locations cannot be placed.
- **Right:** actual city-and-occupation counts for that country from the entire synthetic pool.
  The sides can have different coverage: saved cases do not necessarily cover all 40 profiles.
- **Markers:** the number identifies the city in the list. Red means its smallest positive
  city-and-occupation pool count is 1; orange means 2–4; teal means 5 or more. Gray means no
  positive match or unknown occupation. A city can have multiple occupations, so check the
  lists for each count, including zero-match combinations.

These are real country outlines and representative city centers, **not individual locations**.
The United States panels show the contiguous area only. Maps use the included public-domain
Natural Earth [country boundaries](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson)
and [populated places](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_populated_places.geojson),
not OpenStreetMap; they make no network or model calls. The included extract covers the current
synthetic cities. A new city requires verified geographic data to be added before it can be mapped.

For categorical grids instead of geographic maps, run:

```powershell
uv run --no-sync python step5_test.py --regional-heatmaps
```

This needs only the profiles, produces `regional_heatmaps/report.md` and a counts CSV, and works
offline without saved Step 3 answers. The full reduction command also generates these grids.

### 5. Restrict a run or check it

For example, to run only the unredacted and Presidio cases at `k=5`:

```powershell
uv run --no-sync python step5_test.py --dry-run --redactors none,presidio --k 5
uv run --no-sync python step5_test.py --redactors none,presidio --k 5
uv run --no-sync python step5_test.py --regional-maps --redactors none,presidio --k 5
uv run --no-sync python -m pytest tests\test_step5.py -q
```

The filters apply to reduction and geographic comparisons, not `--regional-heatmaps`. Restricted
runs overwrite their corresponding reports, CSVs and figures; the map report indexes the latest
selection, while images from earlier selections may remain. Back up outputs you want to keep
before rerunning. The test command is optional and uses the `dev` extra.

### Interpretation and troubleshooting

- A smaller candidate pool does **not** prove identification. An incorrect guess can exclude
  the target, and high target retention can occur when unknown answers apply no filters.
- One city-and-occupation match is unique only within this synthetic pool, assuming both
  attributes are known. It does not establish attacker knowledge or real-world privacy risk.
  The dataset is small and not representative of a real population.
- Attribute choices came from profile-derived options. Saved Step 3 records lack note and profile
  hashes, so their exact historical inputs cannot be verified. Cases for the same profile are
  related, and small or unequal groups should not be treated as independent comparisons.
- If an input is missing or a saved pool does not match, inspect the error and the provenance of
  your inputs; generate compatible Step 3 answers rather than editing saved records. If an
  OpenStreetMap lookup fails, inspect the terminal and report if available; the country-map
  command remains offline. City names can be ambiguous, and Natural Earth positions are
  representative, not proof of the intended city.
- Rerunning Step 5 with unchanged inputs only regenerates outputs; it adds no cases or model calls.
  To expand coverage, first generate additional Step 2 notes and Step 3 answers, then rerun Step 4
  and Step 5. Those earlier model calls may incur costs.

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

---

## Synthetic Data Generator

This section covers the profile and conversation generator in
[`synthetic-data-generator/`](synthetic-data-generator/), not the four-step privacy-audit
pipeline described above.

| | Root privacy-audit pipeline | Synthetic data generator |
|---|---|---|
| Code and tests | Repository root | `synthetic-data-generator/` |
| Purpose | Redact, summarize, attack, and evaluate sessions | Create profiles and generate conversation sessions |

The two projects share the root `.venv` and [`uv.lock`](uv.lock). **Run setup from the
repository root**; there is no separate lockfile or environment for the generator:

```powershell
uv sync
```

Both projects require Python 3.15 or newer for this shared environment, plus
[uv](https://docs.astral.sh/uv/getting-started/installation/). The generator's conversation
runner additionally needs Node.js/npm, the Pi CLI, and a Gemini API key.

**Run a generator command from the repository root** (this example runs one user's school
questions):

```powershell
uv run --directory synthetic-data-generator python src\main.py --uuid 101a4b2c-1101-4a01-8b01-000000000001 --category school
```

**Run only the generator's tests from the repository root:**

```powershell
uv run --directory synthetic-data-generator python -m unittest discover -s tests
```

For Pi installation, API-key setup, profile generation, session options, and the full
generator workflow, see the [synthetic data generator README](synthetic-data-generator/README.md).
