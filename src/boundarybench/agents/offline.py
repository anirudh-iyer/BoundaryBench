"""Deterministic test doubles, not simulations of a model's security behavior."""

import hashlib
import json
from dataclasses import dataclass

from boundarybench.models.llm import (
    Message, ModelRequest, ModelResponse, ProviderMetadata, ToolCall,
)


def response(content: str = "", *, query: str | None = None, call_id: str = "search-1") -> ModelResponse:
    calls = () if query is None else (ToolCall(
        call_id=call_id, name="search", arguments_json=json.dumps({"query": query}),
    ),)
    message = Message(role="assistant", content=content, tool_calls=calls)
    return ModelResponse(
        message=message,
        raw_response=json.dumps({"offline_double": True, "message": message.model_dump(mode="json")}),
        finish_reason="tool_calls" if calls else "stop",
    )


@dataclass(frozen=True)
class OfflineProvider:
    # Scripted steps can deliberately disclose, refuse, spoof, loop, or fail.
    # None selects a simple search-then-echo fixture, with no policy reasoning.
    steps: tuple[ModelResponse | Exception, ...] | None = None

    @property
    def metadata(self) -> ProviderMetadata:
        script = None if self.steps is None else [
            step.model_dump(mode="json") if isinstance(step, ModelResponse) else {
                "exception_type": type(step).__name__, "message": str(step),
                "raw_response": getattr(step, "raw_response", None),
            }
            for step in self.steps
        ]
        return ProviderMetadata(
            provider="offline", model="scripted-v1" if self.steps is not None else "search-echo-v1",
            adapter_version="1", offline=True,
            configuration_json=json.dumps({
                "script_sha256": hashlib.sha256(json.dumps(script, sort_keys=True).encode("utf-8")).hexdigest(),
            }),
        )

    def new_session(self) -> "OfflineSession":
        return OfflineSession(self.steps)


class OfflineSession:
    def __init__(self, steps: tuple[ModelResponse | Exception, ...] | None):
        self.steps = steps
        self.index = 0

    def complete(self, request: ModelRequest) -> ModelResponse:
        index = self.index
        self.index += 1
        if self.steps is not None:
            if index >= len(self.steps):
                raise RuntimeError("offline script exhausted")
            step = self.steps[index]
            if isinstance(step, Exception):
                raise step
            return step
        last = request.messages[-1]
        if last.role == "user":
            return response(query=last.content, call_id=f"search-{index}")
        if last.role == "tool":
            return response(last.content or "No matching documents.")
        raise RuntimeError("offline search-echo expected a user or tool message")
