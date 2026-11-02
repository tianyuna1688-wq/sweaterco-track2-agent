"""Small typed allowlist. Tools return authoritative rows/calculations, never execute orders."""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from backend.app.data_access import get_order, get_workshops
from backend.app.schemas import RecommendationRequest
from backend.app.skills.recommendation import recommend, overload_probe
from backend.app.skills.workshop_eligibility import check_workshop_eligibility
from backend.app.skills.delivery_estimation import estimate_delivery


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str = Field(pattern=r"^ORD-\d{3}$")
    stages: bool = False


class WorkshopInput(OrderInput):
    workshop_id: str = Field(pattern=r"^W[1-8]$")


class ListInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["TOPS", "ACCESSORIES"] | None = None
    stages: bool = False


class QueueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workshop_id: str = Field(pattern=r"^W[1-8]$")


class OverloadInput(WorkshopInput):
    additional_pieces: int = Field(ge=0, le=1000000)


def _workshop(wid, stages=False):
    return next(w for w in get_workshops(stages) if w["workshop_id"] == wid)


def call_tool(name, arguments):
    if name not in REGISTRY:
        raise ValueError("工具不在允许列表中")
    spec = REGISTRY[name]
    args = spec["model"].model_validate(arguments)
    return spec["function"](args)


def _recommend(a):
    row = get_order(a.order_id, a.stages)
    if row["status"] != "IN_PROGRESS":
        raise ValueError("该订单已完成，不能作为当前待外包批次推荐；请确认新的订单。")
    return recommend(
        a.order_id,
        a.pieces or row["pieces"],
        a.due_date.isoformat() if a.due_date else row["due_date"],
        a.objective,
        a.excluded_workshops,
        a.preferred_workshop,
        a.stages,
        a.allow_split,
    )


REGISTRY = {
    "get_order": {
        "model": OrderInput,
        "function": lambda a: get_order(a.order_id, a.stages),
        "purpose": "按编号检索订单",
        "non_goals": "不猜测订单、不修改数据",
        "output": "权威订单记录",
    },
    "list_workshops": {
        "model": ListInput,
        "function": lambda a: [
            w
            for w in get_workshops(a.stages)
            if not a.category or a.category in w["makes"].split("+")
        ],
        "purpose": "查询工坊登记档案",
        "non_goals": "不根据名称推断资质",
        "output": "工坊记录列表",
    },
    "check_eligibility": {
        "model": WorkshopInput,
        "function": lambda a: check_workshop_eligibility(
            get_order(a.order_id, a.stages), _workshop(a.workshop_id, a.stages)
        ),
        "purpose": "核对官方资格规则",
        "non_goals": "不把资格等同于按时交货",
        "output": "eligible、reasons",
    },
    "current_queue": {
        "model": QueueInput,
        "function": lambda a: {
            "workshop_id": a.workshop_id,
            "queue_days": _workshop(a.workshop_id)["current_queue_days"],
            "reference_date": "2026-04-01",
        },
        "purpose": "读取聊天快照中的队列",
        "non_goals": "不从模拟回放推算今天队列",
        "output": "queue_days、reference_date",
    },
    "estimate_delivery": {
        "model": WorkshopInput,
        "function": lambda a: estimate_delivery(
            get_order(a.order_id, a.stages), _workshop(a.workshop_id, a.stages)
        ),
        "purpose": "计算三种交期情景与成本",
        "non_goals": "不保证交付、不更新队列",
        "output": "optimistic_date、expected_date、rework_date、cost",
    },
    "overload_probe": {
        "model": OverloadInput,
        "function": lambda a: overload_probe(
            a.order_id, a.workshop_id, a.additional_pieces, a.stages
        ),
        "purpose": "比较新增负载前后的交期",
        "non_goals": "假设探针，不向工坊下单",
        "output": "before、after、added_queue_days",
    },
    "recommend_workshop": {
        "model": RecommendationRequest,
        "function": _recommend,
        "purpose": "组合资格、交期与目标生成建议",
        "non_goals": "不执行分配或绕过硬规则",
        "output": "候选、推荐、拒绝原因与风险",
    },
}


def tool_specs():
    return [
        {
            "name": name,
            "input_schema": spec["model"].model_json_schema(),
            "output": spec["output"],
            "purpose": spec["purpose"],
            "non_goals": spec["non_goals"],
            "side_effects": False,
            "failure_modes": ["参数校验失败", "订单或工坊不存在", "源数据校验失败"],
            "permission": "本地单用户，只读",
            "timeout": "纯本地计算；HTTP 请求整体受服务限制",
            "retries": 0,
            "idempotent": True,
        }
        for name, spec in REGISTRY.items()
    ]
