"""
Static analysis of Lean 4 proofs.

Since formal verification (AXLE API or local Lean+Mathlib) requires network
access that may not be available, this module provides rigorous static analysis
as a proxy metric. It extracts structural features from the generated Lean code
to give a more nuanced picture than a simple sorry/no-sorry binary.

Metrics extracted per proof:
  - sorry_count: number of `sorry` tokens in the code
  - sorry_in_main_theorem: whether the final/main theorem uses sorry
  - theorem_count: number of theorem/lemma declarations
  - complete_theorems: theorems with no sorry in their proof body
  - uses_mathlib: whether the code imports Mathlib modules
  - mathlib_imports: list of Mathlib modules imported
  - tactic_profile: which tactics are used (norm_num, simp, ring, etc.)
  - lines_of_code: non-blank, non-comment lines
  - has_structural_issues: obvious syntax problems detected
"""

import re
from collections import Counter


# Mathlib-dependent tactics (not available in bare Lean 4)
MATHLIB_TACTICS = {
    "norm_num", "simp", "ring", "omega", "nlinarith", "linarith",
    "field_simp", "positivity", "polyrith", "decide", "aesop",
    "push_neg", "contrapose", "by_contra", "ext", "congr",
    "norm_cast", "push_cast", "mod_cast",
}

# Lean 4 built-in tactics
BUILTIN_TACTICS = {
    "intro", "intros", "apply", "exact", "rfl", "rw", "rewrite",
    "cases", "induction", "constructor", "use", "exists",
    "have", "let", "show", "suffices", "calc", "match",
    "trivial", "assumption", "contradiction",
    "funext", "specialize", "obtain", "rcases",
}


def analyze_proof(lean_code: str) -> dict:
    """Run static analysis on a Lean 4 proof string."""
    if not lean_code or not lean_code.strip():
        return {
            "sorry_count": 0,
            "sorry_in_main_theorem": False,
            "theorem_count": 0,
            "complete_theorems": 0,
            "incomplete_theorems": 0,
            "uses_mathlib": False,
            "mathlib_imports": [],
            "tactic_profile": {},
            "lines_of_code": 0,
            "has_structural_issues": True,
            "structural_issues": ["empty_output"],
            "completeness_score": 0.0,
        }

    lines = lean_code.strip().split("\n")
    code_lines = [l for l in lines if l.strip() and not l.strip().startswith("--")]

    # --- Sorry analysis ---
    sorry_pattern = re.compile(r'\bsorry\b')
    sorry_count = len(sorry_pattern.findall(lean_code))

    # --- Theorem extraction ---
    theorem_pattern = re.compile(
        r'(theorem|lemma|def)\s+(\w+)',
        re.MULTILINE,
    )
    theorems = theorem_pattern.findall(lean_code)
    theorem_names = [name for _, name in theorems]

    # Determine which theorems contain sorry
    theorem_blocks = _split_into_theorem_blocks(lean_code, theorem_names)
    complete = 0
    incomplete = 0
    sorry_in_main = False

    for i, (name, block) in enumerate(theorem_blocks):
        block_sorries = len(sorry_pattern.findall(block))
        if block_sorries == 0:
            complete += 1
        else:
            incomplete += 1
            if i == len(theorem_blocks) - 1:
                sorry_in_main = True

    if not theorem_blocks and sorry_count > 0:
        sorry_in_main = True
        incomplete = 1

    # --- Mathlib analysis ---
    import_pattern = re.compile(r'^import\s+(Mathlib\S*)', re.MULTILINE)
    mathlib_imports = import_pattern.findall(lean_code)
    uses_mathlib = len(mathlib_imports) > 0

    mathlib_types = ["ℝ", "ℂ", "ℚ", "ℤ", "Finset", "Polynomial", "Matrix"]
    uses_mathlib_types = any(t in lean_code for t in mathlib_types)

    # --- Tactic profile ---
    tactic_counts = Counter()
    for tactic in MATHLIB_TACTICS | BUILTIN_TACTICS:
        pattern = re.compile(rf'\b{re.escape(tactic)}\b')
        count = len(pattern.findall(lean_code))
        if count > 0:
            tactic_counts[tactic] = count

    # --- Structural issues ---
    issues = []
    if lean_code.count("by") > 0 and lean_code.rstrip().endswith("sorry"):
        issues.append("ends_with_sorry")
    if lean_code.count("{") != lean_code.count("}"):
        issues.append("unbalanced_braces")
    if "unsolved goals" in lean_code.lower():
        issues.append("unsolved_goals_in_output")

    # --- Completeness score ---
    total_theorems = complete + incomplete
    if total_theorems == 0:
        completeness = 0.0
    else:
        completeness = complete / total_theorems

    if sorry_in_main:
        completeness *= 0.5

    return {
        "sorry_count": sorry_count,
        "sorry_in_main_theorem": sorry_in_main,
        "theorem_count": len(theorems),
        "complete_theorems": complete,
        "incomplete_theorems": incomplete,
        "uses_mathlib": uses_mathlib or uses_mathlib_types,
        "mathlib_imports": mathlib_imports,
        "tactic_profile": dict(tactic_counts),
        "lines_of_code": len(code_lines),
        "has_structural_issues": len(issues) > 0,
        "structural_issues": issues,
        "completeness_score": round(completeness, 3),
    }


def _split_into_theorem_blocks(code: str, names: list[str]) -> list[tuple[str, str]]:
    """Split Lean code into approximate theorem blocks."""
    if not names:
        return []

    blocks = []
    lines = code.split("\n")

    for i, name in enumerate(names):
        start = None
        for j, line in enumerate(lines):
            if re.search(rf'\b(theorem|lemma|def)\s+{re.escape(name)}\b', line):
                start = j
                break

        if start is None:
            continue

        if i + 1 < len(names):
            end = None
            for j, line in enumerate(lines[start + 1:], start + 1):
                if re.search(
                    rf'\b(theorem|lemma|def)\s+{re.escape(names[i + 1])}\b',
                    line,
                ):
                    end = j
                    break
            if end is None:
                end = len(lines)
        else:
            end = len(lines)

        block = "\n".join(lines[start:end])
        blocks.append((name, block))

    return blocks


def classify_verification_status(result: dict) -> str:
    """Classify a proof result into a verification status category.

    Categories:
      - "verified": Formally verified by AXLE or local Lean
      - "sorry_free_needs_mathlib": No sorry, but needs Mathlib to verify
      - "sorry_free_basic": No sorry, doesn't need Mathlib
      - "partial_sorry": Some theorems complete, some have sorry
      - "sorry_in_main": Main theorem uses sorry
      - "all_sorry": Every theorem uses sorry
      - "no_output": No Lean code generated
      - "error": Pipeline error
    """
    if "error" in result and "lean_code" not in result:
        return "error"

    code = result.get("lean_code", "")
    if not code or not code.strip():
        return "no_output"

    v = result.get("verification", {})
    if v.get("verified") is True:
        return "verified"

    analysis = result.get("static_analysis", analyze_proof(code))
    sorry_count = analysis["sorry_count"]

    if sorry_count == 0:
        if analysis["uses_mathlib"]:
            return "sorry_free_needs_mathlib"
        return "sorry_free_basic"

    if analysis["sorry_in_main_theorem"]:
        if analysis["complete_theorems"] > 0:
            return "partial_sorry"
        return "sorry_in_main"

    if analysis["complete_theorems"] > 0:
        return "partial_sorry"

    return "all_sorry"
