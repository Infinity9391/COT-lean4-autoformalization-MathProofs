#!/usr/bin/env python3
"""
Analyze experiment results with statistical rigor.

Usage:
    python analyze_results.py [--results results/experiment_results.json]
"""

import argparse
import json
import math
import re
from collections import Counter
from pathlib import Path


DIFFICULTY_PATTERNS = [
    ("IMO", re.compile(r"^imo_")),
    ("AIME", re.compile(r"^aime")),
    ("AMC", re.compile(r"^amc12")),
    ("MATHD", re.compile(r"^mathd_")),
    ("Algebra", re.compile(r"^algebra_")),
    ("NumberTheory", re.compile(r"^numbertheory_")),
    ("Induction", re.compile(r"^induction_")),
]


def classify_difficulty(problem_id: str) -> str:
    for label, pattern in DIFFICULTY_PATTERNS:
        if pattern.match(problem_id):
            return label
    return "Other"


def classify_error(result: dict) -> str:
    if "error" in result:
        return "pipeline_error"

    verification = result.get("verification", {})
    details = verification.get("details", "").lower()

    if verification.get("verified") is True:
        return "success"
    if verification.get("verified") is None:
        return "unverified"
    if "import mathlib" in details or ("import" in details and "mathlib" in details):
        return "missing_mathlib"
    if "unknown tactic" in details or "unknown identifier" in details and any(
        t in details for t in ["norm_num", "simp", "ring", "omega", "nlinarith", "linarith", "field_simp"]
    ):
        return "missing_mathlib"
    if "type mismatch" in details or "type error" in details:
        return "type_error"
    if "unknown identifier" in details or "unknown constant" in details:
        return "unknown_identifier"
    if "expected token" in details or "unexpected token" in details or "parse" in details:
        return "syntax_error"
    if "tactic" in details and ("failed" in details or "unsolved" in details):
        return "tactic_failure"
    if "failed to synthesize" in details:
        return "missing_instance"
    if "timeout" in details:
        return "timeout"
    if not result.get("lean_code", "").strip():
        return "empty_output"
    return "other_error"


def wilson_ci(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 0.0)
    p_hat = successes / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n) / denom
    return (p_hat, max(0, center - spread), min(1, center + spread))


def mcnemar_test(a_results: list[bool], b_results: list[bool]) -> dict:
    assert len(a_results) == len(b_results)
    b_count = sum(1 for a, bv in zip(a_results, b_results) if a and not bv)
    c_count = sum(1 for a, bv in zip(a_results, b_results) if not a and bv)
    both_right = sum(1 for a, bv in zip(a_results, b_results) if a and bv)
    both_wrong = sum(1 for a, bv in zip(a_results, b_results) if not a and not bv)

    n_discord = b_count + c_count
    if n_discord == 0:
        return {"chi2": 0.0, "p_value": 1.0, "b_count": b_count, "c_count": c_count,
                "both_right": both_right, "both_wrong": both_wrong, "note": "No discordant pairs"}

    chi2 = (abs(b_count - c_count) - 1) ** 2 / (b_count + c_count)
    p_value = _chi2_sf(chi2, df=1)
    return {"chi2": chi2, "p_value": p_value, "b_count": b_count, "c_count": c_count,
            "both_right": both_right, "both_wrong": both_wrong}


def wilcoxon_signed_rank(x: list[float], y: list[float]) -> dict:
    assert len(x) == len(y)
    diffs = [(xi - yi) for xi, yi in zip(x, y) if xi != yi]
    n = len(diffs)

    if n == 0:
        return {"W": 0, "p_value": 1.0, "n_nonzero": 0, "note": "All pairs tied"}

    abs_diffs = [(abs(d), i) for i, d in enumerate(diffs)]
    abs_diffs.sort()
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j < n and abs_diffs[j][0] == abs_diffs[i][0]:
            j += 1
        avg_rank = (i + j + 1) / 2
        for k in range(i, j):
            ranks[abs_diffs[k][1]] = avg_rank
        i = j

    w_plus = sum(r for d, r in zip(diffs, ranks) if d > 0)
    w_minus = sum(r for d, r in zip(diffs, ranks) if d < 0)
    W = min(w_plus, w_minus)

    mean_w = n * (n + 1) / 4
    std_w = math.sqrt(n * (n + 1) * (2 * n + 1) / 24)
    if std_w == 0:
        return {"W": W, "p_value": 1.0, "n_nonzero": n}
    z = (W - mean_w) / std_w
    p_value = 2 * _normal_sf(abs(z))
    return {"W": W, "p_value": p_value, "n_nonzero": n, "z": z}


def _normal_sf(x: float) -> float:
    t = 1 / (1 + 0.2316419 * abs(x))
    d = 0.3989422804014327
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
           t * (-1.821255978 + t * 1.330274429))))
    sf = d * math.exp(-x * x / 2) * poly
    return sf if x >= 0 else 1 - sf


def _chi2_sf(x: float, df: int = 1) -> float:
    if df != 1:
        raise ValueError("Only df=1 supported")
    return 2 * _normal_sf(math.sqrt(x))


def analyze(results_path: str):
    with open(results_path) as f:
        all_results = json.load(f)

    pipelines = list(all_results.keys())

    has_verification = any(
        r.get("verification", {}).get("verified") is True
        for pname in pipelines
        for r in all_results[pname].values()
    )

    print("=" * 78)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 78)
    print()

    if has_verification:
        print(f"{'Pipeline':<20} {'N':>4} {'Verified':>9} {'Rate':>7} {'95% CI':>14} {'API Calls':>10}")
    else:
        print(f"{'Pipeline':<20} {'N':>4} {'Generated':>10} {'sorry':>6} {'sorry%':>7} {'Avg Lines':>10} {'API Calls':>10}")
    print("-" * 78)

    pipeline_stats = {}
    for pname in pipelines:
        results = all_results[pname]
        total = len(results)
        verified_count = sum(1 for r in results.values() if r.get("verification", {}).get("verified") is True)
        codes = [r.get("lean_code", "") for r in results.values()]
        generated = sum(1 for c in codes if c.strip())
        sorry_count = sum(1 for c in codes if "sorry" in c.lower())
        lines = [len(c.strip().split("\n")) for c in codes if c.strip()]
        api_calls = [r.get("api_calls", 0) for r in results.values() if "api_calls" in r]

        avg_lines = sum(lines) / len(lines) if lines else 0
        avg_calls = sum(api_calls) / len(api_calls) if api_calls else 0
        rate, ci_lo, ci_hi = wilson_ci(verified_count, total)

        pipeline_stats[pname] = {
            "total": total, "verified": verified_count, "rate": rate,
            "ci_lower": ci_lo, "ci_upper": ci_hi, "generated": generated,
            "sorry_count": sorry_count, "avg_lines": avg_lines, "avg_api_calls": avg_calls,
        }

        if has_verification:
            print(f"{pname:<20} {total:>4} {verified_count:>9} {rate:>6.1%} [{ci_lo:.1%}, {ci_hi:.1%}] {avg_calls:>10.1f}")
        else:
            sorry_pct = sorry_count / total * 100 if total else 0
            print(f"{pname:<20} {total:>4} {generated:>10} {sorry_count:>6} {sorry_pct:>6.1f}% {avg_lines:>10.1f} {avg_calls:>10.1f}")

    print()

    # Statistical tests
    if len(pipelines) >= 2:
        print("=" * 78)
        print("STATISTICAL TESTS (pairwise Wilcoxon on sorry count)")
        print("=" * 78)
        print()

        common_pids = set(all_results[pipelines[0]].keys())
        for pname in pipelines[1:]:
            common_pids &= set(all_results[pname].keys())
        common_pids = sorted(common_pids)

        print(f"  {'Comparison':<35} {'W':>7} {'p-value':>10} {'n(diff)':>8}")
        print("  " + "-" * 62)
        for i, pa in enumerate(pipelines):
            for pb in pipelines[i + 1:]:
                a_sorry = [1 if "sorry" in all_results[pa][pid].get("lean_code", "").lower() else 0 for pid in common_pids]
                b_sorry = [1 if "sorry" in all_results[pb][pid].get("lean_code", "").lower() else 0 for pid in common_pids]
                test = wilcoxon_signed_rank(a_sorry, b_sorry)
                label = f"{pa} vs {pb}"
                sig = " *" if test["p_value"] < 0.05 else ""
                print(f"  {label:<35} {test['W']:>7.1f} {test['p_value']:>9.4f}{sig} {test['n_nonzero']:>8}")
        print()
        print("  * = significant at p < 0.05")
        print()

    # By category
    print("=" * 78)
    print("RESULTS BY PROBLEM CATEGORY")
    print("=" * 78)
    print()

    all_pids = set()
    for pname in pipelines:
        all_pids.update(all_results[pname].keys())

    categories = {}
    for pid in all_pids:
        cat = classify_difficulty(pid)
        categories.setdefault(cat, []).append(pid)

    metric_label = "Verified" if has_verification else "No-sorry"

    for cat in sorted(categories.keys()):
        pids = sorted(categories[cat])
        print(f"  {cat} ({len(pids)} problems):")
        print(f"    {'Pipeline':<20} {metric_label:>10} {'Rate':>8}")
        print(f"    {'-'*42}")
        for pname in pipelines:
            if has_verification:
                count = sum(1 for pid in pids if pid in all_results[pname]
                            and all_results[pname][pid].get("verification", {}).get("verified") is True)
            else:
                count = sum(1 for pid in pids if pid in all_results[pname]
                            and "sorry" not in all_results[pname][pid].get("lean_code", "").lower())
            n = sum(1 for pid in pids if pid in all_results[pname])
            rate = count / n if n else 0
            print(f"    {pname:<20} {count:>5}/{n:<4} {rate:>7.0%}")
        print()

    # Static analysis summary
    has_static = any(
        "static_analysis" in r
        for pname in pipelines
        for r in all_results[pname].values()
    )

    if has_static:
        print("=" * 78)
        print("STATIC ANALYSIS SUMMARY")
        print("=" * 78)
        print()

        print(f"{'Metric':<35}", end="")
        for pname in pipelines:
            print(f" {pname:>12}", end="")
        print()
        print("-" * (35 + 13 * len(pipelines)))

        sa_metrics = [
            ("Sorry-free proofs",
             lambda r: r.get("static_analysis", {}).get("sorry_count", 99) == 0),
            ("Main theorem sorry-free",
             lambda r: not r.get("static_analysis", {}).get("sorry_in_main_theorem", True)),
            ("All lemmas complete",
             lambda r: r.get("static_analysis", {}).get("incomplete_theorems", 1) == 0),
        ]

        for label, fn in sa_metrics:
            print(f"{label:<35}", end="")
            for pname in pipelines:
                results = all_results[pname]
                n = len(results)
                count = sum(1 for r in results.values() if fn(r))
                pct = count / n * 100 if n else 0
                print(f" {count:>5} ({pct:>3.0f}%)", end="")
            print()

        print(f"{'Avg completeness score':<35}", end="")
        for pname in pipelines:
            results = all_results[pname]
            n = len(results)
            avg = sum(r.get("static_analysis", {}).get("completeness_score", 0) for r in results.values()) / n if n else 0
            print(f" {avg:>11.1%}", end="")
        print()
        print()

    # Save structured summary
    output_path = Path(results_path).parent / "analysis_summary.json"
    summary = {
        "has_verification": has_verification,
        "pipeline_stats": pipeline_stats,
        "categories": {cat: pids for cat, pids in categories.items()},
    }
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Structured summary saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze experiment results")
    parser.add_argument("--results", type=str, default="results/experiment_results.json")
    args = parser.parse_args()
    analyze(args.results)


if __name__ == "__main__":
    main()
