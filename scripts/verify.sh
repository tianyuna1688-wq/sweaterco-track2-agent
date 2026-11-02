#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
RUNTIME_DIR="${HOME}/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if [ -d "$RUNTIME_DIR/node/bin" ]; then export PATH="$RUNTIME_DIR/node/bin:$RUNTIME_DIR/bin/fallback:$PATH"; fi
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m evals.run_evaluation
pnpm --dir frontend test
pnpm --dir frontend build
