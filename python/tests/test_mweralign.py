#!/usr/bin/env python3
"""
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

import re
import subprocess
import sys

import pytest
from mweralign import MwerAlign, align_texts, score_tokens, wer


def _run_cli(args, cwd=None):
    """Run the mweralign CLI as a subprocess; return (stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, "-m", "mweralign.mweralign", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
    return result.stdout, result.stderr


def test_basic_alignment():
    """Test basic text alignment functionality."""
    ref = "hello world"
    hyp = "hello world"

    result = align_texts(ref, hyp)
    assert isinstance(result, str)


def test_mweralign_class():
    """Test MwerAlign class."""
    aligner = MwerAlign()
    
    # Test alignment
    result = aligner.align("hello world", "hello world")
    assert isinstance(result, str)
    
    # Test reference loading
    refs = "hello world\ngoodbye world"
    success = aligner.load_references(refs)
    assert isinstance(success, bool)


def test_empty_reference_line():
    """Regression test for issue #1: an empty reference line must not crash.

    An empty line denotes an (empty) segment, so the output must contain a
    line for it and keep the alignment of the surrounding segments intact.
    """
    result = align_texts("aa\n\nbb", "aa bb")
    segments = result.split("\n")
    # one output segment per reference line (trailing newline yields an extra
    # empty element, which we ignore here)
    assert [s.strip() for s in segments[:3]] == ["aa", "", "bb"]


def test_only_empty_reference_lines():
    """Issue #1: a reference made up entirely of empty lines must not crash."""
    result = align_texts("\n\n", "x y")
    assert isinstance(result, str)


def test_score_tokens_counts():
    """score_tokens returns correct substitution/insertion/deletion counts."""
    assert score_tokens(["a", "b", "c"], ["a", "b", "c"]) == (0, 0, 0)
    assert score_tokens(["a", "b", "c"], ["a", "x", "c"]) == (1, 0, 0)  # 1 sub
    assert score_tokens(["a", "b"], ["a", "b", "c"]) == (0, 1, 0)       # 1 ins
    assert score_tokens(["a", "b", "c"], ["a", "c"]) == (0, 0, 1)       # 1 del


def test_score_tokens_empty_inputs():
    """Empty token lists produce only insertions or deletions."""
    assert score_tokens([], []) == (0, 0, 0)
    assert score_tokens([], ["a", "b"]) == (0, 2, 0)   # 2 insertions
    assert score_tokens(["a", "b"], []) == (0, 0, 2)   # 2 deletions


def test_score_tokens_all_different():
    """Completely disjoint sequences of equal length are all substitutions."""
    assert score_tokens(["a", "b", "c"], ["x", "y", "z"]) == (3, 0, 0)


def test_score_tokens_mixed_errors():
    """A mix of substitution, insertion, and deletion is counted correctly."""
    # ref: the quick brown fox
    # hyp: the quik brown lazy fox   (quick->quik sub, +lazy ins)
    subs, ins, dels = score_tokens(
        ["the", "quick", "brown", "fox"],
        ["the", "quik", "brown", "lazy", "fox"],
    )
    assert (subs, ins, dels) == (1, 1, 0)


def test_score_tokens_duplicate_tokens():
    """Repeated tokens align without spurious extra edits."""
    assert score_tokens(["a", "a", "a"], ["a", "a"]) == (0, 0, 1)
    assert score_tokens(["a", "a"], ["a", "a", "a"]) == (0, 1, 0)


def test_wer_basic():
    """wer computes errors / reference length."""
    assert wer("a b c d", "a b c d") == 0.0
    assert wer("a b c d", "a x c d") == 0.25            # 1 sub / 4
    assert wer("a b", "a b c") == 0.5                   # 1 ins / 2


def test_wer_deletions():
    """Deleted hypothesis words count against the reference length."""
    assert wer("a b c d", "a c d") == 0.25              # 1 del / 4
    assert wer("a b c d", "") == 1.0                    # 4 dels / 4


def test_wer_can_exceed_one():
    """WER is unbounded above when insertions outnumber the reference."""
    assert wer("a", "a b c") == 2.0                     # 2 ins / 1


def test_wer_is_case_insensitive_by_default():
    assert wer("Hello World", "hello world") == 0.0
    assert wer("Hello World", "hello world", lowercase=False) == 1.0  # 2 subs / 2


def test_wer_extra_whitespace_is_ignored():
    """Leading/trailing/internal extra whitespace does not affect tokenization."""
    assert wer("  a   b  c ", "a b c") == 0.0


def test_wer_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "a b") == 2.0  # two insertions, defined relative to hyp length


def test_score_matches_alignment_aswer(tmp_path):
    """Scoring the aligner's own output must reproduce its reported AS-WER.

    The standalone scoring mode and the alignment algorithm share the same cost
    model (unit substitution/insertion/deletion costs, normalized by reference
    length), so feeding the alignment output back through ``--score`` must yield
    the same corpus WER the aligner printed as ``AS-WER``.
    """
    ref = tmp_path / "ref.txt"
    sys_in = tmp_path / "sys.txt"
    aligned = tmp_path / "aligned.txt"
    ref.write_text("hello\nthis is a meeting\nwelcome everybody\ngood-bye\n")
    sys_in.write_text("hello this is a\nmeeting welcome here everybody\ngood-bye see you\n")

    # Align and capture both the AS-WER (stderr) and the segmented output.
    _, stderr = _run_cli(["-r", str(ref), "-t", str(sys_in), "-o", str(aligned), "-m", "none"])
    m = re.search(r"AS-WER.*?:\s*([0-9.]+)", stderr)
    assert m, f"could not find AS-WER in stderr:\n{stderr}"
    aswer = float(m.group(1))

    # Score the aligner's own output back against the references.
    stdout, _ = _run_cli(["--score", "-r", str(ref), "-t", str(aligned), "-m", "none"])
    m = re.search(r"TOTAL: WER=([0-9.]+)", stdout)
    assert m, f"could not find TOTAL WER in scoring output:\n{stdout}"
    score_wer = float(m.group(1))

    assert score_wer == pytest.approx(aswer)


def test_score_with_spm_tokenizer(tmp_path):
    """Scoring mode works end-to-end when an SPM tokenizer is requested."""
    spm = pytest.importorskip("sentencepiece")

    corpus = tmp_path / "corpus.txt"
    corpus.write_text(
        "hello this is a meeting\n"
        "welcome everybody good-bye\n"
        "the quick brown fox jumps over the lazy dog\n"
        "internationalization tokenization sentencepiece\n"
    )
    model_prefix = tmp_path / "tiny"
    spm.SentencePieceTrainer.train(
        input=str(corpus),
        model_prefix=str(model_prefix),
        vocab_size=60,
        character_coverage=1.0,
        model_type="bpe",
    )
    model = f"{model_prefix}.model"

    ref = tmp_path / "ref.txt"
    hyp = tmp_path / "hyp.txt"
    ref.write_text("hello this is a meeting\nthe quick brown fox\n")
    hyp.write_text("hello this is the meeting\nthe quick brown fox\n")

    stdout, _ = _run_cli(["--score", "-r", str(ref), "-t", str(hyp), "-m", model])

    # Two parallel segments plus a corpus total, computed over SPM pieces.
    assert stdout.count("segment ") == 2
    total = re.search(r"TOTAL: WER=([0-9.]+)", stdout)
    assert total, f"missing TOTAL line:\n{stdout}"
    # First segment differs (a -> the), second is identical -> total WER > 0.
    assert float(total.group(1)) > 0.0
    assert "segment 2: WER=0.00" in stdout


def test_no_whitespace_flag_matches_chinese_language(tmp_path):
    """``-w`` must be equivalent to ``-l zh`` and differ from the default.

    For a non-whitespace language, SPM pieces should not be treated as
    word-internal, so segment boundaries may start mid-"word". The ``-w``
    flag captures this generically; passing ``-l zh`` is the language-specific
    way to request the same behavior. Both must agree, and both must differ
    from the default (whitespace-language) handling on Chinese input.
    """
    from pathlib import Path

    model = Path(__file__).parent / "regression" / "spm32k.model"
    if not model.exists():
        pytest.skip("zh_spm model fixture not available")

    ref = tmp_path / "ref.txt"
    hyp = tmp_path / "hyp.txt"
    ref.write_text("新旧兼顾解决问题\n我们的规划体系也需要进行调整\n")
    hyp.write_text("新旧兼顾解决问题我们的规划体系也需要进行调整\n")

    out_lang = tmp_path / "lang.txt"
    out_w = tmp_path / "w.txt"
    out_default = tmp_path / "default.txt"
    _run_cli(["-r", str(ref), "-t", str(hyp), "-m", str(model), "-l", "zh", "-o", str(out_lang)])
    _run_cli(["-r", str(ref), "-t", str(hyp), "-m", str(model), "-w", "-o", str(out_w)])
    _run_cli(["-r", str(ref), "-t", str(hyp), "-m", str(model), "-o", str(out_default)])

    # -w and -l zh request the same non-whitespace handling.
    assert out_w.read_text() == out_lang.read_text()
    # ...and that handling differs from the default whitespace-language path.
    assert out_w.read_text() != out_default.read_text()


if __name__ == "__main__":
    pytest.main([__file__])