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

from typing import List

class Segmenter:
    """
    A simple segmenter that tokenizes text based on Latin-1 characters and Han characters.
    It treats Latin-1 words as tokens and Han characters as individual tokens.
    """

    def encode(self, text: str) -> List[str]:
        """
        Encode the input text into a list of tokens.
        
        Args:
            text: Input text to be tokenized
            
        Returns:
            List of tokens
        """
        pass

    def decode(self, tokens: List[str]) -> str:
        """
        Decode a list of tokens back into a string.
        
        Args:
            tokens: List of tokens to be decoded
            
        Returns:
            Decoded string
        """
        return "".join(tokens)


def is_latin1(c):
    """
    Check if a character is within the Latin-1 (ISO-8859-1) range.
    """
    return ord(c) <= 0x00FF


def is_cjk(c: str) -> bool:
    """True if ``c`` is a Han ideograph, Japanese kana, or Korean Hangul.

    Used to detect non-whitespace scripts so the CLI can suggest the language
    flag that allows sentence-initial word boundaries.
    """
    o = ord(c)
    return (
        0x3040 <= o <= 0x30FF      # Hiragana + Katakana
        or 0x3400 <= o <= 0x4DBF   # CJK Unified Ideographs Extension A
        or 0x4E00 <= o <= 0x9FFF   # CJK Unified Ideographs
        or 0xAC00 <= o <= 0xD7AF   # Hangul syllables
        or 0xF900 <= o <= 0xFAFF   # CJK Compatibility Ideographs
    )


def cjk_fraction(text: str) -> float:
    """Fraction of the non-space characters in ``text`` that are CJK."""
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return sum(1 for c in chars if is_cjk(c)) / len(chars)


# SentencePiece meta-symbol used to represent a space (U+2581, "LOWER ONE EIGHTH
# BLOCK"). It does not occur in normal text, so it can stand in for spaces
# without colliding with any literal input character (e.g. an actual '_').
SPM_SPACE = "\u2581"

# Sentinel used to escape a *literal* '▁' that already appears in the input, so
# it is not later mistaken for an encoded space. NUL never occurs in real text.
SPM_SPACE_ESCAPE = "\x00"


class CJSegmenter(Segmenter):
    """
    A segmenter that tokenizes text based on Latin-1 characters and Han characters.
    It treats Latin-1 words as tokens and Han characters as individual tokens.
    """
    def __init__(self):
        pass

    def encode(self, text: str) -> List[str]:
        """
        For Han characters (Chinese, Japanese), treat each character as a token,
        inserting whitespace in between. For interleaved Latin1 characters,
        treat each Latin1 word as a token, and insert whitespace in between.
        """

        # Escape any literal '▁' already in the input so it is not confused with
        # the encoded spaces inserted below, then preserve existing whitespace by
        # mapping spaces to the SentencePiece meta-symbol '▁'. '▁' never occurs in
        # normal text and so cannot be confused with a literal input character
        # (e.g. an actual '_'); the rare literal '▁' is handled by the escape.
        text = text.replace(SPM_SPACE, SPM_SPACE_ESCAPE)
        text = text.replace(" ", SPM_SPACE)

        tokens = []
        i = 0
        while i < len(text):
            c = text[i]
            if is_latin1(c) or c == SPM_SPACE:
                # Move forward over a Latin1 word, keeping attached spaces ('▁')
                start = i
                while i < len(text) and (is_latin1(text[i]) or text[i] == SPM_SPACE):
                    i += 1
                tokens.append(text[start:i])
            else:
                # Treat all non-Latin1 as one-character tokens (e.g., Han characters)
                tokens.append(c)
                i += 1

        return tokens

    def decode(self, text: str) -> str:
        """
        Decode a list of tokens back into a string.
        
        Args:
            tokens: List of tokens to be decoded
            
        Returns:
            Decoded string
        """

        # Drop the inter-token separator spaces, restore the encoded spaces, then
        # un-escape any literal '▁'. The final strip() removes the segment-merge
        # separator space that the aligner leaves at a segment boundary (so a
        # restored segment doesn't gain a spurious leading/trailing space).
        text = text.replace(" ", "").replace(SPM_SPACE, " ").replace(SPM_SPACE_ESCAPE, SPM_SPACE).strip()
        return text
    

class SPSegmenter(Segmenter):
    """
    A segmenter that uses SentencePiece for tokenization.
    """
    def __init__(self, model_path: str):
        import sentencepiece as spm
        self.sp = spm.SentencePieceProcessor(model_file=model_path)

    def encode(self, text: str) -> List[str]:
        return self.sp.encode(text, out_type=str)

    def decode(self, text: str) -> str:
        return self.sp.decode(text.split())