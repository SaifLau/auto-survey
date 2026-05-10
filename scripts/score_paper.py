#!/usr/bin/env python3
"""score_paper.py — heuristic relevance score (1-5) for a paper vs topic.

This is a *cheap* keyword-overlap heuristic, not a semantic match. SKILL.md is
expected to do the real semantic re-ranking via the LLM. The heuristic exists
so that:
  - we never have to ship un-scored papers downstream;
  - the LLM can be primed with a deterministic prior;
  - in pure-batch mode (no LLM available) we still produce *some* ordering.

CLI:
    python3 score_paper.py --topic "..." --title "..." --abstract "..."

Stdout: JSON {"score": int 1-5, "reasons": ["overlap=...", "year_recent", ...]}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Iterable

STOPWORDS = {
    "a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "with", "by",
    "is", "are", "was", "were", "be", "been", "this", "that", "these", "those",
    "it", "its", "as", "at", "from", "we", "our", "you", "your", "their", "there",
    "such", "via", "using", "use", "based", "approach", "method", "model", "models",
    "paper", "study", "results", "result", "show", "shown", "propose", "proposed",
}


def tokenize(text: str) -> list[str]:
    """Tokenize for Jaccard. Pulls ASCII words AND each CJK ideograph as its
    own token. The CJK split is character-level (no segmenter) — coarse but
    enough for the heuristic prior."""
    text = text.lower()
    ascii_tokens = [
        t for t in re.findall(r"[a-zA-Z][a-zA-Z\-]+", text)
        if t not in STOPWORDS and len(t) > 2
    ]
    # Each CJK char treated as a token (covers Chinese, Japanese, Korean Hanja).
    cjk_tokens = re.findall(r"[一-鿿㐀-䶿]", text)
    return ascii_tokens + cjk_tokens


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def score(topic: str, title: str, abstract: str = "", year: int | None = None,
          topic_en: str = "") -> dict:
    """Score paper relevance against topic (and optional English alias).

    Two overlaps are computed: one against `topic`, one against `topic + topic_en`.
    The max is used. This handles the common case of a CJK-only topic whose
    canonical literature is published in English — the alias bridges the gap.
    """
    topic_tok = tokenize(topic)
    title_tok = tokenize(title)
    abs_tok = tokenize(abstract)

    j_title = jaccard(topic_tok, title_tok)
    j_abs = jaccard(topic_tok, abs_tok) if abs_tok else 0.0
    overlap_topic = 0.6 * j_title + 0.4 * j_abs

    overlap_en = 0.0
    if topic_en:
        en_tok = tokenize(topic_en)
        j_title_en = jaccard(en_tok, title_tok)
        j_abs_en = jaccard(en_tok, abs_tok) if abs_tok else 0.0
        overlap_en = 0.6 * j_title_en + 0.4 * j_abs_en

    overlap = max(overlap_topic, overlap_en)
    src = "topic" if overlap_topic >= overlap_en else "topic_en"

    # Map [0, 1] overlap to {1..5}.
    if overlap >= 0.30:
        s = 5
    elif overlap >= 0.20:
        s = 4
    elif overlap >= 0.12:
        s = 3
    elif overlap >= 0.05:
        s = 2
    else:
        s = 1

    reasons = [f"overlap={overlap:.2f}({src})"]

    # Recency bump: +1 if within last 2 years, capped at 5.
    if year:
        try:
            cur_year = datetime.now(timezone.utc).year
            if cur_year - int(year) <= 2:
                if s < 5:
                    s += 1
                    reasons.append("year_recent_bump")
        except (TypeError, ValueError):
            pass

    return {"score": s, "reasons": reasons, "overlap": round(overlap, 3)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--topic", required=True)
    p.add_argument("--topic-en", default="",
                   help="Optional English alias for non-ASCII topics; scores against both, takes max")
    p.add_argument("--title", required=True)
    p.add_argument("--abstract", default="")
    p.add_argument("--year", type=int, default=None)
    args = p.parse_args()
    print(json.dumps(score(args.topic, args.title, args.abstract, args.year,
                           topic_en=args.topic_en)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
