# 安装与部署方案

## 方案 A：本机直接运行（已实测，推荐）

适合毕业项目演示、单人调度与开发。本地浏览器 → 同源 FastAPI → 官方 CSV / SQLite，无需云服务，默认不向任何模型发送数据。

1. 解压交付包到可写目录，不要只打开单个 HTML。
2. macOS 双击 `启动平台.command`，或终端进入项目根目录运行 `bash scripts/start.sh`。
3. 浏览器打开 http://127.0.0.1:8000。终端保持运行。
4. 打开「系统与设置」检查连接、数据哈希和规则模式。
5. 在收件箱选 R21 分析，再用 R20 验证不可行分支。

第一次安装需要网络下载 Python 包。交付包已有前端生产产物，无需 Node 也能运行。若删除了前端 dist 或从 Git 获取源码，需安装 Node 20.19+ 与 pnpm 11。重建界面：`REBUILD_FRONTEND=1 bash scripts/start.sh`。已启动同一服务时脚本会提示现有地址；修改后端后请停止原服务再启动。

Python 推荐 3.12。Windows 可执行：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-lock.txt
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Windows 启动步骤未在本次 macOS 环境实测。修改端口时，前端生产版保持同源不需改 API 地址：`PORT=8080 bash scripts/start.sh`。

## 方案 B：Docker 单机部署

交付已包含多阶段 Dockerfile 和 Compose。构建阶段使用 Node/pnpm，运行阶段仅 Python 和构建后的网页；非 root 用户运行。官方数据随版本只读使用，SQLite 写入命名卷。容器只发布到宿主机 `127.0.0.1`，不会自动开放到局域网或互联网。

```bash
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8000/api/health
```

`health` 应为 `ok`，`data.source_verified` 应为 `true`。容器健康检查每 30 秒一次。

```bash
docker compose logs --tail=100 dispatch
docker compose restart dispatch
docker compose down
```

`down` 保留审计卷；`down -v` 会删除审计数据，常规停止不要使用。重建镜像会恢复随包交付的评估 JSON；用户重新运行的评估报告位于容器可写层，如要保留先导出。审计数据库独立持久化，不随重建丢失。

本次环境没有 Docker 可执行文件，因此没有虚报镜像已构建或容器健康检查已通过。安装 Docker 后，上述三个验证命令是部署验收步骤。

## 方案 C：自己的远程服务器

推荐先采用**单用户 SSH 隧道**，不必为试用公开服务：

1. 将完整项目放到服务器目录，安装 Docker/Compose。
2. 在服务器执行 `docker compose up --build -d`。
3. 在自己的电脑运行 `ssh -L 8000:127.0.0.1:8000 your-user@your-server`。
4. 保持 SSH 连接，在自己的浏览器打开 http://127.0.0.1:8000。

隧道通过现有 SSH 身份认证访问后台；应用仍为单用户审计空间。原始课程数据可按课程说明发布，但真实业务数据接入前需要另行确定访问权限与保留政策。

### 需要域名和团队使用时

在不改变后台 loopback 绑定的前提下，使用你组织现有的 HTTPS/OIDC 认证网关代理到 8000。网关应限制为授权调度员；应用当前所有访问者共享 `local_user` 与审计记录。**本版本没有多用户行级隔离，不应把共享令牌当作独立用户身份。** 若要求每人隔离：增加 authenticated actor/tenant、数据库归属校验、Session Cookie/CSRF、登录/退出与访问审计后再开放。

可选 `APP_ACCESS_TOKEN` 只适合可信网关到后台的额外服务鉴权。网关必须覆盖注入 `X-App-Token`，并在外层完成用户认证；直接设置该变量而不配代理会使浏览器 API 返回 401。不要将此令牌硬编码到前端。

## 模型配置

复制 `.env.example` 为 `.env`。默认留空模型参数，即规则模式。使用自己的兼容服务时填入 `LLM_PROVIDER=openai_compatible`、服务地址、真实模型名及 API Key。Compose 自动读取根目录 `.env` 并仅传入列出的变量。

模型服务须支持 Chat Completions JSON 输出。后端连接超时 5 秒、读写等阶段超时 20 秒；一次调用失败后回退规则，不无限重试。httpx 超时按阶段限制，并非严格的单次总墙钟时间。模型输入包括用户消息和当前澄清上下文；规则模式不发送这些数据。真实模型效果仍需要你配置后重新人工验证。

## 数据备份与恢复

本地 SQLite 路径：`backend/runtime/audit.sqlite3`，可设置 `AUDIT_DB_PATH`。数据库启用 WAL，运行中不要只拷贝主文件。用 SQLite backup API 获取一致备份：

```bash
.venv/bin/python scripts/backup.py --output backups
```

恢复时先停止服务，将备份复制到目标数据库路径，同时清理该目标原来的 `-wal` / `-shm`（仅在已确认停止且备份完整时），再启动检查历史记录。不要覆盖其他数据库。

容器可先用 `docker compose exec dispatch python -c` 配合 sqlite3 backup 把命名卷内数据库备份到 `/app/backend/runtime/backup.sqlite3`，再用 `docker compose cp dispatch:/app/backend/runtime/backup.sqlite3 ./backup.sqlite3` 导出。务必为备份设置与原数据相同的访问权限。

## 升级、回滚与验收

1. 保留上一个交付包/镜像标签和数据库备份。
2. 在新目录安装并运行 `bash scripts/verify.sh`；不得修改官方输入提高评分。
3. 停止旧服务，启动新版本，检查 `/api/health`、R21/R20、多轮 R05、审计记录。
4. 如失败，恢复旧目录/镜像及匹配版本的备份。当前 schema 为简单表结构，未来迁移需独立版本号与回滚方案。

## 日志与常见问题

- 健康检查：`GET /api/health`。流量和平均延迟窗口：`GET /api/metrics`。
- 源哈希不一致：检查 `data` 或 `harness` 是否误改；与 `docs/source/manifest.json` 比对。
- 端口占用：已有平台会提示地址；其他服务占用时改 `PORT`，不要随意结束未知进程。
- 页面显示「前端尚未构建」：运行 `pnpm --dir frontend build`，再刷新。
- 模型不可用：核对 URL、模型名、服务支持和 Key；规则回退信息会出现在工具轨迹。
- API 401：检查是否误设置 `APP_ACCESS_TOKEN`；本地默认应留空。
- 记录未显示：核对 `AUDIT_DB_PATH` 与挂载卷，历史默认最近 100 条。
- 审计数据没有自动删除策略；24 小时仅针对澄清 checkpoint 的有效期，过期会在下次读取时清理。正式运营需制定记录保留周期。
