# Workflow: AI System Evaluation

**Trigger:** AI/LLM feature change (prompt, model, tools, retrieval) or scheduled baseline
**Gate:** `ai-eval-gate` · **Human checkpoint:** `always`
**Config:** `framework.yaml → workflows.ai-system-evaluation`

Testing AI systems is different in kind, not just degree: outputs are non-deterministic,
"correct" is a rubric rather than an assertion, and the failure modes (hallucination,
prompt injection, drift) have no classical-testing equivalent. This workflow treats
**evals as the unit of quality evidence** for AI features.

## Flow

```
AI feature change (prompt / model / tools / RAG corpus)
   │
   ▼
qe-test-strategist ───── define_eval_dimensions
   │   what "good" means: correctness, groundedness, safety,
   │   tone, latency, cost — weighted for this feature
   ▼
qe-test-generator ────── generate_eval_cases
   │   scenario sets per dimension: golden cases, edge cases,
   │   adversarial cases, regression cases from past failures
   ▼
qe-test-executor ─────── run_evals
   │   eval_pass_rate_pct, hallucination_rate_pct,
   │   regression_vs_baseline_pct, avg_cost_per_task_usd
   ▼
qe-security-scanner ──── adversarial_probe
   │   prompt injection, jailbreak attempts, data exfiltration
   │   probes → prompt_injection_failures
   ▼
qe-quality-gatekeeper ── evaluate ai-eval-gate
   │
   ▼
HUMAN CHECKPOINT (always)
   sampled transcript review + verdict review → GO / NO-GO
```

## Eval design rules

- **Rubrics, not string matches.** Each eval case states the dimension, the scenario,
  and a scoring rubric ([templates/eval-rubric.md](../templates/eval-rubric.md)).
  Scoring can be programmatic, LLM-as-judge, or human — the rubric is the contract.
- **LLM-as-judge needs its own QA.** Judge prompts are versioned; judge agreement is
  spot-checked against human scores on a sample every cycle. A drifting judge silently
  corrupts every downstream verdict.
- **Run counts matter.** Non-determinism means single runs are anecdotes. Eval cases
  run N times (N per dimension criticality); pass rates are computed over runs.
- **Baselines are sacred.** Every change is compared against the previous baseline on
  the same eval set (`regression_vs_baseline_pct`). A capability gain that regresses an
  existing behavior is a trade-off for a human to accept, not an agent.
- **Failed production cases become regression evals.** The eval set grows from reality:
  every confirmed production failure is distilled into a permanent eval case.

## Mechanical support (`aqef evals`)

The dataset and its scoring are first-class artifacts
([examples/eval-dataset.yaml](../examples/eval-dataset.yaml)):

```bash
# Validate the dataset and audit its composition (sources, thin dimensions)
aqef evals --dataset eval-dataset.yaml

# Score a results file (one {case_id, score} JSON line per run) into the
# exact metrics the ai-eval-gate consumes
aqef evals --dataset eval-dataset.yaml --results results.jsonl --out eval-metrics.json
aqef gate ai-eval-gate --config framework.yaml --metrics eval-metrics.json
```

- Pass thresholds are **per dimension** — a score of 4 passes correctness
  (`>= 3`) and fails safety (`>= 5`).
- Cases with no scored runs are surfaced as `eval_cases_missing_results`, never
  silently dropped; add `eval_cases_missing_results == 0` as a blocking rule to
  keep the gate fail-closed end to end.
- Composition warnings enforce dataset hygiene: thin dimensions, no
  production-failure cases (golden sets drift without them), no adversarial
  cases (injection resistance untested).

## Adversarial probing scope

The security scanner probes the AI feature itself:

- **Prompt injection** — direct and indirect (via retrieved documents, tool results)
- **Jailbreaks** — attempts to bypass the feature's behavioral constraints
- **Data exfiltration** — coaxing the system to reveal system prompts, other users'
  data, or secrets available to its tools
- **Tool abuse** — inducing unsafe tool invocations through crafted inputs

Any successful probe is a blocking gate failure (`prompt_injection_failures == 0`).
Probing is authorized against the team's own systems only.

## The human checkpoint

The verdict alone is not enough for AI features. The checkpoint includes **sampled
transcript review**: a human reads a stratified sample of actual model outputs (passing
and failing) per cycle. Aggregate metrics hide qualitative failures — tone drift,
subtle unhelpfulness, plausible-but-wrong reasoning — that humans catch in minutes.

## Cost as a quality dimension

`avg_cost_per_task_usd` is tracked at `info` severity: cost regressions don't block,
but a model/prompt change that doubles unit cost is a finding the report must surface.
Quality per dollar is the real curve being optimized.
