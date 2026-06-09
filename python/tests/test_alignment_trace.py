#!/usr/bin/env python3
"""
Tests for the segmentation-DP trace and backpointer (BP) correctness.

The aligner solves a joint segmentation + alignment dynamic program. Its
backpointer bookkeeping is subtle, so these tests pin it down two ways:

1.  *Self-consistency* — the recorded boundary tables, the chosen boundaries,
    and the emitted segmentation all agree with each other.
2.  *Ground truth* — for small inputs the DP's optimum is checked against a
    brute-force search over every possible segmentation, and the segmentation
    the backpointers reconstruct is independently re-scored to confirm it really
    achieves the optimal cost.

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License").
"""

from itertools import combinations_with_replacement

import pytest

from mweralign import MwerAlign, align_texts, align_texts_traced
from mweralign.mweralign import AlignmentTrace


# --------------------------------------------------------------------------- #
# Reference implementations used as ground truth (deliberately simple/slow).
# --------------------------------------------------------------------------- #

def edit_distance(a, b):
    """Plain Levenshtein with unit substitution/insertion/deletion costs.

    Matches the aligner's default (non-human) cost model.
    """
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        curr = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def brute_force_segmentation(ref_segments, hyp_tokens):
    """Exhaustively find the minimum-cost segmentation of ``hyp_tokens``.

    Splits the hypothesis into ``len(ref_segments)`` contiguous (possibly empty)
    pieces and returns ``(best_cost, best_cuts)`` where ``best_cuts`` are the
    segment-end offsets. Only feasible for tiny inputs.
    """
    n_segs = len(ref_segments)
    j = len(hyp_tokens)
    best_cost = None
    best_cuts = None
    for interior in combinations_with_replacement(range(j + 1), n_segs - 1):
        cuts = (0,) + interior + (j,)
        total = 0
        for s in range(n_segs):
            seg = hyp_tokens[cuts[s]:cuts[s + 1]]
            total += edit_distance(ref_segments[s], seg)
        if best_cost is None or total < best_cost:
            best_cost = total
            best_cuts = cuts
    return best_cost, best_cuts


def _ref_str(ref_segments):
    return "\n".join(" ".join(seg) for seg in ref_segments)


def _hyp_str(hyp_tokens):
    return " ".join(hyp_tokens)


# Small fixtures covering identical, substitution, insertion, deletion and
# reordering-across-boundary cases.
CASES = [
    ([["a", "b"], ["c", "d"]], ["a", "b", "c", "d"]),
    ([["a", "b"], ["c", "d"]], ["a", "x", "c", "d"]),           # one sub
    ([["a", "b", "c"], ["d", "e"]], ["a", "b", "c", "d", "e"]),
    ([["a", "b"], ["c", "d"]], ["a", "b", "z", "c", "d"]),      # extra token
    ([["a", "b"], ["c", "d"]], ["a", "c", "d"]),                # missing token
    ([["the", "cat"], ["sat", "down"]], ["the", "cat", "sat", "down"]),
    ([["a"], ["b"], ["c"]], ["a", "b", "c"]),                   # 3 segments
    ([["a", "b"], ["b", "c"]], ["a", "b", "b", "c"]),           # repeated token
]


# --------------------------------------------------------------------------- #
# Opt-in behaviour
# --------------------------------------------------------------------------- #

def test_trace_off_by_default():
    """Without enabling trace collection, the trace tables stay empty."""
    aligner = MwerAlign()
    aligner.align("a b\nc d", "a b c d")
    trace = aligner.get_trace()
    assert trace.boundary_cost == []
    assert trace.boundary_bp == []
    assert trace.cells == []


def test_plain_align_unaffected_by_trace_api():
    """align_texts and align_texts_traced produce the same segmentation."""
    ref, hyp = "a b\nc d", "a b c d"
    plain = align_texts(ref, hyp)
    traced, _ = align_texts_traced(ref, hyp)
    assert plain == traced


# --------------------------------------------------------------------------- #
# Self-consistency of the recorded tables
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ref_segments,hyp_tokens", CASES)
def test_backtrace_self_consistent(ref_segments, hyp_tokens):
    """Reconstructing boundaries from BP reproduces the recorded boundaries."""
    _, trace = align_texts_traced(_ref_str(ref_segments), _hyp_str(hyp_tokens))
    reconstructed = trace.reconstruct_boundaries()
    S = trace.num_segments
    assert reconstructed[1:] == list(trace.boundaries)[1:S + 1]


@pytest.mark.parametrize("ref_segments,hyp_tokens", CASES)
def test_trace_dimensions(ref_segments, hyp_tokens):
    """The boundary table is shaped (J+1) x (S+1) as the DP indexing expects."""
    _, trace = align_texts_traced(_ref_str(ref_segments), _hyp_str(hyp_tokens))
    J, S = len(hyp_tokens), len(ref_segments)
    assert trace.num_hyp == J
    assert len(trace.boundary_cost) == J + 1
    assert all(len(row) == S + 1 for row in trace.boundary_cost)


# --------------------------------------------------------------------------- #
# Ground-truth optimality (the core BP-correctness check)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("ref_segments,hyp_tokens", CASES)
def test_dp_optimum_matches_bruteforce(ref_segments, hyp_tokens):
    """BC[J][S] equals the true minimum over all segmentations."""
    _, trace = align_texts_traced(_ref_str(ref_segments), _hyp_str(hyp_tokens))
    J, S = len(hyp_tokens), len(ref_segments)
    dp_cost = trace.boundary_cost[J][S]
    brute, _ = brute_force_segmentation(ref_segments, hyp_tokens)
    assert dp_cost == brute


@pytest.mark.parametrize("ref_segments,hyp_tokens", CASES)
def test_emitted_segmentation_achieves_optimum(ref_segments, hyp_tokens):
    """Re-scoring the segmentation the BPs produce yields the optimal cost.

    This is the strongest backpointer check: if BP pointed at the wrong
    predecessor, the segmentation actually emitted would not achieve the cost
    the DP claims is optimal.
    """
    result, trace = align_texts_traced(_ref_str(ref_segments), _hyp_str(hyp_tokens))
    J, S = len(hyp_tokens), len(ref_segments)

    emitted = [line.split() for line in result.split("\n")][:S]
    assert len(emitted) == S, f"expected {S} output segments, got {emitted}"

    recomputed = sum(
        edit_distance(ref, seg) for ref, seg in zip(ref_segments, emitted)
    )
    brute, _ = brute_force_segmentation(ref_segments, hyp_tokens)
    assert recomputed == brute == trace.boundary_cost[J][S]


# --------------------------------------------------------------------------- #
# Per-cell costs and the internal-word penalty
# --------------------------------------------------------------------------- #

def test_cells_recorded_and_chosen_is_minimal():
    """Each recorded cell's chosen cost is the minimum of the offered options."""
    _, trace = align_texts_traced("a b\nc d", "a b c d", cells=True)
    assert trace.cells, "expected per-cell costs to be recorded"
    for c in trace.cells:
        assert c.chosen == min(c.del_cost, c.ins_cost, c.sub_cost)
        assert c.op in ("S", "I", "D")


def test_internal_word_penalty_only_fires_under_legacy():
    """The +1000 internal-word penalty fires only in legacy mode.

    The penalty acts on the segment-initial alignment cell, not the output
    boundary, so it no longer governs the normal/SentencePiece paths (the hard
    mid-word boundary constraint does). It is retained solely to reproduce the
    pre-fix (paper) numbers, i.e. it fires only when ``legacy_penalty=True``.
    """
    # A '▁'-marked stream with an internal (markerless) piece 'w'.
    ref = "\u2581x \u2581y\n\u2581z \u2581w"
    hyp = "\u2581x \u2581y \u2581z w"

    _, legacy = align_texts_traced(
        ref, hyp, is_tokenized=True, legacy_penalty=True, cells=True)
    assert any(c.extra == 1000 for c in legacy.cells), \
        "legacy mode should consider the segment-initial internal-word penalty"

    # Tokenized but non-legacy: the penalty must NOT fire (constraint owns this).
    _, tokenized = align_texts_traced(ref, hyp, is_tokenized=True, cells=True)
    assert all(c.extra == 0 for c in tokenized.cells), \
        "non-legacy tokenized alignment must not apply the per-cell penalty"

    _, plain = align_texts_traced(ref, hyp, is_tokenized=False, cells=True)
    assert all(c.extra == 0 for c in plain.cells), \
        "untokenized alignment must not apply the penalty"


def test_penalty_avoids_internal_segment_start_when_possible():
    """With a clean alternative, no non-initial segment starts on an internal piece."""
    ref = "\u2581the \u2581cat\n\u2581sat \u2581down"
    hyp = "\u2581the \u2581cat \u2581sat \u2581down"
    result, _ = align_texts_traced(ref, hyp, is_tokenized=True)
    segments = [line.split() for line in result.split("\n") if line.strip()]
    for seg in segments[1:]:
        assert seg[0].startswith("\u2581"), \
            f"segment unexpectedly starts on an internal piece: {seg}"


def test_format_costs_is_readable():
    """The human-readable dump mentions each segment and its chosen end."""
    _, trace = align_texts_traced("a b\nc d", "a b c d")
    text = trace.format_costs()
    assert "segment 1" in text
    assert "chosen" in text


# --------------------------------------------------------------------------- #
# Hard mid-word boundary constraint
# --------------------------------------------------------------------------- #

def _segments(result):
    return [line.split() for line in result.split("\n") if line.strip()]


def _is_internal_word(piece):
    """Mirror C++ isInternalWord: internal (no '▁') AND not pure punctuation."""
    if piece.startswith("\u2581"):
        return False
    return any(ch.isalnum() for ch in piece)


# (ref_segments, hyp_pieces) where the unconstrained DP makes a mid-word cut.
MIDWORD_CASES = [
    ("\u2581x\n\u2581y", "\u2581x y"),
    ("\u2581the\n\u2581cat", "\u2581the cat"),
    ("\u2581a\n\u2581b\n\u2581c", "\u2581a b c"),
]


@pytest.mark.parametrize("ref,hyp", MIDWORD_CASES)
def test_constraint_forbids_midword_segment_start(ref, hyp):
    """With the constraint on, no non-initial segment starts on an internal word piece."""
    result, _ = align_texts_traced(
        ref, hyp, is_tokenized=True, forbid_midword_boundary=True)
    segments = _segments(result)
    for seg in segments[1:]:
        assert not _is_internal_word(seg[0]), \
            f"segment unexpectedly starts mid-word: {seg}"


@pytest.mark.parametrize("ref,hyp", MIDWORD_CASES)
def test_constraint_preserves_pieces(ref, hyp):
    """The constraint moves boundaries but never adds, drops or reorders pieces."""
    off, _ = align_texts_traced(ref, hyp, is_tokenized=True)
    on, _ = align_texts_traced(
        ref, hyp, is_tokenized=True, forbid_midword_boundary=True)
    off_segs, on_segs = _segments(off), _segments(on)
    # The flattened piece stream is unchanged (only boundaries move; avoiding a
    # mid-word cut may merge pieces into one segment, leaving others empty).
    assert [p for seg in on_segs for p in seg] == \
           [p for seg in off_segs for p in seg]


def test_constraint_off_by_default():
    """Without the flag, mid-word cuts are still permitted (old behavior)."""
    ref, hyp = "\u2581the\n\u2581cat", "\u2581the cat"
    result = align_texts(ref, hyp, is_tokenized=True)
    segments = _segments(result)
    # The unconstrained DP splits 'cat' into its own segment (a mid-word cut).
    assert any(_is_internal_word(seg[0]) for seg in segments[1:])


def test_constraint_allows_punctuation_segment_start():
    """A pure-punctuation internal piece may still start a segment under the constraint."""
    ref = "\u2581hi \u2581there\n. \u2581world"
    hyp = "\u2581hi \u2581there . \u2581world"
    result, _ = align_texts_traced(
        ref, hyp, is_tokenized=True, forbid_midword_boundary=True)
    segments = _segments(result)
    # 'world' is reached via a leading-marker piece; the boundary sits at the
    # punctuation, which is exempt, so the segmentation is still valid.
    assert len(segments) == 2
    assert "\u2581world" in segments[1]


def test_constraint_ignored_for_untokenized_input():
    """The constraint must not fire on plain whitespace input (every word looks internal)."""
    ref, hyp = "the cat\nsat down", "the cat sat down"
    plain = align_texts(ref, hyp, is_tokenized=False)
    constrained = align_texts(
        ref, hyp, is_tokenized=False, forbid_midword_boundary=True)
    assert plain == constrained


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
