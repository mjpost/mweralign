#!/usr/bin/env python3
"""
Download / cache the WMT24 data used by the alignment experiments.

Everything needed for the alignment + (BLEU/chrF/COMET22/gemboid) scoring
pipeline -- sources, references, document ids, domains, and *system outputs* --
is served by sacrebleu's bundled ``DATASETS`` for ``wmt24``. Calling
``get_files`` triggers sacrebleu's own download/cache, so this script simply
"warms" that cache for the requested language pairs and verifies the flores200
SPM model is present.

Human-judgment data (for Kendall-tau correlation) lives in mt-metrics-eval and
is intentionally *not* downloaded here -- that stage is deferred. A stub flag
``--print-mtme-hint`` prints how to fetch it when you are ready.

Usage::

    python -m scripts.experiments.download_data                 # all 11 pairs
    python -m scripts.experiments.download_data -l en-de ja-zh  # subset

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import argparse
import sys

from . import data


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "-l", "--langpairs", nargs="+", default=None,
        help="Language pairs to fetch (default: all 11).",
    )
    parser.add_argument(
        "--print-mtme-hint", action="store_true",
        help="Print how to download mt-metrics-eval human scores (deferred).",
    )
    args = parser.parse_args(argv)

    langpairs = args.langpairs or data.langpairs()

    print(f"Caching WMT24 data for {len(langpairs)} language pair(s)...\n")
    for lp in langpairs:
        # Touch each field so sacrebleu downloads and caches it.
        n_src = len(data.sources(lp))
        n_ref = len(data.references(lp))
        n_sys = len(data.systems(lp))
        n_dom = len(set(data.domains(lp)))
        print(
            f"  {lp:7s} segments={n_src:5d} refs={n_ref} systems={n_sys:2d} "
            f"domains={n_dom}"
        )

    print("\nVerifying flores200 SPM model...")
    try:
        print(f"  found: {data.flores_model()}")
    except FileNotFoundError as exc:
        print(f"  MISSING: {exc}", file=sys.stderr)
        return 1

    if args.print_mtme_hint:
        print(
            "\n[deferred] To fetch human judgments for Kendall-tau correlation:\n"
            "  pip install mt-metrics-eval\n"
            "  python -m mt_metrics_eval.mtme --download   # downloads wmt2x data\n"
            "  # human scores: ~/.mt-metrics-eval/mt-metrics-eval-v2/wmt24/human-scores/"
        )

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
