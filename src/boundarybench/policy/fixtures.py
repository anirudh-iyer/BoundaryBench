"""Independently authored expected policy outcomes; do not derive these in tests."""

from dataclasses import dataclass

from boundarybench.models.schemas import Document, User
from boundarybench.policy.authorization import Decision


@dataclass(frozen=True)
class PolicyFixture:
    name: str
    user: User | None
    document: Document | None
    expected: Decision
