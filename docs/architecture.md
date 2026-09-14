# Architecture

Trusted frozen Pydantic schemas represent users, documents, and development
cases. `authorize` is the shared policy function; malformed or missing metadata
denies access. `rank` uses positive lexical overlap and stable document-ID ties.
B filters the corpus before ranking, C authorizes ranked candidates at the tool
boundary, and D does both. All conditions use the same model-visible JSON
serialization. B/C/D can produce identical content by design.

`SearchTrace` separates diagnostic denials across the full ranking from
counterfactual top-k opportunities and actual prevention. Only `EpisodeRunner`
marks a trace as submitted in a model request. Retrieval-only `OfflineReplay`
never marks model exposure. Returned documents, exposed documents, and assistant
disclosure are separate facts.

`ModelProvider` creates a session per case/condition; sessions consume immutable
`ModelRequest` messages/tool definitions and return `ModelResponse` with raw
response and optional usage. The offline provider can replay prescribed responses
and errors or perform deterministic search/echo. It contains no condition logic
or evaluator expectations. The OpenAI Chat Completions adapter maps the same
interface to HTTPS, sourcing its key only from the environment. It records exact
JSON request bodies, raw responses, usage, finish reasons and bounded transient
retry histories. Credentials and Authorization headers are never persisted.
The adapter contains no authorization logic and has no model/prompt fallback.

The local Ollama profile reuses request mapping, response parsing and attempt
recording. It maps the output budget to `max_tokens`, connects only to literal
loopback without proxy/redirect/credentials, and records the runtime version,
installed-model digest, parameters and upstream template. A separate local gate
cannot authorize paid calls. Its preflight requires installed weights, advertised
tool support and an explicit context of at least 8192 tokens; it never pulls a
model or falls back to a hosted endpoint during an episode.

The runner owns the user registry, body-only injection overrides, conversation,
tool budgets, and traces. `search` accepts only a query. Full request snapshots
show exactly what was submitted, including previous turns and tool calls.
Operational failures terminate the episode and preserve error details and
unreached scripted turns. No retries silently change the episode's treatment.
Provider metadata includes configuration, supported sampling settings, and seed
when applicable. Manifests hash corpus variants, cases, identity, prompts, tool
schema, policy, configuration, and implementation, and record dependency versions.

`live_dev` is a separate opt-in command, accepting only a small development
manifest. Without `--allow-live-api`, it prints the validated plan and makes no
requests. Before execution it snapshots the resolved plan and fixed acceptance
protocol. Normal scores, diagnostic scores, initial human review, private joins,
private per-episode audits and a descriptive private report are separate artifacts.
Only the reviewer artifact is initially shared.

Development modes are separate from `Condition`: no-policy substitutes a neutral
task prompt, empty-context supplies an empty corpus, and deny-all keeps unfiltered
traces but records universal result suppression without policy block credit.
The runner rejects diagnostic held-out cases. Raw schema 3 and scorer version 3
carry explicit modes; primary aggregate functions reject non-normal scores.

`RawRecordStore` uses exclusive-create JSONL shards and flushes them to disk.
It cannot provide OS-level immutable storage or recover a process killed before
the episode write; persistence failures propagate. Versioned automatic scores,
metrics, and blinded review exports are separate derived artifacts. Aggregation
keeps unknown errors outside resolved denominators and reports all-attempt
missing-outcome bounds. Human adjudication and family-aware inference remain
future work. See README and research_plan for exact endpoint semantics.
