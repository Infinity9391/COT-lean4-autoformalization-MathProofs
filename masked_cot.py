"""
Dynamic-masked CoT pipeline (main contribution).

Same 3-step structure as full CoT, but each step only receives:
  - The original theorem statement (anchor block)
  - The immediately preceding step's output (local block)

Inspired by the ICGD paper's observation that local context suffices for
multi-step computation, this pipeline tests whether restricting prompt context
and forcing self-contained intermediate outputs improves proof quality.

Key differences from full_cot.py:
  - Step 3 does NOT see Step 1 output — only theorem + Step 2 output
  - Steps 1-2 explicitly instruct the model to produce self-contained outputs,
    since downstream steps won't see earlier history ("information distillation")
"""

import logging

import anthropic

from pipelines.baseline import extract_lean_code
from prompts.templates import (
    MASKED_COT_STEP1,
    MASKED_COT_STEP2,
    MASKED_COT_STEP3,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


def run_masked_cot(
    problem: dict,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Run the dynamic-masked CoT pipeline on a single problem.

    Each step receives ONLY the original theorem (anchor) and the
    immediately preceding step's output (local block). No full history.

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

    # Step 1: Receives ONLY the theorem (anchor block)
    logger.info("Masked CoT Step 1: proof sketch for %s", problem["id"])
    step1_prompt = MASKED_COT_STEP1.format(theorem=theorem)

    step1_response = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": step1_prompt}],
    )
    step1_output = step1_response.content[0].text

    # Step 2: Receives theorem (anchor) + Step 1 output (local block)
    logger.info("Masked CoT Step 2: proof structure for %s", problem["id"])
    step2_prompt = MASKED_COT_STEP2.format(
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

    # Step 3: Receives theorem (anchor) + Step 2 output (local block)
    # NOTE: Step 1 output is MASKED — not included in context
    logger.info("Masked CoT Step 3: Lean 4 code for %s", problem["id"])
    step3_prompt = MASKED_COT_STEP3.format(
        theorem=theorem, step2_output=step2_output
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
        "pipeline": "masked_cot",
        "lean_code": lean_code,
        "raw_output": step3_output,
        "api_calls": 3,
        "steps": {
            "step1_proof_sketch": step1_output,
            "step2_proof_structure": step2_output,
            "step3_lean_code": step3_output,
        },
    }
