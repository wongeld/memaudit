# Repository instructions

These guidelines apply to work across this repository. For profile-generation tasks, use the detailed workflow and schema in [`.pi/prompts/generate-profiles.md`](.pi/prompts/generate-profiles.md) as the source of truth. For CSV population, follow [`.pi/synthetic-profile-population/SKILL.md`](.pi/synthetic-profile-population/SKILL.md) and its format reference. This file adds repository-wide guidance; it does not replace or redefine those workflows.

## Project structure

- `scripts/news_context.py` discovers news and extracts article text. Keep its CLI and `fetch_news_context` Python API behavior consistent when changing it.
- `src/profile_generation/` contains the installable Python package.
- `.pi/` contains agent prompts, skills, references, and their helper scripts.
- `profiles/` is the destination for generated profile CSV files.
- `README.md` documents setup and common workflows; update it when user-facing commands or repository structure change.

## Development

- Use Python 3.15 or newer and `uv` for dependency management. Declare runtime dependencies in `pyproject.toml` and keep `uv.lock` in sync when dependencies change.
- Run commands from the repository root unless a task requires otherwise.
- Keep changes focused and follow the existing style of the file being edited.
- For Python changes, run a focused check such as `uv run python -m py_compile <file>` and any relevant available tests. Do not claim tests passed unless they were run.

## Generated profile data

- Follow the profile fields, balance, and output location specified by the profile-generation prompt; do not silently change its schema or requirements.
- Profile records must be synthetic, not represented as real records. Use the project’s country-specific randomized ID/phone templates documented in the profile prompt; note that they are mock templates, not verified official formats or guaranteed unassigned values. Email addresses must end in `.com`; provider or company domains may be deliverable or coincide with real mailboxes. Use a unique UUID for `profile_id`.
- The CSV helper flattens nested profile objects into underscore-separated columns and stores lists as JSON text. Keep the profile field set consistent so every appended row matches the existing CSV columns.
