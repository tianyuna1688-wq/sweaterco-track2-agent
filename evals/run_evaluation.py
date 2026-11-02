"""Evaluate all official inbox requests and policies without modifying the harness.

Run from the repository root: python -m evals.run_evaluation
This is a deterministic rules-parser evaluation, not a live LLM benchmark.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "evals/latest.json"
TODAY = date(2026, 4, 1)
SEEDS = tuple(range(5105, 5115))
POLICY_LABELS = {
    "lateness": "交期优先",
    "quality": "质量优先",
    "fairness": "分配均衡",
    "robustness": "稳健调度",
    "hybrid": "混合目标",
    "random": "随机基线",
    "greedy_biggest": "最大产能基线",
    "cheapest": "最低价格基线",
    "earliest_finish": "最早交付简单规则",
}


def verify_sources() -> dict:
    manifest = json.loads((ROOT / "docs/source/manifest.json").read_text())
    files = []
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        actual = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
        files.append(
            {
                "path": relative,
                "expected_sha256": expected,
                "actual_sha256": actual,
                "passed": actual == expected,
            }
        )
    return {"passed": all(row["passed"] for row in files), "files": files}


def _rows(name: str) -> dict[str, dict]:
    with (ROOT / "data" / name).open() as stream:
        rows = list(csv.DictReader(stream))
    return {r["order_id" if "order_id" in r else "workshop_id"]: r for r in rows}


def _close(actual: Any, expected: float) -> bool:
    return (
        isinstance(actual, (int, float))
        and not isinstance(actual, bool)
        and math.isclose(actual, expected, rel_tol=0, abs_tol=0.011)
    )


def _candidate_checks(case: dict, response: dict) -> tuple[list[str], int]:
    """Independent raw-CSV oracle. Never call the recommendation implementation."""
    failures: list[str] = []
    violations = 0
    rec = response.get("recommendation") or {}
    oid = case["expected_slots"].get("order_id")
    orders, workshops = _rows("orders.csv"), _rows("workshops.csv")
    if not oid or oid not in orders:
        return failures, violations
    order = orders[oid]
    pieces = case["expected_slots"].get("pieces") or int(order["pieces"])
    due = case["expected_slots"].get("due_date") or order["due_date"]
    if not rec:
        return ["缺少工坊候选及计算证据"], violations
    candidates = rec.get("candidates") or []
    if {c.get("workshop_id") for c in candidates} != set(workshops):
        failures.append("候选证据未覆盖8家工坊")
    eligible_dates: list[str] = []
    for c in candidates:
        wid = c.get("workshop_id")
        if wid not in workshops:
            failures.append(f"未知工坊 {wid}")
            continue
        w = workshops[wid]
        allowed = (
            w["status"] == "ACTIVE"
            and order["category"] in w["makes"].split("+")
            and (not w["max_batch_pieces"] or pieces <= int(w["max_batch_pieces"]))
            and wid not in case["forbidden_workshops"]
        )
        # Preferred-but-ineligible ids are already excluded by the physical rules.
        if c.get("eligible") != allowed:
            failures.append(f"{wid} 资格与源数据/用户约束不一致")
        if not allowed:
            if not c.get("reasons"):
                failures.append(f"{wid} 缺少拒绝依据")
            continue
        queue, capacity = (
            float(w["current_queue_days"]),
            int(w["capacity_pieces_per_day"]),
        )
        lead, defect = int(w["pickup_lead_days"]), float(w["defect_rate"])
        processing = pieces / capacity
        expected = queue + processing * (1 + 0.5 * defect) + lead
        optimistic = (
            TODAY + timedelta(days=round(queue + processing + lead))
        ).isoformat()
        expected_date = (TODAY + timedelta(days=round(expected))).isoformat()
        rework = (
            TODAY + timedelta(days=round(queue + 1.5 * processing + lead))
        ).isoformat()
        expected_fields = {
            "queue_days": queue,
            "processing_days": processing,
            "lead_days": lead,
            "expected_days": expected,
            "cost": pieces * float(w["cost_per_piece"]),
            "defect_rate": defect,
        }
        for field, value in expected_fields.items():
            if not _close(c.get(field), value):
                failures.append(f"{wid}.{field} 与CSV公式不一致")
        for field, value in {
            "optimistic_date": optimistic,
            "expected_date": expected_date,
            "rework_date": rework,
        }.items():
            if c.get(field) != value:
                failures.append(f"{wid}.{field}: 应为{value}，实际{c.get(field)}")
        if c.get("on_time") != (expected_date <= due):
            failures.append(f"{wid} 按时标记与期望日期不一致")
        eligible_dates.append(optimistic)
    selected = rec.get("recommended")
    if selected:
        selected_id = selected.get("workshop_id")
        valid = next(
            (
                c
                for c in candidates
                if c.get("workshop_id") == selected_id and c.get("eligible")
            ),
            None,
        )
        if valid is None or selected_id in case["forbidden_workshops"]:
            violations += 1
            failures.append("推荐违反工坊硬约束")
        if rec.get("feasibility") in ["infeasible", "no_eligible"]:
            failures.append("不可行时仍输出正式推荐")
    if case["feasibility"] == "infeasible":
        if selected:
            failures.append("不可行请求静默分配")
        if rec.get("feasibility") != "infeasible":
            failures.append("未标记交期不可行")
        if eligible_dates and rec.get("earliest_date") != min(eligible_dates):
            failures.append("最早可达日期与独立无缺陷公式不一致")
        if not rec.get("options"):
            failures.append("不可行请求缺少后续选项")
    return failures, violations


def score_case(case: dict, response: dict) -> dict:
    decision: list[str] = []
    explanation: list[str] = []
    if response.get("status") != case["expected_status"]:
        decision.append(
            f"行为应为 {case['expected_status']}，实际 {response.get('status')}"
        )
    parsed = response.get("parsed") or {}
    for key, value in case["expected_slots"].items():
        if value is not None and parsed.get(key) != value:
            decision.append(f"{key} 应为 {value}，实际 {parsed.get(key)}")
    message = response.get("message") or ""
    if not message.strip():
        explanation.append("缺少用户可读解释")
    rec = response.get("recommendation") or {}
    selected = rec.get("recommended")
    hard_violations = 0
    if case["kind"] in ["complete", "constrained", "ineligible", "impossible"]:
        calculation_failures, hard_violations = _candidate_checks(case, response)
        explanation.extend(calculation_failures)
        if hard_violations:
            decision.append("推荐违反工坊硬约束")
        if case["feasibility"] == "feasible" and not selected:
            decision.append("可行请求未给合法推荐/替代工坊")
        if case["feasibility"] == "infeasible" and selected:
            decision.append("不可行请求不应正式分配")
        if not response.get("trace"):
            explanation.append("缺少工具执行轨迹")
        if selected:
            if selected.get("name", "") not in message:
                explanation.append("文字解释未标明推荐工坊")
            if selected.get("expected_date", "") not in message:
                explanation.append("文字解释未标明期望交期")
    else:
        if selected:
            decision.append("追问/无法回答请求不应给推荐")
        if case["expected_status"] == "clarification":
            fields = (response.get("clarification") or {}).get("fields") or []
            for field in case["clarification_fields"]:
                if field not in fields:
                    decision.append(f"未追问 {field}")
            if not any(x in message for x in ["?", "？", "请", "确认", "补充"]):
                explanation.append("缺少清晰的追问文案")
        elif not any(
            x in message
            for x in [
                "没有",
                "无法",
                "不包含",
                "不含",
                "不存在",
                "未找到",
                "未在",
                "未记录",
                "不提供",
            ]
        ):
            explanation.append("未说明数据无法支持结论")
    if case["preferred_workshop"]:
        if parsed.get("preferred_workshop") != case["preferred_workshop"]:
            decision.append("指定工坊提取错误")
        refusal = rec.get("preferred_refusal")
        if not refusal:
            explanation.append("指定工坊拒绝缺少原因")
        wid = case["preferred_workshop"]
        candidate = next(
            (c for c in rec.get("candidates", []) if c.get("workshop_id") == wid), {}
        )
        reason_text = json.dumps(refusal, ensure_ascii=False) + json.dumps(
            candidate.get("reasons", []), ensure_ascii=False
        )
        required = {
            "R08": ["300", "400"],
            "R11": ["SUSPENDED", "暂停"],
            "R14": ["ACCESSORIES", "类别", "配饰"],
            "R24": ["TOPS", "类别", "上装"],
        }[case["id"]]
        if not any(term in reason_text for term in required):
            explanation.append("拒绝理由未体现原始资格冲突")
    constraints = parsed.get("constraints") or []
    for expected in case["constraints"]:
        if expected["type"] == "exclude":
            if expected["value"] not in (parsed.get("excluded_workshops") or []):
                decision.append(f"未提取排除工坊 {expected['value']}")
            matched = [c for c in constraints if c.get("value") == expected["value"]]
            if not any(c.get("source") == expected["source"] for c in matched):
                explanation.append(f"未记录排除约束提出者 {expected['source']}")
        elif expected["type"] == "allow_split":
            if not parsed.get("allow_split"):
                decision.append("未提取允许拆分约束")
            split = rec.get("split_plan")
            if not split:
                explanation.append("用户请求比较拆分，但缺少拆分试算/说明")
            else:
                parts = split.get("parts") or []
                if len(parts) != 2 or len({p.get("workshop_id") for p in parts}) != 2:
                    explanation.append("拆分方案须含两家不同工坊")
                if (
                    sum(p.get("pieces", 0) for p in parts)
                    != case["expected_slots"]["pieces"]
                ):
                    explanation.append("拆分方案件数不守恒")
                shops = _rows("workshops.csv")
                order = _rows("orders.csv")[case["expected_slots"]["order_id"]]
                for part in parts:
                    w = shops.get(part.get("workshop_id"))
                    n = part.get("pieces", 0)
                    if not w or n <= 0:
                        explanation.append("拆分方案工坊或件数非法")
                        continue
                    if (
                        w["status"] != "ACTIVE"
                        or order["category"] not in w["makes"].split("+")
                        or (w["max_batch_pieces"] and n > int(w["max_batch_pieces"]))
                    ):
                        explanation.append("拆分方案违反工坊资格")
                    expected_days = (
                        float(w["current_queue_days"])
                        + n
                        / int(w["capacity_pieces_per_day"])
                        * (1 + 0.5 * float(w["defect_rate"]))
                        + int(w["pickup_lead_days"])
                    )
                    if not _close(
                        part.get("expected_days"), expected_days
                    ) or not _close(part.get("cost"), n * float(w["cost_per_piece"])):
                        explanation.append("拆分方案数字与CSV公式不一致")
                if parts and (
                    not _close(
                        split.get("expected_days"),
                        max(p["expected_days"] for p in parts),
                    )
                    or not _close(split.get("cost"), sum(p["cost"] for p in parts))
                ):
                    explanation.append("拆分方案整批交期或成本聚合错误")
        elif selected:
            eligible = [c for c in rec.get("candidates", []) if c.get("eligible")]
            preference = expected["value"]
            if preference == "fastest" and eligible:
                best = min(float(c["expected_days"]) for c in eligible)
                if not _close(selected.get("expected_days"), best):
                    decision.append("未选择最快期望交期")
            if preference == "cheapest_on_time":
                eligible = [c for c in eligible if c.get("on_time")]
                if not eligible or not _close(
                    selected.get("cost"), min(c["cost"] for c in eligible)
                ):
                    decision.append("未选择可按时交付候选中的最低成本")
            if preference == "quality" and eligible:
                if not _close(
                    selected.get("defect_rate"), min(c["defect_rate"] for c in eligible)
                ):
                    decision.append("未选择最低缺陷率")
    for expected in case["constraints"]:
        values = (
            [expected["value"]] if expected["type"] != "allow_split" else [True, "true"]
        )
        if not any(
            c.get("value") in values and c.get("source") == expected["source"]
            for c in constraints
        ):
            explanation.append(
                f"约束 {expected['value']} 未记录正确提出者 {expected['source']}"
            )
    return {
        "id": case["id"],
        "kind": case["kind"],
        "label": case["label"],
        "message": case["input"],
        "expected_status": case["expected_status"],
        "actual_status": response.get("status"),
        "decision_passed": not decision,
        "explanation_passed": not explanation,
        "passed": not decision and not explanation,
        "failures": decision + explanation,
        "decision_failures": decision,
        "explanation_failures": explanation,
        "hard_constraint_violations": hard_violations,
        "rationale": case["rationale"],
        "response": response,
    }


def evaluate_chat() -> dict:
    from backend.app.agent.graph import run_chat

    labels = json.loads((ROOT / "evals/labels.json").read_text())
    cases = []
    for case in labels["cases"]:
        try:
            response = run_chat(case["input"], persist=False, use_llm=False)
            cases.append(score_case(case, response))
        except Exception as exc:
            cases.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "label": case["label"],
                    "message": case["input"],
                    "expected_status": case["expected_status"],
                    "actual_status": "error",
                    "decision_passed": False,
                    "explanation_passed": False,
                    "passed": False,
                    "failures": [f"{type(exc).__name__}: {exc}"],
                    "hard_constraint_violations": 0,
                    "response": None,
                }
            )
    grouped = defaultdict(list)
    for case in cases:
        grouped[case["kind"]].append(case)
    return {
        "stages": False,
        "total": len(cases),
        "passed": sum(c["passed"] for c in cases),
        "decision_passed": sum(c["decision_passed"] for c in cases),
        "explanation_passed": sum(c["explanation_passed"] for c in cases),
        "hard_constraint_violations": sum(
            c["hard_constraint_violations"] for c in cases
        ),
        "hard_constraint_violation_rate": sum(
            c["hard_constraint_violations"] for c in cases
        )
        / len(cases),
        "label_method": labels["label_method"],
        "explanation_scope": "机械验证结构化计算、结论一致性和必要理由；不等于独立人工评审所有自由文本事实。",
        "by_kind": [
            {
                "kind": k,
                "label": v[0]["label"],
                "total": len(v),
                "passed": sum(c["passed"] for c in v),
            }
            for k, v in grouped.items()
        ],
        "cases": cases,
    }


def evaluate_simulation(stages: bool = False, seeds: tuple[int, ...] = SEEDS) -> dict:
    from backend.app.allocator import (
        make_allocator,
        earliest_finish,
        DEFAULT_WEIGHTS,
        POLICY_VERSION,
    )
    from harness.simulate import Simulator, random_choice, greedy_biggest, cheapest

    if not seeds:
        raise ValueError("至少提供一个seed")
    factories = {
        "lateness": lambda: make_allocator("lateness"),
        "quality": lambda: make_allocator("quality"),
        "hybrid": lambda: make_allocator("hybrid"),
        "fairness": lambda: make_allocator("fairness"),
        "robustness": lambda: make_allocator("robustness"),
        "random": lambda: random_choice,
        "greedy_biggest": lambda: greedy_biggest,
        "cheapest": lambda: cheapest,
        "earliest_finish": lambda: earliest_finish,
    }
    all_runs: dict[str, list] = {}
    seed_allocations = {}
    for scenario, shock in [("normal", False), ("shock", True)]:
        rows = []
        for name, factory in factories.items():
            runs, counts, pieces = [], Counter(), Counter()
            for seed in seeds:
                sim = Simulator(shock=shock, seed=seed, stages=stages)
                # A fresh allocator prevents fair-allocation memory leaking between runs.
                outcomes = sim.run(factory(), name)
                metrics = sim.metrics(outcomes)
                runs.append({"seed": seed, "metrics": metrics})
                counts.update(o["workshop"] for o in outcomes)
                for o in outcomes:
                    pieces[o["workshop"]] += o["pieces"]
                if seed == seeds[0]:
                    seed_allocations[(scenario, name)] = [
                        o["workshop"] for o in outcomes
                    ]
            mean = {
                key: sum(r["metrics"][key] for r in runs) / len(runs)
                for key in runs[0]["metrics"]
            }
            rows.append(
                {
                    "policy": name,
                    "label": POLICY_LABELS[name],
                    "metrics": mean,
                    "allocation_counts": {
                        w: count / len(seeds) for w, count in sorted(counts.items())
                    },
                    "allocated_pieces": {
                        w: count / len(seeds) for w, count in sorted(pieces.items())
                    },
                    "per_seed": runs,
                }
            )
        all_runs[scenario] = rows
    normal = {r["policy"]: r["metrics"] for r in all_runs["normal"]}
    shock = {r["policy"]: r["metrics"] for r in all_runs["shock"]}
    robust = [
        {
            "policy": p,
            "label": POLICY_LABELS[p],
            "late_change": shock[p]["% late"] - normal[p]["% late"],
            "late_days_change": shock[p]["late days"] - normal[p]["late days"],
        }
        for p in factories
    ]
    primary = normal["lateness"]
    beats = {
        p: primary["% late"] < normal[p]["% late"]
        and primary["late days"] < normal[p]["late days"]
        for p in ["random", "greedy_biggest", "cheapest"]
    }
    tradeoffs = [
        f"交期优先策略的正常迟交率为 {primary['% late']:.2f}%，平均迟交 {primary['late days']:.3f} 天。",
        f"最低价格基线成本 {normal['cheapest']['cost']:,.0f}，交期优先成本 {primary['cost']:,.0f}；低价基线仍保有成本优势。",
        f"简单最早交付规则的迟交率为 {normal['earliest_finish']['% late']:.2f}%，平均迟交 {normal['earliest_finish']['late days']:.3f} 天；不能把工具化界面的价值等同于算法优越性。",
        f"质量策略的按件加权缺陷率为 {normal['quality']['% def pcs']:.2f}%，迟交率为 {normal['quality']['% late']:.2f}%（随机基线 {normal['random']['% late']:.2f}%）。",
    ]
    if not all(beats.values()):
        tradeoffs.append(
            "主目标尚未严格同时胜过所有官方基线的两个交期指标；报告保留真实结果。"
        )
    tradeoffs.append(
        f"质量优先平均迟交 {normal['quality']['late days']:.3f} 天，高于随机的 {normal['random']['late days']:.3f} 天；即使满足官方迟交比例守门指标，也存在严重长尾风险。"
    )
    tradeoffs.append(
        f"均衡策略最大工坊份额 {normal['fairness']['max share']:.2f}%，低于随机 {normal['random']['max share']:.2f}%，但周转为 {normal['fairness']['mean days']:.2f} 天，慢于交期优先 {primary['mean days']:.2f} 天。"
    )
    changes = {
        p: sum(
            a != b
            for a, b in zip(
                seed_allocations[("normal", "lateness")],
                seed_allocations[("normal", p)],
            )
        )
        for p in ["quality", "hybrid", "fairness", "robustness"]
    }
    return {
        "seeds": list(seeds),
        "stages": stages,
        "batch_count": 120,
        "primary_objective": "lateness",
        "policy_version": POLICY_VERSION,
        "hybrid_weights": DEFAULT_WEIGHTS,
        "normal": all_runs["normal"],
        "shock": all_runs["shock"],
        "robustness": robust,
        "tradeoffs": tradeoffs,
        "primary_beats_baselines": beats,
        "quality_guardrail_passed": normal["quality"]["% late"]
        <= normal["random"]["% late"],
        "allocation_changes_vs_lateness_first_seed": changes,
        "assumptions": [
            "未修改官方harness；每批只选择一家工坊。",
            "回放起点2026-01-01；自然日；不读取厂内完成状态。",
            "shock为第30至44天停工；分配器只能观察队列，未收到关闭目标。",
            "每个seed、策略、场景独立初始化；表中每项为各seed的指标均值，不是混合订单后重算。",
        ],
    }


def load_report() -> dict:
    if REPORT_PATH.is_file():
        return json.loads(REPORT_PATH.read_text())
    return {
        "status": "not_run",
        "message": "尚未运行评估，请运行 python -m evals.run_evaluation。",
    }


def evaluate_all(save: bool = True, stages: bool = False) -> dict:
    integrity = verify_sources()
    if not integrity["passed"]:
        raise ValueError("官方数据或模拟器与保存的源哈希不一致，请先核查")
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "rules",
        "live_llm_verified": False,
        "source_integrity": integrity,
        "chat": evaluate_chat(),
        "simulation": evaluate_simulation(stages=stages),
        "versions": {
            "labels": "1.0",
            "harness": "v3",
            "chat_reference_date": TODAY.isoformat(),
            "source_sha256": {
                str(path.relative_to(ROOT)): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted((ROOT / "backend/app").rglob("*.py"))
            },
        },
        "limitations": [
            "30条是已知官方测试集，不是独立的泛化测试。",
            "当前分数评估规则解析器；真实LLM需配置密钥后另测。",
            "标注由实现期独立阅读源文件编写，未经过外部人工盲评。",
        ],
    }
    if save:
        target = ROOT / "evals/latest-stages.json" if stages else REPORT_PATH
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(target)
    return report


def run_evaluation() -> dict:
    return evaluate_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stages",
        action="store_true",
        help="Separately report the optional stage-extension simulation",
    )
    args = parser.parse_args()
    report = evaluate_all(stages=args.stages)
    print(
        json.dumps(
            {
                "chat": {
                    k: report["chat"][k]
                    for k in [
                        "total",
                        "passed",
                        "decision_passed",
                        "explanation_passed",
                        "hard_constraint_violations",
                    ]
                },
                "primary_beats_baselines": report["simulation"][
                    "primary_beats_baselines"
                ],
                "source_integrity": report["source_integrity"]["passed"],
                "report": str(
                    ROOT / "evals/latest-stages.json" if args.stages else REPORT_PATH
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
