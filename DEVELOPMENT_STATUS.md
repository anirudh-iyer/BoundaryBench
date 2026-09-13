# Development status

## Implemented

- Separate corpus availability, unfiltered ranking/window opportunity, diagnostic
  denial, actual prevention, returned content, and submitted model exposure.
- Shared A-D policy/retrieval path; trusted identity and body-only injection.
- 14 development cases covering all ten requested categories, with authorized
  and clean injection counterparts; five users and six small corpus documents.
- Provider-independent interface, deterministic offline doubles, bounded fresh
  sessions, complete request/response/search/error records, and create-only JSONL.
- Provisional exact/cumulative scoring, blinded human-review export, separate ATS
  and refusal heuristics, explicit metric denominators and unresolved-outcome bounds.

## Validation

**65 tests passed** on Python 3.12.0, Pydantic 2.13.5, pytest 9.1.1:

```text
.venv/Scripts/python.exe -m pytest -q --basetemp .pytest_cache/dev-validation-2 --tb=short
```

Tests cover every requested boundary, denied-below-window versus prevention,
retrieval misses, actual request exposure, identity/tool spoofing, injection
metadata isolation, episode reset, immutable raw-record round trips, bounded
execution, raw errors/usage, cumulative disclosure, refusal versus wrong answers,
denominators, review blinding, and all 14 x 4 offline case/condition combinations.
The offline CLI's complete raw/scoring/metrics/review workflow is also tested.
The sandbox's default pytest temp location was inaccessible; validation used a
fresh directory inside the workspace. No live provider or held-out cases ran.

## Methodological choices

The primary interpretation is A versus external enforcement. B/C/D may be
identical and cannot establish architectural superiority. Opportunity uses the
unfiltered top-k counterfactual; denial below that window is not prevention.
Exposure requires submitted request content. Errors remain unresolved unless
positive disclosure/exposure evidence already exists. ATS and over-refusal are
independent provisional labels. Offline outputs are control tests, not results.

## Unresolved issues

Live adapter/model selection and development piloting remain pending. Literal
matching misses semantic inference; utility/refusal heuristics need calibrated
human review. Human adjudication/import, diagnostic model baselines, family-aware
confidence intervals, and the full held-out design remain pending. Raw storage
is create-only at the application layer, not OS-enforced WORM or crash recovery.
Provider submission is observable; remote receipt after an error is uncertain.

## Exact next step before a held-out freeze

Conduct a human audit of the 14 development prompts, facts, retrieval windows,
trace semantics, and review rubric. Then select/configure a provider and model
for a separately authorized development-only pilot with no-policy, empty-context,
and deny-all diagnostics. Use that evidence to freeze prompts, budgets, scoring,
target-family design, and the analysis plan before authoring/freezing held-out
cases. Stop here for this deliverable: no live calls, 96-case generation, or
empirical findings are authorized or produced.
