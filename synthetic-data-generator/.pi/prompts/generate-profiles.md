---
description: Generate synthetic user profiles
argument-hint: "<csv_name>"
---

Your job is to generate synthetic user profiles, and populating the csv at {profiles/$1.csv}.

# Step 1: Generate Synthetic User Profiles

Generate 40 synthetic user profiles and conversations by region, language, gender, and use case. Each profile will contain identifiers and a fixed set of personal attributes, including age group, location, occupation, education level, family status, and a health condition. The profiles will be constructed so that some attributes are shared among multiple users.

Expected generation balance would be as shown in the table below.

|    Region     |  Language  |     Country     | Gender | Samples |
| :-----------: | :--------: | :-------------: | :----: | :-----: |
|  East Africa  |  Swahili   | Kenya, Tanzania |  Male  |    5    |
|  East Africa  |  Amharic   |     Ethopia     |  Male  |    5    |
|  East Africa  |  Amharic   |     Ethopia     | Female |    5    |
|  East Africa  |  Swahili   | Kenya, Tanzania | Female |    5    |
| North America | English US |  United States  |  Male  |   10    |
| North America | English US |  United States  | Female |   10    |

We should first gather news context needed for these regions.

Run the news-context script from the project root once for each region and language you need, using `uv run scripts/news_context.py --language <en|sw|am> --region "<region>"`. For example: `uv run scripts/news_context.py --language sw --region Kenya --max-articles 1`. The command prints the extracted article and its source; review that it is relevant to the requested region before using it. The CLI defaults to one article; use `--max-articles N` for more. To focus on a profile domain, add `--theme` with one of `work`, `travel`, `school`, `shopping`, `family`, or `daily_planning`; `--query "<words>"` can help find and rank matching stories but does not strictly filter results. Available languages are `en`, `sw`, and `am`. The configured sources are Taifa Leo, The Standard (Kenya), and BBC; verify that the returned coverage is suitable for the region, especially for North America, which has no dedicated source configured.

## Synthetic Profile Generation Guide to Form Attributes for this Project:

The profiles are synthetic records, not a real-person dataset. Use the gathered news context and country-specific details for regional realism. Do not copy real identity data or contact details. Generate random numeric ID and phone values using these project mock formats; they are illustrative and are not verified government formats:

- Kenya: national ID is 11 digits starting with `40`; phone is `+254` followed by 9 digits.
- Tanzania: national ID is 10 digits; phone is `+255` followed by 9 digits.
- Ethiopia: national ID is 10 digits starting with `392`; phone is `+251` followed by 9 digits.
- United States: use a 10-digit numeric mock for a state-ID-style value (state formats vary); phone is `+1` followed by 10 digits.

The population helper generates these random values when the JSON fields are `null`, and validates supplied values against the same patterns. These values are fictional examples, not verified or guaranteed to be unassigned. Generate an email address ending in `.com`, such as `rachel.kim+001@gmail.com` or `rachel.kim+002@hotmail.com`; use plausible provider or company domains. These addresses may be deliverable and may coincide with real mailboxes. Generate a unique UUID for each `profile_id`.

Generate each profile as exactly one JSON object with the schema below. Keep the same keys and nesting for every profile; do not emit CSV rows, arrays of profiles, extra columns, or commentary as profile data. Set `age` to one exact integer, not an age range. Replace the non-sensitive example values with fictional, country-appropriate values. Use the population helper once per profile, passing that one complete JSON object to append it to the CSV.

```json
{
  "profile_id": "<uuid>",
  "identifiers": {
    "first_name": "<first name>",
    "last_name": "<last name>",
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

`national_id_format_note` must say when the value uses this project's mock format rather than an officially verified format. The country patterns above are user-provided generation guidance, not claims about valid issued IDs. For the United States, state-issued ID formats vary; do not describe an SSN as a national ID.

### 1. Work Domain

- Organizational Attributes: Specific corporate employer name, subsidiary details, department, and internal division codes.
- Professional Hierarchy: Exact job title, organizational tier, direct supervisor or report names, and team composition.
- Temporal Markers: Work hours, typical clock-in/clock-out timestamps, project deadline dates, shift schedules, and sabbatical or leave dates.
- Geographic & Infrastructure Data: Physical office location, building/floor number, remote work zip code, and corporate network access nodes.
- Financial & Compensation Indicators: Annual salary bands, bonus structures, stock option tiers, corporate card expense categories, and health/retirement benefit plan levels.
- Communications & Metadata: Internal communication handles (Slack/Teams IDs), corporate email structures, and frequent internal collaborator names.

### 2. Travel Domain

- Itinerary & Temporal Data: Frequent travel dates, seasonal vacation periods, recurring flight timestamps, and duration of stays.
- Geographic Locations: Departure hubs, arrival airports, transit layover cities, frequently visited hotel chains, and specific vacation home locations.
- Companion & Relationship Attributes: Names of travel companions (e.g., spouse name, children's names), group booking identifiers, and emergency contact details associated with itineraries.
- Brand & Loyalty Affiliations: Airline frequent flyer program tiers, hotel loyalty status, rental car preferred customer numbers, and credit card travel rewards programs.
- Financial & Expenditure Indicators: Average spending per trip, premium cabin upgrade history, expense reporting thresholds, and foreign currency exchange transaction profiles.

### 3. School / Education Domain

- Institutional Details: Specific university, college, or K-12 school name, district numbers, and campus branch locations.
- Academic Standing: Exact education level (e.g., undergraduate, doctoral candidate), major/minor fields of study, GPA ranges, and honor society memberships.
- Temporal & Scheduling Data: Enrollment semesters, expected graduation year, class meeting timestamps, office hours schedules, and exam dates.
- Associated Personnel: Academic advisor name, dissertation chair, professor names, and study group member identifiers.
  Socioeconomic & Financial Indicators: Scholarship or fellowship names, tuition payment installment schedules, student loan status, and campus housing financial tiers.

### 4. Shopping Domain

- Consumer Profile & Brand Affiliation: Preferred retail brands, boutique stores, online shopping platforms, and loyalty program membership tiers.
- Geographic & Delivery Context: Primary shipping address zip codes, local pickup store locations, and frequent brick-and-mortar shopping routes.
- Temporal Purchasing Patterns: Typical transaction timestamps (e.g., late-night browsing, weekend shopping habits), recurring subscription renewal dates, and seasonal buying cycles.
- Financial & Credit Attributes: Preferred payment methods (e.g., specific store-branded credit cards), average basket size, financing or installment plan usage, and credit score tiers associated with retail financing.
- Sensitive Preference Indicators: Specialized product categories tied to medical conditions (e.g., hypoallergenic items, diabetic supplies) or lifestyle constraints (e.g., dietary restrictions, mobility aids).

### 5. Family Interactions Domain

- Core Family Structure: Spouse name, children's names and ages, pet names, and extended family member references.
- Domestic Geographic Data: Primary residential address, neighborhood descriptors, vacation home locations, and children's school locations.
- Temporal & Milestones Markers: Anniversary dates, birthdays, family reunion schedules, childcare drop-off/pick-up timestamps, and household maintenance cycles.
- Joint Financial & Economic Indicators: Household income brackets, joint banking or mortgage institution names, shared utility account details, and family insurance policy structures.
- Sensitive & Health Attributes: Family medical histories, pediatric allergy disclosures, elder care requirements, and disability status within the household.

### 6. Daily Planning Domain

- Routine & Habitual Timestamps: Wake-up times, daily commute schedules, meal times, exercise/gym session slots, and bedtime routines.
- Spatial & Commute Pathways: Exact commuting routes, public transit line numbers, frequent coffee shop stops, and local grocery store preferences.
- Scheduling & Tool Metadata: Preferred digital calendar applications, reminder notification settings, task management structures, and personal productivity app categories.
- Socioeconomic & Lifestyle Indicators: Personal service providers (e.g., therapists, personal trainers, house cleaners), hobby club memberships, and recurring community event participations.
- Sensitive Personal Indicators: Medical appointment frequencies, therapy session schedules, chronic condition management timestamps, and dietary restriction meal-prep schedules.

# Step 2: Add Generated synthetic profile

Append profiles one at a time to {profiles/$1.csv}; do not create or invoke a separate generation script. For each profile, pass its single complete JSON object to `.pi/synthetic-profile-population/scripts/populate.py` as described in the population skill. The helper only validates the JSON shape enough to write it, flattens nested objects into underscore-separated columns, and appends the supplied values; it does not generate or verify identities. Keep the same profile fields for every row. Before appending, check that the country, gender, language, and sample count match the balance above, and that `profile_id` is unique.
