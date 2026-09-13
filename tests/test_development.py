import pytest
from pydantic import ValidationError

from boundarybench.data import DOCUMENTS, USERS, audit_development_cases, load_development_cases
from boundarybench.models.schemas import EvaluationCase
from boundarybench.retrieval.engine import rank


def test_development_categories_gates_and_topic_retrieval():
    cases = load_development_cases()
    assert len(cases) == 14
    assert {case.gate for case in cases} == {"in_gate", "out_of_gate"}
    assert {
        "ordinary_learning", "answer_key", "proficiency_boundary", "cross_course", "instructor_only",
        "role_impersonation", "paraphrased_restricted_request", "multi_turn_escalation",
        "indirect_inference", "retrieved_prompt_injection",
    } <= {case.category for case in cases}
    for case in cases:
        assert case.split == "development"
        if case.expected_protected_document_ids and not case.document_body_overrides:
            windows = {candidate.document.document_id for turn in case.scripted_turns for candidate in rank(turn, DOCUMENTS)[:3]}
            assert case.expected_protected_document_ids <= windows, case.case_id


def test_audit_rejects_secret_in_prompt_and_held_out_contamination(cases):
    case = cases["dev-answer-key"]
    with pytest.raises(ValueError, match="fact in prompt"):
        audit_development_cases((case.model_copy(update={"scripted_turns": ("amber-orbit-17",)}),), DOCUMENTS, USERS)
    with pytest.raises(ValueError, match="held-out"):
        audit_development_cases((case.model_copy(update={"split": "held_out"}),), DOCUMENTS, USERS)


def test_injection_changes_only_body_and_keeps_clean_user_request(cases):
    attack = cases["dev-injection"]
    clean = cases["dev-injection-clean"]
    assert attack.scripted_turns == clean.scripted_turns
    assert attack.authorized_task and attack.evaluator_only_protected_facts
    assert set(attack.document_body_overrides[0].model_dump()) == {"document_id", "body"}
    assert not clean.document_body_overrides


def test_empty_fact_is_invalid_evaluator_metadata(cases):
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({**cases["dev-answer-key"].model_dump(), "evaluator_only_protected_facts": [""]})
