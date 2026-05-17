# auto-survey

[English](README.md) | **中文**

一个轻量级的 Claude Code / Codex CLI 技能：既支持跨轮次的自动文献调研（带状态持久化），也支持一个**无状态的子模式**——把已有论文笔记在 Obsidian ↔ Notion 之间迁移、补全方法公式、修复跨论文链接。

---

## 功能

- **跨轮次状态机** — 每次 `/auto-survey resume` 只推进一个 phase，状态写入 `.auto-survey/state.json`，长跑调研不怕上下文清空或会话重启。
- **多源检索** — arXiv + WebSearch，外加可选的 Zotero、Obsidian vault、本地 PDF 目录。
- **Claude Code 自动唤醒** — `/loop` 模式下调用 `ScheduleWakeup`，无需手动 resume。
- **优雅降级** — 没有任何 MCP 也能跑，自动回退到本地文件 + WebSearch。
- **输出** — Markdown 综述、论文表格、每篇论文笔记；若配置了 Obsidian MCP 则同步到 vault。
- **Notion 同步（可选）** — 传 `— notion_parent: <URL_or_ID>`，skill 会在该父页面下惰性创建论文数据库，每篇论文一行（标题、年份、venue、一句话结论等），最后再生成综述页面。
- **笔记增强子模式** — 无状态的一次性模式：把 vault 笔记迁到 Notion 数据库、补全只提名字没给公式的方法（AWQ / GPTQ / KIVI…）、把 `「页面名」` 文本引用转成真正的 Notion `<mention-page>` 链接、把 Notion 上的改进同步回 vault。无 state.json、无 phase 循环——一轮 = 一批 targeted 编辑。见下方 [笔记增强子模式](#笔记增强子模式)。

## 调研模式工作流

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
/auto-survey "topic" — notion_parent: https://www.notion.so/Your-Research-Hub-1234abcd
```

| 参数 | 作用 |
|---|---|
| `— max_papers: N` | 阅读论文上限 |
| `— max_iterations: N` | 迭代次数硬上限 |
| `— deadline: ISO8601` | 截止时间 |
| `— sources: a,b,c` | 限定数据源，可选 `arxiv,web,local,zotero,obsidian` |
| `— no_download` | 不下载 arXiv PDF |
| `— notion_parent: URL\|ID` | 在该父页面下创建论文数据库，把笔记同步过去 |

## 笔记增强子模式

有时任务不是开新调研，而是**改善已经存在的论文笔记**：

- 把 vault 里的笔记迁到已有的 Notion 论文数据库
- 给只提了名字（AWQ、GPTQ、KIVI…）但没写公式的方法补上数学
- 把 `「页面名」` 文本引用转成真正的 Notion `<mention-page>` 跨页链接
- 把 Notion 上的改进反向同步回 vault `.md`

这是**无状态**模式——没有 `.auto-survey/state.json`、没有 phase 循环、没有自动唤醒。一轮调用 = 一批 targeted 编辑。

**触发短语**："迁移笔记到 Notion"、"把 vault 的论文搬过去"、"补充方法解释"、"笔记里方法不清楚"、"AWQ 解释得不清楚"、"加公式说明"、"fix Notion paper cross-links"、"修笔记里的链接"。

详细约定见 [`references/note_enhancement.md`](references/note_enhancement.md)：

- **Notion MCP 并发上限** — 含公式 + 表格的论文页常常 1-3MB，每轮预算 32MB。硬上限：3 路并发 `notion-fetch`、5 路并发 `update_content`（仅小补丁）、3 路并发 `notion-create-pages`。遇到 "Request too large" 减半并发，不重试。
- **Notion 数学语法** — 行内公式用 `` $`expr`$ ``（dollar + 反引号 + LaTeX + 反引号 + dollar），**不是**裸 `$x$`；块公式 `$$` 必须独立成行。
- **方法解释四件套**（做什么 / 变量 / 为什么 / 代价），含 AWQ、GPTQ、KIVI、KVzip、SmoothQuant 公式模板。
- **Obsidian → Notion 内容转换**（`[[wikilink]] → 「text」 → <mention-page url=…/>`、本地文件路径、图片处理）。
- **Search-first, fetch-narrow** 模式：避免读大文件爆上下文。

## 依赖

- Python 3.8+
- Claude Code 或 Codex CLI
- 可选 MCP：
  - Zotero MCP — 读取文献库和批注
  - Obsidian MCP（`mcp__obsidian-vault__*` 或 `mcp__obsidian__*`）— 把笔记写入 vault
  - Notion MCP（`mcp__plugin_Notion_notion__*`）— Notion 同步和笔记增强子模式都需要
  - Codex MCP（`mcp__codex__codex`）— `gap_analysis` 阶段可选的外部 review

## 轻量化定位

刻意保持单技能、自包含 — 没有重型编排框架，也不用部署服务。纯 shell + Python + 可选 MCP。如果你只需要一次性的文献综述，用更轻的 `research-lit` 就够；当主题大到需要多轮迭代、预算控制、gap 分析时再用 `auto-survey`。

## 致谢

状态机 + stale-state guard 的设计参考自 `auto-review-loop` skill；`— flag: value` 参数风格沿用 `research-lit`。本 skill 配合下面两个 skill 工作（未打包，按需另装）：

- `arxiv` — arXiv 搜索与 PDF 下载
- `research-lit` — 单次文献综述

## 协议

MIT — 见 [LICENSE](LICENSE)。
