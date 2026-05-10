#!/usr/bin/env python3
"""budget.py — check budget and abort conditions.

Reads .auto-survey/state.json and reports whether the survey should stop.

Exit codes:
  0  continue (no abort condition met)
  10 abort: max_iterations reached
  11 abort: deadline passed
  12 abort: no_progress_streak >= threshold
  13 abort: status already terminal (completed/aborted)

Stdout always prints a single JSON line:
  {"continue": bool, "reason": "...", "code": int}
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import state as state_mod  # noqa: E402


def check(data: dict) -> tuple[bool, str, int]:
    status = data.get("status")
    if status in ("completed", "aborted"):
        return False, f"status={status}", 13

    consumed = data.get("consumed", {})
    budget = data.get("budget", {})

    iters = int(consumed.get("iterations", 0))
    max_iters = int(budget.get("max_iterations", 0) or 0)
    if max_iters and iters >= max_iters:
        return False, f"max_iterations reached ({iters}/{max_iters})", 10

    deadline = budget.get("deadline")
    if deadline:
        try:
            dl = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) >= dl:
                return False, f"deadline passed ({deadline})", 11
        except (ValueError, AttributeError):
            pass  # bad deadline string — ignore

    streak = int(data.get("no_progress_streak", 0))
    threshold = int(data.get("abort_if", {}).get("no_progress_streak", 999))
    if streak >= threshold:
        return False, f"no progress for {streak} phases (threshold {threshold})", 12

    return True, "ok", 0


def main() -> int:
    try:
        data = state_mod.load()
    except FileNotFoundError as e:
        print(json.dumps({"continue": False, "reason": str(e), "code": 14}))
        return 14
    cont, reason, code = check(data)
    print(json.dumps({"continue": cont, "reason": reason, "code": code}))
    return code


if __name__ == "__main__":
    sys.exit(main())
