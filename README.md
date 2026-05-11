# auto-survey

**English** | [中文](README.zh.md)

A lightweight Claude Code / Codex CLI skill for autonomous, long-running literature surveys with cross-turn state persistence and optional Obsidian sync.

---

## Features

- **State machine across turns** — each `/auto-survey resume` advances exactly one phase and persists state to `.auto-survey/state.json`, so a long survey survives context resets and host restarts.
- **Multi-source literature search** — arXiv + WebSearch, plus optional Zotero, Obsidian vault, and local PDF folders.
- **Auto-wake on Claude Code** — uses `ScheduleWakeup` under `/loop` mode to drive the loop without user intervention.
- **Graceful degradation** — works without any MCP server; falls back to local files and standard web search.
- **Outputs** — Markdown survey draft, paper table, and per-paper notes; mirrored to Obsidian if a vault MCP is configured.

## Pipeline

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
```

| Flag | Effect |
|---|---|
| `— max_papers: N` | cap papers to read |
| `— max_iterations: N` | hard iteration ceiling |
| `— deadline: ISO8601` | wall-clock cutoff |
| `— sources: a,b,c` | restrict to subset of `arxiv,web,local,zotero,obsidian` |
| `— no_download` | skip arXiv PDF download |

## Requirements

- Python 3.8+
- Claude Code or Codex CLI
- Optional MCP servers:
  - Zotero MCP — read library and annotations
  - Obsidian MCP (`mcp__obsidian-vault__*` or `mcp__obsidian__*`) — write notes into vault
  - Codex MCP (`mcp__codex__codex`) — optional external review during `gap_analysis`

## Lightweight by design

This skill is intentionally a single self-contained directory — no orchestration framework, no service to deploy. Pure shell + Python + optional MCP. For a one-shot literature review, the simpler `research-lit` skill is enough; reach for `auto-survey` when the topic is broad enough to need a multi-iteration loop with budgeting and gap analysis.

## Acknowledgements

The state-machine + stale-state-guard pattern is inspired by the `auto-review-loop` skill design. The `— flag: value` syntax convention follows `research-lit`. The skill composes with two companion skills (not bundled, install separately if needed):

- `arxiv` — arXiv paper search and PDF fetching
- `research-lit` — single-shot literature review

## License

MIT — see [LICENSE](LICENSE).
