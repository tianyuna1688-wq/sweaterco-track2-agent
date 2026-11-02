"""Numerical, authority-parity, boundary and replay tests for business skills."""

from datetime import date
import copy
import pytest
from harness.simulate import (
    Simulator,
    eligible_workshops,
    load_workshops,
    random_choice,
    greedy_biggest,
    cheapest,
)
from backend.app.data_access import (
    get_orders,
    get_order,
    get_workshops,
    get_requests,
    dataset_info,
)
from backend.app.skills.delivery_estimation import estimate_delivery, official_date
from backend.app.skills.workshop_eligibility import check_workshop_eligibility
from backend.app.skills.recommendation import recommend, overload_probe
from backend.app.allocator import make_allocator


def test_verbatim_dataset_integrity_and_counts():
    info = dataset_info()
    assert (info["orders"], info["workshops"], info["requests"]) == (120, 8, 30)
    assert info["source_verified"] and not info["mismatches"]
    assert len({r["id"] for r in get_requests()}) == 30
    assert all(isinstance(r["pieces"], int) for r in get_orders())


@pytest.mark.parametrize("stages", [False, True])
def test_eligibility_matches_official_for_every_order_workshop(stages):
    workshops = load_workshops(stages)
    rows = get_workshops(stages)
    for order in get_orders(stages):
        batch = {"pieces": order["pieces"], "category": order["category"]}
        if stages:
            batch["from_stage"] = order["dispatch_stage"]
        ids = {w.workshop_id for w in eligible_workshops(batch, workshops)}
        for w in rows:
            result = check_workshop_eligibility(order, w)
            assert result["eligible"] == (w["workshop_id"] in ids)
            assert bool(result["reasons"]) == (w["workshop_id"] not in ids)


def test_stage_extension_has_identical_base_records():
    for base, extended in zip(get_orders(), get_orders(True)):
        assert base == {k: v for k, v in extended.items() if k != "dispatch_stage"}
    for base, extended in zip(get_workshops(), get_workshops(True)):
        assert base == {k: v for k, v in extended.items() if k != "stages"}


@pytest.fixture
def numeric_example():
    return {"order_id": "TEST", "pieces": 1000, "due_date": "2026-04-10"}, {
        "workshop_id": "TEST",
        "capacity_pieces_per_day": 200,
        "current_queue_days": 2,
        "pickup_lead_days": 1,
        "defect_rate": 0.2,
        "cost_per_piece": 4.5,
    }


def test_delivery_formula_and_rounding_are_separate(numeric_example):
    order, w = numeric_example
    original = copy.deepcopy((order, w))
    out = estimate_delivery(order, w)
    assert out["processing_days"] == 5
    assert out["expected_work_days"] == 5.5
    assert out["expected_days"] == 8.5
    assert out["rework_days"] == 10.5
    assert out["cost"] == 4500
    assert out["expected_date"] == "2026-04-09"  # round(90 + 8.5) = 98
    assert out["conservative_date"] == "2026-04-10"
    assert out["late_probability"] == pytest.approx(0.2)
    assert out["expected_late_days"] == pytest.approx(0.2)
    assert (order, w) == original


def test_absolute_half_even_rounding_matches_harness():
    assert (
        official_date(date(2026, 1, 2), 2.5) == "2026-01-05"
    )  # round(1+2.5)=4, not 1+round(2.5)
    assert official_date(date(2026, 1, 1), 2.5) == "2026-01-03"


@pytest.mark.parametrize(
    "field,value",
    [
        ("capacity_pieces_per_day", 0),
        ("capacity_pieces_per_day", -1),
        ("capacity_pieces_per_day", float("nan")),
        ("current_queue_days", -1),
        ("defect_rate", 1.1),
        ("defect_rate", float("inf")),
        ("cost_per_piece", -1),
        ("pickup_lead_days", -1),
    ],
)
def test_invalid_numeric_fields_rejected(numeric_example, field, value):
    order, w = numeric_example
    w[field] = value
    with pytest.raises(ValueError):
        estimate_delivery(order, w)


@pytest.mark.parametrize("pieces", [0, -1, 1.5, True, float("nan")])
def test_invalid_piece_count_rejected(pieces):
    with pytest.raises(ValueError):
        recommend("ORD-081", pieces, "2026-04-13")


@pytest.mark.parametrize(
    "order_id,pieces,deadline",
    [
        ("ORD-103", 2000, "2026-04-04"),
        ("ORD-002", 1000, "2026-03-29"),
        ("ORD-099", 1500, "2026-04-05"),
    ],
)
def test_deliberately_impossible_requests_never_recommend(order_id, pieces, deadline):
    out = recommend(order_id, pieces, deadline)
    assert out["feasibility"] == "infeasible"
    assert out["recommended"] is None
    assert out["earliest_date"] > deadline
    assert len(out["options"]) == 3
    assert out["executed"] is False


@pytest.mark.parametrize(
    "order_id,preferred,reason",
    [
        ("ORD-073", "FreshStart", "上限"),
        ("ORD-008", "OldMill", "暂停"),
        ("ORD-103", "QuickStitch", "不支持"),
        ("ORD-015", "Little Loom", "不支持"),
    ],
)
def test_requested_ineligible_workshop_refused_with_evidence(
    order_id, preferred, reason
):
    order = get_order(order_id)
    out = recommend(
        order_id, order["pieces"], "2026-04-30", preferred_workshop=preferred
    )
    assert out["preferred_refusal"] is not None
    assert reason in " ".join(out["preferred_refusal"]["reasons"])
    assert out["recommended"] is not None
    assert out["recommended"]["name"] != preferred


def test_constraints_accept_aliases_and_never_drop_exclusion():
    out = recommend(
        "ORD-109",
        500,
        "2026-04-13",
        objective="cheapest_on_time",
        excluded_workshops=["Budget Works"],
    )
    assert out["recommended"]["workshop_id"] != "W3"
    w = next(c for c in out["candidates"] if c["workshop_id"] == "W3")
    assert not w["eligible"] and any("排除" in r for r in w["reasons"])
    with pytest.raises(ValueError):
        recommend("ORD-109", 500, "2026-04-13", excluded_workshops=["made-up shop"])


def test_cheapest_on_time_and_quality_constraints():
    out = recommend("ORD-081", 1500, "2026-04-13", objective="cheapest_on_time")
    legal = [c for c in out["candidates"] if c["eligible"] and c["on_time"]]
    assert out["recommended"]["cost"] == min(c["cost"] for c in legal)
    out = recommend("ORD-095", 800, "2026-04-26", objective="quality")
    legal = [c for c in out["candidates"] if c["eligible"] and c["on_time"]]
    assert out["recommended"]["defect_rate"] == min(c["defect_rate"] for c in legal)


def test_split_is_explicit_conserves_pieces_and_respects_eligibility():
    out = recommend("ORD-005", 500, "2026-04-20", allow_split=True)
    plan = out["split_plan"]
    assert plan["status"] == "proposal_only"
    assert sum(p["pieces"] for p in plan["parts"]) == 500
    assert len({p["workshop_id"] for p in plan["parts"]}) == 2
    ws = {w["workshop_id"]: w for w in get_workshops()}
    for p in plan["parts"]:
        assert check_workshop_eligibility(
            {**get_order("ORD-005"), "pieces": p["pieces"]}, ws[p["workshop_id"]]
        )["eligible"]
    assert recommend("ORD-005", 500, "2026-04-20")["split_plan"] is None


def test_all_excluded_no_eligible_and_no_silent_fallback():
    out = recommend(
        "ORD-081",
        1500,
        "2026-04-30",
        excluded_workshops=[w["workshop_id"] for w in get_workshops()],
    )
    assert out["feasibility"] == "no_eligible"
    assert out["recommended"] is None and out["earliest_date"] is None


def test_overload_probe_does_not_mutate_source():
    info = dataset_info()
    out = overload_probe("ORD-081", "W1", 600)
    assert out["added_queue_days"] == 2
    assert out["after"]["expected_days"] - out["before"][
        "expected_days"
    ] == pytest.approx(2)
    assert dataset_info()["hashes"] == info["hashes"]
    assert overload_probe("ORD-081", "W7", 600)["eligible"] is False


@pytest.mark.parametrize(
    "objective", ["lateness", "quality", "fairness", "robustness", "hybrid"]
)
def test_replay_is_deterministic_and_legal_across_reuse(objective):
    policy = make_allocator(objective)
    sim = Simulator(seed=5105)
    a = sim.run(policy, "a")
    b = sim.run(policy, "b")
    c = sim.run(make_allocator(objective), "c")
    assert a == b == c and len(a) == 120
    Simulator(seed=5106, shock=True, stages=True).run(
        make_allocator(objective), "stages"
    )


def test_primary_policy_beats_shipped_baselines_on_lateness():
    sim = Simulator()
    ours = sim.metrics(sim.run(make_allocator(), "ours"))
    for name, policy in [
        ("random", random_choice),
        ("capacity", greedy_biggest),
        ("cost", cheapest),
    ]:
        metrics = sim.metrics(sim.run(policy, name))
        assert ours["% late"] < metrics["% late"]
        assert ours["late days"] < metrics["late days"]


def test_invalid_config_and_unknown_order_rejected():
    with pytest.raises(ValueError):
        make_allocator("unknown")
    with pytest.raises(ValueError):
        make_allocator("hybrid", {"quality": -1})
    with pytest.raises(ValueError):
        make_allocator("hybrid", {"quality": 0})
    with pytest.raises(ValueError):
        make_allocator("hybrid", {"pretend": 1})
    with pytest.raises(LookupError):
        recommend("ORD-999", 100, "2026-04-10")


def test_hybrid_display_score_matches_actual_sort_order():
    out = recommend("ORD-081", 1500, "2026-04-30", objective="hybrid")
    ranked = sorted(
        (c for c in out["candidates"] if c["eligible"]), key=lambda c: c["rank"]
    )
    by_score = sorted(ranked, key=lambda c: (*c["score"], c["workshop_id"]))
    assert [c["workshop_id"] for c in ranked] == [c["workshop_id"] for c in by_score]
