#!/usr/bin/env python3
"""
Python wrapper for MwerAlign C++ library.

Copyright (c) 2025 Matt Post

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""


from typing import List, NamedTuple, Optional, Tuple
import sentencepiece as spm
from ._mweralign import MwerSegmenter as _MwerSegmenter
from .segmenter import CJSegmenter, SPSegmenter, cjk_fraction
from . import models

# load logger
import logging
logger = logging.getLogger(__name__)
# Set up basic logging configuration
logging.basicConfig(level=logging.INFO, format='[mweralign] %(levelname)s: %(message)s')


class CellCost(NamedTuple):
    """One Levenshtein cell recorded by the segmentation DP."""
    j: int            # hypothesis position (1-based)
    i: int            # reference position (1-based)
    ref: int          # reference index
    del_cost: int     # total cost of the deletion option
    ins_cost: int     # total cost of the insertion option
    sub_cost: int     # total cost of the substitution option
    chosen: int       # cost of the option the DP took
    extra: int        # segment-initial internal-word penalty applied here
    op: str           # chosen edit: 'S', 'I' or 'D'
    is_new_sent: bool # whether the cell sits at a segment start


class AlignmentTrace:
    """Structured view of the segmentation DP from a single alignment.

    Captures every competing segment boundary (not just the chosen one), so the
    backpointer logic can be independently verified. Indexing matches the C++
    tables: ``boundary_cost[j][s]`` is the best total cost of a segmentation
    that ends segment ``s`` at hypothesis position ``j``; ``boundary_bp[j][s]``
    is the hypothesis position where segment ``s-1`` ends in that solution.
    """

    # Sentinel the DP uses for unreachable boundary cells.
    UNREACHABLE = 100000000

    def __init__(self, boundary_cost, boundary_bp, boundary_ref,
                 boundaries, segment_costs, cells):
        self.boundary_cost = boundary_cost      # BC[j][s]
        self.boundary_bp = boundary_bp          # BP[j][s]
        self.boundary_ref = boundary_ref        # BR[j][s]
        self.boundaries = boundaries            # chosen boundary[s]
        self.segment_costs = segment_costs      # sentCosts[s]
        self.cells = [CellCost(*c) for c in cells]

    @property
    def num_hyp(self) -> int:
        """Number of hypothesis tokens (J)."""
        return len(self.boundary_cost) - 1

    @property
    def num_segments(self) -> int:
        """Number of segments (S)."""
        return len(self.boundaries) - 1 if self.boundaries else 0

    def column_candidates(self, s: int) -> List[Tuple[int, int, int]]:
        """All reachable segment ends for segment ``s``.

        Returns a list of ``(j, cost, bp)`` for every hypothesis position ``j``
        at which segment ``s`` could end, sorted by increasing cost. The first
        element is the cheapest boundary the DP could have chosen for ``s``.
        """
        out = []
        for j in range(len(self.boundary_cost)):
            row = self.boundary_cost[j]
            if s < len(row):
                cost = row[s]
                if cost < self.UNREACHABLE:
                    out.append((j, cost, self.boundary_bp[j][s]))
        out.sort(key=lambda t: (t[1], t[0]))
        return out

    def reconstruct_boundaries(self) -> List[int]:
        """Independently re-run the backtrace from the boundary tables.

        Follows BP from (j=J, s=S) back to s=0 and returns the segment-end
        positions. Used by the test suite to confirm the C++ backtrace and the
        recorded tables agree.
        """
        J, S = self.num_hyp, self.num_segments
        ends = [0] * (S + 1)
        k, s = J, S
        while s > 0:
            ends[s] = self.boundary_bp[k][s]
            k = self.boundary_bp[k][s]
            s -= 1
        return ends

    def chosen_end(self, s: int) -> int:
        """Hypothesis position at which segment ``s`` ends in the chosen path.

        The C++ ``boundary[s]`` records the end of segment ``s-1``, so segment
        ``s`` ends at ``boundary[s+1]`` (and the final segment ends at ``J``).
        """
        if s >= self.num_segments:
            return self.num_hyp
        return self.boundaries[s + 1]

    def format_costs(self, max_segments: Optional[int] = None) -> str:
        """Human-readable dump of the competing boundary costs per segment."""
        lines = []
        S = self.num_segments
        last = S if max_segments is None else min(S, max_segments)
        for s in range(1, last + 1):
            chosen = self.chosen_end(s)
            cands = self.column_candidates(s)
            chosen_cost = self.boundary_cost[chosen][s] if chosen < len(self.boundary_cost) else None
            lines.append(f"segment {s}: chosen end j={chosen} (cost={chosen_cost})")
            for j, cost, bp in cands[:8]:
                mark = "  <- chosen" if j == chosen else ""
                lines.append(f"    end j={j:4d}  cost={cost:6d}  prev_end={bp}{mark}")
        return "\n".join(lines)


class MwerAlign:
    """Python wrapper for Minimum Word Error Rate Alignment."""
    
    def __init__(self):
        self._segmenter = _MwerSegmenter()
    
    def set_tokenized(self, is_tokenized: bool):
        """
        Set whether the input texts are tokenized.
        
        Args:
            is_tokenized: True if the texts are tokenized, False otherwise
        """
        self._segmenter.set_tokenized(is_tokenized)

    def set_collect_trace(self, enable: bool, cells: bool = False):
        """
        Enable or disable collection of the alignment trace.

        When enabled, the next ``align()`` call records the boundary DP table
        (O(J*S)), retrievable via ``get_trace()``. Per-cell costs (O(J*I*R)) are
        large and only meaningful for small diagnostic inputs, so they are off
        unless ``cells=True``. Disabled by default; the off path adds no
        measurable cost to alignment.

        Args:
            enable: True to collect the boundary trace on subsequent alignments
            cells: True to also record every Levenshtein cell's costs (small
                inputs only)
        """
        self._segmenter.set_collect_trace(enable)
        self._segmenter.set_collect_cells(enable and cells)

    def get_trace(self) -> AlignmentTrace:
        """
        Return the :class:`AlignmentTrace` from the most recent alignment.

        Requires ``set_collect_trace(True)`` to have been set before aligning.

        Returns:
            The structured trace (boundary tables, chosen boundaries, cells).
        """
        return AlignmentTrace(
            boundary_cost=self._segmenter.trace_boundary_cost(),
            boundary_bp=self._segmenter.trace_boundary_bp(),
            boundary_ref=self._segmenter.trace_boundary_ref(),
            boundaries=list(self._segmenter.boundaries()),
            segment_costs=list(self._segmenter.segment_costs()),
            cells=self._segmenter.trace_cells(),
        )

    def set_legacy_penalty(self, enable: bool):
        """
        TEMPORARY: restore the pre-fix penalty behavior.

        When enabled, the segment-initial "internal word" penalty is applied
        even for untokenized (whitespace) input, reproducing alignments produced
        before the untokenized-alignment fix.

        Args:
            enable: True to apply the legacy (paper) penalty behavior
        """
        self._segmenter.set_legacy_penalty(enable)

    def set_forbid_midword_boundary(self, enable: bool):
        """
        Forbid mid-word segmentation boundaries.

        When enabled, the segmentation DP may not end a non-final segment at a
        position that would start the following segment on a word-internal,
        non-punctuation piece. Off by default.

        Args:
            enable: True to forbid mid-word segmentation boundaries
        """
        self._segmenter.set_forbid_midword_boundary(enable)

    def align(self, reference: str, hypothesis: str) -> str:
        """
        Align reference and hypothesis strings.
        
        Args:
            reference: Reference text
            hypothesis: Hypothesis text to align
            
        Returns:
            Aligned result string
        """
        return self._segmenter.mwerAlign(reference, hypothesis)
    def load_references(self, references: str) -> bool:
        """
        Load reference text from string.
        
        Args:
            references: Reference text (one sentence per line)
            
        Returns:
            True if successful
        """
        return self._segmenter.loadrefsFromStream(references)
    
    def load_references_file(self, filename: str) -> bool:
        """
        Load references from file.
        
        Args:
            filename: Path to reference file
            
        Returns:
            True if successful
        """
        return self._segmenter.loadrefs(filename)
    
    def evaluate(self, hypothesis_text: str) -> Tuple[float, str]:
        """
        Evaluate hypothesis against loaded references.
        
        Args:
            hypothesis_text: Hypothesis text to evaluate
            
        Returns:
            Tuple of (error_rate, detailed_output)
        """
        # This would need adaptation based on your SimpleText implementation
        # For now, returning placeholder
        return 0.0, ""


def align_texts(reference: str, hypothesis: str, is_tokenized: bool = False,
                legacy_penalty: bool = False,
                forbid_midword_boundary: bool = False) -> str:
    """
    Convenience function to align two texts.
    
    Args:
        reference: Reference text
        hypothesis: Hypothesis text
        is_tokenized: Whether the texts are tokenized (default: False)
        legacy_penalty: Restore the pre-fix penalty behavior (default: False)
        forbid_midword_boundary: Forbid mid-word segmentation boundaries
            (default: False)
        
    Returns:
        Alignment result
    """
    aligner = MwerAlign()
    aligner.set_tokenized(is_tokenized)
    if legacy_penalty:
        aligner.set_legacy_penalty(True)
    if forbid_midword_boundary:
        aligner.set_forbid_midword_boundary(True)
    return aligner.align(reference, hypothesis)


def align_texts_traced(reference: str, hypothesis: str, is_tokenized: bool = False,
                       legacy_penalty: bool = False,
                       forbid_midword_boundary: bool = False,
                       cells: bool = False) -> Tuple[str, AlignmentTrace]:
    """
    Align two texts and also return the segmentation DP trace.

    Identical to :func:`align_texts` but with trace collection enabled, so the
    competing segment boundaries (and, with ``cells=True``, per-cell costs) are
    available for inspection or testing.

    Args:
        reference: Reference text
        hypothesis: Hypothesis text
        is_tokenized: Whether the texts are tokenized (default: False)
        legacy_penalty: Restore the pre-fix penalty behavior (default: False)
        forbid_midword_boundary: Forbid mid-word segmentation boundaries
            (default: False)
        cells: Also record per-cell costs (O(J*I*R); small inputs only)

    Returns:
        Tuple of (alignment result, :class:`AlignmentTrace`).
    """
    aligner = MwerAlign()
    aligner.set_tokenized(is_tokenized)
    if legacy_penalty:
        aligner.set_legacy_penalty(True)
    if forbid_midword_boundary:
        aligner.set_forbid_midword_boundary(True)
    aligner.set_collect_trace(True, cells=cells)
    result = aligner.align(reference, hypothesis)
    return result, aligner.get_trace()


def score_tokens(ref_tokens: List[str], hyp_tokens: List[str]) -> Tuple[int, int, int]:
    """
    Compute word-level edit counts between a reference and a hypothesis.

    Uses a standard Levenshtein alignment with unit substitution, insertion,
    and deletion costs (matching the default cost model of the C++ aligner).
    Substitutions are preferred over insert+delete on ties so the counts are
    well defined.

    Args:
        ref_tokens: Reference tokens
        hyp_tokens: Hypothesis tokens

    Returns:
        Tuple of (substitutions, insertions, deletions).
    """
    n, m = len(ref_tokens), len(hyp_tokens)
    # cost[i][j] = (total_cost, subs, ins, dels) aligning ref[:i] with hyp[:j]
    prev = [(j, 0, j, 0) for j in range(m + 1)]
    for i in range(1, n + 1):
        curr = [(i, 0, 0, i)] + [(0, 0, 0, 0)] * m
        for j in range(1, m + 1):
            match = ref_tokens[i - 1] == hyp_tokens[j - 1]
            sub_cost, sub_s, sub_i, sub_d = prev[j - 1]
            sub = (sub_cost + (0 if match else 1), sub_s + (0 if match else 1), sub_i, sub_d)
            del_cost, del_s, del_i, del_d = prev[j]
            dele = (del_cost + 1, del_s, del_i, del_d + 1)
            ins_cost, ins_s, ins_i, ins_d = curr[j - 1]
            ins = (ins_cost + 1, ins_s, ins_i + 1, ins_d)
            # Prefer substitution/match, then deletion, then insertion on ties.
            best = sub
            if dele[0] < best[0]:
                best = dele
            if ins[0] < best[0]:
                best = ins
            curr[j] = best
        prev = curr
    _, subs, ins, dels = prev[m]
    return subs, ins, dels


def wer(reference: str, hypothesis: str, lowercase: bool = True) -> float:
    """
    Compute the word error rate (WER) between two whitespace-tokenized strings.

    Args:
        reference: Reference string
        hypothesis: Hypothesis string
        lowercase: Lowercase both sides before comparison (default: True,
            matching the aligner's case-insensitive behavior).

    Returns:
        WER as a fraction of the reference length. An empty reference yields
        0.0 when the hypothesis is also empty, otherwise the number of
        inserted tokens (so the metric stays defined).
    """
    if lowercase:
        reference = reference.lower()
        hypothesis = hypothesis.lower()
    ref_tokens = reference.split()
    hyp_tokens = hypothesis.split()
    subs, ins, dels = score_tokens(ref_tokens, hyp_tokens)
    errors = subs + ins + dels
    if not ref_tokens:
        return 0.0 if not hyp_tokens else float(errors)
    return errors / len(ref_tokens)


def main():
    """Command-line interface for mweralign."""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='Minimum Word Error Rate Alignment')
    parser.add_argument('--ref-file', "-r", type=argparse.FileType("r"), required=True, help='Reference text or file')
    parser.add_argument('--hyp-file', "-t", type=argparse.FileType("r"), required=True, help='Hypothesis text or file')
    parser.add_argument("--docid-file", "-d", type=argparse.FileType("r"), default=None, help="Docid file")
    parser.add_argument('--output', '-o', type=argparse.FileType("w"), default=sys.stdout,
                        help='Output file (default: stdout)')
    parser.add_argument('--tokenizer', '-m', type=str, default="spm32k",
                        help="Tokenizer to use (default: spm32k): 'none' for plain "
                             "whitespace, 'cj' for Han-character segmentation, a "
                             "SentencePiece model path, or a named model downloaded on "
                             "demand (spm32k, spm64k, spm128k, spm256k; 'spm' = 256k).")
    parser.add_argument("--language", "-l", default=None, help="Language being aligned (e.g, en)")
    parser.add_argument("--no-whitespace", "-w", action="store_true", default=False,
                        help="The aligned language does not delimit words with whitespace "
                             "(e.g. Chinese, Japanese). Lets segments begin at word-internal "
                             "boundaries; equivalent to passing -l zh / -l ja.")
    parser.add_argument("--no-detok", action="store_true", default=False)
    parser.add_argument("--score", action="store_true", default=False,
                        help="Scoring mode: ref and hyp are already aligned line-by-line; "
                             "report per-segment and corpus WER instead of aligning.")
    parser.add_argument("--legacy-penalty", action="store_true", default=False,
                        help="TEMPORARY: restore the pre-fix penalty behavior (apply the "
                             "segment-initial internal-word penalty even for untokenized "
                             "input). Used to reproduce pre-fix (paper) results.")
    parser.add_argument("--trace-file", type=argparse.FileType("w"), default=None,
                        help="Collect the segmentation DP trace and write a human-readable "
                             "dump of the competing segment-boundary costs to this file "
                             "('-' for stdout). Off by default; adds no cost when unused.")
    args = parser.parse_args()

    refs = [line.strip() for line in args.ref_file.readlines()]
    hyps = [line.strip() for line in args.hyp_file.readlines()]

    segmenter = None
    if args.tokenizer in ("none", "whitespace"):
        # Plain whitespace tokenization (no segmenter).
        segmenter = None
    elif args.tokenizer == "cj":
        segmenter = CJSegmenter()

    elif args.tokenizer is not None:
        # A named model (e.g. 'spm32k') is fetched/cached on demand; any other
        # value is treated as a filesystem path to a SentencePiece model.
        try:
            model = models.resolve(args.tokenizer)
            segmenter = SPSegmenter(model)
        except Exception as e:
            logger.info(f"Error loading tokenizer: {e}")
            sys.exit(1)

    # Whether the aligned language delimits words with whitespace. CJK languages
    # (and an explicit --no-whitespace) let segments start mid-"word".
    non_whitespace_lang = args.no_whitespace or args.language in ("ja", "zh")

    def tokenize_and_join(text: List[str]) -> List[str]:
        """Tokenize text using the segmenter."""
        if segmenter is not None:
            for i in range(len(text)):
                if " ### " in text[i]:
                    pieces = text[i].strip().split(" ### ")
                    text[i] = " ### ".join([" ".join(segmenter.encode(p)) for p in pieces])
                elif "\t" in text[i]:
                    pieces = text[i].strip().split("\t")
                    # underlying C++ binary still uses ###
                    text[i] = " ### ".join([" ".join(segmenter.encode(p)) for p in pieces])
                else:
                    text[i] = " ".join(segmenter.encode(text[i].strip()))
        return "\n".join(text)

    if args.score:
        if len(refs) != len(hyps):
            logger.info(f"Error: --score requires parallel input, but got {len(refs)} "
                        f"reference lines and {len(hyps)} hypothesis lines.")
            sys.exit(1)

        def tokenize_line(line: str) -> str:
            if segmenter is None:
                return line
            return " ".join(segmenter.encode(line.strip()))

        total_errors = 0
        total_ref_words = 0
        for i, (ref, hyp) in enumerate(zip(refs, hyps), start=1):
            ref_tok = tokenize_line(ref)
            hyp_tok = tokenize_line(hyp)
            subs, ins, dels = score_tokens(ref_tok.lower().split(), hyp_tok.lower().split())
            errors = subs + ins + dels
            n = len(ref_tok.split())
            total_errors += errors
            total_ref_words += n
            seg_wer = 100.0 * errors / n if n else (0.0 if errors == 0 else float("inf"))
            print(f"segment {i}: WER={seg_wer:.2f} (S={subs} I={ins} D={dels} N={n})",
                  file=args.output)

        corpus_wer = 100.0 * total_errors / total_ref_words if total_ref_words else 0.0
        print(f"TOTAL: WER={corpus_wer:.2f} (errors={total_errors} ref_words={total_ref_words})",
              file=args.output)
        return

    docids = []
    if not args.docid_file:
        docids = ["0"] * len(refs)
        hyps = [" ".join(hyps)]
    else:
        docids = [line.strip() for line in args.docid_file.readlines()]

    if len(docids) != len(refs):
        logger.info(f"Error: Number of docids ({len(docids)}) does not match number of references ({len(refs)}).")
        sys.exit(1)

    # make sure the number of distinct docids matches the number of hypotheses
    if len(set(docids)) != len(hyps):
        logger.info(f"Error: Number of distinct docids ({len(set(docids))}) does not match number of hypotheses ({len(hyps)}).")
        sys.exit(1)

    # build a list of docid ranges
    current_docid_start = 0
    current_docid = docids[0]
    docid_ranges = []
    for i in range(1, len(docids)):
        if docids[i] != current_docid:
            docid_ranges.append((current_docid_start, i))
            current_docid_start = i
            current_docid = docids[i]
    if current_docid_start < len(docids):
        docid_ranges.append((current_docid_start, len(docids)))

    # Nudge users who are aligning CJK text without telling the aligner about it.
    if not non_whitespace_lang and cjk_fraction(" ".join(refs[:200])) > 0.2:
        logger.warning(
            "The reference looks like a non-whitespace script (e.g. Chinese or "
            "Japanese), but no language was set. Pass -l zh / -l ja (or "
            "--no-whitespace / -w) so the aligner can begin segments at "
            "word-internal boundaries."
        )

    # This param causes the AS-WER algorithm to disallow internal tokens
    # at the start of sentences (via a high cost penalty). This is important
    # in whitespace languages, but is not what we want with C&J, where most tokens
    # appear to be internal because there was no whitespace.
    is_tokenized = type(segmenter) is SPSegmenter and not non_whitespace_lang

    trace_out = sys.stderr if args.trace_file is None else args.trace_file
    collect_trace = args.trace_file is not None

    for i, (docid_start, docid_end) in enumerate(docid_ranges):
        hyp_str = tokenize_and_join([hyps[i]])
        ref_str = tokenize_and_join(refs[docid_start:docid_end])

        logger.info(f"Aligning {len(hyp_str.split())} tokens to " + str(len(ref_str.split('\n'))) + " references")

        # Perform alignment
        try:
            if collect_trace:
                result, trace = align_texts_traced(
                    ref_str, hyp_str, is_tokenized=is_tokenized,
                    legacy_penalty=args.legacy_penalty,
                    forbid_midword_boundary=is_tokenized)
                print(f"# docid range {i} (segments {docid_start}-{docid_end})",
                      file=trace_out)
                print(trace.format_costs(), file=trace_out)
            else:
                result = align_texts(ref_str, hyp_str, is_tokenized=is_tokenized,
                                     legacy_penalty=args.legacy_penalty,
                                     forbid_midword_boundary=is_tokenized)

            # Output result
            for line in result.split("\n"):
                if segmenter is not None and not args.no_detok:
                    line = segmenter.decode(line)
                print(line, file=args.output)
                
        except Exception as e:
            logger.fatal(f"Error: {e}")
            sys.exit(1)


if __name__ == '__main__':
    main()