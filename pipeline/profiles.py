"""Reading the ground-truth profiles from profiles/profiles.csv.

One row per profile. The columns used are listed in COLUMNS; if the generator
renames a column, change it there.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import config

# Our field name -> column name in profiles.csv.
COLUMNS = {
    "profile_id": "profile_id",
    "first_name": "identifiers_first_name",
    "last_name": "identifiers_last_name",
    "email": "identifiers_email",
    "phone": "identifiers_phone_number",
    "national_id": "identifiers_national_id",
    "country": "identifiers_country",
    "age": "personal_attributes_age",
    "location": "personal_attributes_location",
    "occupation": "personal_attributes_occupation",
    "education": "personal_attributes_education_level",
    "family_status": "personal_attributes_family_status",
    "health_condition": "personal_attributes_health_condition",
    "scenarios": "domain_metadata_active_scenarios",
}

# The six attributes the attacker tries to infer.
ATTRIBUTES = ("age_group", "location", "occupation", "education", "family_status", "health_condition")

ATTRIBUTE_NAMES = {
    "age_group": "Age group", "location": "Location", "occupation": "Occupation",
    "education": "Education", "family_status": "Family status", "health_condition": "Health condition",
}


@dataclass
class Profile:
    profile_id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    national_id: str
    country: str
    age: int
    age_group: str
    location: str
    city: str
    neighborhood: str
    occupation: str
    education: str
    family_status: str
    health_condition: str
    language: str
    scenarios: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def attribute(self, name: str) -> str:
        return getattr(self, name)


def age_group(age: int) -> str:
    for low, high, label in config.AGE_GROUPS:
        if low <= age <= high:
            return label
    return ""


def split_location(text: str) -> tuple[str, str, str]:
    """"Embu, Kenya (Itabua)" -> ("Embu, Kenya", "Embu", "Itabua").

    Location is scored at city level. The neighbourhood is a named place, so it is
    treated as an identifier, not an attribute.
    """
    match = re.match(r"^(.*?)\s*\(([^)]*)\)\s*$", text.strip())
    city_country, neighborhood = (match.group(1), match.group(2)) if match else (text.strip(), "")
    city = city_country.split(",")[0].strip()
    return city_country.strip(), city, neighborhood.strip()


def load_profiles(path: Path = config.PROFILES_FILE) -> dict[str, Profile]:
    """All profiles, keyed by profile_id."""
    if not path.exists():
        raise SystemExit(f"Profiles file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"{path} has no rows")

    missing = [col for col in COLUMNS.values() if col not in rows[0]]
    if missing:
        raise SystemExit(f"{path.name} is missing columns {missing}. Update COLUMNS in pipeline/profiles.py.")

    profiles: dict[str, Profile] = {}
    for row in rows:
        get = {name: (row.get(col) or "").strip() for name, col in COLUMNS.items()}
        location, city, neighborhood = split_location(get["location"])
        age = int(get["age"])
        language = config.COUNTRY_LANGUAGE.get(get["country"], "")
        if not language:
            raise SystemExit(f"No language for country {get['country']!r}. Add it to COUNTRY_LANGUAGE in config.py.")
        try:
            scenarios = json.loads(get["scenarios"]) if get["scenarios"] else []
        except json.JSONDecodeError:
            scenarios = []
        profiles[get["profile_id"]] = Profile(
            profile_id=get["profile_id"], first_name=get["first_name"], last_name=get["last_name"],
            email=get["email"], phone=get["phone"], national_id=get["national_id"], country=get["country"],
            age=age, age_group=age_group(age), location=location, city=city, neighborhood=neighborhood,
            occupation=get["occupation"], education=get["education"], family_status=get["family_status"],
            health_condition=get["health_condition"], language=language, scenarios=scenarios,
        )
    return profiles


def lookalikes(profiles: dict[str, Profile]) -> list[dict]:
    """How many other profiles share each profile's attributes.

    Profiles were built to overlap, so the attacker has to combine clues. For each
    profile this counts the others with the same location, occupation and education,
    and the others with all six attributes the same.
    """
    rows = []
    for p in profiles.values():
        same_three = sum(1 for q in profiles.values() if q is not p and
                         (q.location, q.occupation, q.education) == (p.location, p.occupation, p.education))
        same_six = sum(1 for q in profiles.values() if q is not p and
                       all(q.attribute(a) == p.attribute(a) for a in ATTRIBUTES))
        rows.append({"profile_id": p.profile_id, "lang": p.language, "name": p.name,
                     "same_location_occupation_education": same_three, "same_all_six_attributes": same_six})
    return rows


def summary(profiles: dict[str, Profile]) -> str:
    counts = Counter(p.language for p in profiles.values())
    return ", ".join(f"{counts[lang]} {config.LANGUAGE_NAMES[lang]}" for lang in ("en", "sw", "am") if counts[lang])
