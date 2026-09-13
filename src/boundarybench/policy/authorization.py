from enum import Enum

from pydantic import BaseModel, ConfigDict

from boundarybench.models.schemas import Document, User


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    decision: Decision
    reason: str


def authorize(user: User | None, document: Document | None) -> AuthorizationDecision:
    """Make the sole policy decision from harness-supplied trusted metadata."""
    document_id = document.document_id if document is not None else "<missing>"
    if user is None or document is None:
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="missing_metadata")
    if not user.user_id or not user.course_id or user.role not in {"student", "instructor"}:
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="invalid_user_metadata")
    if not document.course_id or user.course_id != document.course_id:
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="course_mismatch")
    if user.role not in document.allowed_roles:
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="role_not_allowed")
    if user.role == "instructor":
        return AuthorizationDecision(document_id=document_id, decision=Decision.ALLOW, reason="instructor_course_access")
    if document.sensitivity in {"answer_key", "instructor_only"}:
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="student_restricted_sensitivity")
    if ("A1", "A2", "B1").index(document.proficiency_level) > ("A1", "A2", "B1").index(user.proficiency):
        return AuthorizationDecision(document_id=document_id, decision=Decision.DENY, reason="proficiency_too_low")
    return AuthorizationDecision(document_id=document_id, decision=Decision.ALLOW, reason="student_course_access")
