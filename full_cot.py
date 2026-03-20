"""
Full-context CoT pipeline.

Multi-step formalization where each step sees the full prior history:
  Step 1: Theorem → informal proof sketch
  Step 2: All prior context → typed proof structure
  Step 3: All prior context → Lean 4 code
"""

import logging

import anthropic

from pipelines.baseline import extract_lean_code
from prompts.templates import (
    FULL_COT_STEP1,
    FULL_COT_STEP2,
    FULL_COT_STEP3,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def run_full_cot(
    problem: dict,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Run the full-context CoT pipeline on a single problem.

    Each step receives ALL prior steps as context (full history).

    Args:
        problem: Dict with 'id', 'informal_statement', 'formal_statement'.
        client: Anthropic API client.
        model: Model identifier.

    Returns:
        Dict with pipeline results including intermediate steps and final Lean 4 code.
    """
    theorem = problem["informal_statement"]
    if not theorem:
        theorem = problem.get("formal_statement", "")

    # Step 1: Theorem → informal proof sketch
    logger.info("Full CoT Step 1: proof sketch for %s", problem["id"])
    step1_prompt = FULL_COT_STEP1.format(theorem=theorem)

    step1_response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": step1_prompt}],
    )
    step1_output = step1_response.content[0].text

    # Step 2: Full history → typed proof structure
    logger.info("Full CoT Step 2: proof structure for %s", problem["id"])
    step2_prompt = FULL_COT_STEP2.format(
        theorem=theorem, step1_output=step1_output
    )

    step2_response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": step2_prompt}],
    )
    step2_output = step2_response.content[0].text

    # Step 3: Full history (theorem + step1 + step2) → Lean 4 code
    logger.info("Full CoT Step 3: Lean 4 code for %s", problem["id"])
    step3_prompt = FULL_COT_STEP3.format(
        theorem=theorem,
        step1_output=step1_output,
        step2_output=step2_output,
    )

    step3_response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": step3_prompt}],
    )
    step3_output = step3_response.content[0].text
    lean_code = extract_lean_code(step3_output)

    return {
        "problem_id": problem["id"],
        "pipeline": "full_cot",
        "lean_code": lean_code,
        "raw_output": step3_output,
        "api_calls": 3,
        "steps": {
            "step1_proof_sketch": step1_output,
            "step2_proof_structure": step2_output,
            "step3_lean_code": step3_output,
        },
    }
