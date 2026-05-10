#!/usr/bin/env python3
"""obsidian_io.py — write paper notes / survey reports to disk.

This script does NOT call the Obsidian MCP directly (Python has no access to
MCP tools — those live in the Claude harness). Instead it:

  1. Renders a markdown file from a template in templates/.
  2. Writes it to the local fallback path under .auto-survey/notes/ or drafts/.
  3. Prints JSON describing what should *also* be written to Obsidian, so that
     SKILL.md (running in Claude) can call the appropriate `mcp__obsidian*`
     tool with the rendered content.

This split keeps file-rendering logic deterministic and unit-testable while
delegating the MCP write to Claude (where the tool lives).

CLI:
    python3 obsidian_io.py render-note --topic-slug X --paper-id Y --paper-json paper.json
    python3 obsidian_io.py render-table --state state.json
    python3 obsidian_io.py render-survey --state state.json --draft drafts/v3.md

Each prints JSON: {"local_path": "...", "obsidian_path": "...", "content": "..."}.
The "content" field is included so SKILL.md does not need to re-read the file
just to forward it to Obsidian.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import state as state_mod  # noqa: E402

TEMPLATE_DIR = SCRIPT_DIR.parent / "templates"
NOTE_TEMPLATE = TEMPLATE_DIR / "paper_note.template.md"
TABLE_TEMPLATE = TEMPLATE_DIR / "paper_table.template.md"
SURVEY_TEMPLATE = TEMPLATE_DIR / "final_report.template.md"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(s: str, max_len: int = 60) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return (s or "untitled")[:max_len]


def _read_template(p: Path) -> str:
    if not p.exists():
        raise FileNotFoundError(f"template missing: {p}")
    return p.read_text(encoding="utf-8")


def render_note(topic_slug: str, paper: dict[str, Any], topic: str) -> dict:
    raw = _read_template(NOTE_TEMPLATE)
    title = paper.get("title", "")
    paper_slug = _slug(title) if title else paper.get("id", "paper").replace(":", "-")
    authors_str = ", ".join(f'"{a}"' for a in paper.get("authors", []))
    bibtex = paper.get("bibtex") or _fallback_bibtex(paper)

    out = (
        raw.replace("__TITLE__", title.replace('"', "'"))
        .replace("__AUTHORS__", authors_str)
        .replace("__YEAR__", str(paper.get("year", "")))
        .replace("__VENUE__", paper.get("venue", ""))
        .replace("__ARXIV_ID__", paper.get("arxiv_id", paper.get("id", "")))
        .replace("__URL__", paper.get("url", ""))
        .replace("__RELEVANCE__", str(paper.get("relevance", 0)))
        .replace("__TOPIC_SLUG__", topic_slug)
        .replace("__TOPIC__", topic.replace('"', "'"))
        .replace("__READ_AT__", _now())
        .replace("__SOURCE__", paper.get("source", "unknown"))
        .replace("__BIBTEX__", bibtex)
    )

    cwd = Path.cwd()
    local_dir = cwd / ".auto-survey" / "notes"
    local_dir.mkdir(parents=True, exist_ok=True)
    local_path = local_dir / f"{paper_slug}.md"
    local_path.write_text(out, encoding="utf-8")

    obsidian_path = f"Research/{topic_slug}/{paper_slug}.md"
    return {
        "local_path": str(local_path),
        "obsidian_path": obsidian_path,
        "paper_slug": paper_slug,
        "content": out,
    }


def render_table(state_data: dict) -> dict:
    raw = _read_template(TABLE_TEMPLATE)
    topic = state_data.get("topic", "")
    slug = state_data.get("topic_slug", "")
    papers = state_data.get("papers", [])

    rows = []
    top_picks = []
    for i, p in enumerate(papers, 1):
        note_link = f"[[{_slug(p.get('title',''))}]]" if p.get("read") else "—"
        rows.append(
            f"| {i} | {p.get('year','')} | {p.get('title','')[:60]} | {p.get('venue','')} | "
            f"{p.get('method_oneliner','—')} | {p.get('key_result','—')[:30]} | "
            f"{p.get('relevance','?')} | {p.get('source','')} | {note_link} |"
        )
        if p.get("relevance", 0) >= 4:
            top_picks.append(f"- [[{_slug(p.get('title',''))}]] — {p.get('title','')}")

    n_arxiv = sum(1 for p in papers if p.get("source") == "arxiv")
    n_web = sum(1 for p in papers if p.get("source") == "web")
    n_zotero = sum(1 for p in papers if p.get("source") == "zotero")
    n_local = sum(1 for p in papers if p.get("source") == "local")

    out = (
        raw.replace("__TOPIC__", topic.replace('"', "'"))
        .replace("__TOPIC_SLUG__", slug)
        .replace("__NOW__", _now())
        .replace("__TOTAL__", str(len(papers)))
        .replace("__READ__", str(sum(1 for p in papers if p.get("read"))))
        .replace("__N_ARXIV__", str(n_arxiv))
        .replace("__N_WEB__", str(n_web))
        .replace("__N_ZOTERO__", str(n_zotero))
        .replace("__N_LOCAL__", str(n_local))
        .replace("__ROWS__", "\n".join(rows) if rows else "| — | — | (no papers yet) | — | — | — | — | — | — |")
        .replace("__TOP_PICKS__", "\n".join(top_picks) if top_picks else "_none yet_")
    )

    cwd = Path.cwd()
    local_path = cwd / ".auto-survey" / "paper_table.md"
    local_path.write_text(out, encoding="utf-8")
    obsidian_path = f"Research/{slug}/_papers.md"
    return {
        "local_path": str(local_path),
        "obsidian_path": obsidian_path,
        "content": out,
    }


def render_survey(state_data: dict, draft_body: str = "") -> dict:
    raw = _read_template(SURVEY_TEMPLATE)
    topic = state_data.get("topic", "")
    slug = state_data.get("topic_slug", "")
    papers = state_data.get("papers", [])
    sources = state_data.get("config", {}).get("sources", [])
    keywords = state_data.get("keywords", {}).get("searched", [])
    n_read = sum(1 for p in papers if p.get("read"))
    open_qs = state_data.get("open_questions", [])
    open_qs_md = (
        "\n".join(f"- {q}" for q in open_qs)
        if open_qs
        else "_None recorded yet — run gap_analysis to populate._"
    )

    body = draft_body.strip() if draft_body and draft_body.strip() else (
        "_No synthesis draft yet. Run the `synthesis` phase to generate one._"
    )

    out = (
        raw.replace("__TOPIC_SLUG__", slug)
        .replace("__TOPIC__", topic.replace('"', "'"))
        .replace("__NOW__", _now())
        .replace("__STATUS__", state_data.get("status", "?"))
        .replace("__ITERATIONS__", str(state_data.get("iteration", 0)))
        .replace("__TOTAL__", str(len(papers)))
        .replace("__READ__", str(n_read))
        .replace("__SOURCES__", ", ".join(sources) if sources else "(none)")
        .replace("__KEYWORDS__", ", ".join(keywords) if keywords else "_(none)_")
        .replace("__OPEN_QUESTIONS__", open_qs_md)
        .replace("__BODY__", body)
    )

    cwd = Path.cwd()
    local_path = cwd / ".auto-survey" / "final_report.md"
    local_path.write_text(out, encoding="utf-8")
    obsidian_path = f"Research/{slug}/_survey.md"
    return {
        "local_path": str(local_path),
        "obsidian_path": obsidian_path,
        "content": out,
    }


def _fallback_bibtex(paper: dict) -> str:
    arxiv_id = paper.get("arxiv_id") or paper.get("id", "").split(":")[-1]
    key = re.sub(r"[^a-zA-Z0-9]", "", arxiv_id) or "ref"
    authors = " and ".join(paper.get("authors", []) or ["Unknown"])
    return (
        f"@misc{{{key},\n"
        f"  title  = {{{paper.get('title','')}}},\n"
        f"  author = {{{authors}}},\n"
        f"  year   = {{{paper.get('year','')}}},\n"
        f"  eprint = {{{arxiv_id}}},\n"
        f"  archivePrefix = {{arXiv}}\n"
        f"}}"
    )


# CLI ----------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("render-note")
    s.add_argument("--topic-slug", required=True)
    s.add_argument("--topic", required=True)
    s.add_argument("--paper-json", required=True, help="path to a JSON file with paper metadata")

    s = sub.add_parser("render-table")
    s = sub.add_parser("render-survey")
    s.add_argument("--draft", default=None, help="path to drafts/<latest>.md to embed")

    args = p.parse_args()

    if args.cmd == "render-note":
        with open(args.paper_json, "r", encoding="utf-8") as f:
            paper = json.load(f)
        result = render_note(args.topic_slug, paper, args.topic)
    elif args.cmd == "render-table":
        result = render_table(state_mod.load())
    elif args.cmd == "render-survey":
        body = ""
        if args.draft:
            body = Path(args.draft).read_text(encoding="utf-8")
        result = render_survey(state_mod.load(), body)
    else:
        raise SystemExit(2)

    # Strip "content" from the JSON envelope when it would dwarf stdout;
    # SKILL.md can re-read local_path if needed.
    envelope = {k: v for k, v in result.items() if k != "content"}
    envelope["content_bytes"] = len(result["content"])
    print(json.dumps(envelope, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
