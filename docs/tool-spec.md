# 工具规格与业务能力

实现入口是 `backend/app/tools.py` 的 `REGISTRY` / `call_tool()`。工具只读，返回 JSON 可序列化记录，不下发订单、不修改 CSV、不发送外部消息。输入由 Pydantic 校验，额外字段拒绝；完整机器可读输入 Schema 由 `tool_specs()` 提供。

聊天工作流使用与注册工具相同的 Python Skills。工具集合是固定允许列表，没有任意 SQL、文件访问或代码执行工具；模型不决定资格、价格或交期。

## 七个工具

| 工具 | 输入 | 输出与要回答的问题 | 非目标 | 主要失败模式 |
| --- | --- | --- | --- | --- |
| `get_order` | `order_id: ORD-001…ORD-120`；`stages: bool=false` | 单条订单记录：客户、产品、类别、整数件数、日期、厂内状态；启用扩展时带 `dispatch_stage`。回答“这个编号是什么订单？” | 不根据客户名称猜选订单，不修改订单 | 编号格式错误、订单不存在、CSV 数据错误 |
| `list_workshops` | 可选 `category: TOPS/ACCESSORIES`；`stages=false` | 工坊记录数组，保留产能、运输、缺陷概率、加工单价、状态、单批上限和队列；可按产品能力筛选 | 不把类别匹配等同于资格，不隐去暂停工坊 | 非法类别或源数据错误 |
| `check_eligibility` | `order_id`、`workshop_id: W1…W8`；`stages=false` | `{eligible: bool, reasons: string[]}`。回答“按当前整单件数，这家工坊可以承接吗？” | 不判断交期，不替用户修改件数，不排序 | 订单不存在、非法工坊编号或数据错误 |
| `current_queue` | `workshop_id: W1…W8` | `{workshop_id, queue_days: number, reference_date: "2026-04-01"}` | 不把模拟回放队列当成当天队列，不声明是实时生产系统 | 非法编号或源数据错误 |
| `estimate_delivery` | `order_id`、`workshop_id`；`stages=false` | 无缺陷、期望、返工三情景的天数和日期，加成本、缺陷概率、延期概率、日期取整说明 | 不保证交付、不更新队列；数值估算本身不等于资格批准，需配合资格工具 | 非法／非有限数值、未知订单、零产能等 |
| `overload_probe` | `order_id`、`workshop_id`；`additional_pieces: int`，范围 0–1,000,000；`stages=false` | `{eligible, added_queue_days, before, after}`；不合格时返回原因和空的 `before/after`。比较新增负载前后交期 | 假设新增工作先于该批次；不修改真实队列、不抽取随机返工 | 非法负载、未知订单、工坊不合格 |
| `recommend_workshop` | `order_id`；可选 `pieces`、`due_date`、`objective`、`excluded_workshops`、`preferred_workshop`、`stages`、`allow_split` | 所有 8 家工坊的估算／拒绝原因，合格候选排名、推荐或不可行结论、最早日期、风险假设、约束、可选拆单提案 | 只做建议；不覆盖硬资格，不把不可能交期包装成分配成功 | 缺失或非法参数、未知工坊约束、无合格候选、无法按时 |

`recommend_workshop` 的结构化工具调用可省略件数／日期，届时使用源订单字段；聊天入口另有缺失信息策略，用户明确说“新日期待确认”时不会使用旧日期代替。两种入口应按用途理解。

API 可选目标为 `lateness`、`quality`、`fairness`、`robustness`、`hybrid`。聊天语言还可表达“最快”和“按时前提下最便宜”，分别映射到内部 `fastest`、`cheapest_on_time`。混合目标的默认权重在 `allocator.DEFAULT_WEIGHTS`；Python `make_allocator()` / `recommend()` 可传自定义权重。

## 推荐输出契约

| 字段 | 类型与含义 |
| --- | --- |
| `feasibility` | `feasible` / `infeasible` / `no_eligible` |
| `recommended` | 候选对象或 `null`；只有期望日期按时的合法候选才能成为推荐 |
| `candidates` | 8 个对象；每个含 `workshop_id`、`name`、`eligible`、`reasons`、`queue_days`、`processing_days`、`lead_days`、`expected_days`、`optimistic_date`、`expected_date`、`rework_date`、`cost`、`defect_rate`、`on_time`；合格者另有 `rank` 和 `score` |
| `score` | 排序元组的 JSON 数组，值越小越优；不是百分制分数。混合目标的展示值与实际排序使用同一组归一化尺度 |
| `earliest_date` / `earliest_candidate` | 所有合法候选中的最早无缺陷日期与候选；无合法候选时为空 |
| `preferred_refusal` | `{workshop_id, name, reasons}` 或空；解释指定工坊为何不能按要求承接 |
| `split_plan` | 两工坊的件数、情景日期和总成本，或空；`status="proposal_only"`，不能视为已执行 |
| `assumptions` / `sources` | 日期口径、数学假设、规则及源行引用 |
| `policy_version` / `executed` | 策略版本；`executed` 恒为 `false` |

所有价格保留数据的原始单位。官方文件没有声明币种，工具不补写人民币或美元。

## 资格与估算规则

资格最终由原样保留的 `harness/simulate.py:eligible_workshops()` 决定：状态为 ACTIVE、类别匹配、件数不超单批上限。启用 `stages` 时，必须覆盖从 `dispatch_stage` 到 PACKING 的每一道工序。用户排除约束在此基础上继续过滤；不能使本来不合格的工坊变合格。

令件数为 `n`、日产能 `c`、排队天数 `q`、运输天数 `l`、缺陷概率 `p`：

```text
基础生产天数 = n / c
无缺陷周转 = q + n/c + l
期望周转 = q + (n/c) × (1 + 0.5p) + l
返工情景周转 = q + 1.5 × n/c + l
加工成本 = n × 每件加工单价
```

官方模拟器工坊每周工作 7 天；运输不进入生产队列。日期使用官方绝对模拟日 `round(day + turnaround)`，包括 Python 的 .5 取偶规则。`conservative_date` 单独按 `ceil(expected_days)` 展示更保守日期，不能拿它替换官方计分。

期望日期按时不表示没有风险：无缺陷／返工日期分别与截止日期比较，延期概率为 `(1-p) × 无缺陷是否延期 + p × 返工是否延期`；期望延期天数同理加权。这是已知数据模型下的两情景计算，不包含未知停工概率。

## 执行边界与验证

- 工具纯本地执行，不重试。模型请求有单独超时和降级流程，模拟器分配器不调用模型。
- 用户输入只进入类型化参数，不能提供新的工坊产能／价格来替换官方数据。
- 拆单只在用户允许时计算，使用两家工坊、整数件数、部分批次资格和上限；两份数量之和等于总量。提案未执行，也未纳入官方模拟器成绩。
- 过载探针新增队列为 `additional_pieces / capacity`，此新增部分按无返工计算，结果明确列出假设。
- 业务单测位于 `backend/tests/test_engine.py`：包括官方资格全组合一致性、哈希、日期边界、非法数值、3 条不可能请求、指定工坊拒绝、排除、拆单、探针、回放复现与主目标基线。用项目 Python 环境运行 `python -m pytest backend/tests/test_engine.py -q`。
- 每次聊天的工具结果、约束提出者、数据版本、流程记录由审计服务保存；工具本身不把外包建议变成实际生产动作。
