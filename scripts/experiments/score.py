"""
Metrics for the WMT24 alignment experiments.

Implemented metrics:

* ``bleu``    - sacrebleu corpus BLEU (flores200 tokenizer, matching the paper).
* ``chrf``    - sacrebleu corpus chrF.
* ``comet22`` - COMET22 via PyMarian (``pymarian-eval``); model configurable.
* ``gemboid`` - pluggable external scorer supplied by the user (see below).

Each metric exposes ``score(langpair, hyps, refs, srcs) -> float`` where
``hyps`` and ``srcs`` are per-segment lists and ``refs`` is a list of reference
streams (each a per-segment list).

``comet22`` and ``gemboid`` are intentionally decoupled from heavy/optional
dependencies: they shell out to external commands and raise a clear,
actionable error if those are unavailable, so the BLEU/chrF pipeline always
runs even when PyMarian (or the user's gemboid model) is not yet installed.

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List

import sacrebleu

# sacrebleu tokenizer used for BLEU in the paper.
BLEU_TOKENIZER = os.environ.get("MWERALIGN_BLEU_TOK", "flores200")


def bleu(langpair: str, hyps: List[str], refs: List[List[str]], srcs: List[str]) -> float:
    return sacrebleu.corpus_bleu(hyps, refs, tokenize=BLEU_TOKENIZER).score


def chrf(langpair: str, hyps: List[str], refs: List[List[str]], srcs: List[str]) -> float:
    return sacrebleu.corpus_chrf(hyps, refs).score


def _write_lines(path: Path, lines: List[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def comet22(langpair: str, hyps: List[str], refs: List[List[str]], srcs: List[str]) -> float:
    """COMET22 via PyMarian's ``pymarian-eval`` CLI.

    Configurable via environment variables:
      * ``PYMARIAN_EVAL`` - path to the ``pymarian-eval`` executable.
      * ``COMET22_MODEL`` - model name/alias (default ``comet22``).
    """
    exe = os.environ.get("PYMARIAN_EVAL") or shutil.which("pymarian-eval")
    if not exe:
        raise RuntimeError(
            "pymarian-eval not found. Install PyMarian (`pip install pymarian`) "
            "or set PYMARIAN_EVAL to its path. COMET22 scoring is optional; the "
            "BLEU/chrF pipeline runs without it."
        )
    model = os.environ.get("COMET22_MODEL", "comet22")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src_f, hyp_f, ref_f = tmp / "src.txt", tmp / "hyp.txt", tmp / "ref.txt"
        _write_lines(src_f, srcs)
        _write_lines(hyp_f, hyps)
        _write_lines(ref_f, refs[0])  # COMET22 is reference-based, single ref
        cmd = [
            exe, "-m", model,
            "-s", str(src_f), "-t", str(hyp_f), "-r", str(ref_f),
            "--average", "only",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"pymarian-eval failed (exit {result.returncode}):\n{result.stderr}"
            )
        # The "--average only" output is a single floating-point score.
        match = re.search(r"-?\d+\.\d+", result.stdout)
        if not match:
            raise RuntimeError(f"could not parse COMET22 score from:\n{result.stdout}")
        return float(match.group())


def gemboid(langpair: str, hyps: List[str], refs: List[List[str]], srcs: List[str]) -> float:
    """Pluggable external scorer supplied by the user.

    Set the ``GEMBOID_CMD`` environment variable to a command template. The
    tokens ``{src}``, ``{hyp}``, and ``{ref}`` are substituted with temp-file
    paths; the command must print a single floating-point system-level score to
    stdout. Example::

        export GEMBOID_CMD="python /path/to/gemboid.py --src {src} --hyp {hyp} --ref {ref}"
    """
    template = os.environ.get("GEMBOID_CMD")
    if not template:
        raise RuntimeError(
            "gemboid scorer not configured. Set GEMBOID_CMD to a command "
            "template using {src} {hyp} {ref} placeholders that prints a single "
            "score to stdout."
        )
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src_f, hyp_f, ref_f = tmp / "src.txt", tmp / "hyp.txt", tmp / "ref.txt"
        _write_lines(src_f, srcs)
        _write_lines(hyp_f, hyps)
        _write_lines(ref_f, refs[0])
        cmd = shlex.split(
            template.format(src=src_f, hyp=hyp_f, ref=ref_f)
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"gemboid command failed (exit {result.returncode}):\n{result.stderr}"
            )
        match = re.search(r"-?\d+\.\d+", result.stdout)
        if not match:
            raise RuntimeError(f"could not parse gemboid score from:\n{result.stdout}")
        return float(match.group())


Metric = Callable[[str, List[str], List[List[str]], List[str]], float]

METRICS: Dict[str, Metric] = {
    "bleu": bleu,
    "chrf": chrf,
    "comet22": comet22,
    "gemboid": gemboid,
}


def score(metric: str, langpair: str, hyps: List[str], refs: List[List[str]],
          srcs: List[str]) -> float:
    if metric not in METRICS:
        raise ValueError(f"unknown metric {metric!r}; choose from {sorted(METRICS)}")
    return METRICS[metric](langpair, hyps, refs, srcs)
