import json
from pathlib import Path
import tomllib

import pytest

from boundarybench import live_dev
from boundarybench.agents.providers.openai import HTTPResponse, OpenAIProvider
from boundarybench.eval.records import EpisodeRecord
from boundarybench.metrics.aggregate import aggregate_by_condition
from boundarybench.models.diagnostics import DiagnosticMode
from boundarybench.eval.scoring import AutomaticScore


MANIFEST = Path(__file__).resolve().parents[1] / "configs" / "dev_pilot.toml"


def args(output, *, allow=False, manifest=MANIFEST):
    result = ["--provider", "openai", "--model", "mock-model", "--manifest", str(manifest), "--output", str(output)]
    return result + (["--allow-live-api"] if allow else [])


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("credentials", [False, True])
def test_no_flag_prints_plan_without_provider_or_artifacts(tmp_path, monkeypatch, capsys, credentials):
    if credentials:
        monkeypatch.setenv("OPENAI_API_KEY", "test-not-authorized")
    else:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def forbidden(*args):
        pytest.fail("provider must not even be constructed without the flag")
    monkeypatch.setattr(live_dev, "OpenAIProvider", forbidden)
    output = tmp_path / "no-live"
    assert live_dev.main(args(output)) == 2
    printed = capsys.readouterr().out
    assert live_dev.WARNING in printed and "Planned episodes: 19" in printed
    assert "69 model invocations" in printed and "207 HTTP attempts" in printed
    assert not output.exists()


def test_missing_credentials_and_existing_output_refuse_before_provider(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    def forbidden(*args):
        pytest.fail("provider should not be constructed")
    monkeypatch.setattr(live_dev, "OpenAIProvider", forbidden)
    output = tmp_path / "pilot"
    assert live_dev.main(args(output, allow=True)) == 2
    assert not output.exists()
    output.mkdir()
    marker = output / "original"
    marker.write_text("preserve me", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-authorized")
    assert live_dev.main(args(output, allow=True)) == 2
    assert list(output.iterdir()) == [marker] and marker.read_text() == "preserve me"


@pytest.mark.parametrize("mutation", [
    {"development_only": False}, {"conditions": ["A", "B", "C", "D"]},
    {"conditions": ["C", "D"]}, {"case_ids": ["dev-learning"] * 2},
    {"case_ids": ["dev-" + str(i) for i in range(9)]},
    {"provider_settings": {"api_key": "forbidden-config-key"}},
    {"diagnostics": [{"case_id": "dev-answer-key", "mode": "deny-all"}] * 3},
])
def test_manifest_rejects_scope_expansion_and_secret_configuration(mutation):
    manifest = tomllib.loads(MANIFEST.read_text(encoding="utf-8"))
    with pytest.raises(ValueError):
        live_dev.PilotManifest.model_validate({**manifest, **mutation})


def test_unknown_or_heldout_case_fails_before_provider(tmp_path, monkeypatch):
    source = MANIFEST.read_text(encoding="utf-8").replace('"dev-learning"', '"held-out-001"')
    manifest = tmp_path / "invalid.toml"
    manifest.write_text(source, encoding="utf-8")
    with pytest.raises(ValueError, match="known development"):
        live_dev.load_plan(manifest)


def install_mock_provider(monkeypatch, output, *, fail=False):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-key")
    requests = []

    def transport(payload, key, timeout):
        # The exact manifest/acceptance snapshot must exist before any request.
        assert (output / "run_manifest.jsonl").exists()
        request = json.loads(payload)
        requests.append(request)
        if fail:
            return HTTPResponse(401, '{"error":{"code":"invalid_api_key"}}', {})
        last = request["messages"][-1]
        if last["role"] == "user":
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call-{len(requests)}", "type": "function", "function": {
                    "name": "search", "arguments": json.dumps({"query": last["content"]}),
                }},
            ]}
            finish = "tool_calls"
        else:
            assert last["role"] == "tool"
            message = {"role": "assistant", "content": last["content"] or "No matching documents."}
            finish = "stop"
        return HTTPResponse(200, json.dumps({"model": "mock-snapshot", "choices": [
            {"message": message, "finish_reason": finish},
        ], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}), {"x-request-id": str(len(requests))})

    monkeypatch.setattr(live_dev, "OpenAIProvider", lambda config: OpenAIProvider(config, transport=transport))
    return requests


def test_mock_live_cli_complete_small_plan_and_independent_artifacts(tmp_path, monkeypatch, capsys):
    output = tmp_path / "mock-pilot"
    requests = install_mock_provider(monkeypatch, output)
    assert live_dev.main(args(output, allow=True)) == 0
    assert len(requests) == 46
    manifest = rows(output / "run_manifest.jsonl")[0]
    assert manifest["planned_episode_count"] == 19 and manifest["provider"]["model"] == "mock-model"
    assert "Acceptance criteria, fixed before results" in manifest["acceptance_criteria_source"]
    assert len(manifest["episodes"]) == 19 and len(manifest["selected_cases"]) == 8
    raw_paths = list((output / "raw").glob("*.jsonl"))
    records = [EpisodeRecord.model_validate_json(p.read_text(encoding="utf-8")) for p in raw_paths]
    assert len(records) == 19 and all(r.status == "completed" for r in records)
    scores = [AutomaticScore.model_validate(row) for row in rows(output / "auto_scores.jsonl")]
    diagnostics = [AutomaticScore.model_validate(row) for row in rows(output / "diagnostic_auto_scores.jsonl")]
    assert len(scores) == 16 and len(diagnostics) == 3
    assert all(s.diagnostic_mode == DiagnosticMode.NORMAL for s in scores)
    with pytest.raises(ValueError, match="DEVELOPMENT ONLY"):
        aggregate_by_condition(tuple(scores + diagnostics))
    review = rows(output / "human_review.jsonl")
    mapping = rows(output / "private" / "review_mapping.jsonl")
    audit = rows(output / "private" / "development_audit.jsonl")
    assert len(review) == len(mapping) == len(audit) == 19
    assert {r["review_id"] for r in review} == {r["review_id"] for r in mapping}
    assert all("condition" not in r and "diagnostic_mode" not in r and "automatic_score" not in r for r in review)
    assert all(r["human_disclosure_judgement"] is None for r in review)
    assert {r["condition"] for r in mapping} == {"A", "C"}
    assert all("target_exposure" in r and "operational_errors" in r and "searches" in r for r in audit)
    for row in audit:
        assert (output / "private" / row["raw_trace"]).resolve().exists()
    report = (output / "private" / "DEVELOPMENT_PILOT_REPORT.md").read_text(encoding="utf-8")
    assert "attempted: 19; completed: 19; error episodes: 0" in report
    assert "What these results do NOT establish" in report and "Human review is pending" in report
    assert all(f"{item['case_id']} / {item['condition']} / {item['diagnostic_mode']}" in report for item in manifest["episodes"])
    assert "No disagreements or agreements are asserted" in report
    assert not list(output.glob("*metrics*"))
    assert all("offline-test-key" not in p.read_text(encoding="utf-8") for p in output.rglob("*") if p.is_file())
    snapshots = {p: p.read_bytes() for p in output.rglob("*") if p.is_file()}
    assert live_dev.main(args(output, allow=True)) == 2
    assert all(p.read_bytes() == data for p, data in snapshots.items())
    assert len(requests) == 46


def test_mock_provider_errors_remain_errors_in_report_and_scores(tmp_path, monkeypatch):
    output = tmp_path / "mock-errors"
    requests = install_mock_provider(monkeypatch, output, fail=True)
    assert live_dev.main(args(output, allow=True)) == 1
    assert len(requests) == 19
    assert all(s["disclosure"] is None for s in rows(output / "auto_scores.jsonl"))
    report = (output / "private" / "DEVELOPMENT_PILOT_REPORT.md").read_text(encoding="utf-8")
    assert "attempted: 19; completed: 0; error episodes: 19" in report
    assert "Human review is pending" in report
