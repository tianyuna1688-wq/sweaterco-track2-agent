from .workshop_eligibility import check_workshop_eligibility


def normalize_workshop(value: str, workshops: list[dict]) -> str:
    key = "".join(c for c in value.casefold() if c.isalnum())
    for w in workshops:
        if key in {
            "".join(c for c in w["name"].casefold() if c.isalnum()),
            w["workshop_id"].casefold(),
        }:
            return w["workshop_id"]
    raise ValueError(f"未知工坊：{value}")


def filter_eligible_workshops(
    order: dict, workshops: list[dict], excluded_ids: set[str]
) -> dict:
    accepted, rejected = [], []
    for w in workshops:
        check = check_workshop_eligibility(order, w)
        if w["workshop_id"] in excluded_ids:
            check["eligible"] = False
            check["reasons"].append("用户明确排除该工坊")
        (accepted if check["eligible"] else rejected).append({**w, **check})
    return {"eligible": accepted, "rejected": rejected}
