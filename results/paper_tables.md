# Tables for the paper

Generated 2026-11-22 07:29.
Sessions: 5 user messages each. Gemini redactor: gemini-3.1-flash-lite. Summarizer: gemini-3.1-flash-lite. Attacker: gemini-3.1-flash-lite. Candidate pool: all.

## Table 1. Span-level redaction outcomes by language and method

| Language | Redaction Approach | Precision | Recall | F1 Score |
|---|---|---|---|---|
| English | Presidio based redactor | 0.92 | 0.87 | 0.89 |
| English | NER based redactor | 0.90 | 0.68 | 0.77 |
| English | LLM Data Anonymization | 0.99 | 0.91 | 0.95 |
| Swahili | Presidio based redactor | 0.75 | 0.83 | 0.79 |
| Swahili | MasakhaNER based redactor | 0.70 | 0.66 | 0.68 |
| Swahili | LLM Data Anonymization | 1.00 | 0.94 | 0.97 |
| Amharic | Presidio based redactor | 0.74 | 0.90 | 0.81 |
| Amharic | MasakhaNER based redactor | 0.66 | 0.67 | 0.67 |
| Amharic | LLM Data Anonymization | 0.99 | 0.93 | 0.96 |

Reference spans are the profile's name, phone, email, national ID, city, country and neighbourhood, plus places the user searched for and coordinates the user gave, wherever they appear in the session. They are found automatically from profiles.csv and the user's messages, not annotated by hand. A span counts as found only if all its letters and digits are masked; a mask counts as correct if it overlaps a reference span.

## Table 2. Attribute recovery accuracy across session lengths

| Language | Redaction Approach | 1 Session | 3 Sessions | 5 Sessions | 10 Sessions |
|---|---|---|---|---|---|
| English | No redaction | 84.7% | 100.0% | 100.0% | 100.0% |
| English | Presidio based redactor | 68.1% | 84.7% | 90.3% | 83.3% |
| Swahili | Presidio based redactor | 63.3% | 91.7% | 96.7% | 94.4% |
| Amharic | Presidio based redactor | 80.0% | 88.3% | 85.0% | n/a |

Share of the six attributes (age group, location, occupation, education, family status, health condition) the attacker got right from the first k memory notes, averaged over profiles. "Unknown" counts as wrong. n/a: no profile has that many sessions yet. Profiles per cell: 1 session: English 12, Swahili 10, Amharic 10; 3 sessions: English 12, Swahili 10, Amharic 10; 5 sessions: English 12, Swahili 10, Amharic 10; 10 sessions: English 1, Swahili 3.

## Table 3. Profile re-identification accuracy

| Language | Redaction Approach | 1 Session | 3 Sessions | 5 Sessions | 10 Sessions |
|---|---|---|---|---|---|
| English | Presidio based redactor | 91.7% | 100.0% | 100.0% | 100.0% |
| Swahili | Presidio based redactor | 90.0% | 100.0% | 100.0% | 100.0% |
| Amharic | Presidio based redactor | 100.0% | 100.0% | 90.0% | n/a |

Share of memory sets the attacker matched to the right profile out of the candidate list, averaged over profiles. Random chance: 2.5% (1 of 40 candidates). Profiles per cell: 1 session: English 12, Swahili 10, Amharic 10; 3 sessions: English 12, Swahili 10, Amharic 10; 5 sessions: English 12, Swahili 10, Amharic 10; 10 sessions: English 1, Swahili 3.
