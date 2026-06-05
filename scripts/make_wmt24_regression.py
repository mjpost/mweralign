#!/usr/bin/env python3
"""
Generate WMT24 regression fixtures for the ``mweralign`` golden-file suite.

This script pulls small, deterministic slices of real WMT24 data (reference
translations + document ids) from sacrebleu and writes self-contained
regression cases under ``python/tests/regression/wmt24_*``. Each generated
case exercises a different mweralign feature on real data:

* ``wmt24_ende_merge_none``    - whitespace (no segmenter), document-merged
                                  hypotheses realigned via ``-d`` docids.
* ``wmt24_ende_merge_flores``  - same, but with the flores200 SPM segmenter.
* ``wmt24_jazh_merge_cj``      - Han-character (``cj``) segmenter on ja-zh.
* ``wmt24_ende_score``         - ``--score`` mode on a parallel slice.

The "system hypothesis" for the merge cases is synthesised by concatenating
the reference segments within each document (simulating a system that lost
segment boundaries). mweralign must then realign the merged word stream back
into per-segment outputs -- the exact operation performed in the paper's
experiments. Because sacrebleu test sets are versioned and immutable, the
fixtures (and therefore the golden outputs) are fully reproducible.

Usage::

    python scripts/make_wmt24_regression.py          # (re)write fixtures
    MWERALIGN_REGEN=1 pytest python/tests/test_regression.py   # goldens

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Tuple

import sacrebleu

# flores200 SPM model shipped/downloaded by sacrebleu; reused for the `-m` flag.
FLORES_MODEL = Path.home() / ".sacrebleu" / "models" / "flores200sacrebleuspm"

REGRESSION_DIR = Path(__file__).resolve().parent.parent / "python" / "tests" / "regression"


def fetch(langpair: str) -> Tuple[List[str], List[str]]:
    """Return (primary references, docids) for a WMT24 language pair, line-aligned."""
    refs = _field(langpair, _ref_field(langpair))
    docids = _field(langpair, "docid")
    assert len(refs) == len(docids), f"{langpair}: ref/docid length mismatch"
    return refs, docids


def _ref_field(langpair: str) -> str:
    """Name of the primary reference field (e.g. ``ref:refA`` or ``ref``)."""
    fields = sacrebleu.DATASETS["wmt24"].fieldnames(langpair)
    return next(f for f in fields if f == "ref" or f.startswith("ref:"))


def _field(langpair: str, name: str) -> List[str]:
    """Read one field of a WMT24 language pair via the sacrebleu DATASETS API."""
    testset = sacrebleu.DATASETS["wmt24"]
    idx = testset.fieldnames(langpair).index(name)
    path = testset.get_files(langpair)[idx]
    with open(path, encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh]


def select_slice(
    refs: List[str],
    docids: List[str],
    *,
    max_chars: int = 180,
    n_segments: int = 8,
    min_docs: int = 2,
) -> Tuple[List[str], List[str]]:
    """Pick the first ``n_segments`` short segments spanning >= ``min_docs`` docs."""
    sel_refs: List[str] = []
    sel_docids: List[str] = []
    for ref, docid in zip(refs, docids):
        if len(ref) > max_chars or not ref.strip():
            continue
        sel_refs.append(ref)
        sel_docids.append(docid)
        if len(sel_refs) >= n_segments and len(set(sel_docids)) >= min_docs:
            break
    if len(set(sel_docids)) < min_docs:
        raise RuntimeError("could not find enough documents in the slice")
    return sel_refs, sel_docids


def merged_hyps(refs: List[str], docids: List[str]) -> List[str]:
    """Concatenate reference segments within each (contiguous) document."""
    hyps: List[str] = []
    current = None
    for ref, docid in zip(refs, docids):
        if docid != current:
            hyps.append(ref)
            current = docid
        else:
            hyps[-1] = hyps[-1] + " " + ref
    return hyps


def write_case(name: str, cmd: str, files: dict[str, str]) -> None:
    case_dir = REGRESSION_DIR / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "cmd").write_text(cmd.strip() + "\n", encoding="utf-8")
    for fname, content in files.items():
        (case_dir / fname).write_text(content, encoding="utf-8")
    # Remove any stale golden so it is regenerated against the new fixture.
    (case_dir / "expected.txt").unlink(missing_ok=True)
    print(f"wrote {name}: {len(files)} fixture file(s)")


def lines(seq: List[str]) -> str:
    return "\n".join(seq) + "\n"


def build_merge_case(name: str, langpair: str, cmd_extra: str, **slice_kw) -> None:
    refs, docids = fetch(langpair)
    sel_refs, sel_docids = select_slice(refs, docids, **slice_kw)
    hyps = merged_hyps(sel_refs, sel_docids)
    write_case(
        name,
        f"-r ref.txt -t hyp.txt -d docids.txt {cmd_extra}".strip(),
        {
            "ref.txt": lines(sel_refs),
            "docids.txt": lines(sel_docids),
            "hyp.txt": lines(hyps),
        },
    )


def build_score_case(name: str, langpair: str, **slice_kw) -> None:
    refs, docids = fetch(langpair)
    sel_refs, _ = select_slice(refs, docids, **slice_kw)
    # Parallel scoring: hypothesis = reference shifted by one segment, giving a
    # deterministic, non-trivial WER on real text.
    sel_hyps = sel_refs[1:] + sel_refs[:1]
    write_case(
        name,
        "--score -r ref.txt -t hyp.txt",
        {
            "ref.txt": lines(sel_refs),
            "hyp.txt": lines(sel_hyps),
        },
    )


def main() -> None:
    if not FLORES_MODEL.exists():
        raise SystemExit(
            f"flores200 SPM model not found at {FLORES_MODEL}.\n"
            "Trigger a download first, e.g.:\n"
            "  python -c \"from sacrebleu.tokenizers.tokenizer_spm import "
            "Flores200Tokenizer; Flores200Tokenizer()('x')\""
        )

    build_merge_case("wmt24_ende_merge_none", "en-de", "")
    build_merge_case(
        "wmt24_ende_merge_flores", "en-de", f"-m {FLORES_MODEL}",
    )
    build_merge_case("wmt24_jazh_merge_cj", "ja-zh", "-m cj -l zh", max_chars=120)
    build_score_case("wmt24_ende_score", "en-de")

    print("\nDone. Now generate golden outputs with:")
    print("  MWERALIGN_REGEN=1 pytest python/tests/test_regression.py -q")


if __name__ == "__main__":
    main()
