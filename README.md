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

The core flags are:

| Flag | Long form | Meaning |
|------|-----------|---------|
| `-r` | `--ref-file`   | Reference file: the target segmentation, one segment per line. **Required.** |
| `-t` | `--hyp-file`   | Hypothesis file: the system output to re-segment. **Required.** |
| `-o` | `--output`     | Output file (default: stdout). |
| `-m` | `--tokenizer`  | Tokenizer/segmenter to use (default: `spm32k`; see below). |
| `-l` | `--language`   | ISO 639-1 language code (e.g. `de`, `zh`). |
| `-w` | `--no-whitespace` | The language does not delimit words with whitespace (CJK); see *Language code*. |
| `-d` | `--docid-file` | Document ids, one per reference line (see *Document-aware alignment*). |
|      | `--score`      | Scoring mode: report WER instead of re-segmenting (see *Scoring mode*). |

### Aligning a hypothesis to a reference segmentation

The standard use case provides a reference file (segments listed one per line) and a
hypothesis file (the output of a speech-translation system, with no line requirements).
mweralign concatenates the hypothesis into a single word stream and re-splits it to match
the reference segmentation. The output has the **same number of lines as the reference**,
where each line is the slice of the hypothesis aligned to the corresponding reference
segment:

    mweralign -r ref.txt -t hyp.txt -o aligned.txt

### Tokenization

For good alignment you should use a tokenizer, selected with `-m`. The default is
`spm32k` (see the recommendation below). Supported values are:

* `none` (or `whitespace`) — no tokenizer; split on whitespace only;
* `cj` — segments Han characters with whitespace (dependency-free, no model needed);
* a named, on-demand SentencePiece model: `spm32k`, `spm64k`, `spm128k`, or `spm256k`
  (`spm` is an alias for `spm256k`);
* a filesystem path to any SentencePiece `.model` file.

The named models are character-preserving (identity-normalization) models that ship with
the project. They are downloaded on demand the first time you request them, fetched from
the project's GitHub Release, verified against a checksum, and cached under
`~/.cache/mweralign/models` (override with `MWERALIGN_SPM_DIR`):

    mweralign -r ref.txt -t hyp.txt -o aligned.txt -m spm32k   # the default

    mweralign -r ref.txt -t hyp.txt -o aligned.txt -m none     # plain whitespace

To pre-fetch the models (e.g. for offline use):

    python -m mweralign.models --all          # all sizes
    python -m mweralign.models spm32k spm256k # specific ones

**Recommendation:** for the best segmentation quality, use a character-preserving
(identity-normalization) SentencePiece model for *all* languages, including CJK. In our
WMT24 experiments an identity SPM model restored the original segmentation far more
accurately than whitespace tokenization on every language pair, and on the CJK pairs
(en-ja, en-zh, ja-zh) it clearly outperformed the `cj` character segmenter (~94% vs. ~69%
boundary accuracy): per-character tokenization gives the aligner too much freedom, whereas
subword pieces constrain boundaries to sensible word edges. Vocabulary size has little
effect (32k is sufficient; 128k is marginally best), so a small model is a fine default.
The `cj` segmenter remains available as a dependency-free fallback.

Note that the flores200 SPM model (e.g. from sacrebleu) applies NMT-style normalization
that *rewrites* characters, so it is unsuitable when you need the original text restored
verbatim; use an identity-normalization model such as `spm32k` for that.

### Language code

You may also supply the ISO 639-1 language code with `-l`. For `zh` and `ja`, this tells
the underlying AS-WER algorithm not to prevent sentences from starting with the
SentencePiece space character. For other languages it has no effect.

    mweralign -r ref.zh.txt -t hyp.txt -o aligned.txt -m spm256k -l zh

Equivalently, you can pass `--no-whitespace` (`-w`) for any language whose script does not
delimit words with whitespace (e.g. Chinese, Japanese), without naming a specific language:

    mweralign -r ref.zh.txt -t hyp.txt -o aligned.txt -m spm256k -w

If the reference looks like a CJK script but neither `-l zh`/`-l ja` nor `-w` was given,
mweralign prints a one-line suggestion to add the flag.

When a SentencePiece model is used to tokenize a non-CJK language, the aligner also forbids
*mid-word* segment boundaries: no output segment may begin on a word-internal sub-word piece
(one lacking the leading `▁` marker), so re-segmenting never splits a word across two segments.
This is automatic and requires no flag. Pure-punctuation pieces are exempt, since they
legitimately attach to the preceding token.

By default the re-segmented output is detokenized back to plain text. Pass `--no-detok` to
emit the tokenized pieces instead.

### Document-aware alignment

If your hypothesis is split per document (rather than one big stream), pass a docid file
with `-d`. It lists one document id per *reference* line; reference lines sharing a docid
form a document, and the hypothesis file must contain one line per distinct document (in
order). Each document's hypothesis is then aligned independently to its own reference
segments:

    mweralign -r ref.txt -t hyp.txt -d docids.txt -o aligned.txt

### Scoring mode

With `--score`, mweralign skips alignment and instead computes word error rate on already
parallel input: `ref.txt` and `hyp.txt` must have the same number of lines, compared
line-by-line. It prints a per-segment breakdown and a corpus total:

    mweralign --score -r ref.txt -t hyp.txt

    segment 1: WER=150.00 (S=12 I=6 D=0 N=12)
    segment 2: WER=100.00 (S=11 I=0 D=7 N=18)
    ...
    TOTAL: WER=42.50 (errors=85 ref_words=200)

A tokenizer (`-m`) may be combined with `--score` to score on tokenized text.

### Inspecting the segmentation scores

The aligner chooses where to split the hypothesis stream with a dynamic program. You can dump
the competing segment-boundary costs it considered with `--trace-file`. Pass `-` to write the
trace to stdout, or a path to write it to a file. It is off by default and adds no cost when
unused.

    printf 'the cat sat\non the mat\n' > /tmp/ref.txt
    printf 'the cat\nsat on the mat\n' > /tmp/hyp.txt
    mweralign -r /tmp/ref.txt -t /tmp/hyp.txt -o /dev/null --trace-file - 2>/dev/null

Or for a longer example:

    mweralign \
      -r test/data/wmt22.en-de.en \
      -t test/data/wmt22.en-de.sys \
      -m spm256k \
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
