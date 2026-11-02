"""Consistent SQLite backup; safe to run while the local desk is active."""

import argparse
import os
import sqlite3
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, default=root / "backups")
args = p.parse_args()
source = Path(os.getenv("AUDIT_DB_PATH", str(root / "backend/runtime/audit.sqlite3")))
if not source.is_file():
    raise SystemExit("No audit database exists yet; analyse a request first.")
args.output.mkdir(parents=True, exist_ok=True)
target = args.output / (
    "audit-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".sqlite3"
)
with sqlite3.connect(source) as src, sqlite3.connect(target) as dest:
    src.backup(dest)
print(target)
