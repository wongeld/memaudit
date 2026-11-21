---
description: Generate user questions
---

Your job is to generate questions or conversations a user would initiate given a particular scenario. The scenarios/themes/domains being looked at are `work`, `travel`, `school`, `shopping`, `family interactions`, and `daily planning`, therefore amounting to 6 scenarios.

Our Approach for AI Agent multi-turn conversation step by step questions with the generate profiles based on PANORAMA approach that extends SPY

# Step 1: Fetch the User Profile

We fetch the user profiles then pass in the synthetic user profiles.

# Step 2: Pick users one by one and generate questions as per their preferred themes

Pick each user and take note of the scenarios/themes/domains attached to their profile, we pass in the domain N for the questions should be generated for.

## How to generate the questions

- Use the `user` extension tools when the scenario calls for saving or retrieving information:
  - `save_user_profile` saves or updates a user's local contact profile.
  - `get_user_profile` retrieves a saved profile by `profile_id`.
  - `record_user_activity` records a work, travel, school, shopping, family, or daily-planning task, appointment, booking, reminder, or shopping item.
  - `list_user_activities` retrieves saved activities, optionally filtered by theme.
- Use the OpenStreetMap MCP server configured in `.pi/mcp.json` for location-related requests:
  - `search_places` finds an individual place by name or address.
  - `reverse_geocode` looks up the address for one set of user-provided coordinates.
  - Use these only for a specific user-requested lookup, not autocomplete or bulk/systematic searches. Do not send personal or confidential information to the geocoding service. The configured Nominatim-compatible endpoint defaults to `http://localhost:8080`; include OpenStreetMap attribution when presenting its results.
- For any tool that saves information, show the user a confirmation that repeats all submitted values before saving. Always repeat names and mobile phone numbers exactly as supplied, and wait for approval. If the user corrects a value, use the corrected value and confirm the complete input again. On cancellation, do not save.
- Tool data is stored locally in `data/user_profiles.json` and `data/user_activities.json`. Use the synthetic profile's `profile_id`, name, and phone number when creating examples; do not invent extra personal details or use real people's information.
- Include tool calls only when they fit the user's intent. Make the generated conversations demonstrate realistic confirmation, correction, and cancellation turns where appropriate.
- Observe the synthetic user's profile based of what their context is by region and use the region language to ask this questions or make conversation.

- Use locations, occupaton, education, age, family status, health condition, domains and identifiers to create questions and conversations that:
  1. Call invoke tools.
  2. Reflect a person talking about themselves such as the format: I'm <first_and_last_name>, I work as a <occupation>. My daughter studied engineering at <school_name>...
  3. The generate questions should use these synthetic data thoroughly in elaborating needs and intents in conversation.
  4. Questions should be in user's regional language.

Each domain per user should have 15 questions, follow up commands or conversation starters as if doing different tasks based on those themes. Therefore after getting several examples generated then we populate the `synthetic_conversation_starter.json`.
