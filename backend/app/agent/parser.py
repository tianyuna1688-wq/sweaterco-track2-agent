"""Conservative bilingual offline parser. Never keyed by inbox request number."""

import re
from datetime import date, timedelta
from backend.app.schemas import ParsedRequest, Constraint
from backend.app.data_access import get_orders, get_workshops

TODAY = date(2026, 4, 1)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
PRODUCTS = {
    "scarf": ["scarf", "scarves", "围巾"],
    "beanie": ["beanie", "beanies", "帽"],
    "cardigan": ["cardigan", "cardigans", "开衫"],
    "vest": ["vest", "vests", "背心"],
    "hoodie": ["hoodie", "hoodies", "卫衣"],
    "polo shirt": ["polo", "polo shirts", "polo shirt"],
    "crewneck sweater": ["crewneck", "sweaters", "圆领", "毛衣"],
}
NEGATIVE = r"(?:nothing\s+new\s+to|keep\s+it\s+away\s+from|away\s+from|do\s+not\s+(?:use|send\s+to)|don.t\s+(?:use|send\s+to)|avoid|exclude|except|not\s+to|no|不要(?:给|用|选|发给)?|排除|避开|不能给|不选|不考虑)"


def sender_and_body(message):
    m = re.match(r"^(?:R\d+\s+\[[\d:]+\]\s*)?([\w ]{1,30}):\s*(.*)$", message, re.S)
    return (m.group(1).strip(), m.group(2)) if m else ("当前用户", message)


def parse_date(text):
    patterns = [
        (r"\b(202[0-9])-([01]?\d)-([0-3]?\d)\b", "iso"),
        (r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)?", "iso"),
        (
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            "en",
        ),
        (r"(\d{1,2})\s*月\s*(\d{1,2})\s*(?:日|号)?", "cn"),
        (r"\b(\d{1,2})/(\d{1,2})\b", "cn"),
    ]
    found = []
    spans = []
    for pattern, kind in patterns:
        for m in re.finditer(pattern, text, re.I):
            if any(m.start() >= a and m.end() <= b for a, b in spans):
                continue
            spans.append(m.span())
            try:
                if kind == "iso":
                    value = date(*map(int, m.groups())).isoformat()
                elif kind == "en":
                    value = date(
                        2026, MONTHS[m.group(1)[:3].lower()], int(m.group(2))
                    ).isoformat()
                else:
                    value = date(2026, int(m.group(1)), int(m.group(2))).isoformat()
                found.append(value)
            except ValueError:
                return None, True
    if len(set(found)) > 1:
        return None, True
    if found:
        return found[0], False
    if re.search(r"后天|day after tomorrow", text, re.I):
        return (TODAY + timedelta(days=2)).isoformat(), False
    if re.search(r"明天|tomorrow", text, re.I):
        return (TODAY + timedelta(days=1)).isoformat(), False
    weekday = re.search(r"(本|这|下)周([一二三四五六日天])", text)
    if weekday:
        number = "一二三四五六日".find(weekday.group(2).replace("天", "日"))
        delta = number - TODAY.weekday() + (7 if weekday.group(1) == "下" else 0)
        return (TODAY + timedelta(days=delta)).isoformat(), False
    weekday = re.search(
        r"\b(this|next)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b",
        text,
        re.I,
    )
    if weekday:
        number = [
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        ].index(weekday.group(2).lower())
        return (
            TODAY
            + timedelta(
                days=number
                - TODAY.weekday()
                + (7 if weekday.group(1).lower() == "next" else 0)
            )
        ).isoformat(), False
    m = re.search(r"(\d+)\s*(?:天内|days?\s+(?:from now|away))", text, re.I)
    if m:
        return (TODAY + timedelta(days=int(m.group(1)))).isoformat(), False
    return None, False


def parse_request(message, objective="lateness", pending=None):
    sender, text = sender_and_body(message)
    lower = text.lower()
    orders = get_orders()
    workshops = get_workshops()
    order_matches = re.findall(
        r"(?:ORD[-\s]?|order\s*#?\s*|订单\s*#?\s*)(\d{1,3})(?!\d)", text, re.I
    )
    explicit_order = f"ORD-{int(order_matches[0]):03d}" if order_matches else None
    same_pending = bool(
        pending
        and (not explicit_order or explicit_order == pending["parsed"].get("order_id"))
    )
    prior = pending["parsed"] if same_pending else {}
    parsed = ParsedRequest(
        order_id=explicit_order or prior.get("order_id"),
        objective=prior.get("objective", objective),
    )
    if prior.get("order_id"):
        parsed.missing_fields = list(prior.get("missing_fields", []))
    if len(set(order_matches)) > 1:
        parsed.ambiguities.append("请求包含多个订单，请逐单分析并确认当前订单编号。")
    parsed.excluded_workshops = list(prior.get("excluded_workshops", []))
    parsed.constraints = [Constraint(**c) for c in prior.get("constraints", [])]
    parsed.preferred_workshop = prior.get("preferred_workshop")
    parsed.allow_split = bool(prior.get("allow_split", False))
    parsed.pieces = prior.get("pieces")
    parsed.due_date = (
        date.fromisoformat(prior["due_date"]) if prior.get("due_date") else None
    )
    parsed.source_fields = dict(prior.get("source_fields", {}))
    if explicit_order:
        parsed.source_fields["order_id"] = "用户消息"

    if re.search(
        r"last october|去年|去年十月|which workshop did we use|以前.*工坊|之前.*哪家|历史分配",
        lower,
    ):
        parsed.unanswerable_reason = (
            "当前数据没有历史外包分配记录，无法确认过去使用的工坊。"
        )
    if re.search(
        r"what price did we quote|报价给|给.*报价|客户报价|销售价|售价|revenue|profit|revenue|销售额",
        lower,
    ):
        parsed.unanswerable_reason = (
            "数据仅含工坊加工单价，不含对客户的销售报价、收入或利润。"
        )
    if re.search(
        r"organic|certified|certification|有机|认证|工人姓名|联系人电话|电话号码", lower
    ):
        parsed.unanswerable_reason = (
            "当前数据不含此项资质、人员或联系方式，不能据此承诺。"
        )

    qty_pattern = r"(?<![\d.\-])(-?\d[\d,]*)\s*(?:件|pcs\b|pieces\b|beanies\b|scarves\b|cardigans\b|vests\b|hoodies\b|polo\s+shirts?\b|crewneck\s+sweaters?\b|sweaters\b)"
    quantities = [
        int(m.group(1).replace(",", "")) for m in re.finditer(qty_pattern, text, re.I)
    ]
    quantities.extend(
        int(m.group(1).replace(",", ""))
        for m in re.finditer(
            r"(?:quantity|qty|数量)\s*[:：=]?\s*(-?\d[\d,]*)(?![\d.])", text, re.I
        )
    )
    invalid_quantity = bool(
        re.search(
            r"\d+\.\d+\s*(?:件|pieces|pcs)|(?:[一二三四五六七八九十百千万]+|\d+[万千])\s*件",
            text,
            re.I,
        )
    )
    if len(set(quantities)) > 1 or invalid_quantity:
        parsed.pieces = None
        parsed.missing_fields.append("pieces")
        parsed.ambiguities.append(
            "数量存在多个值或不是明确的整数格式，请确认本次唯一件数。"
        )
    elif quantities:
        value = quantities[0]
        if not 1 <= value <= 1000000:
            parsed.missing_fields.append("pieces")
            parsed.ambiguities.append("件数必须是 1 至 1,000,000 的整数。")
            parsed.pieces = None
        else:
            parsed.pieces = value
            parsed.source_fields["pieces"] = "用户消息"
            parsed.missing_fields = [f for f in parsed.missing_fields if f != "pieces"]
    due, invalid_date = parse_date(text)
    if due:
        parsed.due_date = date.fromisoformat(due)
        parsed.source_fields["due_date"] = "用户消息（参考日 2026-04-01）"
        parsed.missing_fields = [f for f in parsed.missing_fields if f != "due_date"]
    if invalid_date:
        parsed.due_date = None
        parsed.missing_fields.append("due_date")
        parsed.ambiguities.append("日期无效或包含多个不同日期，请确认唯一截止年月日。")
    if (
        not due
        and not invalid_date
        and re.search(
            r"(?:due|deadline|back by|交期|截止|交货|交付|回来|完成).{0,12}(?:this week|next week|月底|本周|下周|周末|待定)|(?:本周|下周|周末|月底).{0,8}(?:前|内|交|完成)",
            lower,
        )
    ):
        parsed.due_date = None
        parsed.missing_fields.append("due_date")
    awaiting_date = bool(
        re.search(
            r"will confirm.*date|confirm the new date|date.*(?:pending|follow)|日期.*(?:待定|再确认|稍后)|交期.*(?:待定|再确认)|截止.*待定",
            lower,
        )
    )
    if awaiting_date and not due:
        parsed.due_date = None
        parsed.missing_fields.append("due_date")
    if re.search(r"lateness|交期优先|按期优先|减少延误", lower):
        parsed.objective = "lateness"
        parsed.source_fields["objective"] = "用户消息"
    elif re.search(r"cheapest|最便宜|最低成本|最省钱", lower):
        parsed.objective = "cheapest_on_time"
        parsed.source_fields["objective"] = "用户消息"
    elif re.search(
        r"lowest defect|defect rate.*lowest|最低缺陷|最低返工|质量优先|最.*质量|质量最好",
        lower,
    ):
        parsed.objective = "quality"
        parsed.source_fields["objective"] = "用户消息"
    elif re.search(r"fastest|quickest|最快|尽快", lower):
        parsed.objective = "fastest"
        parsed.source_fields["objective"] = "用户消息"
    split_mentioned = bool(re.search(r"\bsplit\b|拆单|拆分|分给两", lower))
    if split_mentioned:
        parsed.source_fields["allow_split"] = "用户消息"
        parsed.allow_split = not bool(
            re.search(
                r"(?:do not|don.t|never|no)\s+split|(?:不要|不能|禁止|不允许)\s*拆",
                lower,
            )
        )
    negative_clauses = [
        m.group(1)
        for m in re.finditer(NEGATIVE + r"\s*([^。.!?;；]+)", text, re.I)
        if not m.group(1).lower().startswith("special requirements")
    ]
    exclusion_ids = {
        w["workshop_id"]
        for w in workshops
        if any(
            re.search(
                re.escape(w["name"])
                + r"|(?<![A-Za-z0-9])"
                + w["workshop_id"]
                + r"(?!\d)",
                clause,
                re.I,
            )
            for clause in negative_clauses
        )
    }
    source = (
        "Boss"
        if re.search(r"Boss\s+(?:says|wants)|老板(?:说|要求)", text, re.I)
        else sender
    )
    for w in workshops:
        patterns = [
            re.escape(w["name"]),
            r"(?<![A-Za-z0-9])" + w["workshop_id"] + r"(?![0-9])",
        ]
        name_pat = "(?:" + "|".join(patterns) + ")"
        if not re.search(name_pat, text, re.I):
            continue
        wid = w["workshop_id"]
        if (
            wid in exclusion_ids
            or re.search(NEGATIVE + r"\s*" + name_pat, text, re.I)
            or re.search(name_pat + r".{0,6}(?:不能用|不要用|不要选|排除)", text, re.I)
        ):
            parsed.source_fields["excluded_workshops"] = "用户消息"
            if wid not in parsed.excluded_workshops:
                parsed.excluded_workshops.append(wid)
            parsed.constraints.append(
                Constraint(type="exclude", value=wid, source=source)
            )
            if parsed.preferred_workshop == wid:
                parsed.preferred_workshop = None
        elif re.search(r"(?:取消排除|恢复|allow|include)\s*" + name_pat, text, re.I):
            parsed.excluded_workshops = [
                i for i in parsed.excluded_workshops if i != wid
            ]
            parsed.constraints = [
                c
                for c in parsed.constraints
                if not (c.type == "exclude" and c.value == wid)
            ]
        else:
            parsed.source_fields["preferred_workshop"] = "用户消息"
            parsed.preferred_workshop = wid
            parsed.constraints.append(
                Constraint(type="prefer", value=wid, source=source)
            )
    if parsed.objective != objective and not any(
        c.type == "objective" and c.value == parsed.objective
        for c in parsed.constraints
    ):
        parsed.constraints.append(
            Constraint(type="objective", value=parsed.objective, source=source)
        )
    if split_mentioned:
        parsed.constraints = [c for c in parsed.constraints if c.type != "allow_split"]
        parsed.constraints.append(
            Constraint(
                type="allow_split", value=str(parsed.allow_split).lower(), source=source
            )
        )
    explicit_target = re.search(
        r"(?:send.{0,60}?\bto|give.{0,60}?\bto|use|指定|发给|交给)\s+([A-Za-z][A-Za-z ]{1,30})",
        text,
        re.I,
    )
    if explicit_target:
        target = explicit_target.group(1).strip().lower()
        if target not in ("them", "whoever is quickest") and not any(
            w["name"].lower() in target or w["workshop_id"].lower() == target.split()[0]
            for w in workshops
        ):
            parsed.ambiguities.append(
                "指定的工坊未在登记表中，请确认工坊名称或 W1–W8 编号。"
            )
    # A numeric cost cap or an unrecognised negative workshop constraint must not be dropped.
    if re.search(
        r"(?:budget|cost|price|预算|成本|单价).{0,15}(?:under|below|less than|不超过|低于|小于|<=|≤)\s*\d|(?:under|below|less than)\s*[$¥]\s*\d",
        lower,
    ):
        parsed.ambiguities.append(
            "当前策略不支持金额上限硬约束，请确认预算口径后再分析；本次未生成推荐。"
        )
    for m in re.finditer(NEGATIVE + r"\s+([A-Za-z][A-Za-z ]{1,30})", text, re.I):
        target = m.group(1).strip().lower()
        if target.startswith(("special requirements", "matter")):
            continue
        if not any(
            w["name"].lower() in target or w["workshop_id"].lower() == target.split()[0]
            for w in workshops
        ):
            parsed.ambiguities.append(
                "未识别请求中的排除条件，请使用工坊名称或 W1–W8 编号。"
            )
    if re.search(
        r"不(?:要|能)(?:给|用|选|发给)?\s*[\u4e00-\u9fff]{2,8}(?:工坊|工厂)", text
    ):
        parsed.ambiguities.append("请用工坊登记名称或 W1–W8 指明排除对象。")

    order = next((o for o in orders if o["order_id"] == parsed.order_id), None)
    if parsed.order_id and not order:
        parsed.unanswerable_reason = (
            f"未在官方订单数据中找到 {parsed.order_id}，无法查询或分配；请核对编号。"
        )
    if order:
        if order["status"] != "IN_PROGRESS":
            parsed.ambiguities.append(
                "该订单在 4 月 1 日快照中已完成。如需新批次，请确认新的订单、数量和截止日期。"
            )
        if parsed.pieces is None and "pieces" not in parsed.missing_fields:
            parsed.pieces = int(order["pieces"])
            parsed.source_fields["pieces"] = "orders.csv · " + order["order_id"]
        if parsed.due_date is None and "due_date" not in parsed.missing_fields:
            parsed.due_date = date.fromisoformat(order["due_date"])
            parsed.source_fields["due_date"] = "orders.csv · " + order["order_id"]
    else:
        if not parsed.order_id:
            parsed.missing_fields.append("order_id")
        if parsed.pieces is None:
            parsed.missing_fields.append("pieces")
        if parsed.due_date is None:
            parsed.missing_fields.append("due_date")
    candidates = []
    if not parsed.order_id:
        candidates = [o for o in orders if o["status"] == "IN_PROGRESS"]
        customers = [c for c in {o["customer"] for o in orders} if c.lower() in lower]
        if customers:
            candidates = [o for o in candidates if o["customer"] in customers]
        products = [
            key
            for key, terms in PRODUCTS.items()
            if any(term in lower for term in terms)
        ]
        if products:
            candidates = [o for o in candidates if o["product"].lower() in products]
        if not customers and not products:
            candidates = []
        if len(candidates) > 1:
            parsed.ambiguities.append(
                f"共有 {len(candidates)} 个进行中订单可能匹配，请选择订单编号。"
            )
        elif len(candidates) == 1:
            parsed.ambiguities.append("请确认是否指该订单，系统不会自动选择。")
    parsed.missing_fields = list(dict.fromkeys(parsed.missing_fields))
    parsed.ambiguities = list(dict.fromkeys(parsed.ambiguities))
    return parsed, candidates
