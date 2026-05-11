# auto-survey

[English](README.md) | **中文**

一个轻量级的 Claude Code / Codex CLI 技能，用于跨轮次的自动文献调研，自带状态持久化，可选同步到 Obsidian 知识库。

---

## 功能

- **跨轮次状态机** — 每次 `/auto-survey resume` 只推进一个 phase，状态写入 `.auto-survey/state.json`，长跑调研不怕上下文清空或会话重启。
- **多源检索** — arXiv + WebSearch，外加可选的 Zotero、Obsidian vault、本地 PDF 目录。
- **Claude Code 自动唤醒** — `/loop` 模式下调用 `ScheduleWakeup`，无需手动 resume。
- **优雅降级** — 没有任何 MCP 也能跑，自动回退到本地文件 + WebSearch。
- **输出** — Markdown 综述、论文表格、每篇论文笔记；若配置了 Obsidian MCP 则同步到 vault。

## 工作流

```
init → keyword_expansion → literature_search → read_and_note → synthesis → gap_analysis → done
                                ↑                                                ↓
                                └────────────── (循环直到预算耗尽) ────────────────┘
```

## 安装

**Claude Code**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.claude/skills/auto-survey
```

**Codex CLI**

```bash
git clone https://github.com/SaifLau/auto-survey.git ~/.codex/skills/auto-survey
```

下次启动 host 时会自动发现这个 skill。

## 使用

```bash
/auto-survey "diffusion model acceleration"   # 新开一个调研
/auto-survey resume                           # 推进一步
/auto-survey status                           # 查看进度
/auto-survey abort                            # 终止
```

通过 `/loop` 自动循环推进（仅 Claude Code）：

```bash
/loop /auto-survey resume
```

可选参数：

```
/auto-survey "topic" — max_papers: 30 — max_iterations: 20 — sources: arxiv,obsidian
```

| 参数 | 作用 |
|---|---|
| `— max_papers: N` | 阅读论文上限 |
| `— max_iterations: N` | 迭代次数硬上限 |
| `— deadline: ISO8601` | 截止时间 |
| `— sources: a,b,c` | 限定数据源，可选 `arxiv,web,local,zotero,obsidian` |
| `— no_download` | 不下载 arXiv PDF |

## 依赖

- Python 3.8+
- Claude Code 或 Codex CLI
- 可选 MCP：
  - Zotero MCP — 读取文献库和批注
  - Obsidian MCP（`mcp__obsidian-vault__*` 或 `mcp__obsidian__*`）— 把笔记写入 vault
  - Codex MCP（`mcp__codex__codex`）— `gap_analysis` 阶段可选的外部 review

## 轻量化定位

刻意保持单技能、自包含 — 没有重型编排框架，也不用部署服务。纯 shell + Python + 可选 MCP。如果你只需要一次性的文献综述，用更轻的 `research-lit` 就够；当主题大到需要多轮迭代、预算控制、gap 分析时再用 `auto-survey`。

## 致谢

状态机 + stale-state guard 的设计参考自 `auto-review-loop` skill；`— flag: value` 参数风格沿用 `research-lit`。本 skill 配合下面两个 skill 工作（未打包，按需另装）：

- `arxiv` — arXiv 搜索与 PDF 下载
- `research-lit` — 单次文献综述

## 协议

MIT — 见 [LICENSE](LICENSE)。
