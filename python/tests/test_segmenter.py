import pytest
from mweralign.segmenter import CJSegmenter, SPSegmenter, is_latin1, is_cjk, cjk_fraction


class TestIsLatin1:
    """Test the is_latin1 helper function."""

    def test_ascii_characters(self):
        assert is_latin1('a')
        assert is_latin1('Z')
        assert is_latin1('1')
        assert is_latin1(' ')
        assert is_latin1('!')

    def test_extended_latin1(self):
        assert is_latin1('é')  # U+00E9
        assert is_latin1('ñ')  # U+00F1
        assert is_latin1('ü')  # U+00FC

    def test_non_latin1(self):
        assert not is_latin1('中')  # Chinese character
        assert not is_latin1('日')  # Japanese character
        assert not is_latin1('한')  # Korean character
        assert not is_latin1('€')  # Euro symbol (U+20AC)


class TestCJKDetection:
    """Test the is_cjk / cjk_fraction helpers used to suggest the language flag."""

    def test_is_cjk_true(self):
        assert is_cjk('中')   # Han
        assert is_cjk('日')   # Han (also Japanese)
        assert is_cjk('あ')   # Hiragana
        assert is_cjk('カ')   # Katakana
        assert is_cjk('한')   # Hangul

    def test_is_cjk_false(self):
        assert not is_cjk('a')
        assert not is_cjk('é')
        assert not is_cjk('!')
        assert not is_cjk('€')

    def test_cjk_fraction_all_cjk(self):
        assert cjk_fraction('这是测试') == 1.0

    def test_cjk_fraction_none(self):
        assert cjk_fraction('hello world') == 0.0

    def test_cjk_fraction_ignores_whitespace(self):
        # Spaces are excluded from the denominator.
        assert cjk_fraction('中 文') == 1.0

    def test_cjk_fraction_mixed(self):
        # 2 of 4 non-space characters are CJK.
        assert cjk_fraction('ab中文') == pytest.approx(0.5)

    def test_cjk_fraction_empty(self):
        assert cjk_fraction('') == 0.0
        assert cjk_fraction('   ') == 0.0


class TestCJSegmenter:
    """Test the CJSegmenter class.

    ``encode`` preserves whitespace by replacing it with the SentencePiece
    meta-symbol ``▁`` (U+2581) so it can be restored on ``decode``. Runs of
    Latin-1 characters become a single token, while every non-Latin-1 (e.g.
    Han) character is its own token. ``decode`` takes the space-joined token
    string the aligner produces and reconstructs the original text.
    """

    def setup_method(self):
        self.segmenter = CJSegmenter()

    def test_encode_latin1_words(self):
        assert self.segmenter.encode("hello world") == ["hello\u2581world"]

    def test_encode_chinese_characters(self):
        assert self.segmenter.encode("中国") == ["中", "国"]

    def test_encode_mixed_latin1_chinese(self):
        assert self.segmenter.encode("hello中国world") == ["hello", "中", "国", "world"]

    def test_encode_mixed_with_spaces(self):
        assert self.segmenter.encode("hello 中国 world") == ["hello\u2581", "中", "国", "\u2581world"]

    def test_encode_empty_string(self):
        assert self.segmenter.encode("") == []

    def test_encode_only_spaces(self):
        assert self.segmenter.encode("   ") == ["\u2581\u2581\u2581"]

    def test_encode_punctuation(self):
        assert self.segmenter.encode("hello, world!") == ["hello,\u2581world!"]

    def test_decode_latin1_tokens(self):
        # decode receives the space-joined token string from the aligner
        assert self.segmenter.decode("hello world") == "helloworld"

    def test_decode_chinese_tokens(self):
        assert self.segmenter.decode("中 国") == "中国"

    def test_decode_mixed_tokens(self):
        assert self.segmenter.decode("hello 中 国 world") == "hello中国world"

    def test_decode_restores_spaces(self):
        # the meta-symbol '▁' stands in for the original whitespace
        assert self.segmenter.decode("hello\u2581world") == "hello world"

    def test_decode_empty_string(self):
        assert self.segmenter.decode("") == ""

    def test_decode_single_token(self):
        assert self.segmenter.decode("hello") == "hello"

    def test_roundtrip_latin1(self):
        text = "hello world test"
        tokens = self.segmenter.encode(text)
        assert self.segmenter.decode(" ".join(tokens)) == text

    def test_roundtrip_chinese(self):
        text = "中国日本"
        tokens = self.segmenter.encode(text)
        assert self.segmenter.decode(" ".join(tokens)) == text

    @pytest.mark.parametrize("text", [
        "看视频 WxsYTK8l_Gk 结束",      # literal underscore inside a URL/id
        "a_b c",                         # underscore between Latin tokens
        "__double__ and 中文_混合",      # underscores adjacent to Han characters
    ])
    def test_roundtrip_preserves_literal_underscore(self, text):
        # Spaces are encoded with the SentencePiece meta-symbol '▁', so literal
        # underscores pass through untouched and round-trip faithfully
        # (regression for them previously becoming spaces).
        tokens = self.segmenter.encode(text)
        assert self.segmenter.decode(" ".join(tokens)) == text

    @pytest.mark.parametrize("text", [
        "literal ▁ meta symbol",   # a literal U+2581 (the space placeholder)
        "▁leading",                # literal ▁ at the start
        "trailing▁",               # literal ▁ at the end
        "中▁文",                    # literal ▁ between Han characters
    ])
    def test_roundtrip_preserves_literal_meta_symbol(self, text):
        # A literal '▁' is escaped on encode so it is not confused with an
        # encoded space, and restored on decode (regression for it previously
        # collapsing to a space). Note decode() still strips outer whitespace,
        # since a segment-merge separator can leave a spurious edge space.
        tokens = self.segmenter.encode(text)
        assert self.segmenter.decode(" ".join(tokens)) == text


@pytest.mark.skipif(True, reason="Requires SentencePiece model file")
class TestSPSegmenter:
    """Test the SPSegmenter class. Skipped by default as it requires a model file."""

    def setup_method(self):
        # This would need a real SentencePiece model file
        self.model_path = "path/to/test.model"
        self.segmenter = SPSegmenter(self.model_path)

    def test_encode_returns_list(self):
        result = self.segmenter.encode("hello world")
        assert isinstance(result, list)
        assert all(isinstance(token, str) for token in result)

    def test_decode_returns_string(self):
        result = self.segmenter.decode("hello world")
        assert isinstance(result, str)

    def test_roundtrip(self):
        text = "hello world"
        tokens = self.segmenter.encode(text)
        decoded = self.segmenter.decode(" ".join(tokens))
        # Exact match may not be guaranteed due to tokenization
        assert isinstance(decoded, str)


class TestSPSegmenterMocked:
    """Test SPSegmenter with mocked SentencePiece."""

    def test_encode_with_mock(self, monkeypatch):
        """Test encode method with mocked SentencePiece."""

        class MockSentencePiece:
            def __init__(self, model_file):
                pass

            def encode(self, text, out_type=None):
                if text == "hello world":
                    return ["▁hello", "▁world"]
                return ["▁" + text]

        import sys
        mock_spm = type(sys)('mock_sentencepiece')
        mock_spm.SentencePieceProcessor = MockSentencePiece
        monkeypatch.setitem(sys.modules, 'sentencepiece', mock_spm)

        segmenter = SPSegmenter("fake_model.model")
        assert segmenter.encode("hello world") == ["▁hello", "▁world"]

    def test_decode_with_mock(self, monkeypatch):
        """Test decode method with mocked SentencePiece."""

        class MockSentencePiece:
            def __init__(self, model_file):
                pass

            def encode(self, text, out_type=None):
                return []

            def decode(self, tokens):
                return " ".join(token.replace("▁", "") for token in tokens)

        import sys
        mock_spm = type(sys)('mock_sentencepiece')
        mock_spm.SentencePieceProcessor = MockSentencePiece
        monkeypatch.setitem(sys.modules, 'sentencepiece', mock_spm)

        segmenter = SPSegmenter("fake_model.model")
        # decode receives the space-joined token string the aligner produces
        assert segmenter.decode("▁hello ▁world") == "hello world"
