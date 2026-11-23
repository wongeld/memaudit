# Regional synthetic privacy maps

Each figure compares saved Step 3 city and occupation guesses (left) with all 40 synthetic profiles (right). The sides do not have the same coverage: each experiment has only its saved cases, and cases with unknown or invalid locations cannot be placed. `coverage.csv` records the numbers for each experiment.

For each guessed city and occupation, the left panel counts matches in the complete synthetic pool, the saved cases making that guess, and how many of those cases guessed both attributes correctly for their target profile. A zero pool count means the combination matches no synthetic profile. Unknown occupations are shown without a match count. The right panel shows the actual city-and-occupation counts from the full pool. `map_counts.csv` contains the displayed counts.

A red marker means at least one displayed combination has exactly one match in this synthetic pool; orange means the smallest positive match count is 2-4, and teal means 5 or more. Gray indicates no positive match or an unknown occupation. A marker summarizes a city; use the per-city lists for each occupation and for zero-match combinations.

These counts assume access to the full synthetic pool and are not an observed identification, evidence that the guesses are correct, or a real-world risk estimate. Step 3 chose attributes from profile-derived options. Historical inputs lack hashes. Some city names are ambiguous; Natural Earth provides a representative city position, not proof that it is the intended city. Points are city centers, not individual locations.

The United States panels show only the contiguous area; all current US synthetic cities are in that area. The comparison uses offline Natural Earth 1:110m country boundaries and 1:10m populated-place coordinates, not OpenStreetMap or map tiles. The included data is extracted from Natural Earth's [country boundaries](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson) and [populated places](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_10m_populated_places.geojson). Hawassa and Mekelle correspond to the Natural Earth names Awasa and Mekele. Natural Earth data is [public domain](https://www.naturalearthdata.com/about/terms-of-use/).

## Maps

### gemini, k=1 (32 saved cases; 32 with unknown/invalid location)

- [Ethiopia](map_gemini_k1_ethiopia.png)
- [Kenya](map_gemini_k1_kenya.png)
- [Tanzania](map_gemini_k1_tanzania.png)
- [United States](map_gemini_k1_united-states.png)

### gemini, k=3 (32 saved cases; 20 with unknown/invalid location)

- [Ethiopia](map_gemini_k3_ethiopia.png)
- [Kenya](map_gemini_k3_kenya.png)
- [Tanzania](map_gemini_k3_tanzania.png)
- [United States](map_gemini_k3_united-states.png)

### gemini, k=5 (32 saved cases; 16 with unknown/invalid location)

- [Ethiopia](map_gemini_k5_ethiopia.png)
- [Kenya](map_gemini_k5_kenya.png)
- [Tanzania](map_gemini_k5_tanzania.png)
- [United States](map_gemini_k5_united-states.png)

### gemini, k=10 (4 saved cases; 3 with unknown/invalid location)

- [Ethiopia](map_gemini_k10_ethiopia.png)
- [Kenya](map_gemini_k10_kenya.png)
- [Tanzania](map_gemini_k10_tanzania.png)
- [United States](map_gemini_k10_united-states.png)

### ner, k=1 (32 saved cases; 13 with unknown/invalid location)

- [Ethiopia](map_ner_k1_ethiopia.png)
- [Kenya](map_ner_k1_kenya.png)
- [Tanzania](map_ner_k1_tanzania.png)
- [United States](map_ner_k1_united-states.png)

### ner, k=3 (32 saved cases; 7 with unknown/invalid location)

- [Ethiopia](map_ner_k3_ethiopia.png)
- [Kenya](map_ner_k3_kenya.png)
- [Tanzania](map_ner_k3_tanzania.png)
- [United States](map_ner_k3_united-states.png)

### ner, k=5 (32 saved cases; 4 with unknown/invalid location)

- [Ethiopia](map_ner_k5_ethiopia.png)
- [Kenya](map_ner_k5_kenya.png)
- [Tanzania](map_ner_k5_tanzania.png)
- [United States](map_ner_k5_united-states.png)

### ner, k=10 (4 saved cases; 1 with unknown/invalid location)

- [Ethiopia](map_ner_k10_ethiopia.png)
- [Kenya](map_ner_k10_kenya.png)
- [Tanzania](map_ner_k10_tanzania.png)
- [United States](map_ner_k10_united-states.png)

### none, k=1 (32 saved cases; 0 with unknown/invalid location)

- [Ethiopia](map_none_k1_ethiopia.png)
- [Kenya](map_none_k1_kenya.png)
- [Tanzania](map_none_k1_tanzania.png)
- [United States](map_none_k1_united-states.png)

### none, k=3 (32 saved cases; 0 with unknown/invalid location)

- [Ethiopia](map_none_k3_ethiopia.png)
- [Kenya](map_none_k3_kenya.png)
- [Tanzania](map_none_k3_tanzania.png)
- [United States](map_none_k3_united-states.png)

### none, k=5 (32 saved cases; 0 with unknown/invalid location)

- [Ethiopia](map_none_k5_ethiopia.png)
- [Kenya](map_none_k5_kenya.png)
- [Tanzania](map_none_k5_tanzania.png)
- [United States](map_none_k5_united-states.png)

### none, k=10 (4 saved cases; 0 with unknown/invalid location)

- [Ethiopia](map_none_k10_ethiopia.png)
- [Kenya](map_none_k10_kenya.png)
- [Tanzania](map_none_k10_tanzania.png)
- [United States](map_none_k10_united-states.png)

### presidio, k=1 (32 saved cases; 17 with unknown/invalid location)

- [Ethiopia](map_presidio_k1_ethiopia.png)
- [Kenya](map_presidio_k1_kenya.png)
- [Tanzania](map_presidio_k1_tanzania.png)
- [United States](map_presidio_k1_united-states.png)

### presidio, k=3 (32 saved cases; 8 with unknown/invalid location)

- [Ethiopia](map_presidio_k3_ethiopia.png)
- [Kenya](map_presidio_k3_kenya.png)
- [Tanzania](map_presidio_k3_tanzania.png)
- [United States](map_presidio_k3_united-states.png)

### presidio, k=5 (32 saved cases; 7 with unknown/invalid location)

- [Ethiopia](map_presidio_k5_ethiopia.png)
- [Kenya](map_presidio_k5_kenya.png)
- [Tanzania](map_presidio_k5_tanzania.png)
- [United States](map_presidio_k5_united-states.png)

### presidio, k=10 (4 saved cases; 1 with unknown/invalid location)

- [Ethiopia](map_presidio_k10_ethiopia.png)
- [Kenya](map_presidio_k10_kenya.png)
- [Tanzania](map_presidio_k10_tanzania.png)
- [United States](map_presidio_k10_united-states.png)
