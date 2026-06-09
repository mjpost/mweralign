# mweralign

mweralign is a Python package for aligning a stream of words to a reference segmentation.
It is designed for use in speech translation tasks, where system outputs must be aligned to
a reference translation in order for standard MT metrics to work. This package is a Python
wrapper around the original MWERAlign C++ library, which implements the AS-WER algorithm for 
automatic sentence segmentation and alignment. The wrapper also includes a modernization of that
code and support for modern subword tokenization, which helps with alignment.

## Installation

To install the package, you can use pip:

    pip install mweralign

Or install from source:

    git clone https://github.com/mjpost/mweralign
    cd mweralign
    pip install .

## Usage

You can see usage information by running mweralign with the `--help` flag:

    mweralign --help

The standard use case is to provide a reference file, in which segments (sentences) are
listed one per line, and a hypothesis file, which contains the output of a speech translation system,
and has no line requirements. The output will be a file with the same number of lines as the hypothesis,
where each line contains the index of the segment in the reference that corresponds to that hypothesis
line.

    mweralign -r ref.txt -h hyp.txt -o aligned.txt

You will want to use a tokenizer. Currently supported is "cj", which segments Han characters with whitespace,
or any SentencePiece model, which are provided in the form of a filesystem path:

    mweralign -r ref.zh.txt -h hyp.txt -o aligned.txt -t cj

    # download the flores200 SPM model (one time)
    sacrebleu -t wmt24 -l en-zh --echo src | sacrebleu -t wmt24 -l en-zh --tok flores200 > /dev/null
    # align
    mweralign -r ref.txt -h hyp.txt -o aligned.txt -t ~/.sacrebleu/models/flores200sacrebleuspm

You may also wish to supply the ISO 639-1 language code (-l zh). For zh and ja, this tells the underlying
AS-WER algorithm not to prevent sentences from starting with the SentencePiece space character. For other
languages, it has no effect.

    mweralign -r ref.txt -h hyp.txt -o aligned.txt -t cj -l zh

When a SentencePiece model is used to tokenize a non-CJK language, the aligner also forbids
*mid-word* segment boundaries: no output segment may begin on a word-internal sub-word piece
(one lacking the leading `▁` marker), so re-segmenting never splits a word across two segments.
This is automatic and requires no flag. Pure-punctuation pieces are exempt, since they
legitimately attach to the preceding token.

### Inspecting the segmentation scores

The aligner chooses where to split the hypothesis stream with a dynamic program. You can dump
the competing segment-boundary costs it considered with `--trace-file`. Pass `-` to write the
trace to stdout, or a path to write it to a file. It is off by default and adds no cost when
unused.

    printf 'the cat sat\non the mat\n' > /tmp/ref.txt
    printf 'the cat\nsat on the mat\n' > /tmp/hyp.txt
    mweralign -r /tmp/ref.txt -t /tmp/hyp.txt -o /dev/null --trace-file - 2>/dev/null

Or for a longer example:

    mweralign % mweralign \
      -r test/data/wmt22.en-de.en \
      -t test/data/wmt22.en-de.sys \
      -m expt/data/256000.model \
      -l de \
      -o /dev/null \
      --trace-file -

For each segment, the trace lists the chosen end position and every candidate end position with
its cost and the previous segment's end (`prev_end`):

    # docid range 0 (segments 0-2)
    segment 1: chosen end j=3 (cost=0)
        end j=   0  cost=     0  prev_end=0
        end j=   3  cost=     0  prev_end=0  <- chosen
        end j=   2  cost=     1  prev_end=0
        ...
    segment 2: chosen end j=6 (cost=0)
        end j=   6  cost=     0  prev_end=3  <- chosen
        ...

Here `j` is a position in the (tokenized) hypothesis stream, so `segment 1` covers hyp tokens
1..3 and `segment 2` covers 4..6. The alignment output itself still goes to `-o` (sent to
`/dev/null` above so only the trace is shown); `2>/dev/null` suppresses the `AS-WER` line.

The trace above is the boundary-cost table (cheap to record). Finer-grained per-cell edit costs
are available only through the Python API, `align_texts_traced(..., cells=True)`, since they grow
with the full alignment grid and are impractical to print for long inputs.

## Project layout

    src/                 # C++ core library and standalone CLI
    python/
      mweralign/         # Python package (CLI + wrappers)
      bindings/          # pybind11 bindings (mweralign._mweralign)
      tests/             # pytest unit + regression suite
        regression/      # golden-file CLI regression cases
    CMakeLists.txt       # builds the standalone C++ `mweralign` binary
    setup.py / pyproject.toml  # builds the Python package/extension

## Development

Install in editable mode with the development dependencies and run the tests:

    pip install -e ".[dev]"
    pytest python/tests

### Regression suite

The regression suite under `python/tests/regression/` runs the `mweralign`
CLI on fixed inputs and compares the output to committed golden files. Each
case is a directory containing a `cmd` file (the CLI arguments), the input
files it references, and an `expected.txt` golden output.

After an intentional change in behavior, regenerate the golden files with:

    MWERALIGN_REGEN=1 pytest python/tests/test_regression.py

To add a new case, create a directory under `python/tests/regression/`, add a
`cmd` file plus its input files, and run the regen command above to produce
`expected.txt`.

### Building the standalone C++ CLI

The Python package builds its own extension, so this is only needed if you want
the standalone `mweralign` binary:

    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
    cmake --build build
    # binary at build/mweralign

## Citation

If you use this package, please cite the following two papers. We suggest a sentence
similar to the following: "To align the text, we used the mweralign package \citep{post-huang-2025-effects},
which implements a variant of the AS-WER algorithm \citep{matusov-etal-2005-evaluating}.

- [Matusov et al. (2005)](https://aclanthology.org/2005.iwslt-1.19/)
- [Post and Hoang (2025)](https://aclanthology.org/2025.iwslt-1.7/)

## License

This project contains code under multiple licenses:

- **Original C++ alignment code**: GNU General Public License v3 (GPL-3.0)
- **Python bindings and wrapper code**: Apache License 2.0
- **Build scripts and documentation**: Apache License 2.0

**The project as a whole is distributed under GPL-3.0** due to the inclusion of GPL-licensed components.

### What this means for users:
- You can use this library in GPL-compatible projects
- If you distribute software that includes this library, your software must be GPL-compatible
- The Python wrapper code (separate from the C++ core) is available under Apache License 2.0

## Attribution
This software includes original GPL-licensed C++ code for alignment algorithms.
Python bindings and packaging by Matt Post (Apache License 2.0).
