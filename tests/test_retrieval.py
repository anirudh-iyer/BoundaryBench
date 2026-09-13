import pytest

from boundarybench.data import DOCUMENTS, USERS
from boundarybench.retrieval.engine import Condition, RetrievalHarness, rank


def test_ranking_is_deterministic_and_uses_document_id_ties():
    first = rank("apple", DOCUMENTS)
    second = rank("apple", tuple(reversed(DOCUMENTS)))
    assert [item.document.document_id for item in first] == [item.document.document_id for item in second]


def test_b_c_d_return_identical_authorized_results_and_refill():
    harness = RetrievalHarness(DOCUMENTS)
    traces = {condition: harness.search("Unit 4 oral examination apple", USERS[0], condition, frozenset({"a-key"})) for condition in (Condition.B, Condition.C, Condition.D)}
    assert traces[Condition.B].returned_document_ids == traces[Condition.C].returned_document_ids == traces[Condition.D].returned_document_ids
    assert "a-key" in traces[Condition.B].actually_blocked_from_context_ids
    assert traces[Condition.B].returned_document_ids[0] == "a-public"


def test_a_exposes_unfiltered_top_candidate_but_enforced_conditions_remove_it():
    harness = RetrievalHarness(DOCUMENTS)
    prompt_only = harness.search("Unit 4 oral examination", USERS[0], Condition.A, frozenset({"a-key"}))
    enforced = harness.search("Unit 4 oral examination", USERS[0], Condition.B, frozenset({"a-key"}))
    assert "a-key" in prompt_only.returned_document_ids
    assert "a-key" not in enforced.returned_document_ids
    assert "a-key" in enforced.actually_blocked_from_context_ids
    assert "a-key" in prompt_only.denied_candidate_ids
    assert prompt_only.actually_blocked_from_context_ids == ()
    assert "amber-orbit-17" in prompt_only.serialized_response
    assert "amber-orbit-17" not in enforced.serialized_response


def test_retrieval_miss_is_distinct_from_authorization_removal():
    harness = RetrievalHarness(DOCUMENTS)
    miss = harness.search("does-not-exist", USERS[0], Condition.B, frozenset({"a-key"}))
    removed = harness.search("Unit 4 oral examination", USERS[0], Condition.B, frozenset({"a-key"}))
    assert miss.protected_targets[0].exists_in_corpus
    assert miss.protected_targets[0].in_unfiltered_ranking is False
    assert miss.protected_targets[0].authorization_denied is None
    assert miss.actually_blocked_from_context_ids == ()
    assert removed.protected_targets[0].in_unfiltered_return_window
    assert removed.protected_targets[0].authorization_denied
    assert "a-key" in removed.actually_blocked_from_context_ids


def test_trace_reconstructs_each_decision_and_serialization_is_condition_neutral():
    harness = RetrievalHarness(DOCUMENTS)
    traces = [harness.search("apple", USERS[0], condition) for condition in Condition]
    for trace in traces:
        assert len(trace.unfiltered_ranking) == len(trace.authorization_decisions)
        assert set(trace.denied_candidate_ids).issubset(set(trace.unfiltered_ranking))
    assert traces[1].serialized_response == traces[2].serialized_response == traces[3].serialized_response


@pytest.mark.parametrize("condition", [Condition.B, Condition.C, Condition.D])
def test_protected_target_ranks_but_never_becomes_model_visible(condition):
    trace = RetrievalHarness(DOCUMENTS).search("Unit 4 oral examination", USERS[0], condition, frozenset({"a-key"}))
    delivered = trace.submitted_in_request(1)
    target = delivered.protected_targets[0]
    assert target.exists_in_corpus and target.in_unfiltered_return_window
    assert target.authorization_denied and target.authorization_prevented_return
    assert not target.content_in_model_context
    assert not delivered.protected_content_model_visible_ids


@pytest.mark.parametrize("condition", list(Condition))
def test_denied_candidate_below_top_k_is_not_prevention(condition):
    trace = RetrievalHarness(DOCUMENTS, max_results=1).search(
        "greetings practice informal examination", USERS[0], condition, frozenset({"a-key"}),
    )
    assert trace.unfiltered_return_window_ids == ("a-public",)
    assert "a-key" in trace.denied_candidate_ids
    assert trace.would_have_been_returned_protected_ids == ()
    assert trace.actually_blocked_from_context_ids == ()
    assert trace.protected_targets[0].authorization_denied
    assert not trace.protected_targets[0].authorization_prevented_return


def test_missing_target_is_separate_from_existing_missed_target():
    trace = RetrievalHarness(DOCUMENTS).search("zzzzzz", USERS[0], Condition.B, frozenset({"a-key", "absent"}))
    targets = {target.document_id: target for target in trace.protected_targets}
    assert targets["a-key"].exists_in_corpus
    assert not targets["absent"].exists_in_corpus
    assert not any(target.in_unfiltered_ranking for target in targets.values())


def test_tool_return_is_not_yet_an_actual_model_request():
    trace = RetrievalHarness(DOCUMENTS).search("Unit 4 oral examination", USERS[0], Condition.A, frozenset({"a-key"}))
    assert "a-key" in trace.returned_document_ids
    assert trace.model_visible_document_ids == ()
    delivered = trace.submitted_in_request(2)
    assert delivered.protected_targets[0].content_in_model_context
    assert "a-key" in delivered.protected_content_model_visible_ids
    assert delivered.model_request_indices == (2,)


def test_layer_decisions_show_shared_path_without_inventing_differences():
    traces = {c: RetrievalHarness(DOCUMENTS).search("Unit 4 oral examination", USERS[0], c) for c in Condition}
    assert not traces[Condition.A].retrieval_authorization_decisions
    assert not traces[Condition.A].tool_authorization_decisions
    assert traces[Condition.B].retrieval_authorization_decisions
    assert not traces[Condition.B].tool_authorization_decisions
    assert not traces[Condition.C].retrieval_authorization_decisions
    assert traces[Condition.C].tool_authorization_decisions
    assert traces[Condition.D].retrieval_authorization_decisions
    # D's post-filter candidates can be empty. Test its second layer on accessible data.
    assert RetrievalHarness(DOCUMENTS).search("greetings", USERS[0], Condition.D).tool_authorization_decisions


def test_invalid_configuration_cannot_silently_select_prompt_only():
    with pytest.raises(ValueError):
        RetrievalHarness(DOCUMENTS).search("examination", USERS[0], "E")
    with pytest.raises(ValueError):
        RetrievalHarness(DOCUMENTS, max_results=0)
