"""PRIVATE development audit and descriptive report; initial review stays separate."""

from pathlib import Path

from boundarybench.eval.records import EpisodeRecord, canonical_json, write_jsonl_exclusive
from boundarybench.eval.scoring import score_episode
from boundarybench.models.diagnostics import DiagnosticMode


def audit_row(record: EpisodeRecord) -> dict:
    score = score_episode(record)
    return {
        "development_only": True, "private": True, "episode_id": record.episode_id,
        "case_id": record.case.case_id, "condition": record.condition,
        "prompt_version": record.prompt_version, "replicate_id": record.replicate_id,
        "diagnostic_mode": record.diagnostic_mode, "authenticated_user": record.authenticated_user,
        "scripted_user_turns": record.user_turns, "completed_user_turns": record.completed_user_turns,
        "status": record.status, "protected_targets_in_corpus": record.protected_targets_in_corpus,
        "protected_targets_missing_from_corpus": record.protected_targets_missing_from_corpus,
        # Full search traces include ranking/window, every authorization decision,
        # returned bodies, suppressed IDs, submitted IDs and request indices.
        "searches": record.searches, "assistant_outputs": record.assistant_responses,
        "target_opportunity": score.target_retrieval_opportunity,
        "target_exposure": sorted({target.document_id for event in record.searches
                                   for target in event.trace.protected_targets if target.content_in_model_context}),
        "automatic_score": score, "operational_errors": record.operational_errors,
        "raw_trace": f"../raw/{record.episode_id}.jsonl", "human_review_status": "pending",
    }


def export_development_audit(records: tuple[EpisodeRecord, ...], path: Path) -> Path:
    return write_jsonl_exclusive(path, [audit_row(record) for record in records])


def export_development_report(records: tuple[EpisodeRecord, ...], manifest: dict, path: Path) -> Path:
    """Generate only from attempted episodes, never fabricate human judgements.

    This descriptive inventory is for the private auditor. Human acceptance and
    semantic scoring remain pending; the report never declares a pilot passed.
    """
    errors = sum(record.status == "error" for record in records)
    lines = ["# Development pilot report", "", "DEVELOPMENT RUN — NOT HELD-OUT RESEARCH RESULTS",
             "", "PRIVATE: contains conditions and provisional automatic scores. Human review is pending.",
             "", "## Exact provider and configuration", "", "```json",
             canonical_json({"provider": manifest["provider"], "configuration": manifest["resolved_configuration"],
                             "acceptance_criteria_hash": manifest["acceptance_criteria_hash"]}), "```",
             "", f"Planned: {manifest['planned_episode_count']}; attempted: {len(records)}; "
             f"completed: {len(records) - errors}; error episodes: {errors}.",
             "", "Normal episodes and DEVELOPMENT ONLY diagnostics below are separate observations.",
             "No A/B/C/D aggregate result table is generated.", "", "## Per-case observations", ""]
    for record in records:
        score = score_episode(record)
        exposed = sorted({target.document_id for search in record.searches
                          for target in search.trace.protected_targets if target.content_in_model_context})
        lines.extend([
            f"### {record.case.case_id} / {record.condition.value} / {record.diagnostic_mode.value}", "",
            f"Episode `{record.episode_id}`: {record.status}; turns {record.completed_user_turns}/{len(record.user_turns)}; "
            f"requests {len(record.invocations)}; searches {len(record.searches)}.",
            f"Target opportunity: {score.target_retrieval_opportunity}; target exposure: {canonical_json(exposed)}.",
            f"Automatic literal disclosure: {score.disclosure}; utility: {score.authorized_task_success}; "
            f"refusal heuristic: {score.over_refusal}.", "",
        ])
    lines.extend(["## Unexpected tool behavior and operational errors", ""])
    if not errors:
        lines.append("No recorded operational errors. Human inspection of tool choices and arguments is still required.")
    for record in records:
        for error in record.operational_errors:
            lines.append(f"- `{record.episode_id}`: stage {error.stage}, {error.error_type}; see raw error and request.")
    no_search = [r.episode_id for r in records if not r.searches]
    lines.extend(["", "Episodes without a search: " + canonical_json(no_search) + ".",
                  "", "## Retrieval failures and diagnostic controls", ""])
    for record in records:
        if not record.case.expected_protected_document_ids:
            continue
        score = score_episode(record)
        if score.target_retrieval_opportunity is not True:
            lines.append(f"- `{record.episode_id}` ({record.diagnostic_mode.value}): target opportunity "
                         f"{score.target_retrieval_opportunity}; missing from corpus "
                         f"{canonical_json(record.protected_targets_missing_from_corpus)}. "
                         "Inspect query/window traces; absence is not authorization block evidence.")
    for record in records:
        if record.diagnostic_mode in {DiagnosticMode.EMPTY_CONTEXT, DiagnosticMode.DENY_ALL}:
            facts = record.case.evaluator_only_protected_facts
            present = any(fact in invocation.request.model_dump_json() for invocation in record.invocations for fact in facts)
            lines.append(f"- `{record.episode_id}` {record.diagnostic_mode.value}: "
                         f"literal protected fact present in submitted inputs: {present}; "
                         f"automatic disclosure: {score_episode(record).disclosure}.")
    lines.extend(["", "## Disclosure examples (automatic literal evidence)", ""])
    disclosures = [r for r in records if score_episode(r).disclosure is True]
    if not disclosures:
        lines.append("No literal matches detected. Semantic or indirect disclosure remains unreviewed.")
    for record in disclosures:
        score = score_episode(record)
        lines.extend([f"Episode `{record.episode_id}`; facts {canonical_json(score.matched_protected_facts)}.",
                      "Assistant evidence (JSON quoted):", "",
                      canonical_json([record.assistant_responses[i].content for i in score.disclosure_assistant_response_indices]), ""])
    failures = [r.episode_id for r in records if score_episode(r).authorized_task_success is False
                or score_episode(r).over_refusal is True]
    lines.extend(["", "## Utility and over-refusal", "",
                  "Episodes flagged by provisional heuristics: " + canonical_json(failures) + ".",
                  "Errors have unresolved utility/refusal outcomes. Human task assessment is pending.",
                  "", "## Automatic versus human scoring", "",
                  "Human review has not been imported. No disagreements or agreements are asserted.",
                  "", "## Design weaknesses and proposed changes before held-out freeze", "",
                  "Literal matching can miss paraphrase, decomposition and inference. Refusal phrases can mislabel helpful answers.",
                  "Inspect every request, tool call, retrieval miss and diagnostic answer; record semantic human judgements independently.",
                  "Use the private audit to identify observed tool/protocol failures and useful-task failures above. "
                  "Human conclusions about their causes and specific prompt/rubric changes remain pending.",
                  "Calibrate scoring and the review/adjudication workflow on development cases; select supported model settings "
                  "and confirm the fixed acceptance criteria before freezing any held-out materials.",
                  "", "## What these results do NOT establish", "",
                  "These development observations do not establish statistical significance, security, generalization, "
                  "or superiority among B/C/D. The primary V1 comparison remains A versus external enforcement.",
                  "No held-out cases exist. This report does not authorize their creation or freeze.", ""])
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    return path
