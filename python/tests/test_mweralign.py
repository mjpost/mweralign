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

import pytest
from mweralign import MwerAlign, align_texts


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


if __name__ == "__main__":
    pytest.main([__file__])