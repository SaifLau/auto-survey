# auto-survey

**English** | [中文](README.zh.md)

A lightweight Claude Code / Codex CLI skill for autonomous, long-running literature surveys with cross-turn state persistence, plus a stateless sub-mode for upgrading existing paper notes (Obsidian ↔ Notion migration, method-formula fill-ins, cross-paper link repair).

---

## Features

- **State machine across turns** — each `/auto-survey resume` advances exactly one phase and persists state to `.auto-survey/state.json`, so a long survey survives context resets and host restarts.
- **Multi-source literature search** — arXiv + WebSearch, plus optional Zotero, Obsidian vault, and local PDF folders.
- **Auto-wake on Claude Code** — uses `ScheduleWakeup` under `/loop` mode to drive the loop without user intervention.
- **Graceful degradation** — works without any MCP server; falls back to local files and standard web search.
- **Outputs** — Markdown survey draft, paper table, and per-paper notes; mirrored to Obsidian if a vault MCP is configured.
- **Notion sync (optional)** — pass `— notion_parent: <URL_or_ID>` and the skill lazily creates a Papers database under that parent page, with one row per paper (title, year, venue, one-line conclusion, etc.) plus a final Survey page.
- **Note enhancement sub-mode** — stateless one-shot mode for upgrading existing paper notes: migrate vault notes into a Notion database, fill in missing method formulas, convert `「page」` text refs into real Notion mentions, sync upgrades back to the source vault. No state.json, no phase loop — one turn = one batch of edits. See [Note enhancement sub-mode](#note-enhancement-sub-mode) below.

## Survey-mode pipeline

```
init → keyword_expansion → literature_search → read_and_note → synthesis → gap_analysis → done
                                ↑                                                ↓
                                └────────────── (loop until budget) ─────────────┘
```

## Install

**Claude Code**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.claude/skills/auto-survey
```

**Codex CLI**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.codex/skills/auto-survey
```

The skill is auto-discovered the next time the host starts.

## Usage

```bash
/auto-survey "diffusion model acceleration"   # start a new survey
/auto-survey resume                           # advance one phase
/auto-survey status                           # show progress
/auto-survey abort                            # stop
```

Auto-advance via the `/loop` skill (Claude Code only):

```bash
/loop /auto-survey resume
```

Optional flags:

```
/auto-survey "topic" — max_papers: 30 — max_iterations: 20 — sources: arxiv,obsidian
/auto-survey "topic" — notion_parent: https://www.notion.so/Your-Research-Hub-1234abcd
```

| Flag | Effect |
|---|---|
| `— max_papers: N` | cap papers to read |
| `— max_iterations: N` | hard iteration ceiling |
| `— deadline: ISO8601` | wall-clock cutoff |
| `— sources: a,b,c` | restrict to subset of `arxiv,web,local,zotero,obsidian` |
| `— no_download` | skip arXiv PDF download |
| `— notion_parent: URL\|ID` | mirror notes into a Notion database created under that parent page |

## Note enhancement sub-mode

Sometimes the task isn't a new survey — it's improving paper notes that already exist:

- migrating vault notes into an existing Notion paper database
- filling in method explanations that name a method (AWQ, GPTQ, KIVI...) but never show the actual math
- converting `「Page Title」` text references into real Notion `<mention-page>` links so cross-paper navigation works
- syncing an upgraded Notion page back to the source vault `.md`

This is a **stateless** mode — no `.auto-survey/state.json`, no phase loop, no wake-up. One turn = one well-scoped batch of edits.

**Trigger phrases**: "迁移笔记到 Notion", "把 vault 的论文搬过去", "补充方法解释", "笔记里方法不清楚", "AWQ 解释得不清楚", "加公式说明", "fix Notion paper cross-links", "修笔记里的链接".

See [`references/note_enhancement.md`](references/note_enhancement.md) for the operating contract:

- **Concurrency caps for Notion MCP** — paper pages with formulas + tables routinely hit 1-3MB; the per-turn budget is 32MB. Hard caps: 3 parallel `notion-fetch`, 5 parallel `update_content` (small patches only), 3 parallel `notion-create-pages`. Halve concurrency on "Request too large", don't retry.
- **Notion math syntax** — inline math uses `` $`expr`$ `` (dollar + backtick + LaTeX + backtick + dollar), NOT plain `$x$`; block math needs `$$` on its own lines.
- **Four-part formula rule** for method explanations (what / variables / why / cost), with worked examples for AWQ, GPTQ, KIVI, KVzip, SmoothQuant.
- **Obsidian → Notion content transforms** (`[[wikilink]] → 「text」 → <mention-page url=…/>`, local file paths, image handling).
- **Search-first, fetch-narrow** patterns to avoid blowing context on large vault files.

## Requirements

- Python 3.8+
- Claude Code or Codex CLI
- Optional MCP servers:
  - Zotero MCP — read library and annotations
  - Obsidian MCP (`mcp__obsidian-vault__*` or `mcp__obsidian__*`) — write notes into vault
  - Notion MCP (`mcp__plugin_Notion_notion__*`) — required for Notion sync and the note enhancement sub-mode
  - Codex MCP (`mcp__codex__codex`) — optional external review during `gap_analysis`

## Lightweight by design

This skill is intentionally a single self-contained directory — no orchestration framework, no service to deploy. Pure shell + Python + optional MCP. For a one-shot literature review, the simpler `research-lit` skill is enough; reach for `auto-survey` when the topic is broad enough to need a multi-iteration loop with budgeting and gap analysis.

## Acknowledgements

The state-machine + stale-state-guard pattern is inspired by the `auto-review-loop` skill design. The `— flag: value` syntax convention follows `research-lit`. The skill composes with two companion skills (not bundled, install separately if needed):

- `arxiv` — arXiv paper search and PDF fetching
- `research-lit` — single-shot literature review

## License

MIT — see [LICENSE](LICENSE).
