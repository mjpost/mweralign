#!/usr/bin/env python3
"""
Quantify how many WMT24 realignment boundary errors a small set of
*punctuation-placement heuristics* would fix.

Because the domain-merged hypothesis is exactly the system's own concatenated
output, the realigned token stream is identical to the original and the only
question is *where the segment boundaries fall*. For every interior boundary we
know the "gold" boundary (the system's original segmentation) and mweralign's
boundary. This script measures, for each candidate post-processing heuristic,
how many shifted boundaries it would move back onto the gold position -- and,
importantly, how many *correct* boundaries it would break (false positives).

Heuristics evaluated (applied to the boundary between realigned seg k and k+1):

  H1 pull_leading_close   - if seg(k+1) starts with closing punctuation
                            (. , ; : ! ? ) ] } » " " etc.), move that run to the
                            end of seg(k).  ["punct at end, not beginning"]
  H2 push_trailing_open   - if seg(k) ends with opening punctuation
                            (( [ { « " „ ¿ ¡ etc.), move that run to the start of
                            seg(k+1).
  H3 both                 - apply H1 then H2.

For each heuristic we report, over all interior boundaries:
  candidates  - boundaries the heuristic would touch
  fixed       - shifted boundaries it moves exactly onto gold
  broke       - already-correct boundaries it moves off gold
  net         - fixed - broke

A separate breakdown excludes degenerate systems (those whose mean reference
length per segment collapses, e.g. quote-spam) by skipping systems flagged on
the command line, so the numbers reflect realistic MT output.

Usage::

    python -m scripts.experiments.punct_heuristics                 # all pairs
    python -m scripts.experiments.punct_heuristics -l en-de cs-uk
    python -m scripts.experiments.punct_heuristics --skip-systems CycleL CycleL2

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from collections import Counter
from typing import List, Tuple

from . import data, realign

# Closing punctuation that should attach to the *preceding* token/sentence.
CLOSING = set(".,;:!?)]}»”’\"'…。、，！？；：）】」』〕》")
# Opening punctuation that should attach to the *following* token/sentence.
OPENING = set("([{«„“‘¿¡（【「『〔《")


def _is_punct(tok: str) -> bool:
    return bool(tok) and all(unicodedata.category(c)[0] in ("P", "S") for c in tok)


def _is_closing(tok: str) -> bool:
    return _is_punct(tok) and any(c in CLOSING for c in tok)


def _is_opening(tok: str) -> bool:
    return _is_punct(tok) and any(c in OPENING for c in tok)


def _gold_boundaries(segs: List[List[str]]) -> List[int]:
    out, total = [], 0
    for seg in segs[:-1]:  # interior only
        total += len(seg)
        out.append(total)
    return out


def _leading_close_run(tokens: List[str]) -> int:
    n = 0
    for t in tokens:
        if _is_closing(t):
            n += 1
        else:
            break
    return n


def _trailing_open_run(tokens: List[str]) -> int:
    n = 0
    for t in reversed(tokens):
        if _is_opening(t):
            n += 1
        else:
            break
    return n


class Tally:
    def __init__(self) -> None:
        self.interior = 0
        self.shifted = 0
        self.h1 = Counter()  # candidates / fixed / broke
        self.h2 = Counter()
        self.h3 = Counter()


def analyze_system(lp: str, system: str, tally: Tally) -> None:
    manual = data.system_output(lp, system)
    realigned = realign.realign_system(lp, system, "none")
    groups = data.domain_groups(data.domains(lp))

    for _dom, idxs in groups.items():
        gold = [manual[i].split() for i in idxs]
        got = [realigned[i].split() for i in idxs]
        gold_b = _gold_boundaries(gold)
        got_b = _gold_boundaries(got)

        for k in range(len(idxs) - 1):
            tally.interior += 1
            gb, rb = gold_b[k], got_b[k]
            shifted = gb != rb
            if shifted:
                tally.shifted += 1

            seg_k = got[k]
            seg_k1 = got[k + 1]

            # H1: pull leading closing-punct of seg(k+1) back to seg(k).
            lc = _leading_close_run(seg_k1)
            if lc:
                tally.h1["candidates"] += 1
                new_b = rb + lc
                _credit(tally.h1, rb, new_b, gb)

            # H2: push trailing opening-punct of seg(k) forward to seg(k+1).
            to = _trailing_open_run(seg_k)
            if to:
                tally.h2["candidates"] += 1
                new_b = rb - to
                _credit(tally.h2, rb, new_b, gb)

            # H3: combined effect on this boundary.
            new_b = rb + lc - to
            if lc or to:
                tally.h3["candidates"] += 1
                _credit(tally.h3, rb, new_b, gb)


def _credit(counter: Counter, old_b: int, new_b: int, gold_b: int) -> None:
    if new_b == old_b:
        return
    if old_b != gold_b and new_b == gold_b:
        counter["fixed"] += 1
    elif old_b == gold_b and new_b != gold_b:
        counter["broke"] += 1
    elif old_b != gold_b and new_b != gold_b:
        # Moved but still wrong; note whether it got closer.
        counter["moved_still_wrong"] += 1


def _report_block(name: str, c: Counter, out) -> None:
    fixed, broke = c["fixed"], c["broke"]
    print(f"  {name:18s} candidates={c['candidates']:6d} "
          f"fixed={fixed:6d} broke={broke:6d} "
          f"net={fixed - broke:+6d} still_wrong={c['moved_still_wrong']:6d}",
          file=out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("-l", "--langpairs", nargs="+", default=None)
    parser.add_argument("-s", "--systems", nargs="+", default=None)
    parser.add_argument("--skip-systems", nargs="+", default=[],
                        help="System names to exclude (e.g. degenerate baselines).")
    parser.add_argument("--max-systems", type=int, default=None)
    args = parser.parse_args(argv)

    langpairs = args.langpairs or data.langpairs()
    skip = set(args.skip_systems)
    tally = Tally()

    for lp in langpairs:
        sys_list = args.systems or data.systems(lp)
        sys_list = [s for s in sys_list if s not in skip]
        if args.max_systems:
            sys_list = sys_list[: args.max_systems]
        for system in sys_list:
            try:
                analyze_system(lp, system, tally)
            except Exception as exc:  # noqa: BLE001
                print(f"! {lp}/{system}: {exc}", file=sys.stderr)
            print(f"  done {lp:7s} {system}", file=sys.stderr)

    out = sys.stdout
    print("=" * 78, file=out)
    print("Punctuation-heuristic fixability on WMT24 realignment (segmenter=none)",
          file=out)
    print("=" * 78, file=out)
    print(f"interior boundaries : {tally.interior}", file=out)
    pct = 100.0 * tally.shifted / tally.interior if tally.interior else 0.0
    print(f"shifted boundaries  : {tally.shifted}  ({pct:.2f}%)", file=out)
    if skip:
        print(f"excluded systems    : {', '.join(sorted(skip))}", file=out)
    print("", file=out)
    print("heuristic effect (per interior boundary):", file=out)
    _report_block("H1 pull_close", tally.h1, out)
    _report_block("H2 push_open", tally.h2, out)
    _report_block("H3 both", tally.h3, out)
    print("", file=out)
    print("Legend: fixed = shifted boundary moved exactly onto gold; "
          "broke = correct boundary moved off gold; net = fixed - broke.", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
