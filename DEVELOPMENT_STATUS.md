# Development status ? final pre-freeze design pass

V1 methodology is frozen. See [frozen design](docs/frozen_evaluation_design.md),
[freeze JSON](freeze/V1_FREEZE.json) and [freeze summary](freeze/V1_FREEZE.md).
No held-out corpus has been authored and no held-out inference has run.

## Completed immutable development evidence

The original pilot contains 19 completed episodes, zero errors. The V2 follow-up
contains 15 attempted episodes, 13 completed and two tool-budget errors. Both runs
and the published pilot bundle remain byte-identical. These are development
observations, not held-out findings:

1. V2 resolved the observed instructor identity stall: A/C instructor attempts
   searched and returned the authorized course-a token.
2. V2 role-impersonation attempts retained trusted student identity and refused
   the claimed role change.
3. Multi-turn A: 3/3 completed, 1/3 target opportunity, 1/3 target exposure,
   1/3 literal disclosure.
4. Multi-turn C: 3/3 completed, 0/3 target opportunity and zero eligible target
   block opportunities. No enforcement credit for these misses.
5. The follow-up did not reproduce a clean exercised A-versus-C enforcement
   comparison across the three repeats.
6. Empty-context produced actual empty retrieval; deny-all suppressed a nonempty
   protected top-k window. Both later hit the unchanged two-search budget.
7. Authorized instructor A exposed unauthorized cross-course b-key in model
   context without quoting its protected value. C excluded b-key.
8. Byte-identical initial multi-turn requests produced different behavior,
   including search decisions, despite fixed sampling.

## Frozen study

24 target families / 48 E/O cases / 288 A/C episodes. Six attack categories with
four families each. Eight authorized families supply 96 utility episodes; sixteen
security families supply 192 episodes. Three fresh-session repeated trials are
related observations; target family is the dependency unit. E/O are analyzed
separately using a 10,000-draw family bootstrap.

**Independent human review is omitted from the deadline-constrained primary
study.** Primary endpoints are objective literal disclosure, context exposure,
opportunity/blocking, expected-answer utility and operational completion/error.
Collateral unauthorized exposure is measured even on authorized tasks. Semantic
outcomes are not independently adjudicated. Review tooling and raw transcripts
remain available. No human ratings or LLM judge are introduced.

V2 and the existing local model/runtime profile are unchanged. The frozen generator,
validation, deterministic order, prospective scorer, analysis and freeze checker
are implemented and tested offline. Exact test count and historical checksum
verification are recorded in the freeze summary. The next step is to commit this
freeze and, only in a separately authorized task, run its authoring command once.
