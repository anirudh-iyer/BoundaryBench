"""Validate and preserve independent human ratings before a separate private join."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Literal

from pydantic import Field, StrictStr

from boundarybench.eval.records import canonical_json, write_jsonl_exclusive
from boundarybench.eval.runner import now
from boundarybench.eval.scoring import AutomaticScore
from boundarybench.models.diagnostics import DiagnosticMode
from boundarybench.models.llm import FrozenModel, Message
from boundarybench.retrieval.engine import Condition


class HumanJudgements(FrozenModel):
    human_disclosure_judgement: Literal["disclosed", "not_disclosed", "uncertain"]
    human_utility_judgement: Literal["success", "failure", "uncertain", "not_applicable"]
    human_over_refusal_judgement: Literal["yes", "no", "uncertain", "not_applicable"]
    reviewer_notes: StrictStr


HUMAN_FIELDS = frozenset(HumanJudgements.model_fields)


class ReviewExpectation(FrozenModel):
    protected_facts: tuple[str, ...]
    protected_document_ids: tuple[str, ...]
    authorized_task: bool
    expected_answer: tuple[str, ...]
    rubric: str


class IndependentReviewRow(FrozenModel):
    # The original pilot's blank schema is deliberately still accepted.
    review_schema_version: Literal["2"]
    review_id: str = Field(min_length=1)
    case_id: str
    transcript: tuple[Message, ...]
    scripted_user_turns: tuple[str, ...]
    completed_user_turns: int
    operational_status: Literal["completed", "error"]
    evaluator_only_expectation: ReviewExpectation
    human_disclosure_judgement: str | None
    human_utility_judgement: str | None
    human_over_refusal_judgement: str | None
    reviewer_notes: StrictStr


class PrivateMappingRow(FrozenModel):
    mapping_schema_version: Literal["2"]
    review_id: str
    episode_id: str
    condition: Condition
    diagnostic_mode: DiagnosticMode = DiagnosticMode.NORMAL
    automatic_score: AutomaticScore
    prompt_version: Literal["v1", "v2"] = "v1"
    replicate_id: str | None = None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def read_rows(payload: bytes) -> dict[str, dict]:
    rows = {}
    for line in payload.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line, object_pairs_hook=_unique_object)
        if not isinstance(row, dict) or not isinstance(row.get("review_id"), str) or not row["review_id"]:
            raise ValueError("each row requires a nonempty review_id")
        if row["review_id"] in rows:
            raise ValueError("duplicate review_id")
        rows[row["review_id"]] = row
    if not rows:
        raise ValueError("review files must not be empty")
    return rows


def import_review(blank_path: Path, reviewer_path: Path, mapping_path: Path,
                  output: Path, *, reviewer_id: str) -> tuple[Path, Path]:
    """No edits to inputs; validate everything before creating either output.

    Immutable fields use canonical structural equality, including exact string
    content. Row ordering and JSON whitespace may differ. Preserve original
    judgement strings without adjudication, conversion or automatic inference.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", reviewer_id):
        raise ValueError("reviewer identifier must be 1-128 letters/digits or _.@-")
    paths = (blank_path, reviewer_path, mapping_path)
    if len({p.resolve() for p in paths}) != 3:
        raise ValueError("blank, completed review and private mapping must be separate files")
    if output.exists():
        raise FileExistsError(output)
    # Read bytes once, so the validated content and provenance refer to the same snapshot.
    blank_bytes, reviewer_bytes, mapping_bytes = (p.read_bytes() for p in paths)
    blank, reviewed, mapping = (read_rows(data) for data in (blank_bytes, reviewer_bytes, mapping_bytes))
    if blank.keys() != reviewed.keys() or blank.keys() != mapping.keys():
        raise ValueError("review_id sets must be identical; missing/extra rows are forbidden")
    episode_ids = set()
    validated_mappings = {}
    for review_id, original in blank.items():
        IndependentReviewRow.model_validate(original)
        completed = reviewed[review_id]
        IndependentReviewRow.model_validate(completed)
        if set(original) != set(IndependentReviewRow.model_fields) or set(completed) != set(original):
            raise ValueError("review fields must exactly match the blank schema")
        if any(original[k] is not None for k in HUMAN_FIELDS - {"reviewer_notes"}) or original["reviewer_notes"] != "":
            raise ValueError("original review must be blank")
        fixed = lambda row: {k: v for k, v in row.items() if k not in HUMAN_FIELDS}
        if canonical_json(fixed(original)) != canonical_json(fixed(completed)):
            raise ValueError("immutable review content changed: " + review_id)
        judgements = HumanJudgements.model_validate({k: completed[k] for k in HUMAN_FIELDS})
        # Reject explicit label/score annotations in free-text notes as well as extra fields.
        if re.search(r"\bcondition\s*[:=]?\s*[ABCD]\b|\b(?:automatic|auto)[ _-]?scores?\b|\bdiagnostic[ _-]?mode\b",
                     judgements.reviewer_notes, re.IGNORECASE):
            raise ValueError("condition/automatic-score annotations cannot enter independent review notes")
        joined = PrivateMappingRow.model_validate(mapping[review_id])
        score = joined.automatic_score
        if (score.episode_id != joined.episode_id or score.case_id != original["case_id"]
                or score.condition != joined.condition or score.diagnostic_mode != joined.diagnostic_mode):
            raise ValueError("private mapping disagrees with automatic score or review case")
        if joined.episode_id in episode_ids:
            raise ValueError("duplicate episode in private mapping")
        episode_ids.add(joined.episode_id)
        validated_mappings[review_id] = mapping[review_id]
    provenance = {
        "import_schema_version": "1", "reviewer_identifier": reviewer_id, "imported_at": now(),
        "original_blank_sha256": hashlib.sha256(blank_bytes).hexdigest(),
        "reviewer_file_sha256": hashlib.sha256(reviewer_bytes).hexdigest(),
        "private_mapping_sha256": hashlib.sha256(mapping_bytes).hexdigest(),
    }
    preserved = [{**row, "import_provenance": provenance} for row in reviewed.values()]
    private = [{**row, "private_join": validated_mappings[row["review_id"]]} for row in preserved]
    output.mkdir(parents=True, exist_ok=False)
    preserved_path = output / "preserved_review_ratings.jsonl"
    joined_path = output / "private_joined_review.jsonl"
    # Preserve ratings first; a failed preservation write must never create the join.
    write_jsonl_exclusive(preserved_path, preserved)
    write_jsonl_exclusive(joined_path, private)
    return preserved_path, joined_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blank", type=Path, required=True)
    parser.add_argument("--reviewed", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        paths = import_review(args.blank, args.reviewed, args.mapping, args.output, reviewer_id=args.reviewer_id)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Review import stopped: {exc}\n")
    print("Preserved independent ratings: " + str(paths[0]))
    print("PRIVATE joined ratings: " + str(paths[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
