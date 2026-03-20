"""
Baseline pipeline: Direct formalization.

Single prompt → Lean 4 proof attempt. No intermediate steps.
"""

import logging
import re

import anthropic

from prompts.templates import BASELINE_DIRECT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def extract_lean_code(text: str) -> str:
    """Extract Lean 4 code from a response, handling code blocks."""
    # Try to find ```lean ... ``` blocks
    match = re.search(r"```(?:lean4?|)\s*\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no code block, return the full text stripped
    return text.strip()


def run_baseline(
    problem: dict,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Run the baseline (direct) formalization pipeline on a single problem.

    Args:
        problem: Dict with 'id', 'informal_statement', 'formal_statement'.
        client: Anthropic API client.
        model: Model identifier.

    Returns:
        Dict with pipeline results including the generated Lean 4 code.
    """
    theorem = problem["informal_statement"]
    if not theorem:
        theorem = problem.get("formal_statement", "")

    prompt = BASELINE_DIRECT.format(theorem=theorem)

    logger.info("Baseline: generating proof for %s", problem["id"])

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    raw_output = response.content[0].text
    lean_code = extract_lean_code(raw_output)

    return {
        "problem_id": problem["id"],
        "pipeline": "baseline",
        "lean_code": lean_code,
        "raw_output": raw_output,
        "api_calls": 1,
        "steps": {"direct": raw_output},
    }
