"""Local Ollama compatibility profile sharing the tested Chat Completions adapter.

Only literal loopback is used. No proxy, redirect, environment API key, hosted
fallback, automatic model pull, or prompt/tool-schema substitution is permitted.
"""

import json
import re
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from boundarybench.agents.providers.openai import (
    HTTPResponse, NoRedirects, OpenAIConfig, OpenAIProvider, OpenAISession, encode, wire_request,
)
from boundarybench.models.llm import ModelRequest, ProviderError, ProviderMetadata


LOCAL_BASE = "http://127.0.0.1:11434"


def local_http(path: str, body: bytes | None, timeout: float) -> HTTPResponse:
    if path not in {"/api/version", "/api/tags", "/api/show", "/v1/chat/completions"}:
        raise ValueError("unsupported local Ollama path")
    request = Request(LOCAL_BASE + path, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json",
        "User-Agent": "BoundaryBench-development/1",
    })
    try:
        response = build_opener(ProxyHandler({}), NoRedirects()).open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        return HTTPResponse(response.code, response.read().decode("utf-8", errors="replace"),
                            {key.lower(): value for key, value in response.headers.items()})


def local_transport(payload: bytes, unused_key: str, timeout: float) -> HTTPResponse:
    return local_http("/v1/chat/completions", payload, timeout)


def discover_local_model(model: str) -> dict:
    """Read-only runtime/model snapshot, after the local execution gate."""
    def read(path, value=None):
        result = local_http(path, encode(value).encode("utf-8") if value is not None else None, 10)
        if result.status != 200:
            raise ProviderError(f"Ollama preflight failed: HTTP {result.status}", raw_response=result.body)
        return json.loads(result.body)

    version = read("/api/version")
    tags = read("/api/tags")
    match = next((item for item in tags["models"] if item["name"] == model), None)
    if match is None:
        raise ValueError("requested model is not installed locally: " + model)
    info = read("/api/show", {"model": model})
    if model.endswith(":cloud") or info.get("remote_model") or info.get("remote_host"):
        raise ValueError("hosted Ollama models are not allowed in the local pilot")
    if "tools" not in info.get("capabilities", ()):
        raise ValueError("local model does not advertise tool calling")
    parameters = info.get("parameters", "")
    context = re.search(r"(?m)^num_ctx\s+(\d+)\s*$", parameters)
    if context is None or int(context.group(1)) < 8192:
        raise ValueError("local pilot requires an explicit model num_ctx of at least 8192")
    return {"runtime": version, "model_tag": match, "model_info": info,
            "context_tokens": int(context.group(1))}


class OllamaProvider(OpenAIProvider):
    name = "Ollama"

    def __init__(self, config: OpenAIConfig, *, runtime_snapshot: dict, transport=local_transport, **options):
        super().__init__(config, transport=transport, **options)
        self.runtime_snapshot_json = encode(runtime_snapshot)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider="ollama", model=self.config.model, adapter_version="ollama-chat-completions-v1", offline=False,
            configuration_json=encode({**self.config.model_dump(), "execution": "local",
                "endpoint": LOCAL_BASE + "/v1/chat/completions", "api_key_source": "none",
                "wire_token_limit_field": "max_tokens", "tool_choice": "runtime automatic",
                "runtime_snapshot": json.loads(self.runtime_snapshot_json)}),
            supported_sampling_settings=("temperature", "top_p", "seed"),
            sampling_settings_json=encode({"temperature": self.config.temperature, "top_p": self.config.top_p,
                                           "seed": self.config.seed}), seed=self.config.seed,
        )

    def request_json(self, request: ModelRequest) -> str:
        payload = json.loads(wire_request(request, self.config))
        payload["max_tokens"] = payload.pop("max_completion_tokens")
        # Ollama 0.13.5 does not accept these OpenAI controls. The non-streaming
        # endpoint returns one choice and uses automatic tool selection.
        for field in ("store", "n", "tool_choice"):
            payload.pop(field)
        return encode(payload)

    def new_session(self):
        return OpenAISession(self, "")
