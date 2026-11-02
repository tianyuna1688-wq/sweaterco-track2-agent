"""Inspectable deterministic policy shared by replay and chat recommendation."""

from __future__ import annotations
from math import isfinite
from harness.simulate import eligible_workshops
from .skills.delivery_estimation import estimate_delivery

POLICY_VERSION = "dispatch-v1.0"
OBJECTIVES = (
    "lateness",
    "quality",
    "fairness",
    "robustness",
    "hybrid",
    "fastest",
    "cheapest_on_time",
)
DEFAULT_WEIGHTS = {"lateness": 0.45, "quality": 0.25, "fairness": 0.15, "cost": 0.15}


def candidate_key(
    candidate: dict,
    objective: str = "lateness",
    assigned: dict | None = None,
    weights: dict | None = None,
    scales: dict | None = None,
) -> tuple:
    if objective not in OBJECTIVES:
        raise ValueError(f"未知目标：{objective}")
    assigned = assigned or {}
    w_id = candidate["workshop_id"]
    risk = candidate.get("late_probability", 0)
    late_days = candidate.get("expected_late_days", 0)
    expected = candidate["expected_days"]
    defect = candidate["defect_rate"]
    cost = candidate["cost"]
    share = assigned.get(w_id, 0)
    # Every policy first avoids a guaranteed-late choice if an on-time option exists.
    late = int(not candidate.get("on_time", True))
    if objective == "fastest":
        return (expected, risk, cost, w_id)
    if objective == "cheapest_on_time":
        return (late, cost, risk, expected, w_id)
    if objective == "quality":
        return (late, defect, risk, expected, cost, w_id)
    if objective == "fairness":
        return (late, share, risk, expected, cost, w_id)
    if objective == "robustness":
        return (risk, late_days, candidate["rework_days"], expected, cost, w_id)
    if objective == "hybrid":
        weights = validate_weights(weights)
        scales = scales or {
            "lateness": 1.0,
            "quality": 0.12,
            "fairness": max(1, sum(assigned.values())),
            "cost": max(cost, 1),
        }
        components = {
            "lateness": risk + late_days / 14,
            "quality": defect,
            "fairness": share,
            "cost": cost,
        }
        score = sum(weights[k] * components[k] / max(scales[k], 1e-9) for k in weights)
        return (late, score, expected, w_id)
    return (risk, late_days, expected, defect, cost, w_id)


def validate_weights(weights: dict | None) -> dict:
    values = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if not values or any(k not in DEFAULT_WEIGHTS for k in values):
        raise ValueError("hybrid 权重只接受 lateness、quality、fairness、cost")
    if any(
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or not isfinite(v)
        or v < 0
        for v in values.values()
    ):
        raise ValueError("权重必须为非负有限数字")
    total = sum(values.values())
    if total <= 0:
        raise ValueError("权重总和必须大于 0")
    return {k: v / total for k, v in values.items()}


def candidate_scales(candidates: list[dict], assigned: dict | None = None) -> dict:
    return {
        "lateness": 1.0,
        "quality": max((c["defect_rate"] for c in candidates), default=0.12),
        "fairness": max(1, sum((assigned or {}).values())),
        "cost": max((c["cost"] for c in candidates), default=1),
    }


def rank_candidates(
    candidates: list[dict], objective="lateness", assigned=None, weights=None
) -> list[dict]:
    if objective not in OBJECTIVES:
        raise ValueError(f"未知目标：{objective}")
    scales = candidate_scales(candidates, assigned)
    return sorted(
        candidates, key=lambda c: candidate_key(c, objective, assigned, weights, scales)
    )


def make_allocator(objective: str = "lateness", weights: dict | None = None):
    if objective not in OBJECTIVES:
        raise ValueError(f"未知目标：{objective}")
    if objective == "hybrid":
        weights = validate_weights(weights)
    assigned: dict[str, int] = {}
    last_batch = None
    seen = set()

    def allocator(batch, workshops, queues):
        nonlocal last_batch
        # Official helper can reuse the same closure across seeds. Detect the new replay.
        token = (batch["sent_date"], batch["order_id"])
        if last_batch is not None and (token[0] < last_batch[0] or token[1] in seen):
            assigned.clear()
            seen.clear()
        seen.add(token[1])
        last_batch = token
        candidates = []
        for w in eligible_workshops(batch, workshops):
            row = {
                "workshop_id": w.workshop_id,
                "capacity_pieces_per_day": w.capacity,
                "pickup_lead_days": w.lead_days,
                "defect_rate": w.defect_rate,
                "cost_per_piece": w.cost,
                "current_queue_days": queues[w.workshop_id],
            }
            order = {
                "order_id": batch["order_id"],
                "pieces": batch["pieces"],
                "due_date": batch["due_date"].isoformat(),
            }
            candidates.append(estimate_delivery(order, row, batch["sent_date"]))
        if not candidates:
            raise ValueError("没有符合官方规则的工坊")
        choice = rank_candidates(candidates, objective, assigned, weights)[0][
            "workshop_id"
        ]
        assigned[choice] = assigned.get(choice, 0) + batch["pieces"]
        return choice

    return allocator


def earliest_finish(batch, workshops, queues):
    return min(
        eligible_workshops(batch, workshops),
        key=lambda w: (
            queues[w.workshop_id] + batch["pieces"] / w.capacity + w.lead_days,
            w.workshop_id,
        ),
    ).workshop_id
