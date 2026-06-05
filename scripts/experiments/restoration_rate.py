#!/usr/bin/env python3
"""
Measure how well mweralign *restores* a system's original segmentation after
domain-level merging, per WMT24 language pair.

Setup (round-trip / self-consistency test, segmenter=none / untokenized):
  * Each system's per-segment output is parallel to the reference segments.
  * Within each domain the outputs are concatenated (boundaries erased) and
    handed, with the references, to mweralign, which re-splits the merged word
    stream back into per-reference segments.
  * Because no tokens are added or dropped, the realigned boundaries can be
    compared token-for-token against the system's ORIGINAL segmentation (the
    "gold" restoration target).

Metrics (per language pair, micro-averaged over systems):
  * boundary_acc - fraction of interior boundaries placed exactly on gold.
  * seg_exact    - fraction of segments reproduced verbatim.

Robustness: if mweralign fails for a system (e.g. the pre-fix build SIGSEGVs on
large merged inputs), the failure is recorded and the system is skipped, so the
script still completes and reports a completion count.

Per-system rows are written to ``--per-system-tsv`` so two runs (e.g. before vs
after a code change) can be compared on the intersection of systems that
succeeded under both builds.

Usage::

    python -m scripts.experiments.restoration_rate \
        --per-system-tsv /tmp/restore_fixed.tsv

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from typing import List, Optional, Tuple

from . import data, realign


def _nonspace(seg: str) -> str:
    """Non-whitespace characters of a segment (whitespace is not restorable)."""
    return "".join(seg.split())


def _char_boundaries(segs: List[str]) -> List[int]:
    """Interior segment boundaries as cumulative non-space character offsets."""
    out, total = [], 0
    for seg in segs[:-1]:
        total += len(_nonspace(seg))
        out.append(total)
    return out


def _size_stats(langpair: str, system: str) -> dict:
    """Cost-driver stats for one system, computed without running mweralign.

    The DP is ~O(J * S) per domain-merged group, so we record the merged group
    size (whitespace words) that drives it.
    """
    hyps = data.system_output(langpair, system)
    n_segments = len(hyps)
    total_words = sum(len(h.split()) for h in hyps)
    groups = data.domain_groups(data.domains(langpair))
    dom_words = [sum(len(hyps[i].split()) for i in idxs) for idxs in groups.values()]
    return {
        "n_segments": n_segments,
        "total_words": total_words,
        "avg_words_per_seg": round(total_words / n_segments, 3) if n_segments else "",
        "n_domains": len(dom_words),
        "max_domain_words": max(dom_words) if dom_words else 0,
        "sum_domain_sq": sum(w * w for w in dom_words),
    }


def restoration_for_system(
    langpair: str, system: str, segmenter: str, legacy_penalty: bool = False
) -> dict:
    """Measure restoration quality, cost-driver size, and wall time for a system.

    Always returns a dict. ``ok`` is 1 when mweralign succeeded and the
    non-space character stream was preserved (so the boundary comparison is
    valid); 0 otherwise (e.g. the pre-fix build SIGSEGVs, or a segmenter
    rewrote characters as flores200's normalization does). The size stats and
    ``wall_seconds`` are recorded regardless.

    Boundaries are compared at the *non-space character* level rather than by
    whitespace token, so SPM segmenters (which re-tokenize whitespace but, with
    identity normalization, preserve characters) are measurable. For the
    whitespace ``none`` segmenter this is equivalent to comparing word
    boundaries, since breaks can only fall on word boundaries.
    """
    manual = data.system_output(langpair, system)
    row = _size_stats(langpair, system)
    row.update({"ok": 0, "n_boundaries": "", "boundaries_correct": "",
                "segments_exact": "", "wall_seconds": ""})

    t0 = time.perf_counter()
    try:
        realigned = realign.realign_system(langpair, system, segmenter,
                                           legacy_penalty=legacy_penalty)
    except Exception as exc:  # noqa: BLE001 - segfault etc.
        row["wall_seconds"] = round(time.perf_counter() - t0, 3)
        row["_error"] = type(exc).__name__
        return row
    row["wall_seconds"] = round(time.perf_counter() - t0, 3)

    groups = data.domain_groups(data.domains(langpair))
    n_b = b_ok = n_seg = seg_ok = 0
    for _dom, idxs in groups.items():
        gold = [manual[i] for i in idxs]
        got = [realigned[i] for i in idxs]

        # Non-space character stream must match for a valid comparison.
        if "".join(_nonspace(s) for s in gold) != "".join(_nonspace(s) for s in got):
            row["_error"] = "char-mismatch"
            return row

        gb = _char_boundaries(gold)
        rb = set(_char_boundaries(got))
        n_b += len(gb)
        b_ok += sum(1 for off in gb if off in rb)
        n_seg += len(idxs)
        seg_ok += sum(1 for a, c in zip(gold, got) if _nonspace(a) == _nonspace(c))

    row.update({"ok": 1, "n_boundaries": n_b, "boundaries_correct": b_ok,
                "n_segments": n_seg, "segments_exact": seg_ok})
    return row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("-l", "--langpairs", nargs="+", default=None)
    parser.add_argument("-s", "--systems", nargs="+", default=None)
    parser.add_argument("--segmenter", default="none", choices=list(realign.SEGMENTERS))
    parser.add_argument("--skip-systems", nargs="+", default=[])
    parser.add_argument("--max-systems", type=int, default=None)
    parser.add_argument("--legacy-penalty", action="store_true", default=False,
                        help="Use the pre-fix penalty behavior (paper reproduction).")
    parser.add_argument("--per-system-tsv", default=None,
                        help="Write one row per (langpair, system) here.")
    parser.add_argument("--label", default="run",
                        help="Label recorded in the per-system TSV (e.g. 'fixed').")
    args = parser.parse_args(argv)

    langpairs = args.langpairs or data.langpairs()
    skip = set(args.skip_systems)

    rows = []
    agg = defaultdict(lambda: [0, 0, 0, 0, 0, 0])  # lp -> [nb,bok,nseg,segok,ok,fail]

    for lp in langpairs:
        sys_list = args.systems or data.systems(lp)
        sys_list = [s for s in sys_list if s not in skip]
        if args.max_systems:
            sys_list = sys_list[: args.max_systems]
        for system in sys_list:
            res = restoration_for_system(lp, system, args.segmenter,
                                         legacy_penalty=args.legacy_penalty)
            err = res.pop("_error", None)
            row = {"label": args.label, "langpair": lp, "system": system,
                   "segmenter": args.segmenter, **res}
            rows.append(row)
            if res["ok"]:
                a = agg[lp]
                a[0] += res["n_boundaries"]; a[1] += res["boundaries_correct"]
                a[2] += res["n_segments"]; a[3] += res["segments_exact"]; a[4] += 1
                print(f"  done {lp:7s} {system}  J_max={res['max_domain_words']:6d} "
                      f"t={res['wall_seconds']:6.2f}s", file=sys.stderr)
            else:
                agg[lp][5] += 1
                print(f"  FAIL {lp:7s} {system}: {err}  "
                      f"t={res['wall_seconds']}s", file=sys.stderr)

    if args.per_system_tsv:
        with open(args.per_system_tsv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, delimiter="\t", fieldnames=[
                "label", "langpair", "system", "segmenter", "ok",
                "n_boundaries", "boundaries_correct", "n_segments",
                "segments_exact", "total_words", "avg_words_per_seg",
                "n_domains", "max_domain_words", "sum_domain_sq", "wall_seconds"])
            w.writeheader()
            w.writerows(rows)
        print(f"\nWrote {len(rows)} per-system rows to {args.per_system_tsv}",
              file=sys.stderr)

    # Console summary table.
    print(f"\nRestoration of original segmentation  (segmenter={args.segmenter})")
    print(f"{'langpair':8s} {'sys_ok':>6s} {'sys_fail':>8s} "
          f"{'boundary_acc':>12s} {'seg_exact':>10s}")
    tot = [0, 0, 0, 0, 0, 0]
    for lp in langpairs:
        nb, bok, nseg, segok, ok, fail = agg[lp]
        bacc = 100.0 * bok / nb if nb else float("nan")
        sx = 100.0 * segok / nseg if nseg else float("nan")
        print(f"{lp:8s} {ok:6d} {fail:8d} {bacc:11.2f}% {sx:9.2f}%")
        for i in range(6):
            tot[i] += agg[lp][i]
    nb, bok, nseg, segok, ok, fail = tot
    bacc = 100.0 * bok / nb if nb else float("nan")
    sx = 100.0 * segok / nseg if nseg else float("nan")
    print(f"{'ALL':8s} {ok:6d} {fail:8d} {bacc:11.2f}% {sx:9.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
