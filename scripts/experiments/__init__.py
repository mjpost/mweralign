"""
Experiment scaffolding for "Effects of automatic alignment on speech
translation metrics" (Post & Hieu, IWSLT 2025).

This package reproduces the *data + alignment + scoring* pipeline of the paper
on WMT24, for all 11 language pairs. The pipeline is:

1.  ``data``    - load WMT24 sources, references, docids, domains, and system
                  outputs (all served by sacrebleu's bundled DATASETS).
2.  ``realign`` - simulate a system that lost segment boundaries by merging its
                  outputs within each *domain*, then realign the merged word
                  stream back to the reference segmentation with mweralign,
                  using each of the configured segmenters.
3.  ``score``   - score both the original ("manual" segmentation) and the
                  realigned outputs with BLEU + chrF (sacrebleu), COMET22
                  (PyMarian), and a pluggable ``gemboid`` hook.
4.  ``run``     - orchestrate the above across language pairs / systems /
                  segmenters and emit a tidy results table.

Human-judgment correlation (Kendall's tau via mt-metrics-eval) is intentionally
left for a later stage; see the README.

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""
