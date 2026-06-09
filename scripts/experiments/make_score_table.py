#!/usr/bin/env python3
"""
Build paper-style tables from ``run.py`` output (``results.tsv``).

Reproduces the structure of Table 3 in the paper (score differences between the
original "manual" segmentation and the merged+realigned output, averaged over
systems within each language pair), but for the metrics we score with sacrebleu
(BLEU and chrF++). Also emits "raw" variants reporting the mean *realigned*
score per (segmenter, language pair), plus the segmenter-independent ``manual``
baseline row.

Each metric is rendered as its own block. Output is written to stdout as both a
Markdown table and a LaTeX ``tabular`` (and optionally to files).

Examples::

    python -m scripts.experiments.make_score_table \
        --results expt/results/scores/results.tsv

    python -m scripts.experiments.make_score_table \
        --results expt/results/scores/results.tsv \
        --out-prefix expt/results/scores/table

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

# Column order and pretty metric labels, matching the paper where possible.
PAPER_LANGPAIRS = [
    "cs-uk", "en-cs", "en-de", "en-es", "en-hi", "en-is",
    "en-ja", "en-ru", "en-uk", "en-zh", "ja-zh",
]
METRIC_LABELS = {"bleu": "BLEU", "chrf": "chrF", "chrfpp": "chrF++"}
# Row order for segmenters; pretty labels strip the ``spm`` prefix to match paper.
SEG_ORDER = ["none", "cj", "flores200", "spm32k", "spm64k", "spm128k", "spm256k"]
SEG_LABELS = {
    "none": "none", "cj": "cj", "flores200": "flores200",
    "spm32k": "32k", "spm64k": "64k", "spm128k": "128k", "spm256k": "256k",
}


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def load(path: Path):
    """Return rows as a list of dicts with floats parsed where present."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            for k in ("manual", "realigned", "delta"):
                r[k] = float(r[k]) if r.get(k) not in (None, "") else None
            rows.append(r)
    return rows


def _present(values, order):
    """Keep only items from ``order`` that actually occur in ``values``."""
    seen = set(values)
    return [x for x in order if x in seen]


def aggregate(rows, value_key: str):
    """metric -> segmenter -> langpair -> mean(value_key over systems)."""
    bucket: Dict[str, Dict[str, Dict[str, List[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list)))
    for r in rows:
        v = r.get(value_key)
        if v is None:
            continue
        bucket[r["metric"]][r["segmenter"]][r["langpair"]].append(v)
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for metric, segs in bucket.items():
        out[metric] = {seg: {lp: _mean(vs) for lp, vs in lps.items()}
                       for seg, lps in segs.items()}
    return out


def manual_baseline(rows):
    """metric -> langpair -> mean(manual) (segmenter-independent)."""
    # Manual scores repeat per segmenter; collapse on (metric, lp, system).
    seen: set = set()
    bucket: Dict[str, Dict[str, List[float]]] = defaultdict(
        lambda: defaultdict(list))
    for r in rows:
        if r.get("manual") is None:
            continue
        key = (r["metric"], r["langpair"], r["system"])
        if key in seen:
            continue
        seen.add(key)
        bucket[r["metric"]][r["langpair"]].append(r["manual"])
    return {m: {lp: _mean(vs) for lp, vs in lps.items()}
            for m, lps in bucket.items()}


def _fmt(x: float) -> str:
    if x != x:  # NaN
        return "-"
    return f"{x:.1f}"


def render_markdown(title: str, metrics, segments, langpairs,
                    cells: Dict[str, Dict[str, Dict[str, float]]],
                    baseline=None) -> str:
    lines = [f"### {title}", ""]
    header = "| metric | segmenter | " + " | ".join(langpairs) + " |"
    sep = "|" + "---|" * (len(langpairs) + 2)
    lines += [header, sep]
    for metric in metrics:
        if baseline is not None:
            base = baseline.get(metric, {})
            cols = " | ".join(_fmt(base.get(lp, float("nan"))) for lp in langpairs)
            lines.append(f"| {METRIC_LABELS.get(metric, metric)} | manual | {cols} |")
        for seg in segments:
            data = cells.get(metric, {}).get(seg, {})
            cols = " | ".join(_fmt(data.get(lp, float("nan"))) for lp in langpairs)
            lines.append(
                f"| {METRIC_LABELS.get(metric, metric)} | "
                f"{SEG_LABELS.get(seg, seg)} | {cols} |")
    lines.append("")
    return "\n".join(lines)


def render_latex(caption: str, metrics, segments, langpairs,
                 cells: Dict[str, Dict[str, Dict[str, float]]],
                 baseline=None) -> str:
    ncol = len(langpairs)
    lines = [
        "\\begin{table*}[t]", "\\centering",
        "\\begin{tabular}{l" + "r" * ncol + "}", "\\toprule",
        "segmenter & " + " & ".join(langpairs) + " \\\\",
    ]
    for metric in metrics:
        lines.append("\\midrule")
        lines.append("\\multicolumn{%d}{l}{\\textit{%s}} \\\\"
                     % (ncol + 1, METRIC_LABELS.get(metric, metric)))
        if baseline is not None:
            base = baseline.get(metric, {})
            cols = " & ".join(_fmt(base.get(lp, float("nan"))) for lp in langpairs)
            lines.append(f"manual & {cols} \\\\")
        for seg in segments:
            data = cells.get(metric, {}).get(seg, {})
            cols = " & ".join(_fmt(data.get(lp, float("nan"))) for lp in langpairs)
            lines.append(f"{SEG_LABELS.get(seg, seg)} & {cols} \\\\")
    lines += [
        "\\bottomrule", "\\end{tabular}",
        f"\\caption{{{caption}}}", "\\end{table*}",
    ]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--results", default="expt/results/scores/results.tsv",
                    type=Path, help="results.tsv produced by run.py")
    ap.add_argument("--out-prefix", default=None,
                    help="If set, also write <prefix>.md and <prefix>.tex.")
    args = ap.parse_args(argv)

    rows = load(args.results)
    if not rows:
        raise SystemExit(f"no rows in {args.results}")

    metrics = _present((r["metric"] for r in rows),
                       ["bleu", "chrf", "chrfpp"])
    segments = _present((r["segmenter"] for r in rows), SEG_ORDER)
    langpairs = _present((r["langpair"] for r in rows), PAPER_LANGPAIRS)

    diff = aggregate(rows, "delta")
    raw = aggregate(rows, "realigned")
    base = manual_baseline(rows)

    blocks = []
    blocks.append(render_markdown(
        "Score differences (realigned - manual), averaged over systems",
        metrics, segments, langpairs, diff))
    blocks.append(render_markdown(
        "Raw scores: mean realigned score per system (manual = baseline)",
        metrics, segments, langpairs, raw, baseline=base))

    md = "\n".join(blocks)
    print(md)

    tex_diff = render_latex(
        "Score differences (realigned minus original), averaged over systems "
        "per language pair.", metrics, segments, langpairs, diff)
    tex_raw = render_latex(
        "Raw realigned scores, averaged over systems; manual is the baseline "
        "on the original segmentation.", metrics, segments, langpairs, raw,
        baseline=base)

    if args.out_prefix:
        prefix = Path(args.out_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        prefix.with_suffix(".md").write_text(md + "\n", encoding="utf-8")
        prefix.with_suffix(".tex").write_text(
            tex_diff + "\n\n" + tex_raw + "\n", encoding="utf-8")
        print(f"\nWrote {prefix.with_suffix('.md')} and "
              f"{prefix.with_suffix('.tex')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
