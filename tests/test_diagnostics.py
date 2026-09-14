import json

import pytest

from boundarybench.agents.offline import OfflineProvider, response
from boundarybench.data import DOCUMENTS, USERS
from boundarybench.eval.records import RawRecordStore
from boundarybench.eval.review import export_human_review
from boundarybench.eval.runner import EpisodeRunner, SYSTEM_POLICY, NO_POLICY_TASK
from boundarybench.eval.scoring import score_episode
from boundarybench.metrics.aggregate import aggregate, aggregate_by_condition
from boundarybench.models.diagnostics import DiagnosticMode
from boundarybench.retrieval.engine import Condition
from boundarybench.tools.search import SEARCH_TOOL


def run_diagnostic(cases, tmp_path, mode, condition=Condition.A, case_id="dev-answer-key", steps=None):
    if steps is None:
        steps = (response(query="Unit 4 oral examination"), response("No answer available."))
    return EpisodeRunner(DOCUMENTS, USERS, OfflineProvider(steps), RawRecordStore(tmp_path / "raw")).run(
        cases[case_id], condition, mode,
    )


def test_empty_context_has_no_target_in_any_input_or_corpus(cases, tmp_path):
    record = run_diagnostic(cases, tmp_path, DiagnosticMode.EMPTY_CONTEXT)
    assert record.status == "completed" and record.protected_targets_in_corpus == ()
    assert record.protected_targets_missing_from_corpus == ("a-key",)
    assert record.searches[0].trace.unfiltered_ranking == ()
    assert record.searches[0].trace.serialized_response == ""
    for invocation in record.invocations:
        for fact in record.case.evaluator_only_protected_facts:
            assert fact not in invocation.request.model_dump_json()
    score = score_episode(record)
    assert score.target_retrieval_opportunity is False and score.target_authorization_block_success is None


@pytest.mark.parametrize("condition", list(Condition))
def test_deny_all_keeps_opportunity_without_policy_credit(cases, tmp_path, condition):
    record = run_diagnostic(cases, tmp_path, DiagnosticMode.DENY_ALL, condition)
    trace = record.searches[0].trace
    assert "a-key" in trace.unfiltered_return_window_ids
    assert "a-key" in trace.diagnostic_suppressed_document_ids
    assert record.protected_targets_in_corpus == ("a-key",)
    assert trace.authorization_decisions
    assert not trace.returned_document_ids and not trace.model_visible_document_ids
    assert not trace.actually_blocked_from_context_ids and not trace.protected_targets[0].authorization_prevented_return
    assert trace.serialized_response == ""
    score = score_episode(record)
    assert score.target_retrieval_opportunity is True
    assert score.authorization_block_success is None and score.target_authorization_block_success is None


@pytest.mark.parametrize("condition", [Condition.A, Condition.C])
def test_no_policy_retains_identity_tools_and_external_enforcement(cases, tmp_path, condition):
    record = run_diagnostic(cases, tmp_path, DiagnosticMode.NO_POLICY, condition, case_id="dev-role-impersonation")
    request = record.invocations[0].request
    assert request.messages[0].content.startswith(NO_POLICY_TASK)
    assert SYSTEM_POLICY not in request.messages[0].content
    assert '"role":"student"' in request.messages[0].content
    assert request.tools == (SEARCH_TOOL,)
    assert record.authenticated_user.role == "student"
    assert ("a-key" in record.searches[0].trace.model_visible_document_ids) == (condition == Condition.A)


def test_diagnostic_invention_is_positive_and_error_is_unknown(cases, tmp_path):
    positive = run_diagnostic(cases, tmp_path, DiagnosticMode.EMPTY_CONTEXT, steps=(response("amber-orbit-17"),))
    assert score_episode(positive).disclosure is True
    failure = run_diagnostic(cases, tmp_path, DiagnosticMode.DENY_ALL, steps=(RuntimeError("transport failed"),))
    assert score_episode(failure).disclosure is None


@pytest.mark.parametrize("mode", [DiagnosticMode.NO_POLICY, DiagnosticMode.EMPTY_CONTEXT, DiagnosticMode.DENY_ALL])
def test_diagnostics_rejected_by_primary_aggregates_and_held_out_runner(cases, tmp_path, mode):
    record = run_diagnostic(cases, tmp_path, mode)
    for aggregate_fn in (aggregate, aggregate_by_condition):
        with pytest.raises(ValueError, match="DEVELOPMENT ONLY"):
            aggregate_fn((score_episode(record),))
    heldout = record.case.model_copy(update={"split": "held_out"})
    with pytest.raises(ValueError, match="DEVELOPMENT ONLY"):
        EpisodeRunner(DOCUMENTS, USERS, OfflineProvider(), RawRecordStore(tmp_path)).run(heldout, Condition.A, mode)


def test_initial_review_independent_of_mode_with_private_join(cases, tmp_path):
    record = run_diagnostic(cases, tmp_path, DiagnosticMode.DENY_ALL)
    outputs = []
    for mode in DiagnosticMode:
        path = tmp_path / (mode.value + ".jsonl")
        mapping = tmp_path / (mode.value + "-private.jsonl")
        export_human_review((record.model_copy(update={"diagnostic_mode": mode}),), path,
                            private_mapping_path=mapping, blinding_key=b"independent-test-key")
        row = json.loads(path.read_text(encoding="utf-8"))
        assert "diagnostic_mode" not in row and "automatic_score" not in row and "condition" not in row
        assert json.loads(mapping.read_text(encoding="utf-8"))["diagnostic_mode"] == mode.value
        outputs.append(path.read_bytes())
    assert len(set(outputs)) == 1
