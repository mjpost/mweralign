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


from typing import List, Tuple
import sentencepiece as spm
from ._mweralign import MwerSegmenter as _MwerSegmenter
from .segmenter import CJSegmenter, SPSegmenter

# load logger
import logging
logger = logging.getLogger(__name__)
# Set up basic logging configuration
logging.basicConfig(level=logging.INFO, format='mweralign (%(asctime)s) %(levelname)s %(message)s')

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


def align_texts(reference: str, hypothesis: str, is_tokenized: bool = False) -> str:
    """
    Convenience function to align two texts.
    
    Args:
        reference: Reference text
        hypothesis: Hypothesis text
        is_tokenized: Whether the texts are tokenized (default: False)
        
    Returns:
        Alignment result
    """
    aligner = MwerAlign()
    aligner.set_tokenized(is_tokenized)
    return aligner.align(reference, hypothesis)


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
    parser.add_argument('--tokenizer', '-m', type=str, default=None, help="Tokenizer to use (path to model or keyword 'cj')")
    parser.add_argument("--language", "-l", default=None, help="Language being aligned (e.g, en)")
    parser.add_argument("--no-detok", action="store_true", default=False)
    parser.add_argument("--score", action="store_true", default=False,
                        help="Scoring mode: ref and hyp are already aligned line-by-line; "
                             "report per-segment and corpus WER instead of aligning.")
    args = parser.parse_args()

    refs = [line.strip() for line in args.ref_file.readlines()]
    hyps = [line.strip() for line in args.hyp_file.readlines()]

    segmenter = None
    if args.tokenizer == "cj":
        segmenter = CJSegmenter()

    elif args.tokenizer is not None:
        # Load tokenizer if specified
        try:
            segmenter = SPSegmenter(args.tokenizer)
        except Exception as e:
            logger.info(f"Error loading tokenizer: {e}")
            sys.exit(1)

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

    # This param causes the AS-WER algorithm to disallow internal tokens
    # at the start of sentences (via a high cost penalty). This is important
    # in whitespace languages, but is not what we want with C&J, where most tokens
    # appear to be internal because there was no whitespace.
    is_tokenized = type(segmenter) is SPSegmenter and args.language not in ["ja", "zh"]

    for i, (docid_start, docid_end) in enumerate(docid_ranges):
        hyp_str = tokenize_and_join([hyps[i]])
        ref_str = tokenize_and_join(refs[docid_start:docid_end])

        logger.info(f"Aligning {len(hyp_str.split())} tokens to " + str(len(ref_str.split('\n'))) + " references")

        # Perform alignment
        try:
            result = align_texts(ref_str, hyp_str, is_tokenized=is_tokenized)
            
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