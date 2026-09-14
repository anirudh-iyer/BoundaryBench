import json
from pathlib import Path

import pytest

from boundarybench import live_dev
from boundarybench.agents.providers import ollama
from boundarybench.agents.providers.openai import HTTPResponse, OpenAIConfig, wire_request
from boundarybench.agents.providers.ollama import OllamaProvider, discover_local_model
from boundarybench.models.llm import Message, ModelRequest, ToolCall
from boundarybench.tools.search import SEARCH_TOOL


SNAPSHOT = {"runtime": {"version": "0.13.5"}, "model_tag": {"name": "local:dev", "digest": "test-digest"},
            "model_info": {"parameters": "num_ctx 8192\n", "capabilities": ["completion", "tools"],
                           "template": "test upstream template"}, "context_tokens": 8192}
MANIFEST = Path(__file__).resolve().parents[1] / "configs" / "dev_pilot_local.toml"


def test_local_mapping_preserves_prompt_tools_and_tool_results_without_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-forwarded")
    request = ModelRequest(messages=(Message(role="system", content="Original policy"), Message(role="user", content="Task"),
        Message(role="assistant", tool_calls=(ToolCall(call_id="call-1", name="search", arguments_json='{"query":"greeting"}'),)),
        Message(role="tool", tool_call_id="call-1", content="Original tool result")), tools=(SEARCH_TOOL,))
    seen = []
    def transport(payload, key, timeout):
        seen.append((json.loads(payload), key, timeout))
        return HTTPResponse(200, json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "salut"}}], "usage": {"prompt_tokens": 40, "completion_tokens": 2}}), {})
    config = OpenAIConfig(model="local:dev", seed=17)
    provider = OllamaProvider(config, runtime_snapshot=SNAPSHOT, transport=transport)
    response = provider.new_session().complete(request)
    payload, key, timeout = seen[0]
    original = json.loads(wire_request(request, config))
    assert payload["messages"] == original["messages"] and payload["tools"] == original["tools"]
    assert payload["max_tokens"] == original["max_completion_tokens"] == 2048
    assert all(field not in payload for field in ("max_completion_tokens", "store", "n", "tool_choice"))
    assert key == "" and timeout == 30
    assert response.message.content == "salut" and response.usage.input_tokens == 40
    assert json.loads(response.provider_request_json) == payload
    metadata = provider.metadata
    assert metadata.provider == "ollama" and metadata.offline is False
    assert json.loads(metadata.configuration_json)["runtime_snapshot"]["model_tag"]["digest"] == "test-digest"
    assert "must-not-be-forwarded" not in metadata.model_dump_json() + response.model_dump_json()


def test_local_http_disables_proxy_redirect_and_authorization(monkeypatch):
    seen = []
    class Response:
        code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{}'
    class Opener:
        def open(self, request, timeout):
            seen.append(request)
            assert request.full_url == "http://127.0.0.1:11434/v1/chat/completions"
            assert request.get_header("Authorization") is None
            return Response()
    def build(proxy, redirects):
        assert proxy.proxies == {}
        assert redirects.redirect_request(None, None, 302, "", {}, "https://example.invalid") is None
        return Opener()
    monkeypatch.setattr(ollama, "build_opener", build)
    ollama.local_transport(b'{}', "ignored", 30)
    assert len(seen) == 1
    with pytest.raises(ValueError):
        ollama.local_http("https://example.invalid/", None, 30)


@pytest.mark.parametrize("problem", [None, "missing", "cloud", "no-tools", "no-context"])
def test_model_preflight_pins_installed_runtime_and_rejects_invalid_models(monkeypatch, problem):
    info = dict(SNAPSHOT["model_info"])
    if problem == "cloud": info["remote_host"] = "https://ollama.com"
    if problem == "no-tools": info["capabilities"] = ["completion"]
    if problem == "no-context": info["parameters"] = ""
    data = {"/api/version": SNAPSHOT["runtime"], "/api/tags": {"models": [] if problem == "missing" else [SNAPSHOT["model_tag"]]},
            "/api/show": info}
    def http(path, body, timeout):
        assert path != "/v1/chat/completions"
        return HTTPResponse(200, json.dumps(data[path]), {})
    monkeypatch.setattr(ollama, "local_http", http)
    if problem:
        with pytest.raises(ValueError): discover_local_model("local:dev")
    else:
        assert discover_local_model("local:dev") == SNAPSHOT


@pytest.mark.parametrize("provider,flag", [("ollama", None), ("ollama", "--allow-live-api"), ("openai", "--allow-local-model")])
def test_local_and_remote_execution_gates_are_separate(tmp_path, monkeypatch, provider, flag):
    def forbidden(*args, **kwargs): pytest.fail("neither discovery nor inference is authorized")
    monkeypatch.setattr(live_dev, "discover_local_model", forbidden)
    monkeypatch.setattr(live_dev, "OpenAIProvider", forbidden)
    monkeypatch.setattr(live_dev, "OllamaProvider", forbidden)
    arguments = ["--provider", provider, "--model", "local:dev", "--manifest", str(MANIFEST), "--output", str(tmp_path / "run")]
    assert live_dev.main(arguments + ([flag] if flag else [])) == 2
    assert not (tmp_path / "run").exists()


def test_full_local_cli_uses_snapshot_and_no_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(live_dev, "discover_local_model", lambda model: SNAPSHOT)
    requests = []
    def transport(payload, key, timeout):
        requests.append(json.loads(payload))
        assert key == "" and timeout == 120
        return HTTPResponse(200, json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "No model finding: mocked local response."}}]}), {})
    monkeypatch.setattr(live_dev, "OllamaProvider", lambda config, runtime_snapshot: OllamaProvider(
        config, runtime_snapshot=runtime_snapshot, transport=transport))
    output = tmp_path / "local"
    assert live_dev.main(["--provider", "ollama", "--model", "local:dev", "--manifest", str(MANIFEST),
                          "--output", str(output), "--allow-local-model"]) == 0
    manifest = json.loads((output / "run_manifest.jsonl").read_text(encoding="utf-8"))
    assert manifest["allow_local_model"] is True and manifest["allow_live_api"] is False
    assert manifest["provider"]["provider"] == "ollama" and manifest["planned_episode_count"] == 19
    assert manifest["max_http_attempts"] == 69
    assert len(requests) == 23 and len(list((output / "raw").glob("*.jsonl"))) == 19
