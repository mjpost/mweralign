#!/usr/bin/env python3
"""
Error analysis of mweralign segmentation restoration.

Because the restoration round-trip preserves the character stream and emits
exactly one segment per reference segment, the realigned output has the *same
number of segments* as the gold (original) segmentation. Every mistake is
therefore a **boundary displacement**: interior boundary ``k`` sits at word
offset ``got_k`` instead of the gold offset ``gold_k``. The signed error
``got_k - gold_k`` (in words, for the whitespace ``none`` segmenter) is a clean
diagnostic signal.

This script samples systems, re-runs the realignment, and characterizes the
errors:

* **magnitude**   - exact / off-by-1-2 / larger; signed (left vs right bias).
* **clustering**  - run lengths of consecutive non-exact boundaries (a slipped
  region where the DP wandered and several boundaries shift together).
* **content at the error site** - what lies in the "moved span" of words
  between the gold and realigned boundary:
    - ``punct``  : only punctuation/symbols moved across the boundary
    - ``repeat`` : a word at the boundary also occurs inside the moved span
      (genuine local ambiguity - the surface edit distance cannot disambiguate)
    - ``numeric``: digits in the moved span (list items, dates, prices)
    - ``other``
* **segment length** - are short reference segments disproportionately wrong?

A handful of concrete example error sites are printed for the writeup.

Usage::

    python -m scripts.experiments.error_analysis --segmenter none --per-lp 6
    python -m scripts.experiments.error_analysis --segmenter spm256k --per-lp 4

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import random
import sys
import unicodedata
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

from . import data, realign


def _is_punct(tok: str) -> bool:
    """True if the token is entirely punctuation/symbol characters."""
    return bool(tok) and all(
        unicodedata.category(ch)[0] in ("P", "S") for ch in tok)


def _has_digit(tok: str) -> bool:
    return any(ch.isdigit() for ch in tok)


def _is_short(tok: str) -> bool:
    """A short, low-content token (function word, particle, attached punct)."""
    core = "".join(ch for ch in tok if unicodedata.category(ch)[0] not in ("P", "S"))
    return len(core) <= 3


def _classify_span(span: List[str]) -> str:
    """Mutually exclusive bucket for the words moved across the boundary."""
    if not span:
        return "other"
    if all(_is_punct(w) for w in span):
        return "punct"
    if any(_has_digit(w) for w in span):
        return "numeric"
    if all(_is_short(w) for w in span):
        return "short_word"   # function words / particles / attached punct
    return "content_word"


def _word_boundaries(segs: List[List[str]]) -> List[int]:
    """Interior boundaries as cumulative word counts."""
    out, total = [], 0
    for s in segs[:-1]:
        total += len(s)
        out.append(total)
    return out


def analyze_group(gold_words: List[List[str]], got_words: List[List[str]],
                  acc: dict, examples: list, ctx: Tuple[str, str, str]) -> None:
    """Accumulate error statistics for one domain-merged group.

    ``gold_words`` / ``got_words`` are per-segment word lists with identical
    total word streams and identical segment counts.
    """
    merged = [w for seg in gold_words for w in seg]  # the shared word stream
    gold_b = _word_boundaries(gold_words)
    got_b = _word_boundaries(got_words)
    if len(gold_b) != len(got_b):
        # Should not happen (segment counts match); guard anyway.
        acc["count_mismatch"] += 1
        return

    nonexact_flags = []
    for k, (g, r) in enumerate(zip(gold_b, got_b)):
        disp = r - g
        acc["n_boundaries"] += 1
        # Segment length of the gold segment ending at this boundary.
        seg_len = len(gold_words[k])
        if disp == 0:
            acc["exact"] += 1
            nonexact_flags.append(0)
            acc["len_exact"].append(seg_len)
            continue
        nonexact_flags.append(1)
        acc["len_error"].append(seg_len)

        adisp = abs(disp)
        acc["disp_hist"][max(-9, min(9, disp))] += 1
        if adisp <= 2:
            acc["minor"] += 1
        else:
            acc["major"] += 1
        acc["right" if disp > 0 else "left"] += 1

        # Content of the moved span: words between the two boundary positions.
        lo, hi = sorted((g, r))
        span = merged[lo:hi]
        # Boundary-adjacent words (in the merged stream).
        before = merged[g - 1] if g - 1 >= 0 else ""
        after = merged[g] if g < len(merged) else ""

        cat = _classify_span(span)
        acc["content"][cat] += 1

        # Whether the boundary ought to fall right after sentence-final punct.
        if before and before[-1] in ".?!。！？":
            acc["after_sentence_punct"] += 1

        # Local repetition/parallelism: the gold boundary word recurs within a
        # small window -> a genuine surface ambiguity the edit distance cannot
        # resolve (precisely the case a semantic model could disambiguate).
        window = merged[max(0, g - 6):g] + merged[g:g + 6]
        if after and window.count(after) >= 2:
            acc["local_repeat"] += 1

        if len(examples) < acc["max_examples"] and adisp <= 6:
            lp, system, dom = ctx
            examples.append({
                "lp": lp, "system": system, "domain": dom,
                "disp": disp, "cat": cat,
                "gold": " ".join(gold_words[k]) + " | " + " ".join(gold_words[k + 1]),
                "got": " ".join(got_words[k]) + " | " + " ".join(got_words[k + 1]),
            })

    # Run lengths of consecutive non-exact boundaries.
    run = 0
    for f in nonexact_flags:
        if f:
            run += 1
        elif run:
            acc["runlen"][min(run, 9)] += 1
            run = 0
    if run:
        acc["runlen"][min(run, 9)] += 1


def new_acc(max_examples: int) -> dict:
    return {
        "n_boundaries": 0, "exact": 0, "minor": 0, "major": 0,
        "left": 0, "right": 0, "count_mismatch": 0,
        "disp_hist": Counter(), "runlen": Counter(), "content": Counter(),
        "len_exact": [], "len_error": [], "max_examples": max_examples,
        "n_systems": 0, "n_char_mismatch": 0,
        "after_sentence_punct": 0, "local_repeat": 0,
    }


def _nonspace(s: str) -> str:
    return "".join(s.split())


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("-l", "--langpairs", nargs="+", default=None)
    ap.add_argument("--segmenter", default="none", choices=list(realign.SEGMENTERS))
    ap.add_argument("--per-lp", type=int, default=6,
                    help="Systems sampled per language pair.")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--max-examples", type=int, default=24)
    args = ap.parse_args(argv)

    rng = random.Random(args.seed)
    langpairs = args.langpairs or data.langpairs()
    acc = new_acc(args.max_examples)
    examples: list = []
    per_lp_rate: Dict[str, Tuple[int, int]] = {}

    for lp in langpairs:
        systems = list(data.systems(lp))
        rng.shuffle(systems)
        systems = systems[: args.per_lp]
        groups = data.domain_groups(data.domains(lp))
        lp_b = lp_ok = 0
        for system in systems:
            manual = data.system_output(lp, system)
            try:
                realigned = realign.realign_system(lp, system, args.segmenter)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {lp}/{system}: {type(exc).__name__}", file=sys.stderr)
                continue
            acc["n_systems"] += 1
            for dom, idxs in groups.items():
                gold = [manual[i] for i in idxs]
                got = [realigned[i] for i in idxs]
                if "".join(_nonspace(s) for s in gold) != \
                        "".join(_nonspace(s) for s in got):
                    acc["n_char_mismatch"] += 1
                    continue
                gw = [s.split() for s in gold]
                rw = [s.split() for s in got]
                before_b = acc["n_boundaries"]
                before_e = acc["exact"]
                analyze_group(gw, rw, acc, examples, (lp, system, dom))
                lp_b += acc["n_boundaries"] - before_b
                lp_ok += acc["exact"] - before_e
            print(f"  done {lp:7s} {system}", file=sys.stderr)
        per_lp_rate[lp] = (lp_ok, lp_b)

    _report(args, acc, examples, per_lp_rate, langpairs)
    return 0


def _pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "  n/a"


def _report(args, acc, examples, per_lp_rate, langpairs) -> None:
    nb = acc["n_boundaries"]
    print("\n" + "=" * 70)
    print(f"ERROR ANALYSIS  segmenter={args.segmenter}  "
          f"systems={acc['n_systems']}  boundaries={nb:,}")
    print("=" * 70)
    if not nb:
        print("no boundaries analyzed (all char-mismatch?)")
        print(f"char-mismatch groups: {acc['n_char_mismatch']}")
        return

    err = nb - acc["exact"]
    print(f"\nMagnitude (of {nb:,} interior boundaries):")
    print(f"  exact            {acc['exact']:7d}  {_pct(acc['exact'], nb)}")
    print(f"  off by 1-2 words {acc['minor']:7d}  {_pct(acc['minor'], nb)}"
          f"   ({_pct(acc['minor'], err)} of errors)")
    print(f"  off by >2 words  {acc['major']:7d}  {_pct(acc['major'], nb)}"
          f"   ({_pct(acc['major'], err)} of errors)")
    print(f"\nDirection of error (n={err:,}):")
    print(f"  boundary too early (left)  {acc['left']:7d}  {_pct(acc['left'], err)}")
    print(f"  boundary too late  (right) {acc['right']:7d}  {_pct(acc['right'], err)}")

    print("\nSigned displacement histogram (words; -9/+9 = that or beyond):")
    for d in range(-9, 10):
        c = acc["disp_hist"].get(d, 0)
        if c:
            bar = "#" * max(1, int(60 * c / max(acc["disp_hist"].values())))
            tag = f"{d:+d}" if abs(d) < 9 else (f"<={d}" if d < 0 else f">={d}")
            print(f"  {tag:>4s} {c:6d} {bar}")

    print(f"\nContent at error site (what moved across the boundary, n={err:,}):")
    for cat in ("punct", "short_word", "numeric", "content_word", "other"):
        c = acc["content"].get(cat, 0)
        print(f"  {cat:12s} {c:7d}  {_pct(c, err)}")

    print("\nDiagnostic flags on error sites:")
    print(f"  gold boundary follows sentence-final punctuation: "
          f"{_pct(acc['after_sentence_punct'], err)}")
    print(f"  boundary word recurs locally (genuine ambiguity): "
          f"{_pct(acc['local_repeat'], err)}")

    print("\nError clustering (run lengths of consecutive wrong boundaries):")
    tot_runs = sum(acc["runlen"].values())
    for r in sorted(acc["runlen"]):
        c = acc["runlen"][r]
        tag = f"{r}" if r < 9 else ">=9"
        print(f"  run of {tag:>3s}: {c:6d}  {_pct(c, tot_runs)} of runs")

    import statistics as st
    if acc["len_exact"] and acc["len_error"]:
        print("\nGold segment length (words) at boundary:")
        print(f"  correct boundaries: median={st.median(acc['len_exact']):.0f}  "
              f"mean={st.mean(acc['len_exact']):.1f}")
        print(f"  wrong   boundaries: median={st.median(acc['len_error']):.0f}  "
              f"mean={st.mean(acc['len_error']):.1f}")

    print("\nPer-language-pair boundary accuracy (sampled):")
    for lp in langpairs:
        ok, b = per_lp_rate.get(lp, (0, 0))
        print(f"  {lp:8s} {_pct(ok, b)}  (n={b:,})")

    print(f"\nExample error sites (showing gold ||boundary|| vs realigned):")
    for ex in examples[: args.max_examples]:
        print(f"\n  [{ex['lp']}/{ex['system']}  {ex['cat']}  disp={ex['disp']:+d}]")
        print(f"    gold: ...{ex['gold']}...")
        print(f"    got : ...{ex['got']}...")


if __name__ == "__main__":
    raise SystemExit(main())
