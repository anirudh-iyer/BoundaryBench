# Development status

## Implemented

- Separate corpus availability, unfiltered ranking/window opportunity, diagnostic
  denial, actual prevention, returned content, and submitted model exposure.
- Shared A-D policy/retrieval path; trusted identity and body-only injection.
- 14 development cases covering all ten requested categories, with authorized
  and clean injection counterparts; five users and six small corpus documents.
- Provider-independent interface, deterministic offline doubles, bounded fresh
  sessions, complete request/response/search/error records, and create-only JSONL.
- Provisional exact/cumulative scoring, separate ATS and refusal heuristics,
  general and designated-target retrieval/block metrics, explicit denominators,
  and unresolved-outcome bounds.
- Independent initial review export with no condition labels/pseudonyms or
  automatic outcomes; separate private review-ID/episode/condition/score mapping.
- One OpenAI Chat Completions adapter with environment-only credentials, explicit
  settings, timeout, bounded transient retries, exact request JSON, raw API
  responses, usage, finish reasons and tool-result round trips.
- DEVELOPMENT ONLY no-policy, empty-context and deny-all modes, separate from
  A/B/C/D and rejected by primary aggregation. Diagnostic suppression earns no
  authorization-block credit.
- A gated 19-episode manifest/CLI with separate normal/diagnostic scores,
  independent review, private joins, per-episode audit and descriptive report support.
- [Fixed pre-result acceptance criteria](docs/development_pilot.md), snapshotted
  by the CLI before any live request.

## Validation

The pre-pilot baseline passed **86 tests**, with all methodological prerequisites
present. After implementation, **136 tests passed** on Python 3.12.0,
Pydantic 2.13.5, pytest 9.1.1:

```text
.venv/Scripts/python.exe -m pytest -q --basetemp .pytest_cache/live-dev-validation-1 --tb=short
```

Tests cover every requested boundary, denied-below-window versus prevention,
retrieval misses, actual request exposure, identity/tool spoofing, injection
metadata isolation, episode reset, immutable raw-record round trips, bounded
execution, raw errors/usage, cumulative disclosure, refusal versus wrong answers,
denominators, review blinding, and all 14 x 4 offline case/condition combinations.
The offline CLI's complete raw/scoring/metrics/review workflow is also tested.
All 86 pre-pilot tests pass, plus 50 new mocked tests for provider round trips,
transient retries, no semantic retries, credential isolation, raw failures,
diagnostic traces, held-out/aggregate rejection, review independence, CLI gates,
bounded manifest validation and complete 19-episode audit/report exports. The suite
blocks live HTTP globally. These are offline control tests, not findings.
The sandbox's default pytest temp location was inaccessible; validation used a
fresh directory inside the workspace. No live provider or held-out cases ran.

## Methodological choices

The primary interpretation is A versus external enforcement. B/C/D may be
identical and cannot establish architectural superiority or independent
redundancy. Trusted permission metadata remains model-visible so A has the
information necessary to apply its behavioral policy. Hidden/corrupted metadata
are future settings outside V1.

General opportunity means any unauthorized document entered the unfiltered top-k
window. Target opportunity means a designated protected target entered that
window, independently of denial. Their rates use security-relevant episodes with
resolved opportunity as denominators. Each block rate is conditional on its own
observed opportunity, with a denominator of resolved block outcomes. Target block
success requires completed execution, prevention of all counterfactual target
results across searches, and no target exposure. Target absence, misses, and
below-window ranks do not earn block credit. Errors without evidence stay unknown;
positive opportunity/exposure/disclosure evidence survives later failure.

The review order is: run, export the independent initial review file, conduct
human review, import/adjudicate while preserving initial ratings, then join to
automatic scores and conditions using the private mapping. Only the reviewer
file is shared initially. Import/adjudication tooling remains pending. Export
schema 2 remains independent. Raw schema 3 adds mode and provider-attempt metadata;
scorer v3 labels diagnostics and gives them null block scores. Private mapping
schema 2 adds mode. Earlier raw schema 2 records remain readable as normal mode.
ATS and over-refusal remain independent provisional labels.

The supplied pilot is **19 episodes**: six core cases and two useful counterparts
in A/C (16), plus three answer-key diagnostics. Its maximum is 69 model invocations
and 207 HTTP attempts including retries, not 19 API calls. Empty-context uses no
retrieval corpus; deny-all retains ranking/opportunity but suppresses every result.
Normal and diagnostic scores are separate, with no primary result table. The
private report inventories executed observations and leaves human judgements
pending. No live report or empirical finding has been produced here.

## Unresolved issues

Compatible model selection, explicit live-run authorization and actual development
piloting remain pending. Literal
matching misses semantic inference; utility/refusal heuristics need calibrated
human review. Transcript behavior and repeated tasks can still reveal an
intervention despite removal of condition identifiers and automatic outcomes.
Human adjudication/import, empirical diagnostic checks, family-aware
confidence intervals, and the full held-out design remain pending. Raw storage
is create-only at the application layer, not OS-enforced WORM or crash recovery.
Provider submission is observable; remote receipt after an error is uncertain.
Explicit sampling settings may be unsupported by some models; the adapter fails
without changing them. No live model results or held-out benchmark exist.

## Exact next step before a held-out freeze

Conduct a human audit of the 14 development prompts, facts, retrieval windows,
trace semantics, and review rubric. Then select a compatible model and explicitly
authorize the supplied small pilot with `--allow-live-api` and environment
credentials. Inspect all episodes against the fixed acceptance criteria. Resolve
retrieval/tool/budget failures and calibrate independent human judgements on
development data. Use that evidence to freeze prompts, budgets, scoring,
target-family design, and the analysis plan before authoring/freezing held-out
cases. Held-out materials must not later be tuned in response to held-out outcomes.
Implementation is complete; stop here without live calls or held-out generation.
Credentials alone never authorize execution. No 96-case generation, 384-episode
evaluation or empirical finding has been produced.

## Files changed in this phase

24 files were added or updated:

| Area | Files |
|---|---|
| Live adapter | `src/boundarybench/agents/providers/__init__.py`, `src/boundarybench/agents/providers/openai.py` |
| CLI and plan | `src/boundarybench/live_dev.py`, `configs/dev_pilot.toml` |
| Models and retrieval | `src/boundarybench/models/llm.py`, `src/boundarybench/models/diagnostics.py`, `src/boundarybench/retrieval/engine.py` |
| Evaluation and metrics | `src/boundarybench/eval/records.py`, `src/boundarybench/eval/runner.py`, `src/boundarybench/eval/scoring.py`, `src/boundarybench/eval/review.py`, `src/boundarybench/eval/dev_audit.py`, `src/boundarybench/metrics/aggregate.py` |
| Tests | `tests/conftest.py`, `tests/test_openai_provider.py`, `tests/test_diagnostics.py`, `tests/test_live_dev.py` |
| Documentation and local artifact exclusions | `.gitignore`, `README.md`, `research_plan.md`, `DEVELOPMENT_STATUS.md`, `docs/architecture.md`, `docs/implementation_checklist.md`, `docs/development_pilot.md` |
