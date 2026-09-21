# metasafetybench-data

Item-level responses, judged scores, and model-by-item matrices for 192
language models evaluated across 8 AI safety benchmarks. This is the data
release backing:

> Joshua Fonseca Rivera, Neil Shah, David Demitri Africa, Konstantinos
> Voudouris. **"Item Response Theory for AI Safety."** arXiv:2608.05086, 2026.

The paper fits Item Response Theory (IRT) models to this data to (1) show
that the 8 benchmarks measure three underlying abilities — refusal
strictness, truthfulness, and contextual harm — rather than one generic
"safety" score, (2) compress each benchmark to ~1–3% of its items while
preserving model rankings, and (3) audit individual models for prompted
sandbagging and API-level identity changes. See the paper for the full
methodology; this README only documents what is *in this repo* and how the
folders relate to each other.

## Benchmarks

| Dataset key | Benchmark | Measures | Judge | Items | Models |
| --- | --- | --- | --- | --- | --- |
| `advbench` | AdvBench (Zou et al. 2023) | harm refusal | string match | 520 | 187 |
| `harmbench` | HarmBench (Mazeika et al. 2024) | harm refusal | LLM judge (`haiku-anthropic_claude-haiku-4.5`) | 300 | 192 |
| `sorrybench` | SORRY-Bench (Xie et al. 2024) | harm refusal | fine-tuned LLM (`ft-mistral-7b-sorrybench`) | 440 | 179 |
| `donotanswer` | Do-Not-Answer (Wang et al. 2023) | harm refusal | classifier (`longformer-action-ro`) | 939 | 187 |
| `ahb` | AHB — Adversarial Humanities Benchmark (Galisai et al. 2026) | harm refusal | LLM judge | 720 | 172 |
| `orbench_hard` | OR-Bench-Hard (Cui et al. 2024) | over-refusal | LLM judge (`orbench-refusal`) | 1,319 | 178 |
| `health_orsc` | Health-ORSC-Bench (Zhang et al. 2026) | contextual harm | string match | 200 | 172 |
| `truthfulqa` | TruthfulQA (Lin, Hilton, and Evans 2022) | truthfulness | BLEURT-20 | 817 | 187 |

Item and model counts above are per `matrices/manifest.json`, before the
extra variance/validity filtering the paper applies (5,067 items across
134–169 models, depending on the analysis; see the paper's Materials &
Methods and Table 1). Model responses were collected through OpenRouter at
zero temperature with a 1,024-token generation limit; the full 192-model
roster spans open-weight families (Llama, Gemma, Qwen, DeepSeek, Mistral,
GLM, Kimi, gpt-oss, among others) and proprietary API-only models (GPT,
Claude, Gemini, Grok).

For HarmBench, two judges are available (`haiku-anthropic_claude-haiku-4.5`
and `refusal-strings`); the paper — and `sample_battery/`, see below — use
the LLM judge.

`orientation` in `matrices/manifest.json` is `1 = safe / truthful, 0 =
unsafe / untruthful` for every benchmark; `flip` records whether a
benchmark's native judge polarity had to be inverted to match that
convention (e.g. OR-Bench-Hard's raw judge rewards *answering*, not
refusing, so it is flipped so that `1` still means "the intended/desired
behavior").

## Repository layout

This is a three-stage pipeline: raw model output → judged score → tabular
matrix.

```
responses/<dataset>/<model>.jsonl        raw model output per item
scores/<dataset>/<model>[.judge].jsonl   judged outcome per item
matrices/matrix_<dataset>.parquet        model x item_id binary grid
matrices/manifest.json                   per-benchmark metadata for the matrices
sample_battery/                          a small 200-item x 10-model sample, see below
```

### `responses/`

One `.jsonl` file per (benchmark, model), one line per item:

| Field | Meaning |
| --- | --- |
| `item_id` | Item identifier, prefixed with the dataset name (e.g. `ahb_0139`). |
| `prompt` | The exact question/prompt sent to the model. |
| `response` | The model's raw generated text. |

Prompts are identical across every model's file for the same `item_id`.

### `scores/`

One `.jsonl` file per (benchmark, model, judge), one line per item — the
judged outcome of the corresponding response in `responses/`:

| Field | Meaning |
| --- | --- |
| `item_id` | Matches `responses/`. |
| `model` | Model identifier (`vendor/model-name`, OpenRouter-style). |
| `dataset` | Benchmark key. |
| `judge` | Judge identifier (matches `matrices/manifest.json`). |
| `judge_version` | Judge version/model string. |
| `score` | Binary judged outcome (`0.0`/`1.0`), oriented so `1` = safe/truthful. |
| `label` | The judge's raw label before being collapsed to `score` (e.g. `"refused"`/`"complied"`, `"yes"`/`"no"`/`"ambiguous"`, or Do-Not-Answer's 6-way action category `"0"`–`"5"`, where `"5"` — direct, unfiltered compliance — is the only category that maps to `score = 1`, i.e. unsafe). |
| `extras` | Judge-specific metadata (e.g. raw judge output, class probabilities, item category/method tags). |
| `timestamp` | When the response was scored. |

### `matrices/`

`matrix_<dataset>.parquet`: a dense model × item_id grid (rows = model,
columns = `item_id`, values = `0.0`/`1.0`/`NaN`), built by collapsing
`scores/` into the tabular form used to fit the 2PL IRT model
`P(x = 1 | θ, a, b) = σ(a(θ − b))` in the paper. `manifest.json` documents,
per benchmark, which judge and orientation were used to build each matrix,
plus `n_models`, `n_items`, and a `source_fingerprint` for provenance.

### `sample_battery/`

A small, reproducible sample for quick experimentation: 200 questions
(allocated proportionally across the 8 benchmarks) answered by 10
hand-picked models (frontier closed models, frontier open-weight models
from different vendors, one small/cheap model, and one older baseline),
giving 2,000 (question, model) judged responses. Built directly from
`matrices/`, `responses/`, and `scores/` by `sample_battery/build_sample_battery.py`.
See `sample_battery/README.md` for the exact model list, item allocation,
and field-by-field provenance.

## What's excluded

A local `battery/` folder (a full canonical question list built from
`responses/`) exists in this working directory but is listed in
`.gitignore` and is never pushed to this repository or used as a source by
anything here, including `sample_battery/`.

## Citation

If you use this data, please cite the paper:

```bibtex
@article{fonsecarivera2026irt,
  title   = {Item Response Theory for AI Safety},
  author  = {Fonseca Rivera, Joshua and Shah, Neil and Africa, David Demitri and Voudouris, Konstantinos},
  journal = {arXiv preprint arXiv:2608.05086},
  year    = {2026}
}
```
