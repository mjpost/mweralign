# WMT24 alignment experiments

Scaffolding to reproduce the data + alignment + scoring pipeline of
*"Effects of automatic alignment on speech translation metrics"*
(Post & Hieu, IWSLT 2025) on WMT24, for all 11 language pairs.

The experiment simulates a system that lost its segment boundaries: each
system's outputs are merged within every **domain**, then realigned to the
reference segmentation with `mweralign` (using several segmenters). Both the
original ("manual") and realigned outputs are scored, and the per-system score
deltas are reported.

> Human-judgment correlation (Kendall's τ via mt-metrics-eval) is **deferred**;
> this scaffolding stops at producing per-system scores and deltas.

## Components

| Module | Purpose |
| --- | --- |
| `data.py` | WMT24 sources/references/docids/domains/system outputs (via sacrebleu). |
| `realign.py` | Domain-merge + `mweralign` realignment per (pair, system, segmenter). |
| `score.py` | BLEU + chrF (sacrebleu), COMET22 (PyMarian), pluggable `gemboid`. |
| `download_data.py` | Warm the sacrebleu cache for all pairs; verify flores200 SPM. |
| `run.py` | Orchestrate everything; emit `results.tsv` + delta summary. |

## Prerequisites

Run from the repository root with the project venv active:

```bash
source venv/bin/activate           # has mweralign + sacrebleu installed
```

- **BLEU / chrF** — sacrebleu (already a dependency).
- **flores200 segmenter** — uses the SPM model sacrebleu caches at
  `~/.sacrebleu/models/flores200sacrebleuspm`. `download_data.py` verifies it.
- **COMET22** *(optional)* — install PyMarian: `pip install pymarian`. Override
  the binary with `PYMARIAN_EVAL=/path/to/pymarian-eval` and the model with
  `COMET22_MODEL=...` (default `comet22`).
- **gemboid** *(optional, user-supplied)* — set `GEMBOID_CMD` to a command
  template using `{src} {hyp} {ref}` placeholders that prints a single score:
  ```bash
  export GEMBOID_CMD="python /path/to/gemboid.py --src {src} --hyp {hyp} --ref {ref}"
  ```

## Usage

```bash
# 1. Cache the data and check the flores200 model.
python -m scripts.experiments.download_data

# 2. Smoke test: 2 systems of en-de, BLEU + chrF, all applicable segmenters.
python -m scripts.experiments.run -l en-de --max-systems 2

# 3. Full run (all pairs/systems), saving realigned outputs.
python -m scripts.experiments.run --save-outputs

# 4. Add COMET22 (requires PyMarian) and gemboid (requires GEMBOID_CMD).
python -m scripts.experiments.run --metrics bleu chrf comet22 gemboid
```

Segmenters: `none` (whitespace), `cj` (Han characters; auto-skipped for
non-CJK targets), `flores200` (256k SPM). Results land in
`experiments-out/results.tsv`.

## Deferred: human-eval correlation

```bash
python -m scripts.experiments.download_data --print-mtme-hint
```

prints how to fetch WMT24 human scores from mt-metrics-eval, which a later
stage will join with `results.tsv` to compute system-level Kendall's τ.
