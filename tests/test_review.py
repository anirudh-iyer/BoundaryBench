import json

import pytest

from boundarybench.agents.offline import response
from boundarybench.eval.review import export_human_review
from boundarybench.retrieval.engine import Condition


def test_initial_review_payload_does_not_depend_on_condition_or_automatic_score(run_episode, tmp_path):
    record = run_episode(steps=(response("I cannot provide that."),))
    # Hold the raw episode/transcript constant and change only its condition.
    # This would change the old condition pseudonym, but must not change review.
    contents = []
    for condition in Condition:
        path = tmp_path / f"review-{condition.value}.jsonl"
        export_human_review(
            (record.model_copy(update={"condition": condition}),), path,
            private_mapping_path=tmp_path / f"private-{condition.value}.jsonl", blinding_key=b"a-separate-review-key",
        )
        contents.append(path.read_bytes())
    assert len(set(contents)) == 1


def test_repeated_condition_has_individual_episode_ids_without_cluster_label(run_episode, tmp_path):
    records = tuple(run_episode(condition=Condition.B) for _ in range(3))
    path = tmp_path / "review.jsonl"
    export_human_review(records, path, private_mapping_path=tmp_path / "private.jsonl", blinding_key=b"a-separate-review-key")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len({row["review_id"] for row in rows}) == 3
    # With identical input/evidence there is no per-condition identifier other
    # than individual review IDs. A case ID groups tasks, not interventions.
    for row in rows:
        row.pop("review_id")
    assert rows[0] == rows[1] == rows[2]


def test_review_retains_expectations_and_status_without_private_error_evidence(run_episode, tmp_path):
    record = run_episode("dev-learning", steps=(RuntimeError("Condition B provider error detail"),))
    path = tmp_path / "review.jsonl"
    export_human_review((record,), path, private_mapping_path=tmp_path / "private.jsonl", blinding_key=b"a-separate-review-key")
    text = path.read_text(encoding="utf-8")
    row = json.loads(text)
    assert row["operational_status"] == "error"
    assert row["evaluator_only_expectation"]["expected_answer"] == ["salut"]
    assert row["evaluator_only_expectation"]["authorized_task"] is True
    assert "Condition B" not in text
    assert "operational_error_stages" not in row
    assert "automatic_score" not in row


@pytest.mark.parametrize("existing", ["review.jsonl", "private.jsonl"])
def test_review_export_refuses_existing_either_artifact_without_changing_it(run_episode, tmp_path, existing):
    path = tmp_path / existing
    path.write_text("original artifact", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_human_review(
            (run_episode(),), tmp_path / "review.jsonl", private_mapping_path=tmp_path / "private.jsonl",
            blinding_key=b"a-separate-review-key",
        )
    assert path.read_text(encoding="utf-8") == "original artifact"
    other = "private.jsonl" if existing == "review.jsonl" else "review.jsonl"
    assert not (tmp_path / other).exists()


def test_mapping_requires_distinct_path_and_unique_episodes(run_episode, tmp_path):
    record = run_episode()
    path = tmp_path / "review.jsonl"
    with pytest.raises(ValueError, match="separate paths"):
        export_human_review((record,), path, private_mapping_path=path, blinding_key=b"a-separate-review-key")
    with pytest.raises(ValueError, match="duplicate episode"):
        export_human_review((record, record), path, private_mapping_path=tmp_path / "private.jsonl", blinding_key=b"a-separate-review-key")
    assert not path.exists()
