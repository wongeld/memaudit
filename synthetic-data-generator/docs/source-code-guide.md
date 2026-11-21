# Source-code guide

This guide explains the executable source and configuration in this repository: what each part does, how data moves between parts, and where the main behavior is implemented. It describes the checked-in code, not a desired or planned design.

## What the repository does

The project has four related workflows:

1. Gather regional news articles as background context for synthetic profiles.
2. Append synthetic profile JSON objects to a consistently structured CSV.
3. Generate and run synthetic-user conversation prompts through Pi.
4. Provide Pi tools for profile and activity records, profile export, and individual OpenStreetMap lookups.

The Python scripts are invoked directly with `uv run`; Pi loads the TypeScript extensions and MCP configuration from `.pi/`.

## Repository map

| Path | Responsibility |
|---|---|
| `src/main.py` | Command-line selection of one question-bank user or all users, and selected categories. |
| `scripts/spawn_user_session.py` | Validates and selects question-bank prompts, starts Pi in JSON mode, streams its JSONL output, and writes per-user logs. |
| `data/export_multi_turn_conversations.py` | Converts saved session JSONL events into a readable CSV with one row per user turn. |
| `scripts/news_context.py` | Discovers, extracts, ranks, and formats regional news articles. Also provides the `fetch_news_context` Python API. |
| `.pi/synthetic-profile-population/scripts/populate.py` | Validates one nested profile object, fills null mock identifiers, flattens it, and appends it to a CSV. |
| `.pi/extensions/main-extensions.ts` | Registers the conversation-starter population tool. |
| `.pi/extensions/export-profiles.ts` | Registers a CSV-to-nested-JSON profile export tool. |
| `.pi/extensions/user.ts` | Registers local profile and activity read/write tools. |
| `.pi/openstreetmap_mcp.py` | Implements the `search_places` and `reverse_geocode` MCP tools. |
| `.pi/mcp.json` | Tells Pi how to start the OpenStreetMap MCP server and supplies its endpoint. |
| `.pi/prompts/` | Instructions for generating profile data and conversation questions. |
| `.pi/synthetic-profile-population/SKILL.md` and `references/formats.md` | Agent workflow and profile schema contract for the CSV helper. |
| `pyproject.toml` and `uv.lock` | Python project metadata, dependencies, and locked dependency versions. |
| `AGENTS.md` | Repository-specific guidance for AI coding agents. |

`data/synthetic_conversation_starter.json` is the input question bank. `profiles/users.csv` is the profile dataset read by the profile-export extension. These are data inputs, not executable source.

## Profile and news-context workflow

### 1. Gather news context

`scripts/news_context.py` exposes `fetch_news_context(...)` and a small CLI. Its pipeline is:

1. Validate the language, optional theme/category, region, and output limits.
2. Select configured publishers for the requested language and region. Sources currently include Taifa Leo, The Standard (Kenya), and BBC in English, Swahili, and Amharic.
3. Read configured publisher pages and RSS feeds, and optionally supplement discovery with DuckDuckGo searches.
4. Canonicalize and deduplicate candidate URLs; score candidates using theme/category keyword hits, source categories, region mentions, query terms, and publication recency.
5. Fetch likely articles and extract text using publisher-specific selectors, JSON-LD article text, or Readability as a fallback. Short or unusable articles are skipped.
6. Apply strict-region filtering if requested, choose a ranked/balanced set, enforce character limits, and return formatted context plus article metadata and warnings.

The API returns a dictionary with `text` for formatted article context and `details` for structured metadata, skipped articles, and warnings. The CLI prints progress and then the formatted context. Network or publisher changes can affect results; this is a scraper, not a guaranteed news feed.

### 2. Create and append profiles

Profile generation itself is directed by `.pi/prompts/generate-profiles.md`; the prompt describes the synthetic sample balance, fields, regional context, and use of the population helper. The expected nested object contract is in `.pi/synthetic-profile-population/references/formats.md`.

The population helper in `.pi/synthetic-profile-population/scripts/populate.py`:

1. Reads one JSON object from standard input (or its optional positional JSON argument).
2. Generates a phone number and mock national ID if those fields are `null`.
3. Validates the exact profile schema, UUID, email, country, mock identifier patterns, age, and scenario list.
4. Flattens nested objects into underscore-separated CSV columns. Lists remain JSON text in one cell.
5. Creates the destination directory/file and header if needed; otherwise checks that the new row has the same columns and that profile IDs and identifier values are not duplicates.
6. Appends the row or prints an error and exits unsuccessfully.

The country-specific identifier patterns are project examples for synthetic data, not official formats and not guarantees that a value is unassigned.

## Conversation-question workflow

### Question bank

`data/synthetic_conversation_starter.json` contains an array of records. Each record has a `user_id` and arrays for `work`, `travel`, `school`, `shopping`, `family interactions`, and `daily planning`.

`.pi/prompts/generate-questions.md` guides the agent to create realistic, localized, multi-turn prompts from profile context. It describes when to use the profile/activity tools and map lookups, and requires explicit confirmation before saved information is written.

### Command-line selection

`src/main.py`:

1. Requires exactly one of `--uuid` or `--all-users`.
2. Accepts repeatable `--category`; no category selection means all six.
3. Validates category selection and checks question-bank IDs for malformed or duplicate values.
4. Iterates selected users in question-bank order, prints a progress line to stderr, and calls `run_user_question_bank`.

`--model`, `--api-key-env`, `--pi-command`, `--timeout`, and `--session-dir` configure the Pi invocation and output.

### Pi process and log

`scripts/spawn_user_session.py` performs the per-user work:

1. Loads and validates every question-bank record and category array.
2. Finds the requested user and collects all questions from selected categories in category order.
3. Reads the API key from the configured environment variable (default `GEMINI_API_KEY`).
4. Starts one Pi process with `--mode json`, the selected model, the user ID as `--session-id`, and selected questions as positional prompts. For one user, `--resume` omits the longest completed prompt prefix in that user's log. For all users, it resumes at the last existing matching session log in question-bank order, then continues with later users.
5. Copies each JSONL stdout line both to the terminal and to `<session-dir>/<user_id>.jsonl`, flushing the log after each line.
6. Reports startup errors, timeouts, process failures, and empty output rather than treating those cases as success.

By default the output directory is the project `sessions/` folder. `--session-dir` overrides it; otherwise `PI_CODING_AGENT_SESSION_DIR` may be used. Repeated runs append to the same user's log file.

Resume is opt-in. It skips only successful prompt turns recorded in the matching user's log; failed or interrupted prompts are eligible to run again. Use the same category selection and session directory when continuing a run.

**Current behavior to be aware of:** the runner sends every question in each selected category; it does not randomly sample questions. It also has no Python-level setting that limits a conversation to 50 Pi turns per question. Pi receives multiple prompts in one process, so `PI_MAX_TURNS` should not be assumed to provide an independent per-question limit in this runner.

## Pi extensions

Pi loads the TypeScript files in `.pi/extensions/`. Each extension exports a function that registers one or more tools.

### Conversation starters: `main-extensions.ts`

`populate_conversation_starters` accepts a `user_id` and optional arrays of questions for each category. It reads `data/synthetic_conversation_starter.json`, creates a record with empty categories when the user is new, appends supplied questions to existing arrays, and writes the JSON file back.

### Profile export: `export-profiles.ts`

`export_profiles_as_json` reads `profiles/users.csv` by default, or another supplied `csv_path`. Its CSV parser handles quoted values and commas/newlines within fields. It validates required headers and row widths, parses `age` as an integer and active scenarios as a JSON string array, converts each row into the nested profile schema, and returns all profiles as one JSON array.

### User profiles and activities: `user.ts`

This extension stores local JSON arrays under `data/`:

- `save_user_profile` creates or updates a profile in `user_profiles.json`. It repeats the submitted details in a confirmation dialog and writes only after approval.
- `get_user_profile` reads a profile by ID.
- `record_user_activity` saves a themed booking, appointment, task, reminder, or shopping item in `user_activities.json`, only after showing the submitted details for confirmation.
- `list_user_activities` returns activities for a profile, optionally filtered by theme.

The shared helpers read/write JSON arrays, reject malformed stored data, validate non-empty text, and format confirmation/result text.

## OpenStreetMap MCP server

`.pi/mcp.json` configures Pi to launch `.pi/openstreetmap_mcp.py` through `uv run`. The server uses a Nominatim-compatible endpoint from `NOMINATIM_URL`, defaulting to `http://localhost:8080`.

- `search_places` validates a non-empty query up to 200 characters and a result limit of 1–10, then returns place names, coordinates, addresses, OSM links, and attribution.
- `reverse_geocode` validates latitude and longitude ranges, looks up one coordinate, and returns its address and attribution.

Requests are serialized and rate-limited to at most one per second. Network requests have a timeout; HTTP and connection failures are surfaced as errors. The MCP instructions prohibit personal/confidential inputs and bulk or systematic queries.

## Project configuration and entry points

- `uv sync` installs Python dependencies declared in `pyproject.toml`; `uv.lock` pins resolved versions.
- The main conversation runner is launched with `uv run python src/main.py ...`.
- The news script is launched with `uv run scripts/news_context.py ...`.
- The profile helper is launched with `uv run .pi/synthetic-profile-population/scripts/populate.py <csv-path`, with one JSON object piped into standard input.
- Node.js/npm is used to install and launch Pi; the repository does not need a local npm project for the Pi CLI.

The project metadata also declares a `profile-generation` console entry point targeting `profile_generation:main`. No `profile_generation` package/module is present in the current source tree; use the documented Python script entry points above.
