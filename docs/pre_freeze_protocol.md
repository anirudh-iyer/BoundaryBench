# Final pre-freeze protocol ? decisions recorded

The final design pass is complete; [frozen_evaluation_design.md](frozen_evaluation_design.md)
and [V1_FREEZE.json](../freeze/V1_FREEZE.json) govern future authoring and execution.
The earlier prerequisite for independent human review is explicitly superseded
by the user's deadline constraint: review is omitted from the primary study,
semantic outcomes remain not independently adjudicated, and objective endpoints
are primary. This is a methodological limitation, not a claim of semantic validation.
Review tooling remains intact for possible later use.

Both development runs are immutable. No new development experiments, model runs,
held-out facts/cases or human ratings are created during this task. V2 is final;
no attack-specific wording or V3 is introduced.

## Frozen decisions

- A/C only; separate end-to-end and opportunity-controlled strata.
- 24 families, 48 cases, 288 episodes; six categories times four families.
- Eight authorized families, 16 security families; exact allocation in the design.
- Three fresh-session repeated trials with seed 17; no independent-sample claim.
- Ollama 0.13.5, existing Qwen2.5 7B Instruct Q4_K_M model/digest; no upgrades.
- Top-k 3; two searches and three model invocations per turn; three turns maximum.
- Predetermined controlled query contains no fact and must retrieve target before inference.
- All-task collateral unauthorized exposure and objective literal/exposure/utility scoring.
- Unsupported negatives after errors unresolved; positives retained; no selective rerun.
- Family bootstrap: 10,000 draws; E/O separate; no episode-level iid analysis.
- Dedicated order seed 20260915; bootstrap seed 20260916; authoring seed 20260917.
- Hash and validate complete 288-entry shuffled order before inference.

## Completion gate

Run the complete offline suite. Verify all historical artifact bytes. Record exact
V2/source/config/retrieval/tool/scoring/authoring hashes and working-tree provenance.
Commit the freeze and implementation before separately authorized authoring.
No independent-human-review wait blocks objective evaluation. No inference occurs
if validation fails. Author once; retain all attempts and raw outputs. A bug before
authoring requires a new freeze version; a bug after authoring requires a documented
invalid-run decision, never a silent fix or replacement.
