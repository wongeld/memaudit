import csv
import json
import os
import re
import secrets
import sys
from uuid import UUID


PROFILE_FIELDS = {"profile_id", "identifiers", "personal_attributes", "domain_metadata"}
IDENTIFIER_FIELDS = {
    "first_name", "last_name", "email", "phone_number", "national_id",
    "national_id_format_note", "country",
}
PERSONAL_ATTRIBUTE_FIELDS = {
    "age", "location", "occupation", "education_level", "family_status",
    "health_condition",
}
DOMAIN_METADATA_FIELDS = {"primary_domain", "active_scenarios"}
COUNTRY_CODES = {
    "kenya": "KE",
    "tanzania": "TZ",
    "ethiopia": "ET",
    "united states": "US",
}


def flatten_object(data):
    """Flatten nested dictionaries into underscore-separated CSV columns."""
    flattened = {}

    def add_value(column, value):
        if isinstance(value, dict):
            if not value:
                if column in flattened:
                    raise ValueError(f"Flattened column name collision: {column}")
                flattened[column] = "{}"
                return
            for key, nested_value in value.items():
                add_value(f"{column}_{key}", nested_value)
        elif isinstance(value, list):
            flattened[column] = json.dumps(value, ensure_ascii=False)
        else:
            if column in flattened:
                raise ValueError(f"Flattened column name collision: {column}")
            flattened[column] = value

    for key, value in data.items():
        add_value(key, value)
    return flattened


def fill_synthetic_identifiers(data):
    """Generate randomized, country-shaped ID and phone placeholders."""
    identifiers = data.get("identifiers")
    if not isinstance(identifiers, dict):
        return None

    country = identifiers.get("country")
    if not isinstance(country, str) or country.strip().lower() not in COUNTRY_CODES:
        return "identifiers.country must be Kenya, Tanzania, Ethiopia, or United States."

    country_key = country.strip().lower()
    if identifiers.get("national_id") is None:
        if country_key == "kenya":
            identifiers["national_id"] = "40" + _random_digits(9)
        elif country_key == "ethiopia":
            identifiers["national_id"] = "392" + _random_digits(7)
        else:
            identifiers["national_id"] = _random_digits(10, first_digit_nonzero=True)

    if identifiers.get("phone_number") is None:
        if country_key == "kenya":
            prefix = secrets.choice(("1", "7"))
            identifiers["phone_number"] = "+254" + prefix + _random_digits(8)
        elif country_key == "tanzania":
            prefix = secrets.choice(("6", "7", "8"))
            identifiers["phone_number"] = "+255" + prefix + _random_digits(8)
        elif country_key == "ethiopia":
            identifiers["phone_number"] = "+2519" + _random_digits(8)
        else:
            area = secrets.choice("23456789") + _random_digits(2)
            exchange = secrets.choice("23456789") + _random_digits(2)
            identifiers["phone_number"] = "+1" + area + exchange + _random_digits(4)
    return None


def _random_digits(length, first_digit_nonzero=False):
    first = secrets.choice("123456789") if first_digit_nonzero else ""
    remaining = length - len(first)
    return first + "".join(str(secrets.randbelow(10)) for _ in range(remaining))


def validate_profile(data):
    """Validate the repository's synthetic-profile schema and safe identity values."""
    if set(data) != PROFILE_FIELDS:
        return "Profile must contain exactly: " + ", ".join(sorted(PROFILE_FIELDS))
    if not isinstance(data["profile_id"], str):
        return "profile_id must be a UUID string."
    try:
        UUID(data["profile_id"])
    except ValueError:
        return "profile_id must be a valid UUID."

    identifiers = data["identifiers"]
    if not isinstance(identifiers, dict) or set(identifiers) != IDENTIFIER_FIELDS:
        return "identifiers must contain exactly the documented profile fields."
    for field in ("first_name", "last_name", "country", "national_id_format_note"):
        if not isinstance(identifiers[field], str) or not identifiers[field].strip():
            return f"identifiers.{field} must be a non-empty string."
    email = identifiers["email"]
    if not isinstance(email, str) or "@" not in email:
        return "identifiers.email must be an email address ending in .com."
    local_part, domain = email.rsplit("@", 1)
    if not local_part or not domain.lower().endswith(".com") or not domain[:-4]:
        return "identifiers.email must end in a .com domain."
    country_key = identifiers["country"].strip().lower()
    if country_key not in COUNTRY_CODES:
        return "identifiers.country must be Kenya, Tanzania, Ethiopia, or United States."
    national_id_patterns = {
        "kenya": r"40\d{9}",
        "tanzania": r"[1-9]\d{9}",
        "ethiopia": r"392\d{7}",
        "united states": r"[1-9]\d{9}",
    }
    phone_patterns = {
        "kenya": r"\+254[17]\d{8}",
        "tanzania": r"\+255[678]\d{8}",
        "ethiopia": r"\+2519\d{8}",
        "united states": r"\+1[2-9]\d{2}[2-9]\d{2}\d{4}",
    }
    for field, patterns in (
        ("national_id", national_id_patterns),
        ("phone_number", phone_patterns),
    ):
        value = identifiers[field]
        if not isinstance(value, str) or not re.fullmatch(patterns[country_key], value):
            return f"identifiers.{field} does not match the configured synthetic format for {identifiers['country']}."

    attributes = data["personal_attributes"]
    if not isinstance(attributes, dict) or set(attributes) != PERSONAL_ATTRIBUTE_FIELDS:
        return "personal_attributes must contain exactly the documented profile fields."
    if type(attributes["age"]) is not int or attributes["age"] < 0:
        return "personal_attributes.age must be a non-negative integer, not a range."
    for field in PERSONAL_ATTRIBUTE_FIELDS - {"age"}:
        if not isinstance(attributes[field], str) or not attributes[field].strip():
            return f"personal_attributes.{field} must be a non-empty string."

    metadata = data["domain_metadata"]
    if not isinstance(metadata, dict) or set(metadata) != DOMAIN_METADATA_FIELDS:
        return "domain_metadata must contain exactly the documented profile fields."
    if not isinstance(metadata["primary_domain"], str) or not metadata["primary_domain"].strip():
        return "domain_metadata.primary_domain must be a non-empty string."
    if (not isinstance(metadata["active_scenarios"], list)
            or not all(isinstance(item, str) and item for item in metadata["active_scenarios"])):
        return "domain_metadata.active_scenarios must be a list of non-empty strings."
    return None


def add_object_to_csv(csv_filename, json_object_str):
    """
    Flattens and appends a JSON object, creating the CSV and headers if needed.
    """
    json_object_str = json_object_str.strip()

    try:
        new_data = json.loads(json_object_str)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format provided. Details: {e}")
        return False

    if not isinstance(new_data, dict):
        print("Error: The provided input must be a JSON object (dictionary).")
        return False

    fill_error = fill_synthetic_identifiers(new_data)
    if fill_error:
        print(f"Error: {fill_error}")
        return False

    validation_error = validate_profile(new_data)
    if validation_error:
        print(f"Error: {validation_error}")
        return False

    try:
        new_data = flatten_object(new_data)
    except ValueError as e:
        print(f"Error: {e}")
        return False
    if not new_data:
        print("Error: The JSON object must contain at least one field.")
        return False

    # Ensure the directory exists
    os.makedirs(os.path.dirname(os.path.abspath(csv_filename)), exist_ok=True)

    file_exists = os.path.isfile(csv_filename)
    file_is_empty = not file_exists or os.path.getsize(csv_filename) == 0

    incoming_fields = list(new_data.keys())

    # If the file doesn't exist or is empty, create it and write headers automatically
    if file_is_empty:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=incoming_fields)
            writer.writeheader()
            writer.writerow(new_data)
        print(f"Success: Created '{csv_filename}' and added object!")
        return True

    # Read existing headers if file already exists
    with open(csv_filename, mode='r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames
        existing_rows = list(reader)

    if not fieldnames:
        with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=incoming_fields)
            writer.writeheader()
            writer.writerow(new_data)
        print(f"Success: Initialized headers and added object to '{csv_filename}'!")
        return True

    # Keep every row aligned with the existing flattened CSV schema.
    if set(new_data.keys()) != set(fieldnames):
        print("Error: Field mismatch between the object and the existing CSV file.")
        print(f"  - Expected CSV fields : {sorted(list(fieldnames))}")
        print(f"  - Provided object keys: {sorted(list(new_data.keys()))}")
        return False
    if any(row.get("profile_id") == new_data["profile_id"] for row in existing_rows):
        print(f"Error: profile_id {new_data['profile_id']} already exists in the CSV file.")
        return False
    for field in ("identifiers_national_id", "identifiers_phone_number"):
        if any(row.get(field) == new_data[field] for row in existing_rows):
            print(f"Error: {field} already exists in the CSV file; retry with new random values.")
            return False

    # Append row to existing file
    with open(csv_filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writerow(new_data)

    print(f"Success: Object successfully added to '{csv_filename}'!")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: <json_string> | python populate.py <csv_filename>")
        sys.exit(1)
    
    csv_file = sys.argv[1]
    
    if not sys.stdin.isatty():
        json_str = sys.stdin.read()
    elif len(sys.argv) >= 3:
        json_str = sys.argv[2]
    else:
        print("Error: No JSON input provided via stdin or arguments.")
        sys.exit(1)
    
    if not add_object_to_csv(csv_file, json_str):
        sys.exit(1)