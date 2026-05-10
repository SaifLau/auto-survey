# `state.json` schema (auto-survey)

Single source of truth for an in-flight survey. Lives at
`<workdir>/.auto-survey/state.json`. Atomic writes via `scripts/state.py`;
previous version is kept in `state.backup.json`.

`schema_version` is currently **1**. Bump it whenever an incompatible change
lands; `state.py.load()` refuses to load mismatched versions.

## Top-level fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | int | Always 1 in this revision. |
| `topic` | string | Original user-provided topic. |
| `topic_slug` | string | ASCII slug used for filenames and Obsidian folder. |
| `created_at` | ISO8601 UTC | Set at init, never changed. |
| `updated_at` | ISO8601 UTC | Refreshed on every save. |
| `status` | enum | `in_progress` / `completed` / `aborted`. |
| `phase` | enum | See *State machine* below. |
| `iteration` | int | Number of phase advances so far. |
| `obsidian` | object | `{configured: bool, vault_folder: string}`. |
| `config` | object | Knobs the user set at init time (see below). |
| `budget` | object | `{max_iterations, deadline}`. |
| `consumed` | object | `{iterations, papers_read}`. Compared against `budget`. |
| `abort_if` | object | `{no_progress_streak: int}` — soft abort threshold. |
| `no_progress_streak` | int | Reset by `mark-progress`, ++ by `mark-no-progress`. |
| `keywords` | object | `{queue: [str], searched: [str]}`. |
| `papers` | array | See *Paper entry*. |
| `drafts` | array | `[{version, path, ts}]` — synthesis output history. |
| `open_questions` | array | Strings — populated by `gap_analysis`. |
| `log` | array | Append-only event log. Truncated at 500 entries. |

## State machine

`phase` transitions:

```
init
 └─→ keyword_expansion
       └─→ literature_search
             └─→ read_and_note
                   └─→ synthesis
                         └─→ gap_analysis
                               ├─→ literature_search   (gaps + budget left)
                               └─→ done
```

Terminal: `done` (under `status=completed`) or `aborted`.

## `config`

| Field | Default | Description |
|---|---|---|
| `sources` | `["arxiv","web","local","zotero","obsidian"]` | Which sources to search. |
| `arxiv_download` | `true` | Download top-N relevant arXiv PDFs. |
| `arxiv_max_download` | `5` | Cap downloads per session. |
| `min_papers_before_synthesis` | `10` | Don't synthesize until queue is this full. |
| `max_papers_to_read` | `30` | Hard cap on `read_and_note` iterations. |
| `search_recent_years` | `3` | Bias arXiv/web search to last N years. |

## `budget`

- `max_iterations` (int): hard cap. When `consumed.iterations >= max_iterations`, force `done`.
- `deadline` (ISO8601 or null): hard cap on wall-clock.

## Paper entry

```json
{
  "id": "arxiv:2403.12345",
  "title": "...",
  "authors": ["..."],
  "year": 2025,
  "venue": "arXiv | NeurIPS | ICML | ...",
  "source": "arxiv | web | zotero | obsidian | local",
  "abstract": "...",
  "url": "https://arxiv.org/abs/2403.12345",
  "arxiv_id": "2403.12345",
  "relevance": 4,
  "relevance_reasons": ["overlap=0.21", "year_recent_bump"],
  "downloaded": true,
  "pdf_path": ".auto-survey/papers/2403.12345.pdf",
  "read": false,
  "note_path": "Research/diffusion-acceleration/2403.12345.md",
  "method_oneliner": "Per-channel quantization of UNet weights with mixed precision.",
  "key_result": "+1.4 PSNR vs INT4 baseline at 2.3x speedup."
}
```

`relevance` is on a 1–5 scale. The heuristic in `score_paper.py` produces an
initial guess; the LLM may overwrite it during reading.

## Log entry

```json
{
  "ts": "2026-05-02T07:12:34+00:00",
  "phase": "literature_search",
  "action": "search:diffusion quantization",
  "result": "added=4 total=12"
}
```

## Concurrency

`state.json` is rewritten atomically (write to `.tmp` + fsync + rename). Two
parallel `auto-survey` invocations on the same workspace are not safe — the
second one will clobber the first's writes. Per design, exactly one
invocation should be in flight per `.auto-survey/` dir.

## Recovery

If `state.json` is missing or corrupt:

1. Restore from `state.backup.json` (kept in lockstep).
2. Replay the last `log` entry to understand what was in flight.
3. Re-run the corresponding phase from scratch — phases are idempotent except
   for `read_and_note` (PDF downloads are skipped if file already on disk).

## Migrating

When `schema_version` bumps, write a one-shot migration in
`scripts/migrate_v<old>_to_v<new>.py` that reads the old state, transforms
in-memory, and saves under the new schema. Don't load and silently coerce —
fail loudly so the user knows.
