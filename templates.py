"""
Prompt templates for the Dynamic-Masked CoT auto-formalization experiment.

All prompts are defined as named constants for easy inspection and modification.

Design principles:
  - Baseline and guided_baseline use the SAME total max_tokens (4096) in 1 call.
  - CoT pipelines use 3 calls (2048 + 2048 + 4096 = 8192 total).
  - Guided baseline includes comparable strategic instructions to CoT pipelines,
    controlling for "better instructions" vs "multi-step structure."
  - Masked CoT steps explicitly instruct the model to produce self-contained
    outputs, since downstream steps won't see earlier history.
"""

# =============================================================================
# Baseline Pipeline (Direct Formalization — minimal instructions)
# =============================================================================

BASELINE_DIRECT = """\
Here is an informal math theorem:

{theorem}

Write a complete, valid Lean 4 proof for this theorem. Output only the Lean 4 code block, nothing else.\
"""

# =============================================================================
# Guided Baseline Pipeline (Single-call with strategic instructions)
#
# Controls for the "better instructions" confound: gives the model the same
# strategic guidance that CoT pipelines provide, but in a single prompt.
# =============================================================================

GUIDED_BASELINE = """\
Here is an informal math theorem:

{theorem}

Write a complete, valid Lean 4 proof for this theorem. Follow this approach:

1. First, reason about the key mathematical ideas and proof strategy.
2. Identify the specific lemmas needed and how they depend on each other.
3. Choose appropriate Lean 4 tactics for each step (e.g., induction, ring, norm_num, simp, omega, field_simp, nlinarith).
4. Write the complete proof, decomposing it into well-named intermediate lemmas where appropriate.

Output only the Lean 4 code block, nothing else.\
"""

# =============================================================================
# Full-Context CoT Pipeline
# =============================================================================

FULL_COT_STEP1 = """\
Here is an informal math theorem:

{theorem}

Write a concise informal proof sketch in natural language. Focus on:
- The key mathematical insight or technique
- The main logical steps in sequence
- Any critical intermediate results needed

Do not write Lean syntax — just describe the proof strategy.\
"""

FULL_COT_STEP2 = """\
Here is a math theorem:

{theorem}

Here is an informal proof sketch:

{step1_output}

Now identify the formal proof structure: list the key lemmas needed, the logical \
dependencies between them, and the overall proof strategy. Be specific about what \
Lean 4 tactics would handle each step (e.g., induction, ring, norm_num, simp, omega, \
field_simp, nlinarith).\
"""

FULL_COT_STEP3 = """\
Here is a math theorem:

{theorem}

Here is an informal proof sketch:

{step1_output}

Here is a typed proof structure:

{step2_output}

Now write a complete, valid Lean 4 proof. Output only the Lean 4 code block, nothing else.\
"""

# =============================================================================
# Dynamic-Masked CoT Pipeline
#
# Inspired by ICGD's observation that local context suffices for multi-step
# computation: each step sees ONLY the original theorem (anchor) and the
# immediately preceding step's output (local block).
#
# KEY DIFFERENCE from Full CoT: each step's prompt explicitly instructs the
# model to produce SELF-CONTAINED output, because downstream steps won't see
# earlier history. This tests the "information distillation" hypothesis —
# that forcing self-contained intermediate representations improves quality.
# =============================================================================

MASKED_COT_STEP1 = """\
Here is an informal math theorem:

{theorem}

Write a concise informal proof sketch in natural language. Focus on:
- The key mathematical insight or technique
- The main logical steps in sequence
- Any critical intermediate results needed

IMPORTANT: Your output must be fully self-contained. The next step will see your \
output but NOT this original theorem statement, so include all necessary context \
about what is being proved and the key quantities involved.

Do not write Lean syntax — just describe the proof strategy.\
"""

MASKED_COT_STEP2 = """\
Here is a math theorem:

{theorem}

Here is an informal proof sketch:

{step1_output}

Now identify the formal proof structure: list the key lemmas needed, the logical \
dependencies between them, and the overall proof strategy. Be specific about what \
Lean 4 tactics would handle each step (e.g., induction, ring, norm_num, simp, omega, \
field_simp, nlinarith).

IMPORTANT: Your output must be fully self-contained. The next step will see your \
output and the original theorem but NOT the proof sketch above. Include all necessary \
details about the proof approach, specific values, and tactic choices so that a Lean 4 \
proof can be written from your output alone.\
"""

# NOTE: Step 3 receives ONLY theorem + Step 2 output. Step 1 output is masked.
MASKED_COT_STEP3 = """\
Here is a math theorem:

{theorem}

Here is a typed proof structure:

{step2_output}

Now write a complete, valid Lean 4 proof. Output only the Lean 4 code block, nothing else.\
"""

# =============================================================================
# System prompts
# =============================================================================

SYSTEM_PROMPT = """\
You are an expert mathematician and Lean 4 proof assistant. You produce correct, \
concise, and well-structured outputs. When asked to write Lean 4 code, output \
only valid Lean 4 syntax with no surrounding explanation.\
"""
