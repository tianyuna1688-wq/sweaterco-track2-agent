"""Bounded state machine: parse → validate → clarify / tools → explain → audit.

A fixed graph is deliberate: no free-running agent loop, no mutation tool. Pending
checkpoints expire after 24 hours; successful decisions end their constraint scope.
"""

from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
from backend.app.data_access import get_workshops, dataset_info
from backend.app.services.audit import checkpoint, save_result
from backend.app.skills.recommendation import recommend
from .parser import parse_request
from .llm_provider import parse_with_provider
from .prompts import PROMPT_VERSION


def _merge_model(parsed, extracted, message):
    """Schema-checked language extraction, with deterministic guardrails retained."""
    valid_wids = {w["workshop_id"] for w in get_workshops()}
    if any(w not in valid_wids for w in extracted.excluded_workshops) or (
        extracted.preferred_workshop and extracted.preferred_workshop not in valid_wids
    ):
        parsed.ambiguities.append("模型返回了未知工坊，请用登记名称或 W1–W8 重述要求。")
        return parsed
    # Explicit, deterministic fields are authoritative. A provider is not allowed to
    # invent extra restrictions or turn an excluded workshop into a preference.
    additional_exclusions = set(extracted.excluded_workshops) - set(
        parsed.excluded_workshops
    )
    if additional_exclusions and not (
        "excluded_workshops" in parsed.source_fields
        or "preferred_workshop" in parsed.source_fields
    ):
        parsed.ambiguities.append("模型识别了尚未确认的工坊排除条件，请明确工坊编号。")
    if extracted.preferred_workshop and not parsed.preferred_workshop:
        if extracted.preferred_workshop not in parsed.excluded_workshops:
            parsed.ambiguities.append(
                "模型识别了尚未确认的指定工坊，请明确确认后再推荐。"
            )
    # A model may not choose an order from an ambiguous customer name.
    if extracted.order_id and not parsed.order_id:
        parsed.ambiguities.append("模型识别了可能的订单，请明确确认订单编号后再计算。")
    if (
        extracted.pieces
        and parsed.pieces is None
        and "pieces" not in parsed.missing_fields
    ):
        parsed.pieces = extracted.pieces
        parsed.source_fields["pieces"] = "用户消息 · 模型提取"
    if (
        extracted.due_date
        and parsed.due_date is None
        and "due_date" not in parsed.missing_fields
    ):
        parsed.due_date = extracted.due_date
        parsed.source_fields["due_date"] = "用户消息 · 模型提取"
    if (
        extracted.objective
        and parsed.objective == "lateness"
        and "objective" not in parsed.source_fields
    ):
        parsed.objective = extracted.objective
    if "allow_split" not in parsed.source_fields and extracted.allow_split:
        parsed.ambiguities.append("模型识别了尚未确认的拆分意图，请确认是否允许拆单。")
    if extracted.unanswerable_reason and not parsed.unanswerable_reason:
        parsed.unanswerable_reason = (
            "当前数据无法回答该请求中的信息，需补充可靠数据后再处理。"
        )
    if extracted.ambiguity:
        parsed.ambiguities.append(
            "语言解析发现仍有歧义，请明确订单、件数、日期及限制条件。"
        )
    parsed.missing_fields = list(
        dict.fromkeys(parsed.missing_fields + extracted.missing_fields)
    )
    return parsed


def run_chat(
    message: str,
    session_id=None,
    objective="lateness",
    stages=False,
    persist=True,
    use_llm=True,
):
    if not isinstance(message, str) or not message.strip() or len(message) > 8000:
        raise ValueError("消息须为 1 至 8000 字符")
    started = perf_counter()
    session_id = session_id or "session_" + uuid4().hex
    request_id = "req_" + uuid4().hex
    pending = checkpoint(session_id) if persist else None
    trace = []
    last_step_at = started

    def step(name, detail, status="completed"):
        # Interval since the previous trace event (not an individual tool profiler).
        nonlocal last_step_at
        measured_at = perf_counter()
        trace.append(
            {
                "step": name,
                "status": status,
                "detail": detail,
                "duration_ms": round((measured_at - last_step_at) * 1000, 2),
            }
        )
        last_step_at = measured_at

    parsed, options = parse_request(message, objective, pending)
    provider = "rules"
    provider_warning = None
    if use_llm:
        extraction, provider_warning = parse_with_provider(
            message, pending["parsed"] if pending else None
        )
        if extraction:
            parsed = _merge_model(parsed, extraction, message)
            provider = "openai"
    step(
        "parse_request",
        "结构化语言提取完成；规则解析范围受限。"
        if provider == "rules"
        else "结构化模型输出已通过 Schema 校验。",
    )
    if provider_warning:
        step("provider_fallback", provider_warning, "warning")
    step("validate_fields", "订单与工坊编号经过官方数据核对，约束按当前请求保存。")
    recommendation = None
    clarification = None
    if parsed.unanswerable_reason:
        status = "unanswerable"
        answer = parsed.unanswerable_reason
        step("data_boundary", "查询超出当前数据范围；未编造答案。", "stopped")
    elif parsed.missing_fields or parsed.ambiguities:
        status = "clarification"
        names = {"order_id": "订单编号", "pieces": "件数", "due_date": "截止日期"}
        missing = "、".join(names.get(k, k) for k in parsed.missing_fields)
        explanation = " ".join(parsed.ambiguities)
        answer = (
            (f"请补充或确认{missing}。" if missing else "需要先确认请求。")
            + " "
            + explanation
        )
        if options:
            answer += " 下方列出可能匹配的订单。"
        if "due_date" in parsed.missing_fields and parsed.order_id:
            answer += " 原订单交期不会替代尚未确认的新交期。"
        clarification = {
            "fields": parsed.missing_fields,
            "options": [
                {
                    "order_id": o["order_id"],
                    "customer": o["customer"],
                    "product": o["product"],
                    "pieces": o["pieces"],
                    "due_date": o["due_date"],
                }
                for o in options
            ],
            "ambiguities": parsed.ambiguities,
        }
        step("clarify_or_continue", "等待用户确认，未调用推荐工具。", "waiting")
    else:
        step(
            "get_order",
            f"读取 data/orders{'_stages' if stages else ''}.csv · {parsed.order_id}。",
        )
        step("list_workshops", "读取 8 家工坊的当前队列、产能、状态及价格。")
        recommendation = recommend(
            parsed.order_id,
            parsed.pieces,
            parsed.due_date.isoformat(),
            parsed.objective,
            parsed.excluded_workshops,
            parsed.preferred_workshop,
            stages,
            parsed.allow_split,
        )
        eligible = [c for c in recommendation["candidates"] if c["eligible"]]
        step(
            "check_eligibility",
            f"官方资格规则与用户约束过滤后，共 {len(eligible)} 家合格工坊。",
        )
        step(
            "estimate_delivery",
            "Python 工具计算队列 + 生产 + 运输；返回无缺陷、期望和返工情景。",
        )
        chosen = recommendation["recommended"]
        refusal = recommendation["preferred_refusal"]
        if chosen:
            status = "recommended"
            answer = f"建议 {chosen['name']} 承接 {parsed.order_id} 的 {parsed.pieces:,} 件。期望到货 {chosen['expected_date']}，估算加工成本 {chosen['cost']:,.2f}（原始价格单位）。"
            answer += f" 返工情景到货 {chosen['rework_date']}，这是估算而非交付保证。"
        else:
            status = "infeasible"
            earliest = recommendation.get("earliest_candidate")
            if earliest:
                answer = f"当前没有工坊能在期望情景下满足 {parsed.due_date.isoformat()}。最快合法方案是 {earliest['name']}，无缺陷最早 {earliest['optimistic_date']}，期望 {earliest['expected_date']}。可接受延期、评估拆单或升级主管协商。"
            else:
                answer = "当前没有同时满足资格与用户约束的工坊。请调整批量、确认约束或升级主管寻找额外产能。"
        if refusal:
            status = "refused"
            answer = (
                f"不能按要求选择 {refusal['name']}：{'；'.join(refusal['reasons'])}。 "
                + answer
            )
        if recommendation.get("split_plan"):
            split = recommendation["split_plan"]
            answer += f" 双工坊拆分提案期望整批完成 {split['expected_date']}，仅作比较，未执行且不计入官方模拟器评分。"
        step("recommend_workshop", recommendation["ranking_explanation"])
    step("respond", "所有数字来自数据检索或计算工具；未执行真实分配。")
    info = dataset_info()
    result = {
        "session_id": session_id,
        "request_id": request_id,
        "status": status,
        "message": answer.strip(),
        "parsed": parsed.model_dump(mode="json"),
        "recommendation": recommendation,
        "clarification": clarification,
        "trace": trace,
        "provider": provider,
        "provider_warning": provider_warning,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": PROMPT_VERSION,
        "data_version": info["version"],
        "source_verified": info["source_verified"],
        "duration_ms": round((perf_counter() - started) * 1000, 2),
        "executed": False,
        "actor": "local_user",
        "stages": stages,
    }
    if persist:
        step("audit", "已保存请求、约束来源与工具输出；会话澄清状态保留最多 24 小时。")
        save_result(result, message)
    return result
