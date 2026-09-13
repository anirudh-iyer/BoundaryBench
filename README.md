# BoundaryBench

BoundaryBench is a provider-free, synthetic harness for studying authorization enforcement around retrieval. This repository currently implements synthetic schemas, policy decisions, deterministic retrieval, conditions A-D, and offline trace capture. No external LLM calls or evaluation episodes are configured.

## Status

Phase 2 and the non-LLM portion of Phase 3 are implemented. The model provider, held-out benchmark, scoring pipeline, and experiment runner remain pending.

Run the tests with:

```text
pytest
```

## Layout

- `src/boundarybench/models`: trusted schemas
- `src/boundarybench/policy`: authorization and independent fixture types
- `src/boundarybench/retrieval`: lexical ranking and A-D conditions
- `src/boundarybench/replay.py`: provider-free episode trace container
- `data/synthetic`: small infrastructure fixtures only
- `tests`: policy, retrieval, trace, and session-isolation tests
