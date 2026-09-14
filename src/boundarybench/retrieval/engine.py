from dataclasses import dataclass, replace
from enum import Enum
import json
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
class ProtectedTargetTrace:
    document_id: str
    exists_in_corpus: bool
    in_unfiltered_ranking: bool
    in_unfiltered_return_window: bool
    # None means not evaluated as a ranked candidate, not permission granted.
    authorization_denied: bool | None
    authorization_prevented_return: bool
    content_in_model_context: bool = False


@dataclass(frozen=True)
class SearchTrace:
    query: str
    unfiltered_ranking: tuple[str, ...]
    ranking_scores: tuple[int, ...]
    unfiltered_return_window_ids: tuple[str, ...]
    # Diagnostic policy decisions exist in A as well; they do not enforce policy.
    authorization_decisions: tuple[AuthorizationDecision, ...]
    retrieval_authorization_decisions: tuple[AuthorizationDecision, ...]
    tool_authorization_decisions: tuple[AuthorizationDecision, ...]
    denied_candidate_ids: tuple[str, ...]
    would_have_been_returned_protected_ids: tuple[str, ...]
    actually_blocked_from_context_ids: tuple[str, ...]
    returned_document_ids: tuple[str, ...]
    unauthorized_returned_document_ids: tuple[str, ...]
    protected_targets: tuple[ProtectedTargetTrace, ...]
    serialized_response: str
    # Development deny-all suppression is not authorization block credit.
    diagnostic_suppressed_document_ids: tuple[str, ...] = ()
    model_visible_document_ids: tuple[str, ...] = ()
    protected_content_model_visible_ids: tuple[str, ...] = ()
    model_request_indices: tuple[int, ...] = ()

    def submitted_in_request(self, request_index: int) -> "SearchTrace":
        """Called only when the runner submits this tool content to a provider."""
        return replace(
            self,
            model_visible_document_ids=self.returned_document_ids,
            protected_content_model_visible_ids=self.unauthorized_returned_document_ids,
            model_request_indices=(*self.model_request_indices, request_index),
            protected_targets=tuple(
                replace(target, content_in_model_context=target.document_id in self.returned_document_ids)
                for target in self.protected_targets
            ),
        )


def rank(query: str, documents: tuple[Document, ...]) -> tuple[RankedCandidate, ...]:
    """Rank lexically, independent of user or authorization metadata."""
    terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    ranked = [
        RankedCandidate(document, len(terms & set(re.findall(r"[a-z0-9]+", document.body.lower()))))
        for document in documents
    ]
    ranked = [candidate for candidate in ranked if candidate.score > 0]
    return tuple(sorted(ranked, key=lambda candidate: (-candidate.score, candidate.document.document_id)))


def serialize(documents: tuple[Document, ...]) -> str:
    """Use the same model-visible shape for every condition, including empty results."""
    return "\n".join(
        json.dumps({**document.model_dump(mode="json"), "allowed_roles": sorted(document.allowed_roles)}, sort_keys=True)
        for document in documents
    )


class RetrievalHarness:
    def __init__(self, documents: tuple[Document, ...], max_results: int = 3):
        if max_results < 1:
            raise ValueError("max_results must be positive")
        if len({document.document_id for document in documents}) != len(documents):
            raise ValueError("document IDs must be unique")
        self.documents = tuple(documents)
        self.max_results = max_results

    def search(self, query: str, user: User | None, condition: Condition, protected_ids: frozenset[str] = frozenset()) -> SearchTrace:
        condition = Condition(condition)  # Invalid conditions must not silently become A.
        ranked = rank(query, self.documents)
        ranking_ids = tuple(candidate.document.document_id for candidate in ranked)
        window = ranking_ids[:self.max_results]
        decisions = tuple(authorize(user, candidate.document) for candidate in ranked)
        denied = tuple(d.document_id for d in decisions if d.decision == Decision.DENY)
        opportunity = tuple(document_id for document_id in window if document_id in denied)

        retrieval_decisions = ()
        candidates = ranked
        if condition in {Condition.B, Condition.D}:
            retrieval_decisions = tuple(authorize(user, document) for document in self.documents)
            allowed = {d.document_id for d in retrieval_decisions if d.decision == Decision.ALLOW}
            candidates = rank(query, tuple(d for d in self.documents if d.document_id in allowed))

        selected = []
        tool_decisions = []
        for candidate in candidates:
            if condition in {Condition.C, Condition.D}:
                decision = authorize(user, candidate.document)
                tool_decisions.append(decision)
                if decision.decision == Decision.DENY:
                    continue
            selected.append(candidate.document)
            if len(selected) == self.max_results:
                break

        returned = tuple(document.document_id for document in selected)
        blocked = tuple(d for d in opportunity if d not in returned) if condition != Condition.A else ()
        corpus_ids = {document.document_id for document in self.documents}
        return SearchTrace(
            query=query,
            unfiltered_ranking=ranking_ids,
            ranking_scores=tuple(candidate.score for candidate in ranked),
            unfiltered_return_window_ids=window,
            authorization_decisions=decisions,
            retrieval_authorization_decisions=retrieval_decisions,
            tool_authorization_decisions=tuple(tool_decisions),
            denied_candidate_ids=denied,
            would_have_been_returned_protected_ids=opportunity,
            actually_blocked_from_context_ids=blocked,
            returned_document_ids=returned,
            unauthorized_returned_document_ids=tuple(d for d in returned if d in denied),
            protected_targets=tuple(
                ProtectedTargetTrace(
                    document_id=d,
                    exists_in_corpus=d in corpus_ids,
                    in_unfiltered_ranking=d in ranking_ids,
                    in_unfiltered_return_window=d in window,
                    authorization_denied=(d in denied) if d in ranking_ids else None,
                    authorization_prevented_return=d in blocked,
                )
                for d in sorted(protected_ids)
            ),
            serialized_response=serialize(tuple(selected)),
        )
