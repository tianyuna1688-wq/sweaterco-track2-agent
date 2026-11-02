# SweaterCo · 智能外包调度平台

这是可本地运行的 Track 2 完整平台：React / TypeScript 界面、FastAPI 后端、确定性规则与分配策略、可配置模型解析、SQLite 会话与审计、30 条群聊评估及官方 120 单回放。默认规则模式无需 API Key。

原始数据、模拟器均由用户指定的 `track1/track2` 文件夹逐字节复制；没有改写评分规则。源文件哈希见 `docs/source/manifest.json`。

## 现在怎么用

**本机 macOS：双击项目根目录的 `启动平台.command`。** 首次需要安装依赖时会显示安装进度；启动后打开 **http://127.0.0.1:8000**。保持终端窗口开启，按 `Ctrl+C` 停止服务。若系统提示无法打开，直接在终端运行下面的命令，不需要修改系统安全设置。

```bash
bash scripts/start.sh
```

交付 ZIP 内包含已构建的 `frontend/dist`，可以只安装 Python 依赖运行，无需先安装 Node。源代码仓库不跟踪构建目录；从 Git checkout 首次启动则需 Node/pnpm 构建。脚本检测本机 Codex 捆绑运行时，也支持标准 Python/Node 安装，不绑定原作者的绝对路径。

在工作台搜索 **R21** 并点击「分析请求」：平台应推荐 GiantWeave，期望 4 月 12 日、成本 1,650（原始数据无币种），同时显示返工至 4 月 14 日的风险。搜索 **R20**：应明确交期不可行，最早无缺陷日期为 4 月 17 日。**R05** 会追问新的交期；回复 `2026-04-15` 可在原会话继续。

## Docker 启动

安装 Docker Engine / Docker Desktop 与 Compose v2 后，在项目根目录执行：

```bash
docker compose up --build -d
docker compose ps
docker compose logs -f dispatch
```

打开 http://127.0.0.1:8000。停止用 `docker compose down`；不要附加 `-v`，那会删除审计数据卷。

当前电脑未安装 Docker，**容器构建和运行未实测**；Dockerfile、Compose 和本地等价运行流程已提供并静态检查。本地 Python 服务、前端生产构建、实际浏览器交互已验证。完整安装、服务器方案、备份与故障处理见 [部署手册](docs/DEPLOYMENT.md)。

## 手动开发

需要 Python 3.12（推荐）及 Node 20.19+ / pnpm 11。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-lock.txt
corepack enable
corepack prepare pnpm@11.25.0 --activate
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend build
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

前端开发热更新：另一个终端执行 `pnpm --dir frontend dev`，打开 http://127.0.0.1:5173；Vite 将 `/api` 代理给 8000 端口。API 文档在 http://127.0.0.1:8000/docs。

## 模型接入

把 `.env.example` 复制为 `.env`，填写真实服务的配置，然后重启后端：

```dotenv
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-name
LLM_API_KEY=your-secret
```

此处地址和模型名只是格式示例。适配器要求服务支持 `/chat/completions` 及 JSON 输出模式。密钥仅在服务端，不进入浏览器、审计或 Git。显式 `LLM_PROVIDER=rules` 禁用模型。调用超时/限流/响应不合法时返回明确的规则回退提示。**本交付没有真实模型密钥，因此未验证线上模型效果；已测异常回退路径。** 规则解析有范围限制，陌生表达可能需要重述或补充。

## 页面与能力

- **调度工作台**：原始 30 条收件箱、中英输入、缺失信息追问、约束与目标、候选比较、交期情景、导出建议。
- **订单中心 / 合作工坊**：真实数据查询、过滤、排序、订单带入分析；已完成订单不建议再派单。
- **决策记录**：SQLite 持久记录原文、解析、来源、工具轨迹；待补充任务可继续。
- **评估实验室**：30 条行为和解释分开评分，正常 / Shock、9 策略、10 seeds，支持重新运行及 JSON 导出。
- **系统与设置**：模型就绪状态、健康检查、数据完整性和 API 文档。

平台仅生成建议与审计；不会实际给工坊下单，也不会修改原始 CSV。拆单是计算提案，不计入官方单工坊模拟器成绩。

## 验证与复现

```bash
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m evals.run_evaluation
.venv/bin/python -m evals.run_evaluation --stages
.venv/bin/python harness/simulate.py
.venv/bin/python harness/simulate.py --shock --seeds 10
pnpm --dir frontend test
pnpm --dir frontend build
```

也可执行 `bash scripts/verify.sh`。真实最终计数及浏览器验收见 [验收记录](docs/ACCEPTANCE.md)，策略比较见 [评估报告](docs/EVALUATION.md)。默认模式主策略正常迟交率 1.667%，Shock 1.917%；正常场景与简单最早完成策略迟交率持平，不能声称全面领先。质量目标会牺牲周转与迟交，应查看指标后选择。

## 重要业务口径

1. 聊天业务日固定 **2026-04-01**，不使用电脑当天日期替换。
2. 官方回放起点 **2026-01-01**；厂内 `status/current_stage/completed_date` 不参与回放。
3. 官方工坊按 **7 天/周** 工作；Primer 的厂内 6 天工作制不套用到模拟器。
4. 默认每批一家工坊；工序扩展需显式开启，并与其专属基线比较。
5. 官方 `round` 日期与保守 `ceil` 字段分开，期望日期不是承诺。
6. 价格没有声明币种，不擅自标为人民币或美元。

## 结构

```text
frontend/                 React 界面、组件测试、锁文件
backend/app/              API、Schema、数据访问、规则、工具、工作流、审计
backend/tests/            业务 / API / 语言理解 / 回归测试
data/                     官方原始 CSV、群聊、数据字典
harness/simulate.py        官方模拟器（未修改）
evals/                    独立标注、评估器、默认与工序报告
docs/                     架构、工具规格、评估、验收、部署
scripts/                  本地启动、验证、SQLite 安全备份
Dockerfile                前端构建 + Python 运行的多阶段镜像
docker-compose.yml        本地容器、审计持久卷、健康检查
```

当前交付是**本地单用户平台**，不是已完成多租户权限系统的 SaaS。远程访问优先使用 SSH 隧道；若要多人使用，需接入认证网关与身份隔离，具体边界见部署手册。
