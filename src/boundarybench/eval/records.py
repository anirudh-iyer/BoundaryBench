"""Versioned raw records and create-only JSONL persistence."""

from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from boundarybench.models.llm import FrozenModel, Message, ModelRequest, ModelResponse, ProviderMetadata, Usage
from boundarybench.models.schemas import EvaluationCase, User
from boundarybench.retrieval.engine import Condition, SearchTrace


def canonical_json(value: object) -> str:
    def normalize(item):
        if isinstance(item, BaseModel):
            return normalize(item.model_dump(mode="python"))
        if is_dataclass(item):
            return normalize(asdict(item))
        if isinstance(item, dict):
            return {key: normalize(val) for key, val in item.items()}
        if isinstance(item, (set, frozenset)):
            return sorted(normalize(val) for val in item)
        if isinstance(item, (tuple, list)):
            return [normalize(val) for val in item]
        return item
    return json.dumps(normalize(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class OperationalError(FrozenModel):
    stage: str
    error_type: str
    message: str
    user_turn_index: int | None = None
    request_index: int | None = None
    raw_response: str | None = None
    usage: Usage | None = None


class Invocation(FrozenModel):
    user_turn_index: int
    started_at: str
    finished_at: str
    request: ModelRequest
    response: ModelResponse | None = None
    error_index: int | None = None


class SearchEvent(FrozenModel):
    user_turn_index: int
    tool_call_id: str
    trace: SearchTrace


class EpisodeRecord(FrozenModel):
    schema_version: str = "2"
    episode_id: str
    case: EvaluationCase
    condition: Condition
    authenticated_user: User | None
    # Availability is recorded even if an episode never performs a search.
    protected_targets_in_corpus: tuple[str, ...]
    protected_targets_missing_from_corpus: tuple[str, ...]
    provider: ProviderMetadata
    started_at: str
    finished_at: str
    status: Literal["completed", "error"]
    # Includes all scripted turns, even turns not reached after an error.
    user_turns: tuple[str, ...]
    completed_user_turns: int
    conversation: tuple[Message, ...]
    invocations: tuple[Invocation, ...]
    searches: tuple[SearchEvent, ...]
    assistant_responses: tuple[Message, ...]
    operational_errors: tuple[OperationalError, ...]
    manifest_json: str


def write_jsonl_exclusive(path: Path, records: list[object]) -> Path:
    """One create-only artifact; never append to or replace an existing artifact.

    Application-level immutability, not filesystem WORM protection. A failed
    write propagates to the caller, leaving any partial artifact for inspection.
    """
    payload = "".join(canonical_json(record) + "\n" for record in records)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    return path


class RawRecordStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def write(self, record: EpisodeRecord) -> Path:
        # Episode IDs originate in the harness, but reject path components too.
        if not record.episode_id or any(c not in "0123456789abcdef-" for c in record.episode_id):
            raise ValueError("invalid episode ID")
        return write_jsonl_exclusive(self.directory / f"{record.episode_id}.jsonl", [record])
