"""Condition-blinded review files. Keep the blinding key away from reviewers."""

import hashlib
import hmac
from pathlib import Path

from boundarybench.eval.records import EpisodeRecord, write_jsonl_exclusive
from boundarybench.eval.scoring import score_episode


def export_human_review(records: tuple[EpisodeRecord, ...], path: Path, *, blinding_key: bytes) -> Path:
    if len(blinding_key) < 16:
        raise ValueError("use an independently stored blinding key of at least 16 bytes")

    def blind(value: str) -> str:
        return hmac.new(blinding_key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:16]

    rows = []
    for record in records:
        automatic = score_episode(record).model_dump(mode="json")
        # Raw IDs and filenames can be joined to conditions; use review-only IDs.
        automatic.pop("condition")
        automatic.pop("episode_id")
        case = record.case
        rows.append({
            "review_schema_version": "1", "review_id": blind(record.episode_id),
            "case_id": case.case_id, "blinded_condition": blind("condition:" + record.condition.value),
            "transcript": [message.model_dump(mode="json") for message in record.conversation],
            "scripted_user_turns": record.user_turns, "completed_user_turns": record.completed_user_turns,
            "operational_status": record.status,
            # Error text can leak condition names; full details remain in raw records.
            "operational_error_stages": [error.stage for error in record.operational_errors],
            "evaluator_only_expectation": {
                "protected_facts": sorted(case.evaluator_only_protected_facts),
                "protected_document_ids": sorted(case.expected_protected_document_ids),
                "authorized_task": case.authorized_task,
                "expected_answer": case.evaluator_only_expected_answer,
                "rubric": case.evaluator_only_rubric,
            },
            "automatic_score": automatic,
            "human_disclosure_judgement": None, "human_utility_judgement": None,
            "human_over_refusal_judgement": None, "reviewer_notes": "",
        })
    # Do not preserve an A/B/C/D input ordering in the review queue.
    rows.sort(key=lambda row: row["review_id"])
    return write_jsonl_exclusive(path, rows)
