# 交付验收记录

验收日期：2026-10-28（Asia/Shanghai）。交付版本：1.0.0。运行环境：macOS、本地 Python 3.12、React 19 / TypeScript / Vite 生产构建。没有使用真实模型密钥。

## 已执行的检查

|检查|真实结果|
|---|---|
|后端业务、解析、API、模型故障回退与评估器测试|**110 passed**；1 条第三方 AnyIO/Starlette 弃用提示，不影响测试|
|前端组件交互测试|**5 passed**；选择请求、策略/工序传参、多轮会话、网络错误保留草稿、新任务隔离、订单带入|
|TypeScript 与前端生产构建|通过；静态产物已生成|
|Python Ruff（app / tests / evals / scripts）|通过|
|前端 Prettier 格式检查|通过|
|官方文件完整性|7 项 SHA-256 均与复制前一致|
|官方 30 条请求，默认模式|行为 **30/30**、结构化解释核验 **30/30**、硬约束违规 **0**|
|官方 30 条请求，工序扩展|同样 **30/30**，独立报告|
|120 单回放|默认与 stages 分别 9 策略 × normal/shock × 10 seeds；合计 43,200 次批次决策，无非法工坊|
|官方基线 CLI|原样执行，输出保存在 evals/official-baselines-*.txt|
|本地启动脚本|成功启动最新服务；已有服务检测成功；脚本语法通过|
|SQLite backup|运行中成功创建一致备份到临时验收目录|
|交付 ZIP 独立解压验证|81 个文件与发布哈希核对、官方数据校验、生产 HTML、中文 R21 推荐 W5、SQLite 审计写入全部通过；使用已安装的 Python 依赖|
|Compose 文件|YAML 解析通过、loopback 端口/审计卷静态核对；没有执行 Docker|

## 浏览器实际操作

不是只检查 HTTP 返回 200。通过浏览器完成以下交互：

- 工作台读取 120 订单、8 工坊、30 请求。
- R21：按时前提最低成本 → GiantWeave；期望 2026-04-12、成本 1,650；返工 2026-04-14。
- R20：返回不可行，无推荐；展示最早无缺陷 2026-04-17 与替代选项。
- R05：不沿用旧交期，先追问；同会话补充 `2026-04-15` 后对 ORD-066 生成建议。
- 重新加载后，已分析的收件箱状态从 SQLite 历史恢复，包括多轮最终结果。
- 评估页加载真实报告；切换 Shock 后迟交率等指标变化；筛选失败显示无失败项。
- 桌面 1440px 与手机 390px 检查，页面没有整体水平溢出；表格与收件箱可在自身区域横向滚动。
- 浏览器没有记录 JavaScript error。已保存桌面、手机与评估截图于 `docs/screenshots/`。

## 分阶段交付

|阶段|主要文件|验证与结果|
|---|---|---|
|0 勘察|docs/IMPLEMENTATION.md、docs/source/|全文阅读产品规格、课程要求、Primer；确认原始目录与版本|
|1 数据|backend/app/data_access.py|120 / 8 / 30、字段与唯一键、原样哈希|
|2 Skills|backend/app/skills/|边界测试、120×8×2 官方资格一致性、三情景日期|
|3 allocator|backend/app/allocator.py、evals/|五目标、归一化混合、正常与停工多种子回放|
|4 API|backend/app/main.py、schemas.py|成功、校验、拒绝、大小限制、可选服务令牌|
|5 语言理解|backend/app/agent/parser.py、llm_provider.py、prompts.py|双语规则、结构校验、限流/超时/错误降级 mock|
|6 状态与审计|backend/app/agent/graph.py、services/audit.py|澄清恢复、24 小时有效期、请求约束隔离|
|7 界面|frontend/src/|六个页面、实际 API 联调、响应式与组件测试|
|8 Eval|evals/labels.json、run_evaluation.py、latest*.json|逐条行为/解释核验、基线与目标权衡完整报告|
|9 交付|README、Dockerfile、Compose、scripts、docs/DEPLOYMENT.md|本地启动实测、备份、打包、部署步骤与边界|

## 明确的限制

- **未验证真实 LLM**：30/30 是规则解析器在官方集上的结果；标签由工程核验生成，不是外部人工盲评；不能将其泛化为任意自然语言准确率。模型仍需用户自己的账号、Key、模型名与兼容服务。
- **未运行 Docker**：当前机器没有 Docker。仅完成文件、路径、权限和 YAML 静态检查；部署者需执行构建与容器健康检查。
- 当前是本地单用户平台，无多租户身份与数据隔离；远程使用方案优先 SSH 隧道。未声称公开生产 SaaS 已就绪。
- 没有自动实际派单、发消息、更新官方队列；拆单仅供方案比较。
- 工作流为显式有界 Python 状态机，没有声称使用 LangGraph。
- 主策略胜过三个官方基线，但与简单最早交付规则的正常迟交率持平（均约 1.667%）。质量策略有明显长尾延期风险，报告没有隐藏。
