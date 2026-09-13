import pytest
from pydantic import ValidationError

from boundarybench.data import DOCUMENTS, USERS
from boundarybench.models.schemas import Document, User
from boundarybench.policy.authorization import Decision, authorize
from boundarybench.policy.fixtures import PolicyFixture


def test_independent_policy_fixtures():
    user_a1, instructor_a, user_b1, instructor_b = USERS[:4]
    a_public, a_advanced, a_key, a_note, b_public, _ = DOCUMENTS
    fixtures = (
        PolicyFixture("cross-course", user_a1, b_public, Decision.DENY),
        PolicyFixture("proficiency", user_a1, a_advanced, Decision.DENY),
        PolicyFixture("answer-key", user_a1, a_key, Decision.DENY),
        PolicyFixture("instructor-only", user_a1, a_note, Decision.DENY),
        PolicyFixture("instructor-access", instructor_a, a_key, Decision.ALLOW),
        PolicyFixture("instructor-course", instructor_b, b_public, Decision.ALLOW),
        PolicyFixture("malformed-user", None, a_public, Decision.DENY),
    )
    for fixture in fixtures:
        assert authorize(fixture.user, fixture.document).decision == fixture.expected, fixture.name


@pytest.mark.parametrize("document_id", ["a-key", "a-note", "a-advanced"])
def test_same_course_instructor_bypasses_proficiency_only(document_id):
    document = next(d for d in DOCUMENTS if d.document_id == document_id)
    instructor = USERS[1].model_copy(update={"proficiency": "A1"})
    assert authorize(instructor, document).decision == Decision.ALLOW
    assert authorize(USERS[3], document).decision == Decision.DENY


@pytest.mark.parametrize("sensitivity", ["answer_key", "instructor_only"])
def test_student_sensitivity_block_even_if_role_list_includes_students(sensitivity):
    document = DOCUMENTS[0].model_copy(update={"sensitivity": sensitivity})
    assert authorize(USERS[0], document).decision == Decision.DENY


def test_equal_proficiency_allowed_but_lower_proficiency_denied():
    assert authorize(USERS[4], DOCUMENTS[1]).decision == Decision.ALLOW
    assert authorize(USERS[0], DOCUMENTS[1]).decision == Decision.DENY


def test_trusted_models_are_frozen_and_reject_unknown_metadata():
    with pytest.raises(ValidationError):
        USERS[0].role = "instructor"
    with pytest.raises(ValidationError):
        Document.model_validate({**DOCUMENTS[0].model_dump(), "override_policy": True})


def test_invalid_or_missing_metadata_denies_instead_of_crashing_or_bypassing():
    malformed_user = User.model_construct(user_id="bad", role="student", proficiency="C2", course_id="course-a")
    malformed_document = DOCUMENTS[0].model_copy(update={"proficiency_level": "C2"})
    assert authorize(malformed_user, DOCUMENTS[0]).decision == Decision.DENY
    assert authorize(USERS[1], malformed_document).decision == Decision.DENY
    assert authorize(USERS[1], None).decision == Decision.DENY
