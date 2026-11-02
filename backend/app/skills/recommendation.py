"""Compose verified eligibility, estimates, and configurable ranking into advice."""

from __future__ import annotations
from datetime import date
from itertools import combinations
from math import floor, ceil
from ..data_access import get_order, get_workshops, CHAT_REFERENCE_DATE
from ..allocator import (
    rank_candidates,
    candidate_key,
    candidate_scales,
    POLICY_VERSION,
    validate_weights,
    OBJECTIVES,
)
from .workshop_eligibility import check_workshop_eligibility
from .filter_workshops import normalize_workshop
from .delivery_estimation import estimate_delivery

OBJECTIVE_EXPLANATIONS = {
    "lateness": "优先最小化延期概率和期望延期天数，再比较期望周转时间。",
    "fastest": "在满足资格与排除约束后，选择期望周转最快的工坊。",
    "cheapest_on_time": "只在期望日期不晚于截止日期的工坊中选择最低成本。",
    "quality": "先满足期望交期，再选择最低缺陷率，兼顾周转时间。",
    "fairness": "先满足期望交期，再比较本次决策上下文累计分配件数；独立聊天没有历史分配，按风险和交期打破平局。",
    "robustness": "优先降低延期概率与延期天数，再缩短返工情景周转。未假设已知停工工坊。",
    "hybrid": "先满足期望交期，再对归一化延期风险、缺陷率、累计负载和成本加权。",
}


def _split(order, workshops, excluded):
    """Two-shop hypothetical, integer pieces, shared snapshot, never queue writes."""
    total = order["pieces"]
    if total < 2:
        return None
    candidates = [
        w
        for w in workshops
        if w["workshop_id"] not in excluded
        and check_workshop_eligibility({**order, "pieces": 1}, w)["eligible"]
    ]
    options = []
    for a, b in combinations(candidates, 2):
        low = max(1, total - (b["max_batch_pieces"] or total))
        high = min(total - 1, a["max_batch_pieces"] or total)
        if low > high:
            continue
        ar = (1 + 0.5 * a["defect_rate"]) / a["capacity_pieces_per_day"]
        br = (1 + 0.5 * b["defect_rate"]) / b["capacity_pieces_per_day"]
        ideal = (
            b["current_queue_days"]
            + b["pickup_lead_days"]
            + total * br
            - a["current_queue_days"]
            - a["pickup_lead_days"]
        ) / (ar + br)
        for n in {
            low,
            high,
            max(low, min(high, floor(ideal))),
            max(low, min(high, ceil(ideal))),
        }:
            parts = []
            for w, qty in ((a, n), (b, total - n)):
                e = estimate_delivery({**order, "pieces": qty}, w)
                parts.append({**e, "name": w["name"], "pieces": qty})
            options.append(
                {
                    "parts": parts,
                    "expected_days": max(p["expected_days"] for p in parts),
                    "expected_date": max(p["expected_date"] for p in parts),
                    "cost": sum(p["cost"] for p in parts),
                    "on_time": all(p["on_time"] for p in parts),
                    "status": "proposal_only",
                    "note": "双工坊拆单的独立估算；未执行。官方模拟器不支持拆单，未计入模拟器成绩。",
                }
            )
    return (
        min(options, key=lambda p: (p["expected_days"], p["cost"])) if options else None
    )


def recommend(
    order_id: str,
    pieces: int,
    due_date: str,
    objective: str = "lateness",
    excluded_workshops: list[str] | None = None,
    preferred_workshop: str | None = None,
    stages: bool = False,
    allow_split: bool = False,
    weights: dict | None = None,
) -> dict:
    if isinstance(pieces, bool) or not isinstance(pieces, int) or pieces <= 0:
        raise ValueError("pieces 必须是正整数")
    deadline = date.fromisoformat(due_date)
    if objective not in OBJECTIVES:
        raise ValueError(f"未知目标：{objective}")
    if objective == "hybrid":
        weights = validate_weights(weights)
    order = {
        **get_order(order_id, stages),
        "pieces": pieces,
        "due_date": deadline.isoformat(),
    }
    workshops = get_workshops(stages)
    excluded = {
        normalize_workshop(name, workshops) for name in (excluded_workshops or [])
    }
    preferred = (
        normalize_workshop(preferred_workshop, workshops)
        if preferred_workshop
        else None
    )
    candidates = []
    for w in workshops:
        eligibility = check_workshop_eligibility(order, w)
        if w["workshop_id"] in excluded:
            eligibility["eligible"] = False
            eligibility["reasons"].append("用户明确排除该工坊")
        estimate = estimate_delivery(order, w)
        estimate["source"] = (
            f"data/{'workshops_stages.csv' if stages else 'workshops.csv'}:{w['workshop_id']}"
        )
        candidates.append(
            {
                **estimate,
                **eligibility,
                "name": w["name"],
                "capacity": w["capacity_pieces_per_day"],
                "unit_cost": w["cost_per_piece"],
                "max_batch_pieces": w["max_batch_pieces"],
                "score": None,
            }
        )
    eligible = [c for c in candidates if c["eligible"]]
    ranked = rank_candidates(eligible, objective, weights=weights)
    scales = candidate_scales(eligible)
    for i, c in enumerate(ranked):
        c["rank"] = i + 1
        c["score"] = list(candidate_key(c, objective, weights=weights, scales=scales))[
            :-1
        ]
    ontime = [c for c in ranked if c["on_time"]]
    selected = ontime[0] if ontime else None
    preferred_refusal = None
    if preferred:
        requested = next(c for c in candidates if c["workshop_id"] == preferred)
        if requested["eligible"] and requested["on_time"]:
            selected = requested
        else:
            reasons = requested["reasons"] or [
                f"期望到货 {requested['expected_date']} 晚于截止日期 {due_date}"
            ]
            preferred_refusal = {
                "workshop_id": preferred,
                "name": requested["name"],
                "reasons": reasons,
            }
    earliest = (
        min(eligible, key=lambda c: (c["optimistic_days"], c["cost"]))
        if eligible
        else None
    )
    infeasible_options = []
    if not selected:
        if earliest:
            infeasible_options = [
                f"接受延迟：最早无缺陷到货 {earliest['optimistic_date']}，期望 {earliest['expected_date']}。",
                "评估拆分批次，但需分别验证工坊资格与整批完成时间。",
                "升级主管协商交期或额外产能；当前数据没有额外产能承诺。",
            ]
        else:
            infeasible_options = [
                "调整批量或明确撤销用户约束后重新评估。",
                "升级主管寻找新产能；不得绕过暂停、类别或工序限制。",
            ]
    split_plan = _split(order, workshops, excluded) if allow_split else None
    if split_plan and earliest:
        split_plan["faster_than_single"] = split_plan["expected_days"] < min(
            c["expected_days"] for c in eligible
        )
    assumptions = [
        "聊天参考日固定为 2026-04-01，队列来自当天快照；每次推荐独立估算，不更新队列。",
        "工坊按官方模型每周 7 天生产；生产量 / 日产能，运输不占生产队列。",
        "期望生产时间 = 件数 / 日产能 × (1 + 0.5 × 缺陷率)，不是交付保证。",
        "三情景日期采用官方 round 绝对日规则；conservative_date 为独立的 ceil 保守展示。",
        "期望日期按时才推荐；返工情景超期会保留风险，任何建议均未真实下发。",
        "价格单位沿用原始数据，数据未声明币种。",
        "已启用可选 stages：须覆盖当前工序至 PACKING。"
        if stages
        else "默认赛道：未启用可选工序资格扩展。",
    ]
    return {
        "order": order,
        "order_id": order_id,
        "pieces": pieces,
        "due_date": due_date,
        "reference_date": CHAT_REFERENCE_DATE.isoformat(),
        "objective": objective,
        "policy_version": POLICY_VERSION,
        "stages": stages,
        "weights": weights,
        "candidates": candidates,
        "recommended": selected,
        "earliest_date": earliest["optimistic_date"] if earliest else None,
        "earliest_candidate": earliest,
        "feasibility": "feasible"
        if selected
        else "infeasible"
        if eligible
        else "no_eligible",
        "assumptions": assumptions,
        "options": infeasible_options,
        "preferred_refusal": preferred_refusal,
        "split_plan": split_plan,
        "ranking_explanation": OBJECTIVE_EXPLANATIONS[objective],
        "excluded_workshops": sorted(excluded),
        "executed": False,
        "sources": [
            f"data/{'orders_stages.csv' if stages else 'orders.csv'}:{order_id}",
            "harness/simulate.py:eligible_workshops",
            "harness/simulate.py:Simulator.run",
        ],
    }


def overload_probe(
    order_id: str, workshop_id: str, additional_pieces: int, stages: bool = False
) -> dict:
    """Compare one workshop's current scenario to extra queued production."""
    if (
        isinstance(additional_pieces, bool)
        or not isinstance(additional_pieces, int)
        or additional_pieces < 0
    ):
        raise ValueError("additional_pieces 必须为非负整数")
    order = get_order(order_id, stages)
    rows = get_workshops(stages)
    wid = normalize_workshop(workshop_id, rows)
    workshop = next(w for w in rows if w["workshop_id"] == wid)
    eligibility = check_workshop_eligibility(order, workshop)
    if not eligibility["eligible"]:
        return {
            "eligible": False,
            "reasons": eligibility["reasons"],
            "before": None,
            "after": None,
        }
    added_days = additional_pieces / workshop["capacity_pieces_per_day"]
    return {
        "eligible": True,
        "workshop_id": wid,
        "additional_pieces": additional_pieces,
        "added_queue_days": added_days,
        "before": estimate_delivery(order, workshop),
        "after": estimate_delivery(
            order, workshop, queue_days=workshop["current_queue_days"] + added_days
        ),
        "assumption": "新增排队量按无返工生产时间估计；不改变 CSV 或真实队列。",
    }
