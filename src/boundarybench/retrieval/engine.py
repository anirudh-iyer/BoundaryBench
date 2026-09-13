from dataclasses import dataclass
from enum import Enum
import re

from boundarybench.models.schemas import Document, User
from boundarybench.policy.authorization import AuthorizationDecision, Decision, authorize


class Condition(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


@dataclass(frozen=True)
class RankedCandidate:
    document: Document
    score: int


@dataclass(frozen=True)
class SearchTrace:
    query: str
    unfiltered_ranking: tuple[str, ...]
    authorization_decisions: tuple[AuthorizationDecision, ...]
    removed_document_ids: tuple[str, ...]
    returned_document_ids: tuple[str, ...]
    protected_target_retrieval: dict[str, bool]
    model_visible_response: str


def rank(query: str, documents: tuple[Document, ...]) -> tuple[RankedCandidate, ...]:
    """Rank lexically, independent of user or authorization metadata."""
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked = [
        RankedCandidate(document, sum(term in document.body.lower().split() for term in terms))
        for document in documents
    ]
    ranked = [candidate for candidate in ranked if candidate.score > 0]
    return tuple(sorted(ranked, key=lambda candidate: (-candidate.score, candidate.document.document_id)))


def serialize(documents: tuple[Document, ...]) -> str:
    """Use the same model-visible shape for every condition, including empty results."""
    return "\n".join(f"[{document.document_id}] {document.body}" for document in documents)


class RetrievalHarness:
    def __init__(self, documents: tuple[Document, ...], max_results: int = 3):
        self.documents = documents
        self.max_results = max_results

    def search(self, query: str, user: User | None, condition: Condition, protected_ids: frozenset[str] = frozenset()) -> SearchTrace:
        ranked = rank(query, self.documents)
        decisions = tuple(authorize(user, candidate.document) for candidate in ranked)
        allowed = {decision.document_id for decision in decisions if decision.decision == Decision.ALLOW}
        eligible = [candidate for candidate in ranked if candidate.document.document_id in allowed]
        if condition in {Condition.B, Condition.D}:
            selected = eligible[: self.max_results]
        elif condition == Condition.C:
            selected = [candidate for candidate in ranked if candidate.document.document_id in allowed][: self.max_results]
        else:
            selected = list(ranked[: self.max_results])
        selected_documents = tuple(candidate.document for candidate in selected)
        removed = tuple(candidate.document.document_id for candidate in ranked if candidate.document.document_id not in {item.document.document_id for item in selected} and candidate.document.document_id in allowed.symmetric_difference({item.document.document_id for item in ranked}))
        # For A, no authorization is enforced, so only candidates removed by the result cap are absent.
        if condition == Condition.A:
            removed = ()
        return SearchTrace(
            query=query,
            unfiltered_ranking=tuple(candidate.document.document_id for candidate in ranked),
            authorization_decisions=decisions,
            removed_document_ids=tuple(document_id for document_id in (candidate.document.document_id for candidate in ranked) if document_id not in {item.document.document_id for item in selected} and any(d.document_id == document_id and d.decision == Decision.DENY for d in decisions)),
            returned_document_ids=tuple(document.document_id for document in selected_documents),
            protected_target_retrieval={document_id: document_id in tuple(candidate.document.document_id for candidate in ranked[: self.max_results]) for document_id in protected_ids},
            model_visible_response=serialize(selected_documents),
        )
