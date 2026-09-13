from boundarybench.data import DOCUMENTS, USERS
from boundarybench.retrieval.engine import Condition, RetrievalHarness, rank


def test_ranking_is_deterministic_and_uses_document_id_ties():
    first = rank("apple", DOCUMENTS)
    second = rank("apple", tuple(reversed(DOCUMENTS)))
    assert [item.document.document_id for item in first] == [item.document.document_id for item in second]


def test_b_c_d_return_identical_authorized_results_and_refill():
    harness = RetrievalHarness(DOCUMENTS)
    traces = {condition: harness.search("protected fact apple", USERS[0], condition, frozenset({"a-key"})) for condition in (Condition.B, Condition.C, Condition.D)}
    assert traces[Condition.B].returned_document_ids == traces[Condition.C].returned_document_ids == traces[Condition.D].returned_document_ids
    assert "a-key" in traces[Condition.B].removed_document_ids
    assert traces[Condition.B].returned_document_ids[0] == "a-public"


def test_a_exposes_unfiltered_top_candidate_but_enforced_conditions_remove_it():
    harness = RetrievalHarness(DOCUMENTS)
    prompt_only = harness.search("protected fact", USERS[0], Condition.A, frozenset({"a-key"}))
    enforced = harness.search("protected fact", USERS[0], Condition.B, frozenset({"a-key"}))
    assert "a-key" in prompt_only.returned_document_ids
    assert "a-key" not in enforced.returned_document_ids
    assert "a-key" in enforced.removed_document_ids


def test_retrieval_miss_is_distinct_from_authorization_removal():
    harness = RetrievalHarness(DOCUMENTS)
    miss = harness.search("does-not-exist", USERS[0], Condition.B, frozenset({"a-key"}))
    removed = harness.search("protected fact", USERS[0], Condition.B, frozenset({"a-key"}))
    assert miss.protected_target_retrieval["a-key"] is False
    assert "a-key" not in miss.removed_document_ids
    assert removed.protected_target_retrieval["a-key"] is True
    assert "a-key" in removed.removed_document_ids


def test_trace_reconstructs_each_decision_and_serialization_is_condition_neutral():
    harness = RetrievalHarness(DOCUMENTS)
    traces = [harness.search("apple", USERS[0], condition) for condition in Condition]
    for trace in traces:
        assert len(trace.unfiltered_ranking) == len(trace.authorization_decisions)
        assert set(trace.removed_document_ids).issubset(set(trace.unfiltered_ranking))
    assert traces[1].model_visible_response == traces[2].model_visible_response == traces[3].model_visible_response
