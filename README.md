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

> @inproceedings{post-hoang-2025-effects,
>    title = "Effects of automatic alignment on speech translation metrics",
>    author = "Post, Matt and Hoang, Hieu",
>    editor = "Salesky, Elizabeth  and Federico, Marcello  and Anastasopoulos, Antonis",
>    booktitle = "Proceedings of the 22nd International Conference on Spoken Language Translation (IWSLT 2025)",
>    month = jul,
>    year = "2025",
>    address = "Vienna, Austria (in-person and online)",
>    publisher = "Association for Computational Linguistics",
>    url = "https://aclanthology.org/2025.iwslt-1.7/",
>    doi = "10.18653/v1/2025.iwslt-1.7",
>    pages = "84--92",
>    ISBN = "979-8-89176-272-5",
> }

> @inproceedings{matusov2005evaluating,
>   title={Evaluating machine translation output with automatic sentence segmentation},
>   author={Matusov, Evgeny and Leusch, Gregor and Bender, Oliver and Ney, Hermann},
>   booktitle={IWSLT 2005},
>   pages={138--144},
>   year={2005}
> }
> }


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
