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

        # preserve existing whitespaces
        text = text.replace(" ", "_")

        tokens = []
        i = 0
        while i < len(text):
            c = text[i]
            if is_latin1(c):
                # Move forward over a Latin1 word
                start = i
                while i < len(text) and is_latin1(text[i]):
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

        text = text.replace(" ", "").replace("_", " ").strip()  # restore spaces
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