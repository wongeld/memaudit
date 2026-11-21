---
name: synthetic-profile-population
description: Populates comma-separated file (csv) with required data. Use this when you append data to a csv file.
license: MIT
metadata:
  author: Theophilus Owiti
  version: 1.0.0
---

# Synthetic User Profile Population

## Instructions

### Step 1: Identify object

In this step you should identify the object.

### Step 2: Check for format

Read `references/formats.md` then check if format contract has been breached. If format has been breached go to the next object.

### Step 3: Populate the CSV

If format check passes, pass exactly one complete nested profile JSON object to the helper. It appends that object, generates random numbers for null phone and national-ID fields according to the country's project mock template, validates supplied numbers against those templates, and flattens nested objects into underscore-separated columns. Lists are stored as JSON text in a single cell. Generate email addresses ending in `.com`, using plausible provider or company domains; those addresses may be deliverable or coincide with real mailboxes. The configured number templates are user-provided examples, not verified government or telephone allocations; generated values are fictional and not guaranteed to be unassigned.

```bash
'{"profile_id":"00000000-0000-4000-8000-000000000001","identifiers":{"first_name":"Amina","last_name":"Example","email":"amina.0001+001@gmail.com","phone_number":null,"national_id":null,"national_id_format_note":"Synthetic mock format; not verified as an official identifier format.","country":"Kenya"},"personal_attributes":{"age":34,"location":"Nairobi, Kenya","occupation":"Teacher","education_level":"Bachelor degree","family_status":"Single","health_condition":"None"},"domain_metadata":{"primary_domain":"school","active_scenarios":["school","daily_planning"]}}' | uv run .pi/synthetic-profile-population/scripts/populate.py "profiles/user.csv"
```

Every profile appended to an existing CSV must flatten to the same set of columns as its header.
This sample UUID is illustrative only; generate a new unique UUID for each profile.
