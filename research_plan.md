# BoundaryBench Research Plan

## Question and hypotheses

With identity, policy, model, and retrieval workflow held constant, how does external authorization enforcement affect protected-fact disclosure and authorized task completion? External enforcement is expected to reduce unauthorized disclosure and context exposure relative to A, but ties and reversals remain reportable. Enforcement may change authorized success and over-refusal in either direction. B, C, and D may be identical when they protect the same access path; this pilot cannot establish the value of redundancy.

The pilot uses one model, 96 held-out scenarios, four conditions, and one pass: 384 episodes. It separates knowledge from disclosure, exposure from disclosure, retrieval failure from protection, injection success from legitimate utility, and correlated target families from episode counts. Shared policy code means D is not an independent fault domain.

## Conditions and measurement

All conditions use the same system policy. A is prompt-only, B filters before retrieval, C authorizes at the tool boundary after ranking, and D applies both. The primary metrics are unauthorized disclosure rate, authorized task success, over-refusal, and retrieval boundary violation, with explicit denominators and not-applicable cells.

Synthetic facts are corpus-specific and evaluator-only. Retrieval traces preserve candidate rankings, decisions, removed documents, target availability, and exact model-visible responses. Scoring combines exact matching with condition-blind human review, including cumulative and quoted disclosures. Operational errors remain errors.

## Limits and extensions

The pilot is limited by one model, one access path, fixed synthetic attacks, few independent families, and one pass. Zero observations do not establish security or equivalence. Later phases may add repetitions, models, alternate paths, adaptive attacks, metadata faults, and enforcement-layer faults without changing this initial question.
