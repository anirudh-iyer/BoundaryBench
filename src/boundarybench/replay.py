from dataclasses import dataclass

from boundarybench.models.schemas import User
from boundarybench.retrieval.engine import Condition, RetrievalHarness, SearchTrace


@dataclass(frozen=True)
class EpisodeTrace:
    case_id: str
    condition: Condition
    user_id: str
    searches: tuple[SearchTrace, ...]
    assistant_outputs: tuple[str, ...] = ()


class OfflineReplay:
    """Scripted, provider-free replay; it never calls an external model."""

    def __init__(self, harness: RetrievalHarness):
        self.harness = harness

    def run_searches(self, case_id: str, user: User, condition: Condition, queries: tuple[str, ...], protected_ids: frozenset[str] = frozenset()) -> EpisodeTrace:
        traces = tuple(self.harness.search(query, user, condition, protected_ids) for query in queries[:6])
        return EpisodeTrace(case_id=case_id, condition=condition, user_id=user.user_id, searches=traces)
