# Architecture

Trusted Pydantic schemas represent users, documents, and evaluation cases. `authorize` is the single policy function. `rank` has no user input and returns stable lexical scores with document-ID tie breaking. `RetrievalHarness` applies A-D enforcement and emits immutable `SearchTrace` records. `OfflineReplay` groups search traces by case and authenticated user without calling an LLM.

Future execution should keep separate immutable logs for candidate rankings, authorization decisions, exact model-visible messages, assistant outputs, and scoring. Run manifests should record provider, model identifier, supported sampling settings, seeds, timestamps, dependency versions, and hashes of configuration, corpus, policy, and prompts. A provider-independent message/tool interface is intentionally not implemented yet.
