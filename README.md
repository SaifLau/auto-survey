# auto-survey

A lightweight Claude Code / Codex CLI skill for autonomous, long-running literature surveys with cross-turn state persistence and optional Obsidian sync.

一个轻量级的 Claude Code / Codex CLI 技能，用于跨轮次的自动文献调研，自带状态持久化，可选同步到 Obsidian 知识库。

---

## Features / 功能

- **State machine across turns** — each `/auto-survey resume` advances exactly one phase and persists state to `.auto-survey/state.json`, so a long survey survives context resets and host restarts.
  跨轮次状态机：每次 `resume` 只推进一个 phase，状态写入 `.auto-survey/state.json`，长跑调研不怕上下文清空或会话重启。

- **Multi-source literature search** — arXiv + WebSearch, plus optional Zotero, Obsidian vault, and local PDF folders.
  多源检索：arXiv + WebSearch，外加可选的 Zotero、Obsidian vault、本地 PDF 目录。

- **Auto-wake on Claude Code** — uses `ScheduleWakeup` under `/loop` mode to drive the loop without user intervention.
  Claude Code 下自动唤醒：`/loop` 模式中调用 `ScheduleWakeup`，无需手动 resume。

- **Graceful degradation** — works without any MCP server; falls back to local files and standard web search.
  优雅降级：没有任何 MCP 也能跑，自动回退到本地文件 + WebSearch。

- **Outputs** — Markdown survey draft, paper table, and per-paper notes; mirrored to Obsidian if a vault MCP is configured.
  输出：Markdown 综述、论文表格、每篇论文笔记；若配置了 Obsidian MCP 则同步到 vault。

## Pipeline / 工作流

```
init → keyword_expansion → literature_search → read_and_note → synthesis → gap_analysis → done
                                ↑                                                ↓
                                └────────────── (loop until budget) ─────────────┘
```

## Install / 安装

**Claude Code**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.claude/skills/auto-survey
```

**Codex CLI**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.codex/skills/auto-survey
```

That's it — the skill is auto-discovered the next time the host starts.
就这样，下次启动时 host 会自动发现这个 skill。

## Usage / 使用

```bash
/auto-survey "diffusion model acceleration"   # start a new survey / 新开一个调研
/auto-survey resume                           # advance one phase  / 推进一步
/auto-survey status                           # show progress     / 查看进度
/auto-survey abort                            # stop              / 终止
```

Auto-advance via the `/loop` skill (Claude Code only):
通过 `/loop` 自动循环推进（仅 Claude Code）：

```bash
/loop /auto-survey resume
```

Optional flags / 可选参数：

```
/auto-survey "topic" — max_papers: 30 — max_iterations: 20 — sources: arxiv,obsidian
```

| Flag | Effect / 作用 |
|---|---|
| `— max_papers: N` | cap papers to read / 阅读论文上限 |
| `— max_iterations: N` | hard iteration ceiling / 迭代次数硬上限 |
| `— deadline: ISO8601` | wall-clock cutoff / 截止时间 |
| `— sources: a,b,c` | restrict to subset of `arxiv,web,local,zotero,obsidian` |
| `— no_download` | skip arXiv PDF download / 不下载 arXiv PDF |

## Requirements / 依赖

- Python 3.8+
- Claude Code or Codex CLI
- Optional MCP servers / 可选 MCP：
  - Zotero MCP — read library and annotations / 读取文献库和批注
  - Obsidian MCP (`mcp__obsidian-vault__*` or `mcp__obsidian__*`) — write notes into vault / 把笔记写入 vault
  - Codex MCP (`mcp__codex__codex`) — optional external review during `gap_analysis` / 可选的外部 review

## Lightweight by design / 轻量化定位

This skill is intentionally a single self-contained directory — no orchestration framework, no service to deploy. Pure shell + Python + optional MCP. If you only want a one-shot literature review, use the simpler [`research-lit`](https://github.com/SaifLau) skill; reach for `auto-survey` when the topic is broad enough that you want a multi-iteration loop with budgeting and gap analysis.

刻意保持单技能、自包含 — 没有重型编排框架，也不用部署服务。纯 shell + Python + 可选 MCP。如果你只需要一次性的文献综述，用更轻的 `research-lit` 就够；当主题大到需要多轮迭代、预算控制、gap 分析时再用 `auto-survey`。

## Acknowledgements / 致谢

The state-machine + stale-state-guard pattern is inspired by the `auto-review-loop` skill design. Where flag syntax (`— flag: value`) is reused, that convention follows `research-lit`. The skill composes with two companion skills (not bundled, install separately if needed):

状态机 + stale-state guard 的设计参考自 `auto-review-loop` skill；`— flag: value` 参数风格沿用 `research-lit`。本 skill 配合下面两个 skill 工作（未打包，按需另装）：

- `arxiv` — arXiv paper search and PDF fetching / arXiv 搜索与 PDF 下载
- `research-lit` — single-shot literature review / 单次文献综述

## License

MIT — see [LICENSE](LICENSE).
