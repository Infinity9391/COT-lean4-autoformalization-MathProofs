"""
Load and preprocess miniF2F problems from HuggingFace.

Uses the cat-searcher/minif2f-lean4 dataset. Extracts the first 50 problems
from the validation split.
"""

import json
import os
from pathlib import Path

try:
    from datasets import load_dataset
except ImportError:
    load_dataset = None


def load_minif2f_problems(
    num_problems: int = 50,
    split: str = "validation",
    cache_path: str | None = None,
) -> list[dict]:
    """Load miniF2F problems from HuggingFace or local cache.

    Args:
        num_problems: Number of problems to load from the split.
        split: Dataset split to use.
        cache_path: Optional path to a local JSON cache file.

    Returns:
        List of dicts with keys: id, informal_statement, formal_statement.
    """
    if cache_path and os.path.exists(cache_path):
        with open(cache_path) as f:
            problems = json.load(f)
        return problems[:num_problems]

    if load_dataset is None:
        raise ImportError(
            "The `datasets` library is required. Install with: pip install datasets"
        )

    dataset = load_dataset("cat-searcher/minif2f-lean4", split=split)

    problems = []
    for i, row in enumerate(dataset):
        if i >= num_problems:
            break
        problem = {
            "id": row.get("id", f"minif2f_{split}_{i}"),
            "informal_statement": row.get(
                "informal_statement", row.get("informal_stmt", "")
            ),
            "formal_statement": row.get(
                "formal_statement", row.get("formal_stmt", "")
            ),
        }
        if not problem["informal_statement"] and "header" in row:
            problem["informal_statement"] = row["header"]
        if not problem["formal_statement"] and "formal_statement" in row:
            problem["formal_statement"] = row["formal_statement"]
        problems.append(problem)

    # Cache locally for reproducibility
    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w") as f:
            json.dump(problems, f, indent=2)

    return problems


if __name__ == "__main__":
    problems = load_minif2f_problems(
        num_problems=50, cache_path="data/minif2f_cache.json"
    )
    print(f"Loaded {len(problems)} problems")
    if problems:
        print(f"First problem ID: {problems[0]['id']}")
        print(f"Informal statement preview: {problems[0]['informal_statement'][:200]}...")
