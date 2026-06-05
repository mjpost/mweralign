"""
WMT24 data access for the alignment experiments.

All data (sources, references, document ids, domains, and *system outputs*) is
served straight from sacrebleu's bundled ``DATASETS`` for ``wmt24`` -- no
separate download of mt-metrics-eval is required for the alignment/scoring
pipeline. (mt-metrics-eval is only needed later, for human-judgment
correlation.)

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Dict, List

import sacrebleu

TESTSET = "wmt24"

# Fields that are not system outputs.
_META_FIELDS = {"src", "docid", "origlang", "domain"}

# flores200 SPM model downloaded/cached by sacrebleu; reused for mweralign ``-m``.
FLORES_MODEL = Path.home() / ".sacrebleu" / "models" / "flores200sacrebleuspm"


def _dataset():
    return sacrebleu.DATASETS[TESTSET]


def langpairs() -> List[str]:
    """All WMT24 language pairs (e.g. ``en-de``, ``ja-zh``)."""
    return sorted(sacrebleu.get_langpairs_for_testset(TESTSET))


def target_language(langpair: str) -> str:
    """Target-language code of a ``src-tgt`` language pair."""
    return langpair.split("-", 1)[1]


def _fieldnames(langpair: str) -> List[str]:
    return _dataset().fieldnames(langpair)


@functools.lru_cache(maxsize=None)
def _read_field(langpair: str, name: str) -> tuple:
    """Read one field of a language pair as a tuple of lines (cached)."""
    fields = _fieldnames(langpair)
    idx = fields.index(name)
    path = _dataset().get_files(langpair)[idx]
    with open(path, encoding="utf-8") as fh:
        return tuple(line.rstrip("\n") for line in fh)


def _ref_fields(langpair: str) -> List[str]:
    return [f for f in _fieldnames(langpair) if f == "ref" or f.startswith("ref:")]


def sources(langpair: str) -> List[str]:
    return list(_read_field(langpair, "src"))


def docids(langpair: str) -> List[str]:
    return list(_read_field(langpair, "docid"))


def domains(langpair: str) -> List[str]:
    """Per-segment domain label (e.g. ``news``); falls back to the docid."""
    if "domain" in _fieldnames(langpair):
        return list(_read_field(langpair, "domain"))
    return docids(langpair)


def references(langpair: str) -> List[List[str]]:
    """All references as a list of segment lists (one inner list per reference)."""
    return [list(_read_field(langpair, f)) for f in _ref_fields(langpair)]


def primary_reference(langpair: str) -> List[str]:
    """The first reference's segments."""
    return list(_read_field(langpair, _ref_fields(langpair)[0]))


def systems(langpair: str) -> List[str]:
    """Names of all system-output fields for a language pair."""
    return [
        f
        for f in _fieldnames(langpair)
        if f not in _META_FIELDS and not (f == "ref" or f.startswith("ref:"))
    ]


def system_output(langpair: str, system: str) -> List[str]:
    """Segment-level output of one system."""
    return list(_read_field(langpair, system))


def flores_model() -> Path:
    """Path to the flores200 SPM model, raising a helpful error if missing."""
    if not FLORES_MODEL.exists():
        raise FileNotFoundError(
            f"flores200 SPM model not found at {FLORES_MODEL}.\n"
            "Trigger a sacrebleu download once with:\n"
            "  python -c \"from sacrebleu.tokenizers.tokenizer_spm import "
            "Flores200Tokenizer; Flores200Tokenizer()('x')\""
        )
    return FLORES_MODEL


def domain_groups(domain_labels: List[str]) -> Dict[str, List[int]]:
    """Map each domain label to the list of segment indices it contains.

    Order within each group preserves the original segment order, so the
    resulting per-domain documents can be un-permuted back afterwards.
    """
    groups: Dict[str, List[int]] = {}
    for i, dom in enumerate(domain_labels):
        groups.setdefault(dom, []).append(i)
    return groups
