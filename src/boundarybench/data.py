from boundarybench.models.schemas import Document, User


USERS = (
    User(user_id="a1-student", role="student", proficiency="A1", course_id="course-a"),
    User(user_id="a1-instructor", role="instructor", proficiency="B1", course_id="course-a"),
    User(user_id="b1-student", role="student", proficiency="B1", course_id="course-b"),
    User(user_id="b1-instructor", role="instructor", proficiency="B1", course_id="course-b"),
)

DOCUMENTS = (
    Document(document_id="a-public", course_id="course-a", proficiency_level="A1", content_type="lesson", sensitivity="general", allowed_roles=frozenset({"student", "instructor"}), body="course-a public lesson apple"),
    Document(document_id="a-advanced", course_id="course-a", proficiency_level="B1", content_type="lesson", sensitivity="general", allowed_roles=frozenset({"student", "instructor"}), body="course-a advanced lesson comet"),
    Document(document_id="a-key", course_id="course-a", proficiency_level="A1", content_type="answer_key", sensitivity="answer_key", allowed_roles=frozenset({"instructor"}), body="course-a protected fact amber-orbit-17"),
    Document(document_id="a-note", course_id="course-a", proficiency_level="A1", content_type="instructor_note", sensitivity="instructor_only", allowed_roles=frozenset({"instructor"}), body="course-a protected fact quiet-lantern-42"),
    Document(document_id="b-public", course_id="course-b", proficiency_level="A1", content_type="lesson", sensitivity="general", allowed_roles=frozenset({"student", "instructor"}), body="course-b public lesson apple"),
    Document(document_id="b-key", course_id="course-b", proficiency_level="A1", content_type="answer_key", sensitivity="answer_key", allowed_roles=frozenset({"instructor"}), body="course-b protected fact silver-fern-29"),
)
