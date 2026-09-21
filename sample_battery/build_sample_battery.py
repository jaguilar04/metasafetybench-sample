"""Build a small, reproducible sample battery from the full dataset.

Selects 200 questions (spread proportionally across the 8 benchmarks) and
10 hand-picked models, then pulls:
  - the question text from responses/<dataset>/<model>.jsonl
  - the binary judgement (score + label) from scores/<dataset>/<model>.jsonl

Sources (the battery/ folder is intentionally never read):
  - matrices/manifest.json         -> per-benchmark item counts, used for
                                       proportional allocation
  - matrices/matrix_<dataset>.parquet -> model x item_id grid, used to pick
                                       items that all 10 models actually answered
  - responses/<dataset>/<model>.jsonl -> prompt text
  - scores/<dataset>/<model>[.judge].jsonl -> score + label

Output (written to sample_battery/):
  - items.jsonl      one line per question: question_id, dataset, question_text
  - responses.jsonl  one line per (question, model): question_id, model, score, label

Field names follow what the downstream annotation tooling expects
(question_id, question_text as the minimum required fields).
"""

import json
import random
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
MATRICES_DIR = ROOT / "matrices"
RESPONSES_DIR = ROOT / "responses"
SCORES_DIR = ROOT / "scores"
OUTPUT_DIR = Path(__file__).resolve().parent

TOTAL_ITEMS = 200
SEED = 42

# The 10 models selected for diversity: frontier closed models, frontier
# open models from different vendors, one small/cheap model, and one older
# baseline model for a sense of progress over time.
MODELS = [
    "openai/gpt-5-mini",
    "anthropic/claude-sonnet-4.5",
    "google/gemini-2.5-pro",
    "deepseek/deepseek-v3.2",
    "qwen/qwen3.5-plus-20260420",
    "z-ai/glm-4.7",
    "x-ai/grok-4.3",
    "mistralai/mistral-large-2512",
    "meta-llama/llama-3.2-1b-instruct",
    "openai/gpt-3.5-turbo",
]

# HarmBench ships two judges (an LLM judge and a refusal-string matcher).
# We use the LLM judge, matching what the source paper reports.
HARMBENCH_JUDGE = "haiku-anthropic_claude-haiku-4.5"

DATASETS = [
    "ahb",
    "advbench",
    "donotanswer",
    "harmbench",
    "health_orsc",
    "orbench_hard",
    "sorrybench",
    "truthfulqa",
]


def model_to_filename(model: str) -> str:
    return model.replace("/", "_")


def allocate_item_counts(manifest: dict) -> dict[str, int]:
    """Split TOTAL_ITEMS across datasets proportionally to their size,
    using the largest-remainder method so the counts sum exactly to
    TOTAL_ITEMS."""
    sizes = {d: manifest["datasets"][d]["n_items"] for d in DATASETS}
    total_size = sum(sizes.values())

    raw = {d: TOTAL_ITEMS * n / total_size for d, n in sizes.items()}
    counts = {d: int(v) for d, v in raw.items()}
    remainder = TOTAL_ITEMS - sum(counts.values())

    # Give the leftover slots to the datasets with the largest fractional part.
    fractional_order = sorted(raw, key=lambda d: raw[d] - counts[d], reverse=True)
    for d in fractional_order[:remainder]:
        counts[d] += 1

    return counts


def select_items(dataset: str, count: int, rng: random.Random) -> list[str]:
    """Pick `count` item_ids from a dataset's matrix, restricted to items
    that all 10 selected models actually have a (non-null) score for."""
    matrix = pd.read_parquet(MATRICES_DIR / f"matrix_{dataset}.parquet")
    available_models = [m for m in MODELS if m in matrix.index]
    subset = matrix.loc[available_models]
    complete_items = subset.columns[subset.notna().all(axis=0)].tolist()

    if len(complete_items) < count:
        raise ValueError(
            f"{dataset}: only {len(complete_items)} items answered by all "
            f"10 models, need {count}"
        )

    return sorted(rng.sample(complete_items, count))


def load_prompts(dataset: str, item_ids: set[str]) -> dict[str, str]:
    """Read prompts for the given item_ids from the first model (in MODELS
    order) that has a responses file for this dataset. Prompts are shared
    across models for the same item, per the original battery invariant."""
    prompts: dict[str, str] = {}
    for model in MODELS:
        path = RESPONSES_DIR / dataset / f"{model_to_filename(model)}.jsonl"
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                record = json.loads(line)
                item_id = record["item_id"]
                if item_id in item_ids and item_id not in prompts:
                    prompts[item_id] = record["prompt"]
        if len(prompts) == len(item_ids):
            break
    missing = item_ids - prompts.keys()
    if missing:
        raise ValueError(f"{dataset}: missing prompts for {sorted(missing)}")
    return prompts


def scores_path(dataset: str, model: str) -> Path:
    filename = model_to_filename(model)
    if dataset == "harmbench":
        return SCORES_DIR / dataset / f"{filename}.{HARMBENCH_JUDGE}.jsonl"
    return SCORES_DIR / dataset / f"{filename}.jsonl"


def load_scores(dataset: str, model: str, item_ids: set[str]) -> dict[str, tuple[float, str]]:
    """Read (score, label) for the given item_ids from a single model's
    scores file."""
    result: dict[str, tuple[float, str]] = {}
    path = scores_path(dataset, model)
    with open(path) as f:
        for line in f:
            record = json.loads(line)
            item_id = record["item_id"]
            if item_id in item_ids:
                result[item_id] = (record["score"], record["label"])
    return result


def main() -> None:
    rng = random.Random(SEED)
    manifest = json.loads((MATRICES_DIR / "manifest.json").read_text())
    item_counts = allocate_item_counts(manifest)

    items_out = []
    responses_out = []

    for dataset in DATASETS:
        count = item_counts[dataset]
        item_ids = select_items(dataset, count, rng)
        item_id_set = set(item_ids)

        prompts = load_prompts(dataset, item_id_set)
        for item_id in item_ids:
            items_out.append(
                {
                    "question_id": item_id,
                    "dataset": dataset,
                    "question_text": prompts[item_id],
                }
            )

        for model in MODELS:
            scores = load_scores(dataset, model, item_id_set)
            missing = item_id_set - scores.keys()
            if missing:
                raise ValueError(
                    f"{dataset}/{model}: missing scores for {sorted(missing)}"
                )
            for item_id in item_ids:
                score, label = scores[item_id]
                responses_out.append(
                    {
                        "question_id": item_id,
                        "model": model,
                        "score": score,
                        "label": label,
                    }
                )

        print(f"{dataset}: {count} items selected")

    OUTPUT_DIR.mkdir(exist_ok=True)
    with open(OUTPUT_DIR / "items.jsonl", "w") as f:
        for record in items_out:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    with open(OUTPUT_DIR / "responses.jsonl", "w") as f:
        for record in responses_out:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(items_out)} items to items.jsonl")
    print(f"Wrote {len(responses_out)} responses to responses.jsonl")


if __name__ == "__main__":
    main()
