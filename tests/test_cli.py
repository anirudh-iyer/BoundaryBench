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
    metrics = json.loads((output / "offline_metrics.jsonl").read_text(encoding="utf-8"))
    assert "not model research results" in metrics["label"]
    assert set(metrics["by_condition"]) == {"A", "B", "C", "D"}
    with pytest.raises(FileExistsError):
        main()
