#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys


TASK_TO_SCRIPT = {
    "monitor": "/app/monitor_wcnr_jq.py",
    "jsbrjq": "/app/0306jsbrjq_monitor.py",
    "zq": "/app/zq_kshddpt_dsjfx_jq.py",
    "multi": "/app/data_scraper_multi.py",
    "dxpt0123": "/app/0123_dxpt_ceshi.py",
}


def build_command(task: str) -> list[str]:
    script = TASK_TO_SCRIPT[task]
    cmd = [sys.executable, script]

    if task == "dxpt0123":
        if (os.environ.get("DXPT_DRY_RUN") or "").strip() in {"1", "true", "TRUE", "yes", "YES"}:
            cmd.append("--dry-run")
        limit = (os.environ.get("DXPT_LIMIT") or "").strip()
        if limit:
            cmd.extend(["--limit", limit])
        log_level = (os.environ.get("DXPT_LOG_LEVEL") or "").strip()
        if log_level:
            cmd.extend(["--log-level", log_level])

    return cmd


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python /app/task_runner.py [monitor|jsbrjq|zq|multi|dxpt0123]", file=sys.stderr)
        return 2

    task = sys.argv[1].strip()
    if task not in TASK_TO_SCRIPT:
        print(f"Unknown task: {task}", file=sys.stderr)
        print("Valid tasks: monitor, jsbrjq, zq, multi, dxpt0123", file=sys.stderr)
        return 2

    command = build_command(task)
    result = subprocess.run(command, check=False)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
