"""Read-only access to the verbatim Track 2 v3 dataset."""

from __future__ import annotations
import csv
import hashlib
import json
import math
import re
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CHAT_REFERENCE_DATE = date(2026, 4, 1)
SIMULATION_EPOCH = date(2026, 1, 1)


def _read(filename: str) -> list[dict]:
    with (DATA / filename).open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _unique(rows: list[dict], field: str) -> None:
    values = [r[field] for r in rows]
    if len(values) != len(set(values)) or any(not v for v in values):
        raise ValueError(f"数据键 {field} 缺失或重复")


def get_orders(stages: bool = False) -> list[dict]:
    rows = _read("orders_stages.csv" if stages else "orders.csv")
    _unique(rows, "order_id")
    for row in rows:
        row["pieces"] = int(row["pieces"])
        if row["pieces"] <= 0 or row["category"] not in ("TOPS", "ACCESSORIES"):
            raise ValueError(f"订单 {row['order_id']} 数量或类别无效")
        for field in ("order_date", "due_date", "last_activity_date"):
            date.fromisoformat(row[field])
        row["days_late"] = int(row["days_late"]) if row["days_late"] else None
        if stages and row["dispatch_stage"] not in (
            "KNITTING",
            "ASSEMBLY",
            "WASHING",
            "PACKING",
        ):
            raise ValueError("无效 dispatch_stage")
    return rows


def get_order(order_id: str, stages: bool = False) -> dict:
    for row in get_orders(stages):
        if row["order_id"] == order_id:
            return row
    raise LookupError(f"未找到订单：{order_id}")


def get_workshops(stages: bool = False) -> list[dict]:
    rows = _read("workshops_stages.csv" if stages else "workshops.csv")
    _unique(rows, "workshop_id")
    for row in rows:
        for field in ("capacity_pieces_per_day", "pickup_lead_days"):
            row[field] = int(row[field])
        for field in ("defect_rate", "cost_per_piece", "current_queue_days"):
            row[field] = float(row[field])
            if not math.isfinite(row[field]) or row[field] < 0:
                raise ValueError(f"无效 {field}")
        row["max_batch_pieces"] = (
            int(row["max_batch_pieces"]) if row["max_batch_pieces"] else None
        )
        if (
            row["capacity_pieces_per_day"] <= 0
            or row["pickup_lead_days"] < 0
            or row["defect_rate"] > 1
        ):
            raise ValueError("工坊产能、运输或缺陷率无效")
        if row["status"] not in ("ACTIVE", "SUSPENDED"):
            raise ValueError("未知工坊状态")
    return rows


def get_requests() -> list[dict]:
    rows = []
    for line in (
        (DATA / "dispatch_requests.txt").read_text(encoding="utf-8").splitlines()
    ):
        match = re.fullmatch(r"(R\d{2}) \[([\d:]+)\] ([^:]+): (.+)", line)
        if match:
            request_id, time, sender, message = match.groups()
            rows.append(
                {
                    "id": request_id,
                    "request_id": request_id,
                    "time": time,
                    "sender": sender,
                    "message": message,
                    "raw": line,
                }
            )
    _unique(rows, "id")
    return rows


def dataset_info() -> dict:
    files = sorted(DATA.glob("*")) + [ROOT / "harness/simulate.py"]
    hashes = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in files
        if p.is_file()
    }
    manifest_file = ROOT / "docs/source/manifest.json"
    original = (
        json.loads(manifest_file.read_text())["files"] if manifest_file.exists() else {}
    )
    mismatches = [p for p, digest in original.items() if hashes.get(p) != digest]
    return {
        "version": "Track 2 v3 · September 2026",
        "reference_date": CHAT_REFERENCE_DATE.isoformat(),
        "simulation_epoch": SIMULATION_EPOCH.isoformat(),
        "orders": len(get_orders()),
        "workshops": len(get_workshops()),
        "requests": len(get_requests()),
        "order_count": len(get_orders()),
        "workshop_count": len(get_workshops()),
        "request_count": len(get_requests()),
        "hashes": hashes,
        "source_verified": bool(original) and not mismatches,
        "mismatches": mismatches,
        "source": "官方 data/*.csv 与 harness/simulate.py（只读）",
    }
