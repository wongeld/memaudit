"""Experiment settings, all in one place.

Change values here, not in the code. Model names and API keys are not here:
they go in .env (see .env.example).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Input folders and files.
SESSIONS_DIR = ROOT / "sessions"
PROFILES_FILE = ROOT / "profiles" / "profiles.csv"

# Output folders, one per step.
REDACTED_DIR = ROOT / "redacted"
MEMORY_DIR = ROOT / "memory"
RESULTS_DIR = ROOT / "results"

# How each profile's history is cut into sessions.
#   5    -> every 5 user messages is one session, as in the methodology (10 sessions of 5 turns).
#   None -> a new session starts where the user introduces themselves ("profile_id: ...").
#           In the current data that is one session per scenario, 15 user messages each.
SESSION_SIZE = 5

# Number of memory notes the attacker reads (the first k sessions).
MEMORY_LENGTHS = (1, 3, 5, 10)

# Redaction conditions to run. "open" (open-weight LLM) can be added if OPEN_* is set in .env.
REDACTORS = ("none", "ner", "presidio", "gemini")

# Session language for each country in profiles.csv.
COUNTRY_LANGUAGE = {"Kenya": "sw", "Tanzania": "sw", "Ethiopia": "am", "United States": "en"}

LANGUAGE_NAMES = {"en": "English", "sw": "Swahili", "am": "Amharic"}

# Candidates for the identification attack.
#   "all"      -> all profiles, as in the methodology (chance = 1 / 40).
#   "language" -> only profiles of the same language.
CANDIDATE_POOL = "all"

# What each candidate card shows the attacker. Phone, email and national ID are left out:
# the card describes a person the way a public record or social profile would.
CARD_FIELDS = (
    ("name", "Name"),
    ("age", "Age"),
    ("location", "Location"),
    ("neighborhood", "Neighbourhood"),
    ("occupation", "Occupation"),
    ("education", "Education"),
    ("family_status", "Family status"),
    ("health_condition", "Health condition"),
)

# Age groups for the age attribute: (lowest age, highest age, label).
AGE_GROUPS = ((18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 59, "45-59"), (60, 120, "60+"))

# Seed for candidate shuffles and bootstrap resampling, so every run gives the same numbers.
SEED = 20261121

# Profile-level bootstrap for 95% confidence intervals.
BOOTSTRAP_RESAMPLES = 10_000
