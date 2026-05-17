# Note Enhancement & Migration Reference

This file backs the **Sub-mode: Enhance Existing Paper Notes** in `SKILL.md`. It exists because two failure modes keep recurring:

1. **The 32MB crash** — `notion-fetch` or `update_content` issued in batches of 5+ saturates the per-turn request budget, the call returns `Request too large (max 32MB)`, and progress halts mid-batch.
2. **The named-but-unexplained method** — a note says "AWQ scales weights" or "GPTQ uses Hessian-based updates" without showing the actual operation, so the note is useless when you come back six months later and need to remember *why* it works.

The patterns below prevent both.

---

## Concurrency limits — read before any MCP call

These are not suggestions; they're calibrated from real failures.

| Tool | Max parallel | Why this cap |
|------|-------------|--------------|
| `notion-fetch` (paper page) | **3** | Paper pages with formulas + tables routinely render to 1-3MB each. Three is the largest batch that reliably stays under the 32MB budget. |
| `notion-fetch` (data source / database) | 5 | Schema fetches are small; safe to parallelize. |
| `update_content` (search-and-replace patch) | **5** | Patches that touch only a few hundred bytes are fine in parallel. |
| `update_content` (full-page rewrite) | **1** | Always sequential. Full-page payloads frequently exceed 8MB on their own. |
| `notion-create-pages` (with body content) | **3** | Page body markdown can be 50-200KB per paper note. |
| `notion-search` | unlimited | Returns titles/IDs only; cheap. |

### Recovery when "Request too large" fires

Don't retry the same batch — the failure mode is request size, not transient. Step down:

1. **Halve the parallelism** for the same operation (5 → 3 → 1).
2. If a single call is still failing, the **payload itself** is too large. Split the work:
   - For `update_content`: break one large patch into multiple smaller search-and-replace patches.
   - For `notion-create-pages`: create the page with minimal frontmatter first, then `update_content` the body in chunks.
3. Log which page hit the ceiling — those pages typically need restructuring (tables that should be databases, embedded SVGs that should be uploaded as files).

### Avoid reading large files in the first place

Before any `Read` on a vault `.md`:

```bash
wc -l "filename.md"            # > 500 lines? Don't read whole.
grep -n "^## " "filename.md"   # Get section headers; pick what you need.
```

Then `Read` with `offset` and `limit` to grab just the section you're editing. Full reads only when the file is under ~300 lines AND you genuinely need most of it.

For Notion: prefer `notion-search` (returns title + ID) before `notion-fetch` (returns full body). Don't fetch a page just to check whether it exists.

---

## Notion math syntax (read before writing formulas)

Notion's enhanced markdown uses a **non-standard math delimiter**. The usual `$x$` and `$$...$$` from LaTeX won't render as math — Notion silently escapes them to literal text `\$x\$`.

| Math kind | Notion enhanced-markdown syntax |
|-----------|---------------------------------|
| Inline | `` $`expr`$ `` — dollar + backtick + LaTeX + backtick + dollar |
| Block | `$$` on its own line, equation on next line, `$$` on its own line |

Block example (the `$$` must be on a line by itself, not glued to the equation):

```
$$
\mathbf{y} = \mathbf{W}\mathbf{x}
$$
```

**Common mistakes** (all silently produce literal text, not math):
- `$x$` without backticks → stored as `\$x\$`, renders as text.
- `$$x$$` on a single line → demoted to inline math, renders smaller than intended.
- `$\alpha$` without backticks → backslash gets stripped, stored as `\$alpha\$`, renders as text "alpha".

**When fixing existing pages where math broke**, use search-and-replace patches:
- old_str matches the stored escaped form (e.g. `\$s\$`)
- new_str uses the proper backtick form (e.g. `` $`s`$ ``)

Verify by re-fetching after every math edit — broken math is silent and easy to miss.

## The formula rule for method explanations

When a paper note mentions a method, the explanation should make the math legible to a future reader. The bar:

1. **What it computes** — one equation showing the actual operation.
2. **What the variables mean** — one short line per symbol.
3. **Why this form** — one sentence on the intuition (what observation motivated it).
4. **What it costs** — memory / FLOPs / accuracy delta vs the baseline it replaces.

Apply this any time a method is **central to the paper's claim** or **referenced more than once** in the note. For a method that appears in passing ("we compare against GPTQ"), a one-line description is fine.

### Worked examples

These are the templates to model new explanations after. They double as a small library of formulas that come up repeatedly in on-device LLM inference notes.

#### AWQ (Activation-aware Weight Quantization)

> AWQ observes that not all weights matter equally — a small fraction (≈1%) of channels with the largest activation magnitudes dominate output error. Rather than mixing precisions, scale these salient channels up *before* quantizing so they survive INT4 rounding, then absorb the inverse scale into the preceding activation:
>
> $$Q(\mathbf{W} \cdot \mathrm{diag}(s)) \cdot \frac{x}{s} \approx \mathbf{W} \cdot x$$
>
> - $s_j = \max(|x_j|)^{\alpha}$ — per-channel scale, $\alpha \in [0,1]$ grid-searched on a small calibration set to minimize MSE.
> - Salient channels see a smaller *relative* quantization error because their dynamic range is widened pre-quantization; the inverse scale on activations preserves the linear-layer output exactly in FP, approximately under quantization.
>
> **Cost**: zero runtime overhead (scales fused into the preceding RMSNorm or pre-multiplied into weights). <1% perplexity gap vs FP16 on Llama-7B at INT4.

#### GPTQ (per-column OBQ with Cholesky)

> GPTQ quantizes weights one column at a time. After quantizing column $q$, it propagates the resulting error into the unquantized columns $F$ via a closed-form update derived from the layer's Hessian $\mathbf{H} = 2\mathbf{X}\mathbf{X}^\top$:
>
> $$\mathbf{w}_F \leftarrow \mathbf{w}_F - \frac{w_q - \mathrm{quant}(w_q)}{[\mathbf{H}^{-1}]_{qq}} \cdot [\mathbf{H}^{-1}]_{F,q}$$
>
> - $w_q$ — current column being quantized.
> - $[\mathbf{H}^{-1}]_{F,q}$ — column $q$ of the inverse Hessian, restricted to rows $F$.
> - The Cholesky factorization of $\mathbf{H}^{-1}$ is computed once and reused across columns, making one transformer block quantizable in minutes on a single GPU.
>
> **Cost**: post-training (no fine-tuning), ~3-4 bit weights with negligible perplexity loss for OPT/BLOOM-scale models.

#### KIVI (asymmetric KV-cache quantization)

> KIVI quantizes the K cache **per channel** and the V cache **per token**, because the two play different roles in attention:
>
> - **K** participates in $\mathrm{softmax}(QK^\top)$ — a few outlier channels carry most of the score signal, so per-channel quantization preserves them.
> - **V** is just a value lookup weighted by attention — per-token quantization keeps each accessed value precise.
>
> $$\tilde{K}_{i,j} = \mathrm{round}\!\left(\frac{K_{i,j} - z^K_j}{s^K_j}\right), \quad \tilde{V}_{i,j} = \mathrm{round}\!\left(\frac{V_{i,j} - z^V_i}{s^V_i}\right)$$
>
> The 2-bit version recovers ≈99% of FP16 quality on long-context tasks while shrinking KV memory by 8×.

#### KVzip (query-agnostic KV importance via context reconstruction)

> KVzip scores each KV pair by how much **reconstructing the original context** depends on it, not by how much a *specific* query attends to it. The score for token position $t$ in layer $\ell$, head $h$:
>
> $$\mathrm{imp}_{\ell,h,t} = \max_{q \in \mathcal{Q}_{\mathrm{recon}}} A_{\ell,h}(q, t)$$
>
> - $\mathcal{Q}_{\mathrm{recon}}$ — reconstruction queries (essentially: ask the model to repeat its own context).
> - $A_{\ell,h}(q,t)$ — attention weight from query $q$ to position $t$ in head $h$.
>
> Because the score is query-agnostic, one compressed cache serves arbitrary future queries on the same context — unlike SnapKV/H2O which need to know the query first.
>
> **Cost**: one extra forward pass per context to compute scores; afterwards the compressed cache plugs into standard inference.

#### SmoothQuant (W8A8 with activation difficulty migration)

> Activation outliers are concentrated in a few channels and break naive INT8 quantization of activations. SmoothQuant moves the difficulty from activations to weights via a per-channel scale, mathematically equivalent to a no-op:
>
> $$\mathbf{Y} = (\mathbf{X} \cdot \mathrm{diag}(s)^{-1}) \cdot (\mathrm{diag}(s) \cdot \mathbf{W})$$
>
> - $s_j = \max(|X_j|)^{\alpha} / \max(|W_j|)^{1-\alpha}$ — balances the smoothing between $X$ and $W$.
> - $\alpha \in [0,1]$ — migration strength; 0.5 is the default.
>
> $\mathrm{diag}(s)^{-1}$ is fused into the previous LayerNorm; $\mathrm{diag}(s) \cdot \mathbf{W}$ is precomputed at quantization time. Both quantize cleanly to INT8.

---

## Obsidian → Notion content transforms

When moving content between vault and Notion, the following substitutions happen consistently. Apply them at the source so the destination renders cleanly.

| Obsidian source | Notion destination | Rationale |
|-----------------|--------------------|-----------|
| `[[Page Name]]` | `「Page Name」` (text form) | Notion mentions need page IDs, which only exist after the destination page is created. Convert to text first; resolve to mentions in a second pass. |
| `[[Page Name\|alias]]` | `「alias」` | Carry the alias forward; the second-pass mention can still point to the right URL. |
| `[file](../99-附件/foo.pdf)` | `[arXiv 2505.23416](https://arxiv.org/abs/2505.23416)` | Local PDF paths break in Notion. Replace with the canonical web URL. |
| `[snippet](/Users/.../file.py)` | `file.py:42` (plain text) | Local code paths are dead links in Notion; preserve the filename + line number for navigation. |
| `![[image.png]]` (vault embed) | upload via `notion-create-page` attachment, or describe in text | Vault image embeds don't survive migration. Either upload separately or replace with a text description. |
| Math `$x$` / `$$...$$` | same syntax | Notion supports LaTeX inline and block math. |

---

## Cross-page mention conversion (the second pass)

After all pages exist in the destination Notion database, sweep through and convert `「Page Title」` text references into real mentions:

```
<mention-page url="https://www.notion.so/PAGE-ID" />
```

The page ID is the trailing 32-char hex in the page URL.

### Process

1. **Build a title → page-ID map once** via `notion-search` against the database. Cache it for the whole sweep — you'll reuse it for every page.
2. **For each page, in batches of 3:**
   - `notion-fetch` the page body.
   - Extract all `「...」` patterns via regex.
   - For each match, look up the page ID; if not in the map, skip (likely refers to a page outside the database, e.g. an overview page).
   - Build a list of `search_replace` patches.
3. **Submit patches via `update_content`**, up to 5 in parallel.
4. **Verify by re-fetching one or two pages** at random and confirming the mentions render.

### Edge cases

- **Title contains punctuation or trailing colon**: search-and-replace is exact-match. Strip trailing punctuation before lookup.
- **Same title appears in body text without `「」`**: don't blindly replace — only the bracketed form is a deliberate cross-link. Naked title strings are often just prose.
- **Title was renamed in Notion**: the old title in the source vault won't match. Maintain a manual alias map for renamed pages.

---

## Database schema discovery

Before any `notion-create-pages` call against a database, run `notion-fetch` on the **data source** (not a single page in the database). The response includes:

- Property names and types (title, rich_text, multi_select, status, date, url, ...)
- Multi-select option lists (so you don't submit invalid values)
- Status enum values and their groupings
- Required vs optional fields

This prevents the "validation error on submit" cycle and means you can map vault frontmatter to Notion properties without guessing.

---

## Sync back to vault

If you upgrade a Notion page during enhancement (added formulas, fixed cross-links, restructured a section), **also sync the upgrade back to the source vault `.md` file**. Otherwise:

- The vault drifts out of sync, and the next migration overwrites your improvements.
- Future `auto-survey` runs that read the vault as a source will surface the old, unimproved version.

The sync direction is asymmetric: vault is the long-term source of truth for *what was read*; Notion is the working surface for *cross-paper structure*. Both should reflect the same content.

---

## What not to do

- Don't read the whole vault folder with `cat *` or unbounded `Read` — `ls` and `wc -l` first, then targeted reads.
- Don't fetch 5+ Notion paper pages in parallel. Default to 3, drop to 1 when in doubt.
- Don't rewrite a whole Notion page when only a paragraph changes — use `update_content` in search-and-replace mode.
- Don't migrate a note without first verifying the destination database schema via `notion-fetch` on the data source.
- Don't leave a method named without a formula if the method is central to the paper's claim. That's the gap this whole sub-mode exists to close.
- Don't fabricate citations or formula details. If uncertain about a formula's exact form, mark it `<!-- TODO: verify against source -->` and check the paper PDF or arXiv abstract before claiming it.
- Don't retry a "Request too large" failure with the same batch size — halve concurrency or split the payload.
