"""Provider-neutral wire records. No evaluator data or identity tool arguments."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolCall(FrozenModel):
    call_id: str = Field(min_length=1)
    name: str
    arguments_json: str


class Message(FrozenModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


class ToolDefinition(FrozenModel):
    name: str
    description: str
    parameters_json: str


class ProviderMetadata(FrozenModel):
    provider: str
    model: str
    adapter_version: str
    offline: bool
    configuration_json: str = "{}"
    supported_sampling_settings: tuple[str, ...] = ()
    sampling_settings_json: str = "{}"
    seed: int | None = None


class Usage(FrozenModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    # Preserve provider-specific counters as JSON without requiring a common schema.
    details_json: str | None = None


class ModelRequest(FrozenModel):
    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...]


class ProviderAttempt(FrozenModel):
    attempt: int = Field(ge=1)
    status_code: int | None = None
    request_id: str | None = None
    error_type: str | None = None
    raw_response: str | None = None
    retry_delay_seconds: float | None = None


class ModelResponse(FrozenModel):
    message: Message
    raw_response: str
    usage: Usage | None = None
    finish_reason: str | None = None
    provider_request_json: str | None = None
    retry_count: int = Field(default=0, ge=0)
    attempts: tuple[ProviderAttempt, ...] = ()


class ProviderSession(Protocol):
    def complete(self, request: ModelRequest) -> ModelResponse: ...


class ModelProvider(Protocol):
    @property
    def metadata(self) -> ProviderMetadata: ...

    def new_session(self) -> ProviderSession:
        """Return a fresh session for a single case/condition."""
        ...


class ProviderError(Exception):
    """Adapters can preserve an error payload and partial usage without a response."""

    def __init__(self, message: str, *, raw_response: str | None = None, usage: Usage | None = None,
                 provider_request_json: str | None = None, attempts: tuple[ProviderAttempt, ...] = ()):
        super().__init__(message)
        self.raw_response = raw_response
        self.usage = usage
        self.provider_request_json = provider_request_json
        self.attempts = attempts
        self.retry_count = max(0, len(attempts) - 1)
