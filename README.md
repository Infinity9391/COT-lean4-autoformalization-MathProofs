# Dynamic Masked Chain-of-Thought for Lean 4

Can chain-of-thought prompting help LLMs write formally verified mathematical proofs or does it actually make them worse is our question.

We test whether multi-step CoT prompting  with and without context restriction between steps  improves LLM auto-formalization of informal mathematics into verified Lean 4 proofs. Proofs are formally verified against Lean 4 + Mathlib via the AXLE API.

**Our surprising finding:** the simplest baseline (a single direct prompt) dramatically outperforms all CoT variants under formal verification. Baseline verified 26% of proofs, while guided baseline verified only 8%, and both CoT pipelines verified just 10%. CoT reasoning, rather than helping, appears to anchor the model to human style proof strategies that don't translate well into valid Lean 4 tactic proofs.

---

## The Problem

Auto formalization is esseentiallly the process of translating informal mathematical reasoning into computer verified proofs and rightn now it is one of the hardest challenges in AI for mathematics. It requires the model to not only understand the math but produce syntactically and semantically valid code in a formal proof language.

It's important that eveyrone notes that, we are NOT measuring whether the model gets the right mathematical answer!!! A model might reason perfectly about a problem but still fail to produce valid Lean 4 code. Our metric is formal verification rate: does the generated Lean 4 proof fully compile and type check against Lean 4 + Mathlib? So either the proof either passes or it doesn't. There is no partial credit.

This distinction matters because the gap between "mathematically correct reasoning" and "valid formal proof" is enormous. A model can know that the answer is 42 but still fail to express a valid proof of that fact in Lean 4. Our experiment measures the model's ability to bridge that gap.

It would be intersting to see if local context is theoretically sufficient for multi-step computation, does restricting prompt context in practice lead to better outputs?

Auto formalization is an ideal testbed. It requires multi step reasoning (understand the math → plan the proof → write correct Lean 4 code), and correctness is objectively measurable via formal verification.

We test the following we force each reasoning step to produce self contained output (because downstream steps won't see earlier history) may lead to better distilled intermediate representations and ultimately higher quality proofs.

---

## Experiment Design

We compare four prompting pipelines on 50 problems from the miniF2F benchmark (AMC 12, AIME, and algebra competition problems). All pipelines use Claude Sonnet 4 (claude-sonnet-4-20250514) at temperature 0 for reproducibility.

### Pipeline 1: Baseline (Direct)
Single prompt → Lean 4 proof. Minimal instructions: just the theorem and "write a complete, valid Lean 4 proof." 1 API call, 4096 max tokens.

### Pipeline 2: Guided Baseline
Single prompt with detailed strategic instructions  reason about key mathematical ideas, identify specific lemmas, choose appropriate Lean 4 tactics (induction, ring, norm_num, simp, omega, etc.), and decompose into intermediate lemmas. 1 API call, 4096 max tokens. This controls for the possibility that CoT improvements come from better instructions rather than multi-step structure.

### Pipeline 3: Full-Context CoT
Three step formalization where each step sees all prior context:

- **Theorem → Proof Sketch** (2048 tokens): Natural language mathematical reasoning
- **Full History → Proof Structure** (2048 tokens): Identify lemmas, dependencies, and tactics
- **Full History → Lean 4 Code** (4096 tokens): Generate the formal proof

3 API calls, 8192 total max tokens.

### Pipeline 4: Context-Restricted (Masked) CoT
Same three steps, but each step only receives:

- The original theorem statement (anchor)
- The immediately preceding step's output (local context)

Each step's prompt explicitly instructs the model to produce self-contained output because downstream steps won't see earlier history.

### What Each Comparison Tests

| Comparison | What it isolates |
|---|---|
| Baseline vs Guided Baseline | Do better instructions help (independent of structure)? |
| Guided Baseline vs Full CoT | Does multistep decomposition add value beyond instructions? |
| Full CoT vs Restricted CoT | Does restricting context (forcing distillation) help or hurt? |
| Baseline vs Restricted CoT | Combined effect of structure + restriction |

### Important Design Note
Each pipeline condition runs as completely independent API calls  there is no shared conversation or context between conditions. The order in which pipelines are run has zero effect on results. Each problem × pipeline combination is a fresh, isolated API call.

---

## Methodology

### Dataset
50 problems from the miniF2F validation split, cached in `data/minif2f_cache.json`. Each problem includes an informal natural language statement and a formal Lean 4 theorem signature. Problems span three difficulty tiers: AMC 12 (17 problems), AIME (15 problems), and algebra (18 problems).

### Generation
Each pipeline generates a complete Lean 4 proof for each problem. All generation uses the Anthropic API with claude-sonnet-4-20250514 at temperature 0. The 4 pipelines × 50 problems = 200 generated proofs.

### Evaluation: Formal Verification via AXLE API
All 200 generated proofs are formally verified against Lean 4 + Mathlib using the AXLE API. A PASS means the proof fully type checks  no sorry placeholders, no tactic failures, no type errors, no import issues. This is the only metric that matters.

We deliberately chose formal verification over softer metrics (like "sorry free rate" from static analysis) because static analysis dramatically overestimates proof quality. A proof can be sorry free but still fail compilation due to tactic errors, type mismatches, or incorrect Mathlib API usage.

Our experiment operates at a different level: we restrict what text appears in multi step prompts, not how attention operates within a forward pass. The model's internal attention can still attend to everything in each individual prompt.

We test the behavioral analog: if local context suffices in principle, does restricting prompt context in practice lead to better outputs?

---

## Results

### Formal Verification — AXLE API (All 50 Problems)

| Pipeline | Verified | Failed | Errors | Verification Rate |
|---|---|---|---|---|
| Baseline | 13/50 | 37/50 | 0 | **26.0%** |
| Guided Baseline | 4/50 | 46/50 | 0 | 8.0% |
| Full-Context CoT | 5/50 | 45/50 | 0 | 10.0% |
| Masked CoT | 5/50 | 45/50 | 0 | 10.0% |

The baseline  the simplest possible prompt  outperforms every other condition by a wide margin.

### Static Analysis (50 problems per pipeline)
For context, static analysis (checking for sorry tokens without compiling) tells a very different story:

| Pipeline | Sorry-Free | Sorry-Free % | Completeness | Main Thm OK |
|---|---|---|---|---|
| Baseline | 36/50 | 72% | 74.0% | 74% |
| Guided Baseline | 38/50 | 76% | 81.6% | 82% |
| Full-Context CoT | 46/50 | 92% | 94.0% | 94% |
| Restricted CoT | 41/50 | 82% | 85.1% | 84% |

Full CoT looks best on static analysis (92% sorry-free) but heinous on actual verification (10%). This underscores why formal verification is essential — static analysis is deeply misleading for evaluating proof quality.

---

## Analysis: Why Does CoT Hurt?

### 1. CoT Anchors the Model to Human Style Proof Strategies
The most revealing evidence comes from individual problem analysis. Consider mathd_algebra_13 (partial fraction decomposition):

**Baseline (PASSED):** The model imported Mathlib.Algebra.Field.Basic and Mathlib.Tactic, then let powerful automation tactics handle the proof. It chose its own strategy freely and succeeded.

**Full CoT (FAILED):** Step 1 produced a proof sketch: "The key insight is to use partial fraction decomposition by finding a common denominator and equating coefficients." Step 3, now anchored to this human style strategy, attempted to manually execute it with `intro x h3 h5` and explicit rewriting — leading to unsolved goals and a sorry fallback.

The baseline model likely used `field_simp`, `ring`, or `norm_num` — powerful Lean automation that doesn't correspond to how a human would write the proof on paper. The CoT reasoning steered the model away from the best Lean strategy and toward a human readable but Lean incompatible approach.

### 2. Natural Language Reasoning ≠ Formal Proof Strategy
Lean 4's strength is its tactic system: `norm_num` can dispatch numeric computations, `ring` handles ring identities, `omega` solves linear arithmetic, and `simp` applies simplification lemmas. These tactics don't map to natural language proof steps like "factor the denominator" or "equate coefficients."

When the CoT pipeline asks the model to first describe a proof in natural language, it forces the model to think in human mathematical terms. When it then asks for Lean code, the model tries to translate that human reasoning into tactics  often choosing a harder path than necessary.

### 3. Error Propagation Across Steps
In multi step pipelines, each step is a separate API call. If step 1 produces a plausible sounding but subtly flawed proof sketch, step 3 is anchored to that strategy. The model might know a simpler approach but feels obligated to follow the plan laid out in previous steps.

### 4. The Baseline Lets the Model Use Internal Reasoning
With temperature 0 and 4096 max tokens, the baseline model already performs CoT reasoning internally before outputting code. The explicit CoT pipelines may be replacing effective internal reasoning with worse explicit reasoning  essentially overriding the model's natural problem solving process with a constrained human style workflow.

### 5. Guided Instructions Create Conflicting Pressure
The guided baseline (8%  worst of all) tells the model to "reason about key mathematical ideas" and "identify specific lemmas" while also saying "output only the Lean 4 code block." These conflicting instructions  think elaborately, but only output code appear to really mess with the performance even further than multi step CoT.

---

## Key Takeaways

1. **CoT hurts formal proof generation.** Explicit multi step reasoning reduces Lean 4 verification rates from 26% to 8-10%. The best strategy is the simplest: give the model the theorem and ask for a proof directly.

2. **Sorry free is NOT the same as formally verifying it.** The gap between sorry free rates (72-92%) and verification rates (8-26%) is enormous. Static analysis gives a false sense of quality. Without formal verification, we would have concluded the opposite — that CoT helps.

3. **Natural language reasoning interferes with tactic based proving.** The best Lean proof strategy is often "let automation handle it" (norm_num, ring, simp). CoT forces the model into verbose human-style reasoning that doesn't translate to effective tactic selection.

4. **Better instructions alone make things worse.** The guided baseline performs worst (8%), suggesting that detailed strategic instructions without multi-step structure actively hurt. The model performs best when given maximum freedom to choose its own approach.

5. **Context restriction doesn't rescue CoT.** Masked CoT (10%) performs identically to full CoT (10%). The information distillation hypothesis is neither confirmed nor refuted — the fundamental problem is that explicit reasoning hurts, regardless of context management.

---

## Limitations

- **Single model.** All results use Claude Sonnet 4 at temperature 0. Results may differ for other models (especially those specifically trained for formal verification), temperatures, or with retry/best-of-N strategies.
- **50 problems.** While all 50 were formally verified (not a subset), the dataset limits statistical power for detecting smaller effects.
- **Prompt level vs attention level masking.** Our context restriction operates at the prompt level, a much coarser intervention than the attention level masking.
- **No fine tuning.** We test prompting strategies only. A model fine tuned on Lean 4 proofs might respond differently to CoT structuring.
- **Competition math only.** miniF2F contains competition-style problems. Results may differ for research-level mathematics or other formal verification domains.

---

## Setup
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="your-key-here"
```

## Usage
```bash
# Run full experiment (50 problems, all 4 pipelines)
python run_experiment.py

# Run specific pipelines
python run_experiment.py --pipelines baseline,full_cot,masked_cot

# Run fewer problems for testing
python run_experiment.py --num-problems 5

# Resume interrupted experiment
python run_experiment.py --resume

# Formal verification via AXLE API
python verify_results.py --axle

# Static analysis only (no network needed)
python verify_results.py
python analyze_results.py
```

## Project Structure
```
├── README.md                 # This file — full writeup and results
├── requirements.txt          # Python dependencies
├── data/
│   ├── load_minif2f.py       # Load and preprocess miniF2F problems
│   └── minif2f_cache.json    # Cached dataset (50 problems)
├── pipelines/
│   ├── baseline.py           # Direct formalization (1 call)
│   ├── guided_baseline.py    # Strategic instructions (1 call)
│   ├── full_cot.py           # Full-context 3-step CoT (3 calls)
│   └── masked_cot.py         # Context-restricted 3-step CoT (3 calls)
├── prompts/
│   └── templates.py          # All prompt templates
├── verification/
│   ├── axle_client.py        # AXLE API client for formal verification
│   └── static_analysis.py    # Sorry tracking, completeness scoring
├── run_experiment.py          # Main experiment runner
├── verify_results.py          # Post-hoc verification + static analysis
├── analyze_results.py         # Statistical analysis + stratification
└── results/                   # Output JSON files
    ├── experiment_results.json
    └── analysis_summary.json
```

## Dataset
miniF2F — 50 problems from the validation split. Competition math (AMC 12, AIME, algebra). Each problem has an informal statement and a formal Lean 4 theorem signature.

## Verification
Formal verification uses the AXLE API (axiom-axle SDK), which compiles proofs against Lean 4 + Mathlib. Anonymous access, no API key required (rate-limited to 10 concurrent requests).

## LLM Backbone
All generation uses Claude Sonnet 4 (claude-sonnet-4-20250514) via the Anthropic API at temperature 0 for reproducibility.

## References
- miniF2F: Facebook Research — Benchmark dataset for formal mathematics
- AXLE API: Axiom Mathematics — Lean 4 + Mathlib formal verification service

---

*The narrative arc: we expected CoT to help, static analysis said it did, but formal verification revealed the opposite. The punchline is that without AXLE verification, we would have published the wrong conclusion.*
