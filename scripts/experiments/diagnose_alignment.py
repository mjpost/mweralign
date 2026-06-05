#!/usr/bin/env python3
"""
Diagnose alignment errors in mweralign over the complete WMT24 data.

For each (language pair, system) the system's outputs are merged by **domain**
(less constrained than per-document merging) and realigned back to the
reference segmentation with mweralign. Because the merged hypothesis is exactly
the concatenation of the system's own segments, the token stream is preserved
and a *perfect* re-aligner would reproduce the original segment boundaries.
Any boundary that lands elsewhere is therefore a concrete misalignment.

The diagnostic classifies the failures, with special attention to the cues
mentioned for heuristic fixes:

* ``leading_punct``  - a realigned segment *starts* with punctuation (the prime
                       candidate for a "keep punctuation at the end of the
                       previous sentence" heuristic).
* ``empty_segment``  - a reference segment received no hypothesis tokens (its
                       words were absorbed by a neighbour -> "unaligned" gap).
* ``trailing_steal`` - a realigned segment ends by stealing the next segment's
                       leading word(s).
* ``boundary_shift`` - any interior boundary that differs from the original;
                       reported with whether the drifted tokens are punctuation.

Usage::

    # All 11 pairs, whitespace segmenter (default), full report to a file.
    python -m scripts.experiments.diagnose_alignment -o align-diagnosis.txt

    # Quick look at one pair / a few systems.
    python -m scripts.experiments.diagnose_alignment -l en-de --max-systems 3

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from . import data, realign


# --------------------------------------------------------------------------- #
# Token classification
# --------------------------------------------------------------------------- #

# Characters that are "punctuation" for the start/end-of-sentence cue. We treat
# a token as punctuation if every character is a Unicode punctuation/symbol mark
# (categories P* and S*), covering ASCII (. , ; : ! ? ) " ' - ...) as well as
# CJK and typographic marks (。 、 ， 」 ）" " „ « » … · etc.).
def is_punct_token(tok: str) -> bool:
    if not tok:
        return False
    return all(unicodedata.category(ch)[0] in ("P", "S") for ch in tok)


# Closing punctuation that, when it *starts* a segment, almost certainly belongs
# to the end of the previous one.
_CLOSING = set(".,;:!?)]}»”’\"'…。、，！？；：）】」』")


def starts_with_closing_punct(tokens: List[str]) -> bool:
    return bool(tokens) and is_punct_token(tokens[0]) and any(
        ch in _CLOSING for ch in tokens[0]
    )


# --------------------------------------------------------------------------- #
# Per-system analysis
# --------------------------------------------------------------------------- #

@dataclass
class Example:
    langpair: str
    system: str
    seg_index: int
    prev_realigned: str
    manual: str
    realigned: str


@dataclass
class Stats:
    n_segments: int = 0
    n_interior_boundaries: int = 0
    n_shifted_boundaries: int = 0
    category_counts: Counter = field(default_factory=Counter)
    shift_sizes: Counter = field(default_factory=Counter)
    examples: dict = field(default_factory=lambda: {})

    def add_example(self, category: str, ex: Example, cap: int) -> None:
        bucket = self.examples.setdefault(category, [])
        if len(bucket) < cap:
            bucket.append(ex)


def analyze_system(
    langpair: str,
    system: str,
    segmenter: str,
    stats: Stats,
    example_cap: int,
) -> None:
    manual = data.system_output(langpair, system)
    realigned = realign.realign_system(langpair, system, segmenter)
    domain_labels = data.domains(langpair)
    groups = data.domain_groups(domain_labels)

    for _domain, idxs in groups.items():
        man_segs = [manual[i].split() for i in idxs]
        re_segs = [realigned[i].split() for i in idxs]

        stats.n_segments += len(idxs)

        # Direct symptom scans (independent of boundary math).
        for pos, i in enumerate(idxs):
            re_tok = re_segs[pos]
            man_tok = man_segs[pos]
            prev_re = " ".join(re_segs[pos - 1]) if pos > 0 else ""

            if not re_tok and man_tok:
                stats.category_counts["empty_segment"] += 1
                stats.add_example(
                    "empty_segment",
                    Example(langpair, system, i, prev_re,
                            " ".join(man_tok), " ".join(re_tok)),
                    example_cap,
                )
            elif starts_with_closing_punct(re_tok) and not starts_with_closing_punct(man_tok):
                stats.category_counts["leading_punct"] += 1
                stats.add_example(
                    "leading_punct",
                    Example(langpair, system, i, prev_re,
                            " ".join(man_tok), " ".join(re_tok)),
                    example_cap,
                )

        # Boundary-shift analysis on the shared token stream.
        man_off = _offsets(man_segs)
        re_off = _offsets(re_segs)
        # Interior boundaries only (exclude the final domain boundary).
        for k in range(len(idxs) - 1):
            stats.n_interior_boundaries += 1
            mb, rb = man_off[k], re_off[k]
            if mb == rb:
                continue
            stats.n_shifted_boundaries += 1
            shift = rb - mb
            stats.shift_sizes[_bucket(shift)] += 1

            flat = [t for seg in man_segs for t in seg]
            drifted = flat[min(mb, rb):max(mb, rb)]
            all_punct = bool(drifted) and all(is_punct_token(t) for t in drifted)
            if all_punct:
                stats.category_counts["punct_drift"] += 1
            else:
                stats.category_counts["word_drift"] += 1

            if rb < mb and any(is_punct_token(t) for t in drifted):
                # Boundary moved left: punctuation now leads the next segment.
                i = idxs[k + 1]
                stats.add_example(
                    "punct_to_next_start",
                    Example(langpair, system, i,
                            " ".join(re_segs[k]),
                            " ".join(man_segs[k + 1]),
                            " ".join(re_segs[k + 1])),
                    example_cap,
                )
                stats.category_counts["punct_to_next_start"] += 1


def _offsets(segs: List[List[str]]) -> List[int]:
    """Cumulative token offset after each segment (boundary positions)."""
    out, total = [], 0
    for seg in segs:
        total += len(seg)
        out.append(total)
    return out


def _bucket(shift: int) -> str:
    if shift < 0:
        return f"-{_mag(-shift)}"
    return f"+{_mag(shift)}"


def _mag(n: int) -> str:
    if n == 1:
        return "1"
    if n <= 3:
        return "2-3"
    if n <= 10:
        return "4-10"
    return ">10"


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #

def write_report(stats: Stats, out, segmenter: str) -> None:
    p = lambda *a: print(*a, file=out)  # noqa: E731
    p("=" * 78)
    p(f"mweralign WMT24 alignment diagnosis  (segmenter={segmenter}, domain merge)")
    p("=" * 78)
    p(f"segments analysed           : {stats.n_segments}")
    p(f"interior boundaries         : {stats.n_interior_boundaries}")
    sh = stats.n_shifted_boundaries
    pct = 100.0 * sh / stats.n_interior_boundaries if stats.n_interior_boundaries else 0.0
    p(f"shifted boundaries          : {sh}  ({pct:.2f}%)")
    p("")
    p("category counts:")
    for cat, n in stats.category_counts.most_common():
        p(f"  {cat:22s} {n}")
    p("")
    p("boundary shift sizes (realigned - original, in tokens):")
    for size, n in sorted(stats.shift_sizes.items()):
        p(f"  {size:>5s} {n}")
    p("")

    for cat in ("leading_punct", "punct_to_next_start", "empty_segment"):
        exs = stats.examples.get(cat, [])
        if not exs:
            continue
        p("-" * 78)
        p(f"EXAMPLES: {cat}  (showing {len(exs)})")
        p("-" * 78)
        for ex in exs:
            p(f"[{ex.langpair} / {ex.system} / seg {ex.seg_index}]")
            if ex.prev_realigned:
                p(f"  prev (realigned): ...{_tail(ex.prev_realigned)}")
            p(f"  manual          : {ex.manual}")
            p(f"  realigned       : {ex.realigned}")
            p("")


def _tail(text: str, n: int = 8) -> str:
    toks = text.split()
    return " ".join(toks[-n:])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("-l", "--langpairs", nargs="+", default=None,
                        help="Language pairs (default: all 11).")
    parser.add_argument("-s", "--systems", nargs="+", default=None,
                        help="System names (default: all for each pair).")
    parser.add_argument("--segmenter", default="none",
                        choices=list(realign.SEGMENTERS),
                        help="Segmenter to use (default: none / whitespace).")
    parser.add_argument("--max-systems", type=int, default=None,
                        help="Limit systems per pair (smoke testing).")
    parser.add_argument("--max-examples", type=int, default=40,
                        help="Examples to keep per category (default: 40).")
    parser.add_argument("-o", "--output", default=None,
                        help="Write the full report here (default: stdout).")
    args = parser.parse_args(argv)

    langpairs = args.langpairs or data.langpairs()
    stats = Stats()

    for lp in langpairs:
        if args.segmenter == "cj" and data.target_language(lp) not in ("zh", "ja"):
            continue
        sys_list = args.systems or data.systems(lp)
        if args.max_systems:
            sys_list = sys_list[: args.max_systems]
        for system in sys_list:
            try:
                analyze_system(lp, system, args.segmenter, stats, args.max_examples)
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"! {lp}/{system}: {exc}", file=sys.stderr)
            print(f"  done {lp:7s} {system}", file=sys.stderr)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            write_report(stats, fh, args.segmenter)
        write_report(stats, sys.stdout, args.segmenter)  # also digest to stdout
        print(f"\nFull report written to {args.output}")
    else:
        write_report(stats, sys.stdout, args.segmenter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
