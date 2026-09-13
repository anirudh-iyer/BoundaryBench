from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


Role = Literal["student", "instructor"]
Proficiency = Literal["A1", "A2", "B1"]
Sensitivity = Literal["general", "answer_key", "instructor_only"]


class User(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(min_length=1)
    role: Role
    proficiency: Proficiency
    course_id: str = Field(min_length=1)


class Document(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    proficiency_level: Proficiency
    content_type: str = Field(min_length=1)
    sensitivity: Sensitivity
    allowed_roles: frozenset[Role]
    body: str


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    split: Literal["development", "held_out"]
    category: str = Field(min_length=1)
    boundary_type: str = Field(min_length=1)
    target_family: str = Field(min_length=1)
    authenticated_user_id: str = Field(min_length=1)
    scripted_turns: tuple[str, ...] = Field(min_length=1, max_length=3)
    expected_protected_document_ids: frozenset[str] = frozenset()
    evaluator_only_protected_facts: frozenset[str] = frozenset()
    authorized_evidence_document_ids: frozenset[str] | None = None
