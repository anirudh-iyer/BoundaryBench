"""Independent initial review and a separate private join for later analysis."""

import hashlib
import hmac
from pathlib import Path

from boundarybench.eval.records import EpisodeRecord, write_jsonl_exclusive
from boundarybench.eval.scoring import score_episode


def export_human_review(
    records: tuple[EpisodeRecord, ...], path: Path, *, private_mapping_path: Path, blinding_key: bytes,
) -> Path:
    """Export judgement inputs only; withhold the mapping until adjudication.

    Both files are create-only. The mapping is written first so a mapping-write
    failure cannot leave a reviewer file without its join. Writes are not a
    two-file transaction; persistence failures propagate for inspection.
    """
    if len(blinding_key) < 16:
        raise ValueError("use an independently stored blinding key of at least 16 bytes")
    if path.resolve() == private_mapping_path.resolve():
        raise ValueError("review and private mapping must use separate paths")
    for artifact in (path, private_mapping_path):
        if artifact.exists():
            raise FileExistsError(artifact)
    if len({record.episode_id for record in records}) != len(records):
        raise ValueError("duplicate episode cannot define a unique review mapping")

    def blind(value: str) -> str:
        return hmac.new(blinding_key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:32]

    rows = []
    private_rows = []
    for record in records:
        # This ID depends on the episode, never on a shared condition label.
        review_id = blind(record.episode_id)
        case = record.case
        rows.append({
            "review_schema_version": "2", "review_id": review_id,
            "case_id": case.case_id,
            "transcript": [message.model_dump(mode="json") for message in record.conversation],
            "scripted_user_turns": record.user_turns, "completed_user_turns": record.completed_user_turns,
            "operational_status": record.status,
            # Error stages/text and all derived scores stay out of initial review.
            "evaluator_only_expectation": {
                "protected_facts": sorted(case.evaluator_only_protected_facts),
                "protected_document_ids": sorted(case.expected_protected_document_ids),
                "authorized_task": case.authorized_task,
                "expected_answer": case.evaluator_only_expected_answer,
                "rubric": case.evaluator_only_rubric,
            },
            "human_disclosure_judgement": None, "human_utility_judgement": None,
            "human_over_refusal_judgement": None, "reviewer_notes": "",
        })
        private_rows.append({
            "mapping_schema_version": "2", "review_id": review_id,
            "episode_id": record.episode_id, "condition": record.condition.value,
            "diagnostic_mode": record.diagnostic_mode.value,
            "prompt_version": record.prompt_version, "replicate_id": record.replicate_id,
            "automatic_score": score_episode(record).model_dump(mode="json"),
        })
    # Do not preserve an A/B/C/D input ordering in the review queue.
    rows.sort(key=lambda row: row["review_id"])
    private_rows.sort(key=lambda row: row["review_id"])
    write_jsonl_exclusive(private_mapping_path, private_rows)
    return write_jsonl_exclusive(path, rows)
