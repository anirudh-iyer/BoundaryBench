import json

import pytest

from boundarybench.eval.__main__ import main


def test_offline_cli_writes_separate_raw_scores_metrics_and_review(tmp_path, monkeypatch, capsys):
    output = tmp_path / "offline-smoke"
    monkeypatch.setattr("sys.argv", ["boundarybench.eval", "--output", str(output)])
    main()
    assert "56 offline fixture episodes" in capsys.readouterr().out
    assert len(list((output / "raw").glob("*.jsonl"))) == 56
    assert len((output / "automatic_scores.jsonl").read_text(encoding="utf-8").splitlines()) == 56
    assert len((output / "human_review.jsonl").read_text(encoding="utf-8").splitlines()) == 56
    review = [json.loads(line) for line in (output / "human_review.jsonl").read_text(encoding="utf-8").splitlines()]
    mapping = [json.loads(line) for line in (output / "private_review_mapping.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(mapping) == 56
    assert {row["review_id"] for row in review} == {row["review_id"] for row in mapping}
    assert all("condition" not in row and "blinded_condition" not in row and "automatic_score" not in row for row in review)
    assert {row["condition"] for row in mapping} == {"A", "B", "C", "D"}
    metrics = json.loads((output / "offline_metrics.jsonl").read_text(encoding="utf-8"))
    assert "not model research results" in metrics["label"]
    assert set(metrics["by_condition"]) == {"A", "B", "C", "D"}
    assert all("target_retrieval_opportunity_rate" in cell and "target_authorization_block_rate" in cell for cell in metrics["by_condition"].values())
    with pytest.raises(FileExistsError):
        main()
