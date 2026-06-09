#!/usr/bin/env python3
"""
Orchestrate the WMT24 alignment experiment: for every (language pair, system,
segmenter), realign the domain-merged system output back to the reference
segmentation and score both the original ("manual") and realigned outputs.

Outputs:

* ``<out>/outputs/<lp>/<system>.<segmenter>.txt`` - realigned hypotheses
  (only when ``--save-outputs`` is given).
* ``<out>/results.tsv`` - one row per (lp, system, metric, segmenter) with the
  manual score, realigned score, and their delta.

Examples::

    # Quick smoke test: 2 systems of en-de, BLEU+chrF only.
    python -m scripts.experiments.run -l en-de --max-systems 2

    # Full run, all pairs/systems/segmenters, add COMET22 (needs PyMarian).
    python -m scripts.experiments.run --metrics bleu chrf comet22

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import csv
import sys
import traceback
from collections import defaultdict
from pathlib import Path
from typing import List

from . import data, realign, score

DEFAULT_SEGMENTERS = ["none", "cj", "flores200"]
DEFAULT_METRICS = ["bleu", "chrf"]
# cj segmentation is only meaningful for CJK targets.
_CJK_TARGETS = {"zh", "ja"}


def applicable_segmenters(langpair: str, requested: List[str]) -> List[str]:
    tgt = data.target_language(langpair)
    out = []
    for seg in requested:
        if seg == "cj" and tgt not in _CJK_TARGETS:
            continue
        out.append(seg)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("-l", "--langpairs", nargs="+", default=None,
                        help="Language pairs (default: all 11).")
    parser.add_argument("-s", "--systems", nargs="+", default=None,
                        help="System names (default: all for each pair).")
    parser.add_argument("--segmenters", nargs="+", default=DEFAULT_SEGMENTERS,
                        choices=list(realign.SEGMENTERS))
    parser.add_argument("--metrics", nargs="+", default=DEFAULT_METRICS,
                        choices=list(score.METRICS))
    parser.add_argument("-o", "--output-dir", default="experiments-out",
                        help="Directory for results.tsv and realigned outputs.")
    parser.add_argument("--save-outputs", action="store_true",
                        help="Also write realigned hypotheses to disk.")
    parser.add_argument("--max-systems", type=int, default=None,
                        help="Limit systems per pair (smoke testing).")
    args = parser.parse_args(argv)

    langpairs = args.langpairs or data.langpairs()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results_path = out_dir / "results.tsv"

    rows = []
    deltas = defaultdict(list)  # (segmenter, metric) -> [delta, ...]

    for lp in langpairs:
        srcs = data.sources(lp)
        refs = data.references(lp)
        seg_list = applicable_segmenters(lp, args.segmenters)
        sys_list = args.systems or data.systems(lp)
        if args.max_systems:
            sys_list = sys_list[: args.max_systems]

        for system in sys_list:
            try:
                manual = data.system_output(lp, system)
            except Exception as exc:  # noqa: BLE001 - report and continue
                print(f"! skip {lp}/{system}: {exc}", file=sys.stderr)
                continue

            manual_scores = {m: score.score(m, lp, manual, refs, srcs)
                             for m in args.metrics if m in ("bleu", "chrf", "chrfpp")}
            # Optional metrics may be unavailable; record None on failure.
            for m in args.metrics:
                if m in manual_scores:
                    continue
                try:
                    manual_scores[m] = score.score(m, lp, manual, refs, srcs)
                except Exception as exc:  # noqa: BLE001
                    print(f"! metric {m} unavailable ({lp}/{system}): {exc}",
                          file=sys.stderr)
                    manual_scores[m] = None

            for segmenter in seg_list:
                try:
                    realigned = realign.realign_system(lp, system, segmenter)
                except Exception:  # noqa: BLE001
                    print(f"! realign failed {lp}/{system}/{segmenter}:",
                          file=sys.stderr)
                    traceback.print_exc()
                    continue

                if args.save_outputs:
                    odir = out_dir / "outputs" / lp
                    odir.mkdir(parents=True, exist_ok=True)
                    (odir / f"{system}.{segmenter}.txt").write_text(
                        "\n".join(realigned) + "\n", encoding="utf-8")

                for m in args.metrics:
                    manual_score = manual_scores.get(m)
                    try:
                        realigned_score = score.score(m, lp, realigned, refs, srcs)
                    except Exception as exc:  # noqa: BLE001
                        print(f"! metric {m} failed {lp}/{system}/{segmenter}: {exc}",
                              file=sys.stderr)
                        continue
                    delta = (realigned_score - manual_score
                             if manual_score is not None else None)
                    if delta is not None:
                        deltas[(segmenter, m)].append(delta)
                    rows.append({
                        "langpair": lp, "system": system, "metric": m,
                        "segmenter": segmenter,
                        "manual": _fmt(manual_score),
                        "realigned": _fmt(realigned_score),
                        "delta": _fmt(delta),
                    })
                    print(f"{lp:7s} {system:18s} {m:7s} {segmenter:9s} "
                          f"manual={_fmt(manual_score):>8} "
                          f"realigned={_fmt(realigned_score):>8} "
                          f"delta={_fmt(delta):>8}")

    _write_tsv(results_path, rows)
    print(f"\nWrote {len(rows)} rows to {results_path}")

    if deltas:
        print("\nMean delta (realigned - manual) by segmenter x metric:")
        for (segmenter, m), vals in sorted(deltas.items()):
            print(f"  {segmenter:9s} {m:7s} n={len(vals):4d} "
                  f"mean={sum(vals) / len(vals):+.3f}")
    return 0


def _fmt(value) -> str:
    return "" if value is None else f"{value:.4f}"


def _write_tsv(path: Path, rows: List[dict]) -> None:
    fields = ["langpair", "system", "metric", "segmenter", "manual",
              "realigned", "delta"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
