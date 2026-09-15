"""Synthetic reviewer inputs only: these tests do not rate actual model episodes."""

import hashlib
import json

import pytest

from boundarybench.eval.records import canonical_json
from boundarybench.eval.review import export_human_review
from boundarybench import review_import


def write_rows(path, rows):
    path.write_text("\n".join(canonical_json(row) for row in rows) + "\n", encoding="utf-8")


@pytest.fixture
def review_inputs(run_episode, tmp_path):
    blank = tmp_path / "blank.jsonl"
    mapping = tmp_path / "mapping.jsonl"
    reviewer = tmp_path / "reviewer.jsonl"
    records = (run_episode(), run_episode("dev-learning"))
    export_human_review(records, blank, private_mapping_path=mapping, blinding_key=b"synthetic-test-review-key")
    rows = [json.loads(line) for line in blank.read_text().splitlines()]
    for row in rows:
        row.update(human_disclosure_judgement="uncertain", human_utility_judgement="uncertain",
                   human_over_refusal_judgement="uncertain", reviewer_notes="Synthetic validation fixture only.\nNo actual human rating.")
    write_rows(reviewer, rows)
    return blank, reviewer, mapping, tmp_path / "imported"


@pytest.mark.parametrize("mutation", [
    "transcript", "expectation", "rubric", "case_id", "status", "scripted_turns", "missing", "extra", "duplicate",
    "condition", "automatic_score", "nested_condition", "condition_note", "score_note", "unknown_note_field",
    "boolean_judgement", "missing_judgement", "unknown_enum",
])
def test_rejects_tampering_before_any_output(review_inputs, mutation):
    blank, reviewer, mapping, output = review_inputs
    rows = [json.loads(line) for line in reviewer.read_text().splitlines()]
    row = rows[0]
    if mutation == "transcript":
        row["transcript"][-1]["content"] += " edited"
    elif mutation == "expectation":
        row["evaluator_only_expectation"]["expected_answer"] = ["tampered"]
    elif mutation == "rubric":
        row["evaluator_only_expectation"]["rubric"] += " tampered"
    elif mutation == "case_id":
        row["case_id"] = "changed-case"
    elif mutation == "status":
        row["operational_status"] = "error"
    elif mutation == "scripted_turns":
        row["scripted_user_turns"] = ["changed"]
    elif mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append({**row, "review_id": "extra-id"})
    elif mutation == "duplicate":
        rows.append(row)
    elif mutation in {"condition", "automatic_score", "unknown_note_field"}:
        row[mutation] = "injected"
    elif mutation == "nested_condition":
        row["evaluator_only_expectation"]["condition"] = "C"
    elif mutation == "condition_note":
        row["reviewer_notes"] = "Condition C: looks good"
    elif mutation == "score_note":
        row["reviewer_notes"] = "automatic_score says false"
    elif mutation == "boolean_judgement":
        row["human_disclosure_judgement"] = True
    elif mutation == "missing_judgement":
        row["human_disclosure_judgement"] = None
    else:
        row["human_disclosure_judgement"] = "probably safe"
    write_rows(reviewer, rows)
    snapshots = [p.read_bytes() for p in (blank, reviewer, mapping)]
    with pytest.raises(ValueError):
        review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    assert not output.exists()
    assert [p.read_bytes() for p in (blank, reviewer, mapping)] == snapshots


def test_preserves_exact_ratings_hashes_and_joins_only_after_preservation(review_inputs, monkeypatch):
    blank, reviewer, mapping, output = review_inputs
    original = [json.loads(line) for line in reviewer.read_text().splitlines()]
    # Reordering and JSON whitespace changes are allowed; string content is exact.
    reviewer.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in reversed(original)), encoding="utf-8")
    snapshots = [p.read_bytes() for p in (blank, reviewer, mapping)]
    real_write = review_import.write_jsonl_exclusive
    def write(path, rows):
        if path.name == "private_joined_review.jsonl":
            preserved = output / "preserved_review_ratings.jsonl"
            assert preserved.exists()
            for line in preserved.read_text().splitlines():
                independent = json.loads(line)
                assert not ({"condition", "automatic_score", "private_join", "episode_id", "replicate_id", "diagnostic_mode"} & independent.keys())
        return real_write(path, rows)
    monkeypatch.setattr(review_import, "write_jsonl_exclusive", write)
    preserved_path, joined_path = review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    preserved = [json.loads(line) for line in preserved_path.read_text().splitlines()]
    joined = [json.loads(line) for line in joined_path.read_text().splitlines()]
    private = {r["review_id"]: r for r in map(json.loads, mapping.read_text().splitlines())}
    for row, expected, joined_row in zip(preserved, reversed(original), joined):
        provenance = row.pop("import_provenance")
        assert row == expected
        assert provenance["reviewer_identifier"] == "synthetic-reviewer"
        assert provenance["reviewer_file_sha256"] == hashlib.sha256(snapshots[1]).hexdigest()
        assert provenance["original_blank_sha256"] == hashlib.sha256(snapshots[0]).hexdigest()
        assert provenance["private_mapping_sha256"] == hashlib.sha256(snapshots[2]).hexdigest()
        assert provenance["import_schema_version"] == "1" and provenance["imported_at"].endswith("+00:00")
        assert joined_row["private_join"] == private[row["review_id"]]
        assert all(joined_row[k] == expected[k] for k in review_import.HUMAN_FIELDS)
    assert [p.read_bytes() for p in (blank, reviewer, mapping)] == snapshots
    with pytest.raises(FileExistsError):
        review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")


@pytest.mark.parametrize("mutation", ["wrong_condition", "wrong_case", "missing_id", "duplicate_episode", "nonblank_original"])
def test_invalid_mapping_or_nonblank_original_rejected(review_inputs, mutation):
    blank, reviewer, mapping, output = review_inputs
    rows = [json.loads(line) for line in mapping.read_text().splitlines()]
    if mutation == "wrong_condition":
        rows[0]["condition"] = "D"
    elif mutation == "wrong_case":
        rows[0]["automatic_score"]["case_id"] = "wrong-case"
    elif mutation == "missing_id":
        rows.pop()
    elif mutation == "duplicate_episode":
        rows[1]["episode_id"] = rows[0]["episode_id"]
        rows[1]["automatic_score"]["episode_id"] = rows[0]["episode_id"]
    else:
        blank.write_bytes(reviewer.read_bytes())
    write_rows(mapping, rows)
    with pytest.raises(ValueError):
        review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    assert not output.exists()


def test_original_mapping_without_new_metadata_is_accepted(review_inputs):
    blank, reviewer, mapping, output = review_inputs
    rows = [json.loads(line) for line in mapping.read_text().splitlines()]
    for row in rows:
        row.pop("prompt_version")
        row.pop("replicate_id")
        row["automatic_score"].pop("primary_analysis_eligible")
        row["automatic_score"]["scorer_version"] = "exact-and-refusal-heuristic-v3"
    write_rows(mapping, rows)
    review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    assert (output / "private_joined_review.jsonl").exists()


def test_preservation_write_failure_never_creates_join(review_inputs, monkeypatch):
    blank, reviewer, mapping, output = review_inputs
    def fail(path, rows):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(review_import, "write_jsonl_exclusive", fail)
    with pytest.raises(OSError):
        review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    assert not (output / "private_joined_review.jsonl").exists()


def test_duplicate_json_key_is_rejected(review_inputs):
    blank, reviewer, mapping, output = review_inputs
    reviewer.write_text(reviewer.read_text().replace('"case_id":', '"case_id":"duplicate","case_id":', 1), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate JSON key"):
        review_import.import_review(blank, reviewer, mapping, output, reviewer_id="synthetic-reviewer")
    assert not output.exists()


def test_review_import_cli(review_inputs, capsys):
    blank, reviewer, mapping, output = review_inputs
    assert review_import.main(["--blank", str(blank), "--reviewed", str(reviewer), "--mapping", str(mapping),
                               "--output", str(output), "--reviewer-id", "synthetic-reviewer"]) == 0
    assert "PRIVATE joined ratings" in capsys.readouterr().out
