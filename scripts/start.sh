#!/usr/bin/env bash
set -euo pipefail
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"
RUNTIME_DIR="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if [ -d "$RUNTIME_DIR/node/bin" ]; then export PATH="$RUNTIME_DIR/node/bin:$RUNTIME_DIR/bin/fallback:$PATH"; fi
if [ ! -x .venv/bin/python ]; then
  if [ -x "$RUNTIME_DIR/python/bin/python3" ]; then "$RUNTIME_DIR/python/bin/python3" -m venv .venv; else python3 -m venv .venv; fi
fi
if ! .venv/bin/python -c 'import fastapi,uvicorn,httpx,dotenv' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r backend/requirements-lock.txt
fi
if [ ! -f frontend/dist/index.html ] || [ "${REBUILD_FRONTEND:-0}" = "1" ]; then
  if command -v pnpm >/dev/null 2>&1; then
    pnpm --dir frontend install --frozen-lockfile
    pnpm --dir frontend build
  elif command -v corepack >/dev/null 2>&1; then
    corepack pnpm --dir frontend install --frozen-lockfile
    corepack pnpm --dir frontend build
  else
    echo '需要 Node.js 20.19+ 和 pnpm；安装后重新运行本脚本。发行包已附构建产物，无需重建即可启动。'
    exit 1
  fi
fi
DISPATCH_PORT="${PORT:-8000}"
if .venv/bin/python - "$DISPATCH_PORT" <<'PY'
import json,sys,urllib.request
try:
 with urllib.request.urlopen(f'http://127.0.0.1:{sys.argv[1]}/api/health', timeout=2) as response:
  data=json.load(response)
  if data.get('version')=='1.0.0' and data.get('reference_date')=='2026-04-01':sys.exit(0)
except Exception:pass
sys.exit(1)
PY
then
  echo "平台已在运行：http://127.0.0.1:$DISPATCH_PORT"
  exit 0
fi
printf '\nSweaterCo 调度平台：http://127.0.0.1:%s\n按 Ctrl+C 停止服务。\n\n' "$DISPATCH_PORT"
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$DISPATCH_PORT"
