#!/usr/bin/env python3
"""init.py — initialise a new .auto-survey/ workspace in the current directory.

Used by SKILL.md when the user runs `/auto-survey "topic"` for the first time.

Usage:
    python3 init.py "topic" [--max-papers 30] [--max-iterations 30]
                            [--deadline ISO8601] [--no-arxiv-download]
                            [--max-download N] [--obsidian-configured 0|1]

The script:
  1. Slugifies the topic.
  2. Creates ./.auto-survey/{papers,notes,drafts}/.
  3. Loads templates/state.template.json, fills in placeholders, writes state.json.
  4. Prints a JSON summary on stdout for the SKILL to consume.

If state.json already exists, prints the existing summary and exits 0 unless
`--force` is given (in which case it backs up old state first).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# Make state.py importable as a sibling module.
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import state as state_mod  # noqa: E402

TEMPLATE_DIR = SCRIPT_DIR.parent / "templates"
STATE_TEMPLATE = TEMPLATE_DIR / "state.template.json"


def slugify(text: str, max_len: int = 60) -> str:
    """Lowercase ASCII slug. For non-ASCII (CJK etc.) topics, fall back to a
    short stable hash of the *original* text — never of the empty string."""
    original = text
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not text:
        import hashlib
        digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:8]
        text = f"topic-{digest}"
    return text[:max_len].strip("-")


def init_workspace(
    topic: str,
    *,
    max_papers: int = 30,
    max_iterations: int = 30,
    deadline: str | None = None,
    arxiv_download: bool = True,
    arxiv_max_download: int = 5,
    obsidian_configured: bool = False,
    notion_parent: str | None = None,
    force: bool = False,
    slug_override: str | None = None,
) -> dict:
    cwd = Path.cwd()
    sdir = state_mod.state_dir(cwd)
    spath = state_mod.state_path(cwd)

    if spath.exists() and not force:
        existing = state_mod.load(cwd)
        return {
            "status": "exists",
            "state_path": str(spath),
            "topic": existing.get("topic"),
            "phase": existing.get("phase"),
            "summary": state_mod.summary(existing),
        }

    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "papers").mkdir(exist_ok=True)
    (sdir / "notes").mkdir(exist_ok=True)
    (sdir / "drafts").mkdir(exist_ok=True)

    if not STATE_TEMPLATE.exists():
        raise FileNotFoundError(f"template missing: {STATE_TEMPLATE}")

    raw = STATE_TEMPLATE.read_text(encoding="utf-8")
    slug = slug_override or slugify(topic) or "untitled-topic"
    # Validate user-provided slug stays filesystem-safe.
    if slug_override:
        clean = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug_override).strip("-").lower()
        if not clean:
            raise ValueError(f"--slug {slug_override!r} produces empty slug")
        slug = clean[:60]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    raw = (
        raw.replace("__TOPIC__", topic.replace('"', '\\"'))
        .replace("__TOPIC_SLUG__", slug)
        .replace("__NOW__", now)
    )
    data = json.loads(raw)

    # Apply CLI overrides.
    data["config"]["arxiv_download"] = arxiv_download
    data["config"]["arxiv_max_download"] = arxiv_max_download
    data["config"]["max_papers_to_read"] = max_papers
    data["budget"]["max_iterations"] = max_iterations
    data["budget"]["deadline"] = deadline
    data["obsidian"]["configured"] = obsidian_configured
    if notion_parent:
        data["notion"]["configured"] = True
        data["notion"]["parent_page_id"] = notion_parent

    state_mod.append_log(
        data,
        phase="init",
        action="init_workspace",
        result=f"topic={topic} slug={slug}",
    )
    state_mod.save(data, cwd)

    return {
        "status": "created",
        "state_path": str(spath),
        "topic": topic,
        "topic_slug": slug,
        "phase": data["phase"],
        "summary": state_mod.summary(data),
    }


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(description="initialise a .auto-survey workspace")
    p.add_argument("topic", help="research topic / question")
    p.add_argument("--max-papers", type=int, default=30)
    p.add_argument("--max-iterations", type=int, default=30)
    p.add_argument("--deadline", default=None, help="ISO8601 UTC, e.g. 2026-05-10T00:00:00Z")
    p.add_argument("--no-arxiv-download", action="store_true")
    p.add_argument("--max-download", type=int, default=5)
    p.add_argument("--obsidian-configured", type=int, choices=[0, 1], default=0)
    p.add_argument("--notion-parent", default=None,
                   help="Notion parent page ID or URL — enables Notion sync")
    p.add_argument("--slug", default=None,
                   help="Override the auto-generated slug (useful for CJK-only topics)")
    p.add_argument("--force", action="store_true")
    args = p.parse_args(argv)

    result = init_workspace(
        args.topic,
        max_papers=args.max_papers,
        max_iterations=args.max_iterations,
        deadline=args.deadline,
        arxiv_download=not args.no_arxiv_download,
        arxiv_max_download=args.max_download,
        obsidian_configured=bool(args.obsidian_configured),
        notion_parent=args.notion_parent,
        force=args.force,
        slug_override=args.slug,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "summary"}, ensure_ascii=False))
    print("---")
    print(result["summary"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
