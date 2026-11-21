The expected format should be the following JSON style example given below:

```json
{
  "profile_id": "<unique UUID>",
  "identifiers": {
    "first_name": "<fictional first name>",
    "last_name": "<fictional last name>",
    "email": "<fictional address ending in .com>",
    "phone_number": null,
    "national_id": null,
    "national_id_format_note": "Synthetic mock format; not verified as an official identifier format.",
    "country": "<country>"
  },
  "personal_attributes": {
    "age": 34,
    "location": "<city, country, and optional neighborhood>",
    "occupation": "<occupation>",
    "education_level": "<education level>",
    "family_status": "<family status>",
    "health_condition": "<fictional health condition or none>"
  },
  "domain_metadata": {
    "primary_domain": "<primary domain>",
    "active_scenarios": ["<scenario>", "<scenario>"]
  }
}
```

Keep the profile as this nested JSON object when generating it. The CSV population helper flattens nested objects into columns named with underscore-separated paths, such as `identifiers_first_name` and `personal_attributes_age`. Use an exact integer for `age`, not a range. Lists remain in one cell as JSON text, for example `["work", "shopping"]` in the `domain_metadata_active_scenarios` column.

Profiles are fictional, not a real-person dataset. Use a unique UUID for `profile_id` and email addresses ending in `.com`, such as provider or company domains. Such addresses may be deliverable or coincide with real mailboxes. The helper generates random phone and national-ID numbers when those fields are null, using the project's mock templates: Kenya ID 11 digits starting `40`; Tanzania ID 10 digits; Ethiopia ID 10 digits starting `392`; US state-ID-style mock 10 digits. Phone templates are `+254` plus 9 digits, `+255` plus 9 digits, `+251` plus 9 digits, and `+1` plus 10 digits. These templates are user-provided examples, not verified official formats, and random values are not guaranteed to be unassigned or valid. State this in `national_id_format_note`. Append one complete profile object per population-helper invocation.
