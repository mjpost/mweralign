# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
