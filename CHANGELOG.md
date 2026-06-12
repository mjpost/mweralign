# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2026-06-12

### Added
- `--version` / `-V`: print the installed version and exit.

## [1.4.0] - 2026-06-12

### Changed
- **`spm32k` is now the default tokenizer.** Running without `-m`/`--tokenizer`
  previously split on whitespace; it now uses the on-demand `spm32k`
  SentencePiece model (downloaded and cached on first use). Pass `-m none` (or
  `-m whitespace`) to restore the plain-whitespace behavior.

### Added
- `--no-whitespace` / `-w`: a language-agnostic flag for scripts that do not
  delimit words with whitespace (e.g. Chinese, Japanese). It lets output
  segments begin at word-internal boundaries, equivalent to `-l zh` / `-l ja`.
- CJK detection hint: when the reference looks like a non-whitespace script but
  neither `-l zh`/`-l ja` nor `-w` was given, the CLI prints a one-line
  suggestion to add the flag. New `is_cjk()` and `cjk_fraction()` helpers in
  `mweralign.segmenter` back this check.

## [1.3.0] - 2026-06-11

### Added
- On-demand SentencePiece model download: the pre-trained, character-preserving
  (identity-normalization) models are published as GitHub Release assets and
  fetched the first time they are requested by name (`-m spm32k`, `spm64k`,
  `spm128k`, `spm256k`; `spm` aliases 256k), checksum-verified, and cached under
  `~/.cache/mweralign/models` (override with `MWERALIGN_SPM_DIR`). A standalone
  `python -m mweralign.models [--all | NAME ...]` pre-fetches them for offline
  use.
- Mid-word segmentation boundary constraint for SentencePiece input: a hard,
  opt-in constraint that forbids a non-final segment from ending where the next
  segment would begin on a word-internal, non-punctuation piece, eliminating
  mid-word segment cuts. Unlike the per-cell internal-word penalty it acts on
  the segmentation boundary itself (the merge step), so the dynamic program
  cannot route around it; it drives the mid-word cut rate to ~0% (versus the
  ~22% reduction the penalty achieved). Auto-activated whenever a SentencePiece
  model tokenizes a non-CJK language (no user flag); also exposed via
  `MwerAlign.set_forbid_midword_boundary()` and
  `align_texts(..., forbid_midword_boundary=)`. Pure-punctuation pieces are
  exempt (they legitimately attach to the previous token).
- Segmentation DP trace: `--trace-file` (use `-` for stdout) dumps the
  competing segment-boundary costs the aligner considered, listing each
  segment's chosen end and every candidate end with its cost and the previous
  segment's end. Off by default and free when unused. Finer-grained per-cell
  edit costs are exposed through the Python API via
  `align_texts_traced(..., cells=True)`.
- WMT24 regression suite: golden-file test cases built from real WMT24 data
  exercising whitespace, `cj`, and SentencePiece segmenters, document-merged
  realignment (`-d`), and `--score`.

### Changed
- The segment-initial internal-word penalty (the `additionalInsertionCosts`
  +1000 cost and its sibling `extra_cost` term) is now gated behind the
  `legacyPenalty_` flag only, instead of firing for all tokenized input. The
  penalty acts on the segment-initial *reference* alignment cell rather than on
  the output segmentation boundary, so the alignment could still begin an output
  segment mid-word by absorbing the fragment elsewhere. The new mid-word
  boundary constraint now owns mid-word-cut prevention for the normal and
  SentencePiece paths; the penalty is retained only to reproduce the pre-fix
  (paper) numbers.

### Fixed
- `cj` segmenter dropped literal underscores: it previously mapped spaces to `_`
  to preserve whitespace, so any literal `_` in the input (e.g. inside URLs or
  identifiers like `WxsYTK8l_Gk` or `user_name_123`) was turned into a space on
  detokenization. Spaces are now represented with the SentencePiece meta-symbol
  `▁` (U+2581), which never occurs in normal text, so the segmenter round-trips
  any input faithfully without escaping. A rare literal `▁` in the input is
  escaped so it is never confused with an encoded space.

## [1.2.0] - 2026-06-05

### Added
- Scoring mode (`--score`): treats the reference and hypothesis as already
  aligned line-by-line and reports per-segment and corpus word error rate (WER)
  instead of re-segmenting. Honors the existing tokenizer (`--tokenizer`) and is
  case-insensitive, consistent with the aligner. Exposes `score_tokens()` and
  `wer()` helpers in the public API.

## [1.1.1] - 2026-06-05

### Fixed
- Incorrect segmentation for plain (non-tokenized) input: the word-internal
  "don't start a segment with an internal piece" penalty in
  `additionalInsertionCosts` was applied unconditionally. Because `isInternal()`
  treats every whitespace word as internal (no leading `▁` marker), the 1000-cost
  penalty fired on every segment-initial insertion, forcing trailing tokens into
  the wrong segment and yielding suboptimal alignments. The penalty is now gated
  by the `segmenting` flag (consistent with the sibling `extra_cost` term), so it
  only applies in SentencePiece/tokenized mode. Added a `whitespace_segment`
  regression test covering this case.
- `mweralign` CLI now requires `--ref-file/-r` and `--hyp-file/-t`, printing a
  usage error instead of crashing with `AttributeError: 'NoneType' object has no
  attribute 'readlines'` when run with no arguments.

## [1.1.0] - 2026-06-04

### Added
- CI job that builds the standalone C++ CLI via CMake on Linux and macOS and
  runs a real alignment against the bundled test data as a smoke test.
- CPython 3.14 binary wheels (cibuildwheel now builds `cp310`–`cp314`).

### Changed
- Expanded the supported/tested Python versions to 3.10–3.14 (added 3.11, 3.13,
  and 3.14 to the test matrix).
- Renamed the standalone C++ CLI target/binary from `mwerAlign` to `mweralign`
  (and the CMake static-library target to `mweralign_lib`) for consistent
  lowercase naming.
- Bumped `pypa/cibuildwheel` to 3.4.1 (required to build 3.13/3.14 wheels) and
  switched the wheel-build runner from the retired `ubuntu-20.04` to
  `ubuntu-latest`.

### Fixed
- Segmentation fault when a reference line is empty (issue #1): empty reference
  lines are now preserved as empty segments so the segment count stays in sync
  with the segmentation markers, preventing the backtrace from being corrupted.
  Added an `empty_ref` regression test covering this case.
- Build failures on macOS/Linux caused by an `operator<<` declaration ordering
  issue that broke two-phase name lookup under clang and GCC.
- `ImportError: undefined symbol: gzwrite` when importing the Python extension:
  the pybind11 module now links against zlib.
- Wheel build failures inside the `manylinux2014` container caused by the
  non-standard `uint` type; replaced with `unsigned int`.
- Removed an unnecessary CMake-install step from the wheel build `before-all`
  that failed against the now-EOL CentOS 7 (`manylinux2014`) package repos; the
  package builds with pybind11/setuptools and does not require system CMake.

## [1.0.1] - 2025-07-23

### Fixed
- Packaging/publishing fixes for the initial PyPI release (build metadata for
  publishing and license keywords).

## [1.0.0]

Initial release: the original RWTH MWERAlign C++ library (AS-WER algorithm)
packaged as a pip-installable Python package with pybind11 bindings, a
`mweralign` command-line entry point and Python API, CJ/SentencePiece
segmenter support, a regression test suite, and GitHub Actions builds.

[1.1.0]: https://github.com/mjpost/mweralign/releases/tag/v1.1.0
[1.0.1]: https://github.com/mjpost/mweralign/releases/tag/v1.0.1
[1.0.0]: https://pypi.org/project/mweralign/1.0.0/
