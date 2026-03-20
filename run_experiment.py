#!/usr/bin/env python3
"""
Main experiment runner: runs all 4 pipelines on miniF2F problems and saves results.

Usage:
    python run_experiment.py [--num-problems 50] [--resume] [--pipelines baseline,full_cot,masked_cot]

Environment variables:
    ANTHROPIC_API_KEY: Required. API key for Claude.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import anthropic

from data.load_minif2f import load_minif2f_problems
from pipelines.baseline import run_baseline
from pipelines.full_cot import run_full_cot
from pipelines.guided_baseline import run_guided_baseline
from pipelines.masked_cot import run_masked_cot
from verification.axle_client import AxleClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PIPELINE_RUNNERS = {
    "baseline": run_baseline,
    "guided_baseline": run_guided_baseline,
    "full_cot": run_full_cot,
    "masked_cot": run_masked_cot,
}

RESULTS_DIR = Path("results")


def load_existing_results(results_file: Path) -> dict:
    if results_file.exists():
        with open(results_file) as f:
            return json.load(f)
    return {}


def save_results(results: dict, results_file: Path):
    results_file.parent.mkdir(parents=True, exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)


def run_pipeline_on_problem(
    pipeline_name: str,
    problem: dict,
    client: anthropic.Anthropic,
    axle: AxleClient,
    model: str,
    rate_limit_delay: float = 1.0,
) -> dict:
    runner = PIPELINE_RUNNERS[pipeline_name]
    result = runner(problem, client, model=model)
    time.sleep(rate_limit_delay)

    if result["lean_code"]:
        verification = axle.verify_proof(result["lean_code"])
        result["verification"] = verification
    else:
        result["verification"] = {
            "verified": False,
            "method": "none",
            "details": "No Lean code generated.",
            "raw_response": None,
        }

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run Dynamic-Masked CoT experiment on miniF2F"
    )
    parser.add_argument("--num-problems", type=int, default=50)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--reverify", action="store_true")
    parser.add_argument(
        "--pipelines",
        type=str,
        default="baseline,guided_baseline,full_cot,masked_cot",
    )
    parser.add_argument("--model", type=str, default="claude-sonnet-4-20250514")
    parser.add_argument("--rate-limit-delay", type=float, default=1.0)
    parser.add_argument("--data-cache", type=str, default="data/minif2f_cache.json")
    args = parser.parse_args()

    axle = AxleClient()
    client = None
    if not args.reverify:
        try:
            client = anthropic.Anthropic()
        except anthropic.AuthenticationError:
            logger.error("Anthropic API key not found. Set ANTHROPIC_API_KEY.")
            sys.exit(1)

    logger.info("Loading miniF2F problems...")
    problems = load_minif2f_problems(
        num_problems=args.num_problems, cache_path=args.data_cache
    )
    logger.info("Loaded %d problems.", len(problems))

    pipelines = [p.strip() for p in args.pipelines.split(",")]
    for p in pipelines:
        if p not in PIPELINE_RUNNERS:
            logger.error("Unknown pipeline: %s", p)
            sys.exit(1)

    results_file = RESULTS_DIR / "experiment_results.json"
    all_results = (
        load_existing_results(results_file) if (args.resume or args.reverify) else {}
    )

    if args.reverify:
        if not all_results:
            logger.error("No existing results to reverify.")
            sys.exit(1)
        total = sum(len(v) for v in all_results.values())
        done = 0
        for pipeline_name, results in all_results.items():
            for pid, result in results.items():
                done += 1
                lean_code = result.get("lean_code", "")
                if not lean_code:
                    continue
                logger.info("Verifying %s / %s (%d/%d)", pipeline_name, pid, done, total)
                verification = axle.verify_proof(lean_code)
                result["verification"] = verification
                if verification.get("verified"):
                    logger.info("  VERIFIED")
                elif verification.get("verified") is False:
                    logger.info("  Failed: %s", verification.get("details", "")[:100])
                save_results(all_results, results_file)
        logger.info("Re-verification complete.")
        return

    total = len(problems) * len(pipelines)
    completed = 0

    for pipeline_name in pipelines:
        if pipeline_name not in all_results:
            all_results[pipeline_name] = {}

        for problem in problems:
            pid = problem["id"]

            if pid in all_results[pipeline_name]:
                logger.info("Skipping %s / %s (already done)", pipeline_name, pid)
                completed += 1
                continue

            logger.info("Running %s on %s (%d/%d)", pipeline_name, pid, completed + 1, total)

            try:
                result = run_pipeline_on_problem(
                    pipeline_name=pipeline_name,
                    problem=problem,
                    client=client,
                    axle=axle,
                    model=args.model,
                    rate_limit_delay=args.rate_limit_delay,
                )
                all_results[pipeline_name][pid] = result

            except anthropic.RateLimitError:
                logger.warning("Rate limited. Waiting 60s...")
                time.sleep(60)
                try:
                    result = run_pipeline_on_problem(
                        pipeline_name=pipeline_name,
                        problem=problem,
                        client=client,
                        axle=axle,
                        model=args.model,
                        rate_limit_delay=args.rate_limit_delay,
                    )
                    all_results[pipeline_name][pid] = result
                except Exception as e:
                    logger.error("Failed on %s / %s after retry: %s", pipeline_name, pid, e)
                    all_results[pipeline_name][pid] = {
                        "problem_id": pid,
                        "pipeline": pipeline_name,
                        "error": str(e),
                    }

            except Exception as e:
                logger.error("Failed on %s / %s: %s", pipeline_name, pid, e)
                all_results[pipeline_name][pid] = {
                    "problem_id": pid,
                    "pipeline": pipeline_name,
                    "error": str(e),
                }

            save_results(all_results, results_file)
            completed += 1

    logger.info("Experiment complete. Results saved to %s", results_file)
    logger.info("Run `python analyze_results.py` to generate the summary.")


if __name__ == "__main__":
    main()
