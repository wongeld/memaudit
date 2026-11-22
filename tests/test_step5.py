import csv
import io
import json
import sys
from dataclasses import replace

import pytest

import step5_test
from pipeline.profiles import Profile
from pipeline.regional_heatmaps import regional_counts
from pipeline.regional_maps import guess_counts, load_geodata
from pipeline.simulation_map import draw_world, resolve_city


def profile(ident, location, occupation, education):
    city = location.split(",")[0]
    return Profile(ident, "", "", "", "", "", "Kenya", 30, "25-34", location, city, "",
                   occupation, education, "", "", "sw", [])


def case(ident, answers, size):
    return {
        "key": f"{ident}|none|1", "profile_id": ident, "redactor": "none", "k": 1, "lang": "sw",
        "memory": "memory", "pool": "all", "pool_size": size, "model": "fake",
        "parse_error": False, "answers": answers,
    }


def test_reduction_records_exclusion_and_skips_unknown():
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Embu, Kenya", "doctor", "degree"),
        "c": profile("c", "Nairobi, Kenya", "teacher", "diploma"),
    }
    record = case("a", {"location": "Embu, Kenya", "occupation": "doctor", "education": "unknown"}, 3)
    rows = step5_test.reduce_case(record, profiles, None)
    assert [row["remaining_count"] for row in rows] == [3, 2, 1, 1]
    assert [row["target_retained"] for row in rows] == [True, True, False, False]
    assert rows[-1]["filter_applied"] is False
    assert rows[-1]["reduction_pct"] == pytest.approx(200 / 3)
    assert rows[-1]["step3_identification_available"] is False


def test_reduction_rejects_mismatched_pool_and_unsupported_answer():
    profiles = {"a": profile("a", "Embu, Kenya", "teacher", "degree")}
    wrong_pool = case("a", {}, 2)
    with pytest.raises(ValueError, match="candidate pool"):
        step5_test.reduce_case(wrong_pool, profiles, None)
    bad_answer = case("a", {"location": "Somewhere else"}, 1)
    with pytest.raises(ValueError, match="not a saved pool option"):
        step5_test.reduce_case(bad_answer, profiles, None)


def test_aggregate_reports_target_retention_and_actual_denominator():
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Nairobi, Kenya", "doctor", "degree"),
    }
    rows = []
    for ident in profiles:
        rows.extend(step5_test.reduce_case(
            case(ident, {"location": "Embu, Kenya", "occupation": "unknown", "education": "invalid"}, 2),
            profiles, None,
        ))
    result = next(row for row in step5_test.aggregate(rows) if row["stage"] == "location")
    assert result["cases"] == 2
    assert result["mean_candidates"] == 1
    assert result["mean_reduction_pct"] == 50
    assert result["targets_retained"] == 1 and result["target_retention_pct"] == 50


def test_regional_counts_include_zeros_normalize_and_separate_countries():
    a = profile("a", "Embu, Kenya", "Teacher", "degree")
    profiles = {
        "a": a,
        "b": replace(a, profile_id="b", city="embu", occupation="teacher"),
        "c": profile("c", "Nairobi, Kenya", "Doctor", "degree"),
        "d": replace(a, profile_id="d", country="Tanzania"),
    }
    rows = regional_counts(profiles)
    counts = {(row["country"], row["city"], row["occupation"]): row["count"] for row in rows}
    assert counts == {
        ("Kenya", "Embu", "Doctor"): 0, ("Kenya", "Embu", "Teacher"): 2,
        ("Kenya", "Nairobi", "Doctor"): 1, ("Kenya", "Nairobi", "Teacher"): 0,
        ("Tanzania", "Embu", "Teacher"): 1,
    }
    assert sum(counts.values()) == len(profiles)
    with pytest.raises(ValueError, match="missing a country, city or occupation"):
        regional_counts({"a": replace(a, occupation="")})


def test_regional_heatmaps_cli_is_offline_and_uses_full_pool(monkeypatch, tmp_path):
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Nairobi, Kenya", "doctor", "degree"),
    }
    output = tmp_path / "reduction"
    monkeypatch.setattr(step5_test, "OUT", output)
    monkeypatch.setattr(step5_test, "load_profiles", lambda *_args: profiles)
    monkeypatch.setattr(step5_test, "read_records", lambda *_args, **_kwargs: pytest.fail("read Step 3"))
    monkeypatch.setattr("pipeline.simulation_map.map_candidates",
                        lambda *_args: pytest.fail("used map service"))
    monkeypatch.setattr(sys, "argv", ["step5_test.py", "--regional-heatmaps"])
    step5_test.main()
    region = output / "regional_heatmaps"
    assert (region / "region_001.png").is_file()
    with (region / "city_occupation_counts.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert sum(int(row["count"]) for row in rows) == 2
    assert len(rows) == 4 and sum(row["count"] == "0" for row in rows) == 2
    report = (region / "report.md").read_text(encoding="utf-8")
    assert "not geographic maps" in report and "not proof of identification" in report


def test_map_guess_counts_distinguish_unknown_and_unmatched_combinations():
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Embu, Kenya", "teacher", "degree"),
        "c": profile("c", "Nairobi, Kenya", "doctor", "degree"),
    }
    cases = [
        case("a", {"location": "Embu, Kenya", "occupation": "teacher"}, 3),
        case("b", {"location": "Embu, Kenya", "occupation": "doctor"}, 3),
        case("c", {"location": "unknown", "occupation": "invalid"}, 3),
        case("c", {"location": "Nairobi, Kenya", "occupation": "unknown"}, 3),
    ]
    rows, unknown_location, unknown_occupation = guess_counts(profiles, cases)
    counts = {(row["city"], row["occupation"]): (row["candidates"], row["cases"], row["correct_cases"])
              for row in rows}
    assert counts == {("Embu", "teacher"): (2, 1, 1), ("Embu", "doctor"): (0, 1, 0),
                      ("Nairobi", "Unknown occupation"): (None, 1, None)}
    assert (unknown_location, unknown_occupation) == (1, 2)


def test_offline_country_geometry_and_cities_exist():
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Nairobi, Kenya", "doctor", "degree"),
    }
    countries, cities = load_geodata(profiles)
    assert countries["kenya"]["type"] == "Polygon"
    assert len(cities[("kenya", "embu")]) == 2
    profiles["b"].city = "Not in the dataset"
    with pytest.raises(ValueError, match="No Natural Earth geometry"):
        load_geodata(profiles)


def test_regional_maps_cli_preserves_coverage_and_never_uses_map_services(monkeypatch, tmp_path):
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Nairobi, Kenya", "doctor", "degree"),
    }
    records = [
        case("a", {"location": "Embu, Kenya", "occupation": "teacher"}, 2),
        case("b", {"location": "unknown", "occupation": "doctor"}, 2),
    ]
    attacks = tmp_path / "results" / "attacks"
    attacks.mkdir(parents=True)
    (attacks / "attributes.jsonl").write_text(
        "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
    )
    monkeypatch.setattr(step5_test.config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(step5_test, "OUT", tmp_path / "reduction")
    monkeypatch.setattr(step5_test, "load_profiles", lambda *_args: profiles)
    monkeypatch.setattr("pipeline.simulation_map.map_candidates",
                        lambda *_args: pytest.fail("used map service"))
    monkeypatch.setattr(sys, "argv", ["step5_test.py", "--regional-maps"])
    step5_test.main()
    output = tmp_path / "reduction" / "regional_maps"
    assert (output / "map_none_k1_kenya.png").is_file()
    with (output / "coverage.csv").open(encoding="utf-8", newline="") as stream:
        coverage = list(csv.DictReader(stream))
    assert coverage[0]["saved_cases"] == "2" and coverage[0]["unknown_location"] == "1"
    with (output / "map_counts.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len([row for row in rows if row["side"] == "ground_truth"]) == 2
    assert len([row for row in rows if row["side"] == "saved_guesses"]) == 1
    assert next(row for row in rows if row["side"] == "saved_guesses")["correct_cases"] == "1"
    assert "not an observed identification" in (output / "report.md").read_text(encoding="utf-8")


def test_reduction_uses_bars_and_horizontal_stage_labels(monkeypatch, tmp_path):
    import matplotlib.pyplot as plt

    figures = []
    original = plt.subplots

    def capture(*args, **kwargs):
        fig, axes = original(*args, **kwargs)
        figures.append(fig)
        return fig, axes

    monkeypatch.setattr(plt, "subplots", capture)
    profiles = {"a": profile("a", "Embu, Kenya", "teacher", "degree")}
    rows = step5_test.reduce_case(case("a", {"location": "Embu, Kenya"}, 1), profiles, None)
    step5_test.draw_reduction(step5_test.aggregate(rows), tmp_path / "reduction.png")
    assert len(figures[0].axes) == 2
    for axis in figures[0].axes:
        assert len(axis.patches) == 4
        assert all(label.get_rotation() == 0 for label in axis.get_xticklabels())


def test_city_disambiguation_uses_public_neighborhood_without_guessing():
    class Search:
        def __init__(self):
            self.queries = []

        def search(self, query):
            self.queries.append(query)
            if query == "Boston, United States":
                return [
                    {"name": "Boston", "category": "boundary", "type": "administrative",
                     "lat": "42.36", "lon": "-71.06", "address": {"country": "United States"}},
                    {"name": "Boston", "category": "boundary", "type": "administrative",
                     "lat": "30.79", "lon": "-83.79", "address": {"country": "United States"}},
                ]
            if query == "Back Bay, Boston, United States":
                return [{"name": "Back Bay", "category": "place", "type": "neighbourhood",
                         "lat": "42.35", "lon": "-71.08", "address": {"country": "United States"}}]
            return []

    search = Search()
    assert resolve_city(search, "Boston", "United States", {"Back Bay"}) == (42.36, -71.06)
    assert resolve_city(search, "Boston", "United States", {"123 Private House"}) is None
    assert "123 Private House, Boston, United States" not in search.queries


def test_public_city_and_neighborhood_names_allow_exact_alias_normalization():
    class Search:
        def search(self, query, *, namedetails=False):
            results = {
                "Mekelle, Ethiopia": [
                    {"name": "Mek'elē", "category": "boundary", "type": "administrative",
                     "lat": "13.49", "lon": "39.47", "address": {"country": "Ethiopia"},
                     "namedetails": {"alt_name": "(2) Mekelle, Mekele."} if namedetails else {}},
                ],
                "Newark, United States": [
                    {"name": "Newark", "category": "boundary", "type": "administrative",
                     "lat": "40.73", "lon": "-74.17", "address": {"country": "United States"}},
                    {"name": "Newark", "category": "boundary", "type": "administrative",
                     "lat": "39.68", "lon": "-75.75", "address": {"country": "United States"}},
                ],
                "Ironbound, Newark, United States": [
                    {"name": "The Ironbound", "category": "place", "type": "village",
                     "lat": "40.72", "lon": "-74.16", "address": {"country": "United States"}},
                ],
            }
            return results[query]

    assert resolve_city(Search(), "Mekelle", "Ethiopia", set()) == (13.49, 39.47)
    assert resolve_city(Search(), "Newark", "United States", {"Ironbound"}) == (40.73, -74.17)


def test_world_map_fills_figure_and_includes_city_counts(monkeypatch, tmp_path):
    import matplotlib.pyplot as plt
    import numpy as np
    from PIL import Image

    image = io.BytesIO()
    plt.imsave(image, np.ones((2, 2, 3)))

    class Response:
        content = image.getvalue()

        def raise_for_status(self):
            pass

    monkeypatch.setattr("pipeline.simulation_map.requests.get", lambda *_args, **_kwargs: Response())
    figures = []
    original = plt.figure

    def capture(*args, **kwargs):
        fig = original(*args, **kwargs)
        figures.append(fig)
        return fig

    monkeypatch.setattr(plt, "figure", capture)
    points = [
        {"city": "Embu", "country": "Kenya", "count": 2, "latitude": -.53, "longitude": 37.45},
        {"city": "Boston", "country": "United States", "count": 4, "latitude": 42.36, "longitude": -71.06},
    ]
    output = tmp_path / "map.png"
    draw_world(points, output, tmp_path / "tiles", 6)
    axis = figures[0].axes[0]
    assert axis.get_position().width >= .95 and axis.get_position().height >= .85
    assert "6/6 mapped" in figures[0]._suptitle.get_text()
    assert "Embu, Kenya  (2)" in axis.texts[-1].get_text()
    with Image.open(output) as image_file:
        assert image_file.width >= 2500 and image_file.height >= 1200


def test_simulation_uses_saved_answers_and_preserves_old_outputs(monkeypatch, tmp_path):
    profiles = {
        "a": profile("a", "Embu, Kenya", "teacher", "degree"),
        "b": profile("b", "Nairobi, Kenya", "doctor", "degree"),
    }
    record = case("a", {"location": "Embu, Kenya", "occupation": "teacher", "education": "degree"}, 2)
    identity = {**record, "candidates": ["a", "b"], "chosen_profile_id": "a"}
    attacks = tmp_path / "results" / "attacks"
    attacks.mkdir(parents=True)
    (attacks / "attributes.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    (attacks / "identify.jsonl").write_text(json.dumps(identity) + "\n", encoding="utf-8")
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (memory_dir / "a_s01_none.txt").write_text("First synthetic note.", encoding="utf-8")
    (memory_dir / "b_s01_none.txt").write_text("Second synthetic note.", encoding="utf-8")
    simulation = tmp_path / "simulation"
    simulation.mkdir()
    old = simulation / "old_results.jsonl"
    old.write_text("preserved", encoding="utf-8")
    monkeypatch.setattr(step5_test.config, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(step5_test.config, "MEMORY_DIR", memory_dir)
    monkeypatch.setattr(step5_test, "OUT", simulation / "reduction")
    monkeypatch.setattr(step5_test, "load_profiles", lambda *_args: profiles)
    monkeypatch.setattr("pipeline.simulation_map.map_candidates", lambda _profiles, _out: (2, []))
    monkeypatch.setattr(sys, "argv", ["step5_test.py"])
    step5_test.main()
    with (simulation / "reduction" / "case_stages.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4 and rows[-1]["target_retained"] == "True"
    assert rows[-1]["step3_identification_correct"] == "True"
    report = (simulation / "reduction" / "report.md").read_text(encoding="utf-8")
    assert "hypothetical analysis" in report
    assert "a separate attack on the full pool" in report
    assert "2 matching cases; 1 lack saved attribute answers" in report
    assert "no note or profile hashes" in report
    assert "| none | 1 | 1 |" in report
    assert old.read_text(encoding="utf-8") == "preserved"
