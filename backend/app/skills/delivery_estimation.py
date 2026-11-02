"""Deterministic scenario estimates. No queue mutation or random draw."""

from __future__ import annotations
from datetime import date, timedelta
from math import ceil, isfinite
from ..data_access import CHAT_REFERENCE_DATE, SIMULATION_EPOCH


def _number(value, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} 必须是数值")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} 必须是数值") from None
    if not isfinite(result) or result < minimum:
        raise ValueError(f"{name} 必须是大于等于 {minimum} 的有限数")
    return result


def official_date(reference_date: date, days: float) -> str:
    """Round absolute simulation day, including Python's ties-to-even rule."""
    day = (reference_date - SIMULATION_EPOCH).days
    return (SIMULATION_EPOCH + timedelta(days=round(day + days))).isoformat()


def estimate_delivery(
    order: dict,
    workshop: dict,
    reference_date: date = CHAT_REFERENCE_DATE,
    queue_days: float | None = None,
) -> dict:
    if isinstance(reference_date, str):
        reference_date = date.fromisoformat(reference_date)
    pieces = _number(order.get("pieces"), "pieces", 1)
    if pieces != int(pieces):
        raise ValueError("pieces 必须是正整数")
    capacity = _number(workshop.get("capacity_pieces_per_day"), "capacity", 0)
    if capacity <= 0:
        raise ValueError("capacity 必须大于 0")
    queue = _number(
        workshop.get("current_queue_days") if queue_days is None else queue_days,
        "queue_days",
    )
    lead = _number(workshop.get("pickup_lead_days"), "lead_days")
    defect = _number(workshop.get("defect_rate"), "defect_rate")
    if defect > 1:
        raise ValueError("defect_rate 不可大于 1")
    cost = _number(workshop.get("cost_per_piece"), "cost_per_piece")
    work = pieces / capacity
    best = queue + work + lead
    expected_work = work * (1 + 0.5 * defect)
    expected = queue + expected_work + lead
    rework = queue + work * 1.5 + lead
    due = order.get("due_date")
    expected_date = official_date(reference_date, expected)
    result = {
        "order_id": order.get("order_id"),
        "workshop_id": workshop.get("workshop_id"),
        "queue_days": queue,
        "processing_days": work,
        "base_work_days": work,
        "lead_days": lead,
        "expected_work_days": expected_work,
        "optimistic_days": best,
        "best_case_days": best,
        "expected_days": expected,
        "rework_days": rework,
        "defect_case_days": rework,
        "optimistic_date": official_date(reference_date, best),
        "best_case_date": official_date(reference_date, best),
        "expected_date": expected_date,
        "rework_date": official_date(reference_date, rework),
        "defect_case_date": official_date(reference_date, rework),
        "conservative_date": (
            reference_date + timedelta(days=ceil(expected))
        ).isoformat(),
        "conservative_rework_date": (
            reference_date + timedelta(days=ceil(rework))
        ).isoformat(),
        "cost": pieces * cost,
        "estimated_cost": pieces * cost,
        "defect_rate": defect,
        "on_time": expected_date <= due if due else None,
        "rounding": "官方绝对回放日 round（.5 取偶数）；conservative_date 单独使用 ceil",
        "source": f"data/workshops.csv:{workshop.get('workshop_id')}",
    }
    if due:
        due_date = date.fromisoformat(due)
        best_late = max(
            0, (date.fromisoformat(result["optimistic_date"]) - due_date).days
        )
        rework_late = max(
            0, (date.fromisoformat(result["rework_date"]) - due_date).days
        )
        result["late_probability"] = (1 - defect) * (best_late > 0) + defect * (
            rework_late > 0
        )
        result["expected_late_days"] = (1 - defect) * best_late + defect * rework_late
    return result
