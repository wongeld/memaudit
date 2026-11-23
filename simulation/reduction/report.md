# Hypothetical synthetic candidate filtering

- Candidate pool: 40 synthetic profiles.
- Cases: 400; cases with saved Step 3 identification: 400.
- Distinct target profiles: 32.
- Attribute attacker models: gemini-3.1-flash-lite.
- Mapped profiles by public city center: 40/40.
- No new model calls were used.

## What the simulation shows

This asks what could happen if the saved Step 3 attribute guesses were used to filter the same full synthetic profile pool. It is a hypothetical analysis, not a record of how the Step 3 attacker made its identification decision. It complements Step 4's identification accuracy by measuring candidate counts and whether the known target remains.
Each case applies the saved location, occupation and education answers in that order. Unknown or invalid answers leave the pool unchanged. Target identity is used only for evaluation; if a filter removes the target, it is not restored.

## Coverage

Current memory files provide 400 matching cases; 0 lack saved attribute answers, and 0 saved cases lack current memory sets. This checks case availability, not whether note contents are unchanged.

| Redactor | k notes | Saved cases |
| --- | ---: | ---: |
| gemini | 1 | 32 |
| gemini | 3 | 32 |
| gemini | 5 | 32 |
| gemini | 10 | 4 |
| ner | 1 | 32 |
| ner | 3 | 32 |
| ner | 5 | 32 |
| ner | 10 | 4 |
| none | 1 | 32 |
| none | 3 | 32 |
| none | 5 | 32 |
| none | 10 | 4 |
| presidio | 1 | 32 |
| presidio | 3 | 32 |
| presidio | 5 | 32 |
| presidio | 10 | 4 |

## Weaknesses and interpretation

- The pool contains only synthetic profiles; its size and composition do not represent a real population or establish real-world identification risk.
- Step 3 selected attributes from a fixed set of profile-derived choices. This gives the attacker information that may not be available in an open-world search.
- Filtering assumes exact matching against known candidate attributes. The selected filter order is a simulation choice, not a demonstrated optimal search method.
- A smaller pool is not an identification success. The saved Step 3 identification result comes from a separate attack on the full pool, not an attack on this filtered shortlist.
- Incorrect guesses can exclude the target. Unknown or invalid guesses apply no filter, so high target retention alone does not demonstrate a successful attack.
- Saved Step 3 records have no note or profile hashes, so their exact historical inputs cannot be independently verified against the current files.
- Cases from the same profile are related. Group sizes may differ across redactors and k; small groups are uncertain, and unpaired differences do not establish a causal effect.
- The map shows city-level counts for the original candidate pool, not filtered survivors, individual locations or journeys.

## Rerunning

Rerunning Step 5 with unchanged inputs only regenerates these outputs; it does not add cases or make model calls. A broader experiment requires additional Step 2 memories and Step 3 answers, followed by Step 4 and Step 5; those earlier model calls may incur costs.

## Outputs

- `case_stages.csv`: individual stage sizes, reductions, target retention and Step 3 outcomes.
- `stage_summary.csv` and `reduction.png`: counts and retention by redactor and k.
- `candidate_map.png` and `candidate_cities.csv`: synthetic profile counts by public city center, not individual locations.
- `regional_maps/report.md`: offline country maps comparing saved attribute guesses with synthetic ground truth, including coverage and limitations.

## Unmapped cities

- None.
