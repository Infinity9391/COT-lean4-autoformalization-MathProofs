#!/usr/bin/env python3
"""
Post-hoc verification and static analysis of experiment results.

Usage:
    # Static analysis only (no network needed):
    python verify_results.py

    # Static analysis + AXLE formal verification:
    python verify_results.py --axle

    # Just print summary without modifying results:
    python verify_results.py --dry-run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from verification.static_analysis import analyze_proof, classify_verification_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

RESULTS_FILE = Path("results/experiment_results.json")


def run_static_analysis(all_results: dict) -> dict:
    """Add static analysis to every proof result."""
    total = sum(len(v) for v in all_results.values())
    done = 0

    for pipeline_name, results in all_results.items():
        for pid, result in results.items():
            done += 1
            code = result.get("lean_code", "")
            analysis = analyze_proof(code)
            result["static_analysis"] = analysis
            result["verification_status"] = classify_verification_status(result)

            if done % 50 == 0 or done == total:
                logger.info("Static analysis: %d/%d", done, total)

    return all_results


def run_axle_verification(all_results: dict) -> dict:
    """Re-run AXLE verification on all proofs."""
    try:
        from verification.axle_client import AxleClient
    except ImportError:
        logger.error("AXLE client not available.")
        return all_results

    axle = AxleClient()
    total = sum(len(v) for v in all_results.values())
    done = 0
    verified = 0
    failed = 0

    for pipeline_name, results in all_results.items():
        for pid, result in results.items():
            done += 1
            code = result.get("lean_code", "")
            if not code.strip():
                continue

            logger.info("AXLE verify %s/%s (%d/%d)", pipeline_name, pid, done, total)
            v = axle.verify_proof(code)
            result["verification"] = v

            if v.get("verified") is True:
                verified += 1
                logger.info("  VERIFIED")
            elif v.get("verified") is False:
                failed += 1
                logger.info("  FAILED: %s", v.get("details", "")[:80])

            result["verification_status"] = classify_verification_status(result)

    logger.info("AXLE complete: %d verified, %d failed out of %d", verified, failed, total)
    return all_results


def print_summary(all_results: dict):
    pipelines = list(all_results.keys())

    print()
    print("=" * 80)
    print("VERIFICATION & STATIC ANALYSIS SUMMARY")
    print("=" * 80)
    print()

    header = (
        f"{'Pipeline':<20} {'N':>3} {'Sorry=0':>8} {'Compl.':>7} "
        f"{'Verified':>9} {'Status':>30}"
    )
    print(header)
    print("-" * 80)

    for pname in pipelines:
        results = all_results[pname]
        n = len(results)

        sorry_free = sum(
            1 for r in results.values()
            if r.get("static_analysis", {}).get("sorry_count", 99) == 0
        )
        avg_completeness = sum(
            r.get("static_analysis", {}).get("completeness_score", 0)
            for r in results.values()
        ) / n if n else 0

        formally_verified = sum(
            1 for r in results.values()
            if r.get("verification", {}).get("verified") is True
        )

        statuses = {}
        for r in results.values():
            s = r.get("verification_status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

        status_str = ", ".join(f"{k}:{v}" for k, v in sorted(statuses.items()))
        verified_str = f"{formally_verified}/{n}" if formally_verified > 0 else "N/A"

        print(
            f"{pname:<20} {n:>3} {sorry_free:>5}/{n:<2} "
            f"{avg_completeness:>6.1%} {verified_str:>9}   {status_str}"
        )

    print()
    print("=" * 80)
    print("VERIFICATION STATUS BREAKDOWN")
    print("=" * 80)
    print()

    all_statuses = set()
    for pname in pipelines:
        for r in all_results[pname].values():
            all_statuses.add(r.get("verification_status", "unknown"))

    status_order = [
        "verified", "sorry_free_needs_mathlib", "sorry_free_basic",
        "partial_sorry", "sorry_in_main", "all_sorry", "no_output", "error",
    ]
    status_order = [s for s in status_order if s in all_statuses]

    print(f"{'Status':<30}", end="")
    for pname in pipelines:
        print(f" {pname:>15}", end="")
    print()
    print("-" * (30 + 16 * len(pipelines)))

    for status in status_order:
        print(f"{status:<30}", end="")
        for pname in pipelines:
            count = sum(
                1 for r in all_results[pname].values()
                if r.get("verification_status") == status
            )
            n = len(all_results[pname])
            pct = count / n * 100 if n else 0
            print(f" {count:>6} ({pct:>4.0f}%)", end="")
        print()

    print()


def main():
    parser = argparse.ArgumentParser(description="Verify and analyze experiment results")
    parser.add_argument("--axle", action="store_true", help="Run AXLE formal verification")
    parser.add_argument("--dry-run", action="store_true", help="Print without saving")
    parser.add_argument("--results", type=str, default=str(RESULTS_FILE))
    args = parser.parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        logger.error("Results file not found: %s", results_path)
        sys.exit(1)

    with open(results_path) as f:
        all_results = json.load(f)

    logger.info("Loaded %d pipelines, %d total proofs",
                len(all_results),
                sum(len(v) for v in all_results.values()))

    all_results = run_static_analysis(all_results)

    if args.axle:
        all_results = run_axle_verification(all_results)

    print_summary(all_results)

    if not args.dry_run:
        with open(results_path, "w") as f:
            json.dump(all_results, f, indent=2)
        logger.info("Updated results saved to %s", results_path)
    else:
        logger.info("Dry run — results not saved.")


if __name__ == "__main__":
    main()
