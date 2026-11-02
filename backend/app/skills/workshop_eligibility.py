"""Explain the official eligibility decision, never override it."""

from harness.simulate import Workshop, STAGES, eligible_workshops, remaining_stages


def to_workshop(row: dict) -> Workshop:
    return Workshop(
        row["workshop_id"],
        row["name"],
        int(row["capacity_pieces_per_day"]),
        int(row["pickup_lead_days"]),
        float(row["defect_rate"]),
        float(row["cost_per_piece"]),
        set(row["makes"].split("+")),
        row["status"],
        int(row["max_batch_pieces"]) if row.get("max_batch_pieces") else None,
        float(row["current_queue_days"]),
        row.get("notes", ""),
        frozenset(row["stages"].split("+")) if row.get("stages") else frozenset(STAGES),
    )


def check_workshop_eligibility(order: dict, workshop: dict) -> dict:
    w = to_workshop(workshop)
    batch = {"category": order["category"], "pieces": order["pieces"]}
    if order.get("dispatch_stage"):
        batch["from_stage"] = order["dispatch_stage"]
    if batch["pieces"] <= 0:
        raise ValueError("pieces 必须大于 0")
    reasons = []
    if w.status != "ACTIVE":
        reasons.append("工坊已暂停：SUSPENDED，禁止接收新批次")
    if batch["category"] not in w.makes:
        reasons.append(f"不支持 {batch['category']} 产品类别")
    if w.max_batch is not None and batch["pieces"] > w.max_batch:
        reasons.append(f"{batch['pieces']} 件超过试用期单批上限 {w.max_batch} 件")
    missing = remaining_stages(batch) - w.stages
    if missing:
        reasons.append("缺少剩余工序：" + "、".join(s for s in STAGES if s in missing))
    return {
        "eligible": bool(eligible_workshops(batch, {w.workshop_id: w})),
        "reasons": reasons,
    }
