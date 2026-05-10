#!/usr/bin/env python3
"""state.py — atomic read/write helpers for .auto-survey/state.json.

Used by SKILL.md and the other scripts. CLI usage:

    python3 state.py show              # print state.json (or summary if --summary)
    python3 state.py show --summary
    python3 state.py phase NEW_PHASE   # set state.phase, append a log entry
    python3 state.py log ACTION RESULT # append a log entry without phase change
    python3 state.py mark-progress     # reset no_progress_streak to 0
    python3 state.py mark-no-progress  # ++no_progress_streak
    python3 state.py inc-iteration     # ++iteration, ++consumed.iterations, update updated_at
    python3 state.py set-status STATUS # in_progress | completed | aborted

All writes are atomic (write to .tmp, fsync, rename) and create state.backup.json
holding the previous content. The schema_version field is checked on load.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

SCHEMA_VERSION = 1
STATE_DIR_NAME = ".auto-survey"
STATE_FILE = "state.json"
BACKUP_FILE = "state.backup.json"
MAX_LOG_ENTRIES = 500  # truncate oldest if log grows beyond this


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_dir(cwd: Optional[Path] = None) -> Path:
    cwd = cwd or Path.cwd()
    return cwd / STATE_DIR_NAME


def state_path(cwd: Optional[Path] = None) -> Path:
    return state_dir(cwd) / STATE_FILE


def backup_path(cwd: Optional[Path] = None) -> Path:
    return state_dir(cwd) / BACKUP_FILE


def load(cwd: Optional[Path] = None) -> Dict[str, Any]:
    p = state_path(cwd)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} does not exist. Run `/auto-survey \"topic\"` first."
        )
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    sv = data.get("schema_version")
    if sv != SCHEMA_VERSION:
        raise ValueError(
            f"state.json schema_version {sv!r} != expected {SCHEMA_VERSION}. "
            "Manual migration required."
        )
    return data


def save(data: Dict[str, Any], cwd: Optional[Path] = None) -> None:
    """Atomic write: backup current → write tmp → fsync → rename."""
    sp = state_path(cwd)
    sp.parent.mkdir(parents=True, exist_ok=True)
    bp = backup_path(cwd)

    # Backup existing state.json (best-effort).
    if sp.exists():
        shutil.copy2(sp, bp)

    data["updated_at"] = _now()
    # Truncate log if too long.
    log = data.get("log") or []
    if len(log) > MAX_LOG_ENTRIES:
        data["log"] = log[-MAX_LOG_ENTRIES:]

    fd, tmp = tempfile.mkstemp(prefix=".state-", suffix=".tmp", dir=str(sp.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, sp)
    except Exception:
        # Cleanup tmp on failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def append_log(
    data: Dict[str, Any],
    *,
    phase: Optional[str] = None,
    action: str,
    result: str = "",
) -> None:
    entry = {
        "ts": _now(),
        "phase": phase or data.get("phase", ""),
        "action": action,
        "result": result,
    }
    data.setdefault("log", []).append(entry)


def set_phase(data: Dict[str, Any], new_phase: str, *, reason: str = "") -> None:
    old = data.get("phase")
    data["phase"] = new_phase
    append_log(
        data,
        phase=new_phase,
        action=f"phase_change: {old} -> {new_phase}",
        result=reason,
    )


def inc_iteration(data: Dict[str, Any]) -> None:
    data["iteration"] = int(data.get("iteration", 0)) + 1
    consumed = data.setdefault("consumed", {})
    consumed["iterations"] = int(consumed.get("iterations", 0)) + 1


def set_status(data: Dict[str, Any], status: str) -> None:
    if status not in ("in_progress", "completed", "aborted"):
        raise ValueError(f"invalid status: {status!r}")
    data["status"] = status
    append_log(data, action=f"status: {status}")


def mark_progress(data: Dict[str, Any], *, reason: str = "") -> None:
    data["no_progress_streak"] = 0
    if reason:
        append_log(data, action="progress", result=reason)


def mark_no_progress(data: Dict[str, Any], *, reason: str = "") -> None:
    data["no_progress_streak"] = int(data.get("no_progress_streak", 0)) + 1
    append_log(data, action="no_progress", result=reason)


def summary(data: Dict[str, Any]) -> str:
    """One-screen human summary."""
    papers = data.get("papers", [])
    n_read = sum(1 for p in papers if p.get("read"))
    n_dl = sum(1 for p in papers if p.get("downloaded"))
    kw = data.get("keywords", {})
    consumed = data.get("consumed", {})
    budget = data.get("budget", {})
    drafts = data.get("drafts", [])
    last_log = (data.get("log") or [])[-3:]

    lines = [
        f"topic         : {data.get('topic')}",
        f"slug          : {data.get('topic_slug')}",
        f"status        : {data.get('status')}",
        f"phase         : {data.get('phase')}",
        f"iteration     : {data.get('iteration')} / {budget.get('max_iterations')}",
        f"papers        : {len(papers)} found, {n_dl} downloaded, {n_read} read",
        f"keywords      : {len(kw.get('searched', []))} searched / {len(kw.get('queue', []))} queued",
        f"drafts        : {len(drafts)}",
        f"no_progress   : {data.get('no_progress_streak', 0)} (abort at {data.get('abort_if', {}).get('no_progress_streak')})",
        f"obsidian      : {'yes' if data.get('obsidian', {}).get('configured') else 'no (local fallback)'}",
        f"updated_at    : {data.get('updated_at')}",
        "",
        "recent log:",
    ]
    for e in last_log:
        lines.append(f"  [{e.get('ts','?')[:19]}] {e.get('phase','?')}: {e.get('action','?')} — {e.get('result','')[:60]}")
    return "\n".join(lines)


# CLI ----------------------------------------------------------------------

def _cmd_show(args: argparse.Namespace) -> int:
    data = load()
    if args.summary:
        print(summary(data))
    else:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _cmd_phase(args: argparse.Namespace) -> int:
    data = load()
    set_phase(data, args.new_phase, reason=args.reason or "")
    save(data)
    print(f"phase -> {args.new_phase}")
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    data = load()
    append_log(data, action=args.action, result=args.result or "")
    save(data)
    return 0


def _cmd_mark_progress(_: argparse.Namespace) -> int:
    data = load()
    mark_progress(data, reason="")
    save(data)
    return 0


def _cmd_mark_no_progress(_: argparse.Namespace) -> int:
    data = load()
    mark_no_progress(data, reason="")
    save(data)
    print(f"no_progress_streak={data['no_progress_streak']}")
    return 0


def _cmd_inc_iteration(_: argparse.Namespace) -> int:
    data = load()
    inc_iteration(data)
    save(data)
    print(f"iteration={data['iteration']}")
    return 0


def _cmd_set_status(args: argparse.Namespace) -> int:
    data = load()
    set_status(data, args.status)
    save(data)
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description="auto-survey state helper")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show")
    s.add_argument("--summary", action="store_true")
    s.set_defaults(func=_cmd_show)

    s = sub.add_parser("phase")
    s.add_argument("new_phase")
    s.add_argument("--reason", default="")
    s.set_defaults(func=_cmd_phase)

    s = sub.add_parser("log")
    s.add_argument("action")
    s.add_argument("result", nargs="?", default="")
    s.set_defaults(func=_cmd_log)

    s = sub.add_parser("mark-progress")
    s.set_defaults(func=_cmd_mark_progress)

    s = sub.add_parser("mark-no-progress")
    s.set_defaults(func=_cmd_mark_no_progress)

    s = sub.add_parser("inc-iteration")
    s.set_defaults(func=_cmd_inc_iteration)

    s = sub.add_parser("set-status")
    s.add_argument("status", choices=["in_progress", "completed", "aborted"])
    s.set_defaults(func=_cmd_set_status)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
