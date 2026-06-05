#!/usr/bin/env python3
"""Build a before/after restoration comparison table from two per-system TSVs.

Reads the per-system TSVs written by ``restoration_rate.py`` (one for the
legacy/pre-fix build, one for the fixed build), intersects on the systems that
succeeded under BOTH builds, and prints a per-langpair table comparing
boundary accuracy and exact-segment restoration.

Usage:
    python -m scripts.experiments.compare_restoration \
        --before /tmp/restore_legacy.tsv --after /tmp/restore_fixed.tsv
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from typing import Dict, Tuple


def load(path: str) -> Dict[Tuple[str, str], dict]:
    """Map (langpair, system) -> row dict for systems that succeeded (ok==1)."""
    out: Dict[Tuple[str, str], dict] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            if row.get("ok") != "1":
                continue
            out[(row["langpair"], row["system"])] = {
                "n_boundaries": int(row["n_boundaries"]),
                "boundaries_correct": int(row["boundaries_correct"]),
                "n_segments": int(row["n_segments"]),
                "segments_exact": int(row["segments_exact"]),
            }
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--before", required=True, help="Pre-fix (legacy) per-system TSV.")
    p.add_argument("--after", required=True, help="Post-fix per-system TSV.")
    p.add_argument("--langpairs", nargs="+", default=None)
    args = p.parse_args(argv)

    before = load(args.before)
    after = load(args.after)

    # Systems that succeeded under BOTH builds, so the comparison is apples-to-apples.
    common = sorted(set(before) & set(after))
    langpairs = args.langpairs or sorted({lp for lp, _ in common})

    # lp -> {build -> [nb, bok, nseg, segok], "n": count}
    agg = defaultdict(lambda: {"before": [0, 0, 0, 0], "after": [0, 0, 0, 0], "n": 0})
    for key in common:
        lp, _ = key
        if langpairs and lp not in langpairs:
            continue
        a = agg[lp]
        a["n"] += 1
        for build, src in (("before", before), ("after", after)):
            r = src[key]
            a[build][0] += r["n_boundaries"]
            a[build][1] += r["boundaries_correct"]
            a[build][2] += r["n_segments"]
            a[build][3] += r["segments_exact"]

    def pct(num, den):
        return 100.0 * num / den if den else float("nan")

    only_before = sorted(set(before) - set(after))
    only_after = sorted(set(after) - set(before))

    print("Restoration of original segmentation (untokenized, segmenter=none)")
    print("Systems compared are those that succeeded under BOTH builds.\n")
    header = (f"{'langpair':8s} {'n_sys':>5s} | "
              f"{'bound_before':>12s} {'bound_after':>11s} {'Δ':>7s} | "
              f"{'exact_before':>12s} {'exact_after':>11s} {'Δ':>7s}")
    print(header)
    print("-" * len(header))

    tot = {"before": [0, 0, 0, 0], "after": [0, 0, 0, 0], "n": 0}
    for lp in langpairs:
        if lp not in agg:
            continue
        a = agg[lp]
        bb = pct(a["before"][1], a["before"][0])
        ba = pct(a["after"][1], a["after"][0])
        sb = pct(a["before"][3], a["before"][2])
        sa = pct(a["after"][3], a["after"][2])
        print(f"{lp:8s} {a['n']:5d} | "
              f"{bb:11.2f}% {ba:10.2f}% {ba-bb:+6.2f} | "
              f"{sb:11.2f}% {sa:10.2f}% {sa-sb:+6.2f}")
        for build in ("before", "after"):
            for i in range(4):
                tot[build][i] += a[build][i]
        tot["n"] += a["n"]

    bb = pct(tot["before"][1], tot["before"][0])
    ba = pct(tot["after"][1], tot["after"][0])
    sb = pct(tot["before"][3], tot["before"][2])
    sa = pct(tot["after"][3], tot["after"][2])
    print("-" * len(header))
    print(f"{'ALL':8s} {tot['n']:5d} | "
          f"{bb:11.2f}% {ba:10.2f}% {ba-bb:+6.2f} | "
          f"{sb:11.2f}% {sa:10.2f}% {sa-sb:+6.2f}")

    print(f"\nSystems only in BEFORE (failed/absent in after): {len(only_before)}")
    print(f"Systems only in AFTER  (failed/absent in before): {len(only_after)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
