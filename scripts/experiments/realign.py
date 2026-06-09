"""
Domain-merge + mweralign realignment for the WMT24 experiments.

For a given (language pair, system, segmenter) this:

1.  groups the system's segment outputs by *domain* (the paper's unit of
    re-segmentation);
2.  concatenates each domain's outputs into a single word stream, simulating a
    system whose segment boundaries were lost;
3.  realigns that stream back to the reference segmentation with mweralign,
    using the chosen segmenter; and
4.  restores the original segment order.

The mweralign CLI is invoked as a subprocess (the same entry point users run),
exercising its document-constrained (`-d`) alignment path.

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List

from . import data

# Segmenter name -> function(target_language) -> extra mweralign CLI args.
SEGMENTERS = {
    "none": lambda tgt: [],
    "cj": lambda tgt: ["-m", "cj", "-l", tgt],
    "flores200": lambda tgt: ["-m", str(data.flores_model())],
    # Custom identity-normalization SPM (paper models); character-preserving.
    # "spm" is an alias for the 256k model; size-specific names are also exposed.
    "spm": lambda tgt: ["-m", str(data.spm_model(256000))],
    "spm32k": lambda tgt: ["-m", str(data.spm_model(32000))],
    "spm64k": lambda tgt: ["-m", str(data.spm_model(64000))],
    "spm128k": lambda tgt: ["-m", str(data.spm_model(128000))],
    "spm256k": lambda tgt: ["-m", str(data.spm_model(256000))],
}


def segmenter_args(segmenter: str, target_language: str) -> List[str]:
    if segmenter not in SEGMENTERS:
        raise ValueError(
            f"unknown segmenter {segmenter!r}; choose from {sorted(SEGMENTERS)}"
        )
    return SEGMENTERS[segmenter](target_language)


def _run_mweralign(
    refs: List[str], merged_hyps: List[str], doc_labels: List[str], extra: List[str],
    legacy_penalty: bool = False
) -> List[str]:
    """Invoke the mweralign CLI and return its realigned output lines."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        ref_f, hyp_f, doc_f, out_f = (
            tmp / "ref.txt",
            tmp / "hyp.txt",
            tmp / "docids.txt",
            tmp / "out.txt",
        )
        ref_f.write_text("\n".join(refs) + "\n", encoding="utf-8")
        hyp_f.write_text("\n".join(merged_hyps) + "\n", encoding="utf-8")
        doc_f.write_text("\n".join(doc_labels) + "\n", encoding="utf-8")
        cmd = [
            sys.executable, "-m", "mweralign.mweralign",
            "-r", str(ref_f), "-t", str(hyp_f), "-d", str(doc_f),
            "-o", str(out_f), *extra,
        ]
        if legacy_penalty:
            cmd.append("--legacy-penalty")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"mweralign failed (exit {result.returncode}):\n{result.stderr}"
            )
        return out_f.read_text(encoding="utf-8").splitlines()


def realign_system(langpair: str, system: str, segmenter: str,
                   legacy_penalty: bool = False) -> List[str]:
    """Return the realigned, per-segment output for one system (original order)."""
    refs = data.primary_reference(langpair)
    hyps = data.system_output(langpair, system)
    domain_labels = data.domains(langpair)
    if not (len(refs) == len(hyps) == len(domain_labels)):
        raise ValueError(
            f"{langpair}/{system}: length mismatch "
            f"(refs={len(refs)} hyps={len(hyps)} domains={len(domain_labels)})"
        )

    groups = data.domain_groups(domain_labels)

    # Build domain-contiguous inputs and remember the original positions.
    order: List[int] = []
    ordered_refs: List[str] = []
    ordered_docids: List[str] = []
    merged_hyps: List[str] = []
    for domain, indices in groups.items():
        order.extend(indices)
        ordered_refs.extend(refs[i] for i in indices)
        ordered_docids.extend(domain for _ in indices)
        merged_hyps.append(" ".join(hyps[i].strip() for i in indices))

    extra = segmenter_args(segmenter, data.target_language(langpair))
    realigned = _run_mweralign(ordered_refs, merged_hyps, ordered_docids, extra,
                               legacy_penalty=legacy_penalty)

    if len(realigned) != len(order):
        raise RuntimeError(
            f"{langpair}/{system}/{segmenter}: mweralign returned "
            f"{len(realigned)} lines, expected {len(order)}"
        )

    # Un-permute back to the original segment order.
    restored = [""] * len(order)
    for pos, seg in zip(order, realigned):
        restored[pos] = seg
    return restored
