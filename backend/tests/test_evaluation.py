"""Evaluate the evaluator's safety checks, not only the policy under test."""

import copy
import json
from collections import Counter

from evals.run_evaluation import ROOT, evaluate_simulation, score_case, verify_sources
from backend.app.skills.recommendation import recommend


def test_labels_cover_every_official_request_and_documented_kind_counts():
    labels = json.loads((ROOT / "evals/labels.json").read_text())
    source = [
        line
        for line in (ROOT / "data/dispatch_requests.txt").read_text().splitlines()
        if line.startswith("R")
    ]
    assert [c["input"] for c in labels["cases"]] == source
    assert (
        dict(Counter(c["kind"] for c in labels["cases"])) == labels["expected_counts"]
    )
    assert len({c["id"] for c in labels["cases"]}) == 30


def test_original_source_hashes_match():
    assert verify_sources()["passed"]


def response_fixture():
    case = next(
        c
        for c in json.loads((ROOT / "evals/labels.json").read_text())["cases"]
        if c["id"] == "R04"
    )
    rec = recommend("ORD-041", 600, "2026-04-21")
    selected = rec["recommended"]
    response = {
        "status": "recommended",
        "parsed": case["expected_slots"],
        "recommendation": rec,
        "message": f"建议 {selected['name']}，期望 {selected['expected_date']} 交付。",
        "trace": [{"step": "recommend"}],
    }
    return case, response


def test_evaluator_detects_invented_arithmetic_separately_from_decision():
    case, response = response_fixture()
    assert score_case(case, response)["passed"]
    broken = copy.deepcopy(response)
    chosen_id = broken["recommendation"]["recommended"]["workshop_id"]
    candidate = next(
        c
        for c in broken["recommendation"]["candidates"]
        if c["workshop_id"] == chosen_id
    )
    candidate["cost"] += 123
    scored = score_case(case, broken)
    assert scored["decision_passed"]
    assert not scored["explanation_passed"]
    assert any("cost" in f for f in scored["explanation_failures"])


def test_evaluator_counts_ineligible_recommendation_as_hard_violation():
    case, response = response_fixture()
    response["recommendation"]["recommended"] = {
        "workshop_id": "W7",
        "name": "OldMill",
        "expected_date": "2026-04-05",
    }
    scored = score_case(case, response)
    assert scored["hard_constraint_violations"] == 1
    assert not scored["passed"]


def test_each_simulation_policy_uses_clean_state_and_reports_all_120_batches():
    first = evaluate_simulation(seeds=(5105, 5106))
    second = evaluate_simulation(seeds=(5105, 5106))
    assert first == second
    assert set(first["primary_beats_baselines"]) == {
        "random",
        "greedy_biggest",
        "cheapest",
    }
    for scenario in ("normal", "shock"):
        for policy in first[scenario]:
            assert sum(policy["allocation_counts"].values()) == 120
            assert len(policy["per_seed"]) == 2
            assert policy["metrics"]["cost"] > 0
