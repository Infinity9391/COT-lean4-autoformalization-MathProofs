"""
Guided baseline pipeline: Single-call with strategic instructions.

Controls for the "better instructions" confound. Same token budget as baseline
(1 call, 4096 max_tokens), but includes the same strategic guidance that the
CoT pipelines provide in their multi-step prompts.

If guided_baseline ≈ CoT pipelines, then the improvement comes from better
instructions, not from multi-step structure.
If CoT pipelines > guided_baseline, then multi-step decomposition adds value
beyond just giving better instructions.
"""

import logging

import anthropic

from pipelines.baseline import extract_lean_code
from prompts.templates import GUIDED_BASELINE, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def run_guided_baseline(
    problem: dict,
    client: anthropic.Anthropic,
    model: str = "claude-sonnet-4-20250514",
) -> dict:
    """Run the guided baseline pipeline on a single problem.

    Same as baseline but with strategic instructions that match the CoT pipelines.
    Single API call, same max_tokens budget as baseline.
    """
    theorem = problem["informal_statement"]
    if not theorem:
        theorem = problem.get("formal_statement", "")

    prompt = GUIDED_BASELINE.format(theorem=theorem)

    logger.info("Guided baseline: generating proof for %s", problem["id"])

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
        "pipeline": "guided_baseline",
        "lean_code": lean_code,
        "raw_output": raw_output,
        "api_calls": 1,
        "steps": {"direct": raw_output},
    }
