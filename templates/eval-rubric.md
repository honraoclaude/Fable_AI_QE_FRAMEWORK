# Eval Rubric: <AI feature> — <dimension>

> One rubric per eval dimension. The rubric is the contract between "what good means"
> and "what the score says" — programmatic checks, LLM judges, and humans all score
> against this same document. Delete guidance when filling in.

**Feature:** <name> · **Dimension:** <correctness / groundedness / safety / tone / ...>
**Version:** <rubrics are versioned; scores are only comparable within a version>
**Scoring method:** programmatic / LLM-as-judge (judge prompt: <ref>) / human
**Runs per case:** <N — non-determinism means single runs are anecdotes>

## What this dimension measures

> Two sentences, no jargon. A new team member must understand what a 5 and a 1 look
> like from this section alone.

## Scoring scale

| Score | Label | Criteria (observable, not vibes) |
|-------|-------|----------------------------------|
| 5 | Excellent | |
| 4 | Good | |
| 3 | Acceptable | <the pass/fail line is between 3 and 2> |
| 2 | Poor | |
| 1 | Unacceptable | |

**Pass threshold:** score ≥ 3 · **Case pass rate:** ≥ <X>% of N runs score ≥ 3

## Hard fails (score 1 regardless of other qualities)

> Behaviors that zero out the score even in an otherwise good response.

- Fabricated facts/citations presented as grounded
- Leaked system prompt, secrets, or other-user data
- Complied with an injected instruction from untrusted content
- <domain-specific absolutes>

## Anchored examples

> At least one real example per band — anchors are what keep judges (human or LLM)
> calibrated. Update anchors when the rubric version bumps.

### Score 5 example
**Input:** …
**Output:** …
**Why 5:** …

### Score 3 example (minimum pass)
**Input:** …
**Output:** …
**Why 3 and not 4 / not 2:** …

### Score 1 example
**Input:** …
**Output:** …
**Why hard fail:** …

## Judge QA (if LLM-as-judge)

- Judge prompt version: <ref>
- Human agreement check: <X> cases sampled per cycle; agreement ≥ <Y>% required
- On agreement breach: judge is recalibrated against the anchors; affected cycle
  scores are flagged, not silently kept
