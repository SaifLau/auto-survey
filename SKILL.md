---
name: auto-survey
description: "Run an autonomous, long-lived literature-survey workflow that maintains state across turns. Use when user says \"自动调研\", \"auto survey\", \"长跑调研\", \"start a survey on X\", \"resume my survey\", or wants a recoverable multi-phase research-survey loop on top of arxiv / research-lit. Outputs a Markdown survey + paper table; persists to Obsidian if MCP is configured."
argument-hint: ["topic" | resume | status | abort]
allowed-tools: Bash(*), Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, mcp__zotero__*, mcp__obsidian-vault__*, mcp__obsidian__*, mcp__codex__codex, mcp__codex__codex-reply
---

# auto-survey: long-running literature-survey orchestrator

Drive a multi-phase survey via a state machine in `.auto-survey/state.json`. Each invocation advances **at most one phase**, persists state, and either schedules itself to wake up (in `/loop` dynamic mode) or asks the user to `/auto-survey resume`.

Designed to run identically under Claude Code and Codex CLI. The body below uses only generic tools (shell, file I/O, web search, optional MCP). The only host-specific piece is the wake-up step at the end, which degrades gracefully when the host doesn't support it.

## Context: $ARGUMENTS

## Safety Rules — READ FIRST

- **NEVER** `sudo`, `rm -rf`, `rm -r`, recursive deletion, or destructive git ops.
- **NEVER** modify files outside the current working directory's `.auto-survey/` folder, unless writing to an explicitly user-configured Obsidian vault.
- **NEVER** download more than `arxiv_max_download` PDFs per phase.
- If a step *would* require any of the above, STOP and report.

## Engine Layout

The Python engine lives next to this file:

```
SKILL_DIR/
  scripts/
    init.py        # initialise .auto-survey/ workspace
    state.py       # atomic state.json read/write + CLI subcommands
    budget.py      # check abort conditions
    score_paper.py # heuristic relevance scoring
    obsidian_io.py # render templates → markdown files
  templates/       # state.template.json, paper_note.template.md, ...
```

To resolve `SKILL_DIR` from anywhere:

```bash
SKILL_DIR=$(python3 -c "
import pathlib
for p in [
    pathlib.Path.home() / '.claude' / 'skills' / 'auto-survey',
    pathlib.Path.home() / '.codex'  / 'skills' / 'auto-survey',
]:
    if (p / 'scripts' / 'state.py').exists():
        print(p); break
")
```

Use `$SKILL_DIR/scripts/<name>.py` in subsequent commands.

## Step 0 — Parse $ARGUMENTS

Detect the sub-command:

| First token | Meaning |
|---|---|
| `resume` (or empty) | Advance one phase based on existing state.json |
| `status` | Print state summary; no writes |
| `abort` | Set status=aborted; refuse future advances |
| anything else | Treat as a topic; init a new workspace |

Also extract `— flag: value` overrides (same style as `research-lit`):

| Flag | Effect |
|---|---|
| `— max_papers: N` | sets `config.max_papers_to_read` |
| `— max_iterations: N` | sets `budget.max_iterations` |
| `— deadline: ISO8601` | sets `budget.deadline` |
| `— sources: a,b,c` | restrict to subset of `arxiv,web,local,zotero,obsidian` |
| `— no_download` | sets `config.arxiv_download = false` |

## Step 1 — Load or initialise state

```bash
if [ -f .auto-survey/state.json ]; then
  python3 "$SKILL_DIR/scripts/state.py" show --summary
else
  # init mode (only allowed when first token is a topic, not resume/status/abort)
  python3 "$SKILL_DIR/scripts/init.py" "TOPIC" \
    --max-papers $MAX_PAPERS --max-iterations $MAX_ITERS \
    --obsidian-configured $OBSIDIAN_AVAILABLE
fi
```

**Stale-state guard** (mirrors `auto-review-loop`):

- If `status == "completed"` or `"aborted"`: refuse `resume`; tell user to `rm -rf .auto-survey/` first.
- If `status == "in_progress"` AND `updated_at` older than 24h: warn but continue (the user may have abandoned it).

**Obsidian detection**: try one Obsidian MCP call (`mcp__obsidian-vault__*` or `mcp__obsidian__*`). If it succeeds, set `state.obsidian.configured = true` and remember the vault folder `Research/<topic_slug>/`. If it fails, fall back to local `.auto-survey/notes/`.

## Step 2 — Check budget

```bash
python3 "$SKILL_DIR/scripts/budget.py"
# Exit 0  → continue
# Exit 10/11/12/13/14 → abort: read the JSON for reason
```

If abort: skip to Step 4 (done) and write final report from whatever has been collected.

## Step 3 — Dispatch by phase

The state machine. Read `state.phase` and execute the matching block. **Each block does ONE small step then returns to Step 5** (don't try to loop multiple phases in one turn — that's what wake-up is for).

### Phase: `init`

Just transition to `keyword_expansion`.
```bash
python3 "$SKILL_DIR/scripts/state.py" phase keyword_expansion --reason "init complete"
```

### Phase: `keyword_expansion`

Generate 5-10 search keywords / aliases for the topic. Write them to `state.keywords.queue`. Examples for "diffusion model acceleration":
- "diffusion model inference acceleration"
- "fast diffusion sampling"
- "diffusion model quantization"
- "diffusion distillation"
- "consistency models"

Use a Python edit (read state.json → modify → save):

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('.auto-survey/state.json')
data = json.loads(p.read_text())
data['keywords']['queue'] = [...your 5-10 keywords...]
p.write_text(json.dumps(data, indent=2, ensure_ascii=False))
PY
python3 "$SKILL_DIR/scripts/state.py" phase literature_search --reason "keywords ready"
python3 "$SKILL_DIR/scripts/state.py" log "expanded_keywords" "N=<count>"
python3 "$SKILL_DIR/scripts/state.py" mark-progress
```

### Phase: `literature_search`

Pop ONE keyword from `keywords.queue` and search it across configured sources. Don't drain the whole queue in one turn — that overruns context.

1. Pop next keyword: `kw = state.keywords.queue.pop(0)` and append to `state.keywords.searched`.
2. **arXiv** (if in `config.sources`):
   ```bash
   ARXIV=$(find "$SKILL_DIR/.." ~/.claude/skills/arxiv ~/.codex/skills/arxiv \
     -name arxiv_fetch.py 2>/dev/null | head -1)
   python3 "$ARXIV" search "$kw" --max 10
   ```
3. **WebSearch** (if in `config.sources`): one search for `"$kw" 2024..2026`. Skim for non-arXiv venue papers.
4. **Zotero / Obsidian** (if MCP available + in sources): search vault/library for `$kw`.
5. **Local PDFs** (if in sources): `Glob: papers/**/*.pdf, literature/**/*.pdf` — match filenames/abstracts.
6. **Score and merge**: for each newly-found paper:
   ```bash
   python3 "$SKILL_DIR/scripts/score_paper.py" --topic "<state.topic>" --title "..." --abstract "..." --year YYYY
   ```
   Add to `state.papers` with the score; de-duplicate by arxiv_id or normalised title.

7. **Decide next phase**:
   - If `keywords.queue` not empty AND `len(papers) < config.min_papers_before_synthesis`: stay in `literature_search`.
   - Else: advance to `read_and_note`.

8. Log progress and mark progress/no-progress:
   ```bash
   python3 "$SKILL_DIR/scripts/state.py" log "search:$kw" "added=N total=M"
   python3 "$SKILL_DIR/scripts/state.py" mark-progress  # or mark-no-progress if N==0
   ```

### Phase: `read_and_note`

Pop ONE paper at a time (highest relevance first). Don't read more than ~2 papers per turn — each PDF fills context.

1. Pick the highest-relevance, unread paper: `papers.filter(read=false).max(relevance)`.
2. **Download PDF** (if `config.arxiv_download` and `relevance >= 4` and not already on disk):
   ```bash
   python3 "$ARXIV" download <arxiv_id> --dir .auto-survey/papers/
   ```
   Cap by `config.arxiv_max_download` per session.
3. **Read** the PDF (first ~10 pages: title, abstract, intro, method, key results). If no PDF, fall back to abstract.
4. **Render note**: dump paper metadata + your reading into JSON, then:
   ```bash
   echo '{"id":"...", "title":"...", "authors":[...], "year":2025, ...}' > /tmp/p.json
   python3 "$SKILL_DIR/scripts/obsidian_io.py" render-note \
     --topic-slug "<state.topic_slug>" --topic "<state.topic>" --paper-json /tmp/p.json
   ```
   This writes `<.auto-survey>/notes/<paper-slug>.md`. Read its content (or grab `content_bytes` envelope) and:
   - **If Obsidian MCP available**: call the vault's "create file" tool with path `Research/<topic_slug>/<paper-slug>.md` and the rendered markdown.
   - Else: keep the local copy.

5. Update state: mark `papers[i].read = true`, `papers[i].note_path = "..."`, fill `method_oneliner`, `key_result`. Use the same Python heredoc pattern as keyword_expansion.

6. **Decide next phase**:
   - If unread relevance≥3 papers remain AND `consumed.papers_read < config.max_papers_to_read`: stay in `read_and_note`.
   - Else: advance to `synthesis`.

### Phase: `synthesis`

Read ALL notes from `.auto-survey/notes/` (use `Glob` + `Read`). Group into 3-5 themes. Write a draft:

```bash
DRAFT=.auto-survey/drafts/survey_v$(date +%s).md
# write a 3-5 page draft to $DRAFT (Read all notes, then Write the draft)
python3 "$SKILL_DIR/scripts/state.py" log "synthesis" "draft=$DRAFT"
```

Append to `state.drafts`, advance to `gap_analysis`, mark progress.

### Phase: `gap_analysis`

Critically review the latest draft:
- What papers/ideas are missing?
- What questions are unanswered?
- Is any theme thin?

**Optional external review** (if `mcp__codex__codex` is available *and* you're running in Claude): kick off a one-shot codex call asking "what's missing from this survey?" and parse its response. Otherwise, do the review yourself.

Decide:
- If gaps found AND `consumed.iterations < budget.max_iterations - 3`: append new search terms to `keywords.queue`, advance back to `literature_search`. Append findings to `state.open_questions`.
- Else: advance to `done`.

### Phase: `done`

1. Compile final report:
   ```bash
   python3 "$SKILL_DIR/scripts/obsidian_io.py" render-survey \
     --draft .auto-survey/drafts/<latest>.md
   python3 "$SKILL_DIR/scripts/obsidian_io.py" render-table
   ```
2. **Sync to Obsidian** (if configured): write both `_survey.md` and `_papers.md` into `Research/<topic_slug>/` via the Obsidian MCP. For each paper note, ensure it's in the vault (already done in `read_and_note`).
3. Set status=completed:
   ```bash
   python3 "$SKILL_DIR/scripts/state.py" set-status completed
   ```
4. Print a one-paragraph summary to the user. Done.

## Step 4 — Increment iteration

After ANY phase that did real work:
```bash
python3 "$SKILL_DIR/scripts/state.py" inc-iteration
```

## Step 5 — Wake-up (host-specific)

The skill should advance one phase per turn. To make it self-driving:

**On Claude Code, in /loop dynamic mode** — call the host's `ScheduleWakeup` tool:

```
ScheduleWakeup(
  prompt="/auto-survey resume",
  delaySeconds=120,
  reason="advance to <next_phase> after <current_phase>"
)
```

Pick `delaySeconds`:
- 60–180s for normal phase transitions (stays in cache).
- 300s+ if waiting for a long download/upload.
- Skip wake-up entirely if `phase == done` or status is terminal.

If `ScheduleWakeup` is unavailable (not in /loop), instead print:
```
Next: /auto-survey resume   (or /loop /auto-survey resume to auto-advance)
```

**On Codex CLI** — Codex doesn't have ScheduleWakeup. Two options:

1. **User-driven**: print the same `Next: ...` line. User re-invokes `auto-survey resume` manually.
2. **Routine-driven**: the user can wrap with the `schedule` skill's recurring routine (`*/3 * * * *` running `auto-survey resume` until `phase=done`).

Always print the next-step hint regardless of host, so the workflow is visible even if auto-wake fails silently.

## Step 6 — Status / Abort sub-commands

If `$ARGUMENTS` started with `status`:
```bash
python3 "$SKILL_DIR/scripts/state.py" show --summary
```
Print and return. No state changes.

If `$ARGUMENTS` started with `abort`:
```bash
python3 "$SKILL_DIR/scripts/state.py" set-status aborted
```
Print confirmation and return.

## Recovery

If `state.json` is corrupted or missing but `state.backup.json` exists:
```bash
cp .auto-survey/state.backup.json .auto-survey/state.json
python3 "$SKILL_DIR/scripts/state.py" log "recovery" "restored from backup"
```
Then continue normally.

## Schema

`state.json` follows `references/state_schema.md`. Key fields:
- `phase` ∈ {init, keyword_expansion, literature_search, read_and_note, synthesis, gap_analysis, done}
- `status` ∈ {in_progress, completed, aborted}
- `papers[]` with id, title, year, source, relevance (1-5), read, note_path
- `budget`: max_iterations, deadline
- `abort_if.no_progress_streak`: soft abort after N stalled phases
- `log[]`: append-only, truncated at 500 entries

## Key Rules

- **One phase per turn.** Never chain phases inside a single invocation — let the wake-up loop do it.
- **State is the source of truth.** If unsure where you are, re-read `.auto-survey/state.json`.
- **Atomic writes via state.py.** Don't hand-edit state.json with `Edit` tool — race conditions and backups break.
- **De-duplicate aggressively.** Same paper from arXiv and Zotero → keep the Zotero entry (richer metadata).
- **Cite everything.** Every claim in `_survey.md` should `[[wikilink]]` to a specific paper note.
- **Be honest.** If only 5 papers were read, write "based on 5 papers" — don't pad.
- **Cap recursion.** `gap_analysis → literature_search` is the only loop; never auto-loop more than `max_iterations` times.
