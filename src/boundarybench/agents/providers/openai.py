"""OpenAI Chat Completions adapter; no authorization or evaluator knowledge.

Uses the standard library HTTPS client so SDK defaults cannot add hidden retries
or transform requests. Transport, sleeping and jitter are injectable for tests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import os
import random
import socket
import ssl
import time
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from pydantic import Field

from boundarybench.models.llm import (
    FrozenModel, Message, ModelRequest, ModelResponse, ProviderAttempt, ProviderError,
    ProviderMetadata, ToolCall, Usage,
)


ENDPOINT = "https://api.openai.com/v1/chat/completions"


def encode(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class OpenAISettings(FrozenModel):
    # These settings are sent explicitly; incompatible models fail, without fallback.
    temperature: float = Field(default=0, ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(default=1, gt=0, le=1, allow_inf_nan=False)
    seed: int | None = None
    max_completion_tokens: int = Field(default=2048, ge=1, le=32768)
    timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    max_retries: int = Field(default=2, ge=0, le=3)
    retry_base_seconds: float = Field(default=0.5, gt=0, le=10, allow_inf_nan=False)
    max_retry_delay_seconds: float = Field(default=30, gt=0, le=60, allow_inf_nan=False)


class OpenAIConfig(OpenAISettings):
    model: str = Field(min_length=1, pattern=r"^\S+$")


@dataclass(frozen=True)
class HTTPResponse:
    status: int
    body: str
    headers: Mapping[str, str]


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the Authorization header to a redirected host.
        return None


def send_https(payload: bytes, api_key: str, timeout: float) -> HTTPResponse:
    request = Request(ENDPOINT, data=payload, method="POST", headers={
        "Authorization": "Bearer " + api_key, "Content-Type": "application/json",
        "Accept": "application/json", "User-Agent": "BoundaryBench-development/1",
    })
    try:
        response = build_opener(NoRedirects()).open(request, timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        return HTTPResponse(response.code, response.read().decode("utf-8", errors="replace"),
                            {key.lower(): value for key, value in response.headers.items()})


def transient_transport(exc: Exception) -> bool:
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return False
    if isinstance(reason, socket.gaierror):
        return reason.errno == socket.EAI_AGAIN
    return isinstance(reason, (TimeoutError, ConnectionError))


def transient_http(response: HTTPResponse) -> bool:
    if response.status in {408, 500, 502, 503, 504}:
        return True
    if response.status != 429:
        return False
    try:
        error = json.loads(response.body)["error"]
        # Quota/billing exhaustion and unknown 429s are never retried.
        code = error.get("code")
        return code in {"rate_limit_exceeded", "slow_down"} or (
            code is None and error.get("type") == "rate_limit_error"
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return False


def retry_after(headers: Mapping[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        delay = float(value)
        return max(0.0, delay) if delay == delay else None
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def wire_request(request: ModelRequest, config: OpenAIConfig) -> str:
    messages = []
    for message in request.messages:
        item = {"role": message.role, "content": message.content}
        if message.tool_calls:
            item["tool_calls"] = [
                {"id": call.call_id, "type": "function",
                 "function": {"name": call.name, "arguments": call.arguments_json}}
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            item["tool_call_id"] = message.tool_call_id
        messages.append(item)
    payload = {
        "model": config.model, "messages": messages,
        "tools": [{"type": "function", "function": {
            "name": tool.name, "description": tool.description,
            "parameters": json.loads(tool.parameters_json),
        }} for tool in request.tools],
        "temperature": config.temperature, "top_p": config.top_p,
        "max_completion_tokens": config.max_completion_tokens,
        "tool_choice": "auto", "n": 1, "stream": False, "store": False,
    }
    if config.seed is not None:
        payload["seed"] = config.seed
    return encode(payload)


def parse_response(raw: str, payload: str, attempts: tuple[ProviderAttempt, ...], *, provider_name: str = "OpenAI") -> ModelResponse:
    usage = None
    try:
        data = json.loads(raw)
        if data.get("usage") is not None:
            counters = data["usage"]
            usage = Usage(input_tokens=counters.get("prompt_tokens"), output_tokens=counters.get("completion_tokens"),
                          details_json=encode(counters))
        choices = data["choices"]
        if len(choices) != 1:
            raise ValueError("expected exactly one choice")
        choice = choices[0]
        finish = choice["finish_reason"]
        if finish not in {"stop", "tool_calls", "length", "content_filter"}:
            raise ValueError("unsupported finish reason")
        message = choice["message"]
        if message["role"] != "assistant" or message.get("function_call") is not None:
            raise ValueError("unsupported assistant message")
        content = message.get("content")
        refusal = message.get("refusal")
        # A provider refusal has no ordinary content in some responses. Keep
        # the original structure in raw_response and use its text for scoring.
        if content is None:
            content = refusal if refusal is not None else ""
        if not isinstance(content, str):
            raise ValueError("assistant content must be text")
        calls = []
        for call in message.get("tool_calls") or []:
            if call["type"] != "function":
                raise ValueError("unsupported tool call type")
            calls.append(ToolCall(call_id=call["id"], name=call["function"]["name"],
                                  arguments_json=call["function"]["arguments"]))
        if (finish == "tool_calls") != bool(calls) and finish not in {"length", "content_filter"}:
            raise ValueError("finish reason disagrees with tool calls")
        return ModelResponse(message=Message(role="assistant", content=content, tool_calls=tuple(calls)),
                             raw_response=raw, usage=usage, finish_reason=finish,
                             provider_request_json=payload, retry_count=len(attempts) - 1, attempts=attempts)
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        raise ProviderError(provider_name + " model-protocol failure: " + type(exc).__name__, raw_response=raw,
                            usage=usage, provider_request_json=payload, attempts=attempts) from None


class OpenAIProvider:
    name = "OpenAI"

    def __init__(self, config: OpenAIConfig, *, transport: Callable = send_https,
                 sleep: Callable = time.sleep, jitter: Callable = random.random):
        self.config = config
        self.transport = transport
        self.sleep = sleep
        self.jitter = jitter

    def request_json(self, request: ModelRequest) -> str:
        return wire_request(request, self.config)

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata(
            provider="openai", model=self.config.model, adapter_version="chat-completions-v1", offline=False,
            configuration_json=encode({**self.config.model_dump(), "endpoint": ENDPOINT,
                                       "api_key_source": "OPENAI_API_KEY environment only",
                                       "raw_redaction": "API key occurrences replaced with [REDACTED]"}),
            supported_sampling_settings=("temperature", "top_p", "seed"),
            sampling_settings_json=encode({"temperature": self.config.temperature, "top_p": self.config.top_p,
                                           "seed": self.config.seed}), seed=self.config.seed,
        )

    def new_session(self):
        # Never accept a key in model configuration, a file, or a CLI option.
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key.strip():
            raise ProviderError("OPENAI_API_KEY is not configured")
        return OpenAISession(self, api_key)


class OpenAISession:
    def __init__(self, provider: OpenAIProvider, api_key: str):
        self.provider = provider
        self._api_key = api_key

    def complete(self, request: ModelRequest) -> ModelResponse:
        provider = self.provider
        config = provider.config
        payload = provider.request_json(request)
        attempts = []
        for index in range(config.max_retries + 1):
            result = None
            error_type = None
            try:
                result = provider.transport(payload.encode("utf-8"), self._api_key, config.timeout_seconds)
                def redact(value: str) -> str:
                    return value.replace(self._api_key, "[REDACTED]") if self._api_key else value
                result = HTTPResponse(result.status, redact(result.body),
                                      {k.lower(): redact(v) for k, v in result.headers.items()})
                transient = transient_http(result)
            except (OSError, URLError) as exc:
                error_type = type(exc).__name__
                transient = transient_transport(exc)
            delay = None
            success = result is not None and result.status == 200
            if not success and transient and index < config.max_retries:
                backoff = config.retry_base_seconds * (2 ** index) * (1 + provider.jitter())
                delay = max(backoff, retry_after(result.headers) or 0) if result else backoff
                # Do not retry earlier than Retry-After if it exceeds our bound.
                if delay > config.max_retry_delay_seconds:
                    delay = None
            attempts.append(ProviderAttempt(
                attempt=index + 1, status_code=result.status if result else None,
                request_id=result.headers.get("x-request-id") if result else None,
                error_type=error_type or (None if success else "HTTPError"),
                raw_response=result.body if result else None, retry_delay_seconds=delay,
            ))
            if success:
                return parse_response(result.body, payload, tuple(attempts), provider_name=provider.name)
            if delay is None:
                raise ProviderError(provider.name + " request failed: " + (str(result.status) if result else error_type),
                                    raw_response=result.body if result else None,
                                    provider_request_json=payload, attempts=tuple(attempts))
            provider.sleep(delay)
        raise AssertionError("unreachable retry loop")
