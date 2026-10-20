# Incremental edge-inference briefs

Use Python 3.9+ (no third-party dependencies). Run from the user's project:

```bash
python3 /path/to/auto-survey/scripts/incremental.py scan --arxiv 'all:"edge inference"' --limit 100
python3 /path/to/auto-survey/scripts/incremental.py scan --github ggml-org/llama.cpp
python3 /path/to/auto-survey/scripts/incremental.py scan --input findings.json --source-id web-search
python3 /path/to/auto-survey/scripts/incremental.py brief
python3 /path/to/auto-survey/scripts/incremental.py status
```

Place `--workspace PATH` before the command to select a workspace. Default storage
is `.auto-survey/incremental/.auto-survey/`, isolated from the survey's state.
Reuse `state.py` atomic writes/backups and `score_paper.py` heuristic ordering prior.
The score is recorded, not an automatic quality filter. Review relevance before delivery.

## Collection contract

Reuse survey keyword expansion and WebSearch/arxiv companion search to gather model
architecture, inference frameworks, operators, and hardware deployment changes.
Use primary papers, official release notes, merged PRs, and vendor documentation.
Import these searches through the same normalized batch contract:

```json
{
  "cursor": "collector-specific-checkpoint",
  "items": [{
    "kind": "paper",
    "category": "operator",
    "title": "Example inference paper",
    "url": "https://arxiv.org/abs/2610.12345v1",
    "published_at": "2026-10-01",
    "updated_at": "2026-10-02",
    "arxiv_id": "2610.12345",
    "doi": null,
    "authors": ["Author Name"],
    "affiliations": null,
    "lab": null,
    "company": null,
    "background": null,
    "summary": "Specific technical change; measured results need a source.",
    "evidence": {"authors": "https://arxiv.org/abs/2610.12345"}
  }]
}
```

Kinds: `paper`, `release`, `news`. Categories: `architecture`, `framework`,
`operator`, `hardware`. Releases additionally accept `repository` and `version`.
Do not infer affiliations from GitHub usernames. Record unknown metadata as null.
Evidence is retained as supplied, not independently certified by this tool.
Company strengths, representative work, and investment claims require primary links.

The arXiv adapter reads Atom title/authors/abstract and original publication/update
dates; it cannot verify affiliations. Its default category is architecture; for
operator or hardware papers, use reviewed JSON imports with the correct category.
GitHub adapter paginates all stable releases, preserving tag, release URL, body,
and publication date; it does not inspect unreleased commits, infer benchmarks,
or claim every release is relevant. First scan imports historical releases too.

Source cursors and success times are persisted only after successful validation.
They are audit checkpoints, not exclusive date cutoffs: GitHub replays releases
so edited notes are detected; arXiv replays a bounded latest-updated window.
High-volume arXiv queries can exceed that window: narrow queries, increase `--limit`,
or import a paginated external collector for complete backfills. Do not claim full
coverage. Failed collection does not advance the checkpoint.

## Validation and identity

HTTP(S) links are syntax checked; use `scan --verify-links ...` to perform GET
reachability checks. Reachability does not prove authorship or claim accuracy.
Imported records are labeled `unverified-import`; API adapters use `source-metadata`.
Dates must parse as ISO 8601 and cannot be in the future; missing/invalid dates render
as unknown. First discovery time is distinct from original publication time.

Match DOI, versionless arXiv ID, canonical source URL, or normalized paper title.
Ambiguous identities fail the batch rather than silently combine unrelated items.
Alias sets persist across executions. Sparse records do not erase rich metadata.
A changed semantic record creates an update event; unchanged items create no event.
Distinct release URLs remain distinct releases. All discovered items remain in state.

## Recovery and output

The exclusive scan lock rejects overlapping processes. After a crashed process,
check that its PID is no longer active before manually removing `scan.lock`.
Malformed JSON restores the previous backup and preserves `.corrupt` bytes;
unsupported schemas fail rather than silently resetting state. A backup may lag
one operation; rescan sources after recovery. Do not manually delete survey state.

`scan` commits discovery events before `brief`. `brief` writes a deterministic
Markdown file before recording rendered state; retry after a crash repairs the
same pending report. A failed write leaves events pending. Repeated empty runs
produce an explicit no-new-results report. Markdown is reusable as an Obsidian
note or input to the existing Notion workflow; no external sync occurs here.
`rendered_at` means local Markdown generation, and `delivered_at` stays null.
No scheduled trigger or notification sender is installed or verified. Verify each
separately, including durable state retention and delivery acknowledgements,
before claiming daily push notifications.

Run automated verification from the repository:

```bash
python3 -m unittest discover -s tests -v
```
