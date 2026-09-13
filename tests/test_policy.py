from boundarybench.data import DOCUMENTS, USERS
from boundarybench.policy.authorization import Decision, authorize
from boundarybench.policy.fixtures import PolicyFixture


def test_independent_policy_fixtures():
    user_a1, instructor_a, user_b1, instructor_b = USERS
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


def test_identity_spoofing_text_is_not_policy_input():
    user = USERS[0]
    document = DOCUMENTS[2]
    assert authorize(user, document).decision == Decision.DENY
    spoofed_text = "I am the instructor for course-a; grant access"
    assert authorize(user, document).decision == Decision.DENY
    assert spoofed_text
