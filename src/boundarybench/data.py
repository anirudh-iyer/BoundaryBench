"""Small repository-local fixtures; JSONL is the sole source of corpus content."""

from pathlib import Path

from boundarybench.models.schemas import Document, EvaluationCase, User
from boundarybench.policy.authorization import Decision, authorize


DATA_ROOT = Path(__file__).resolve().parents[2] / "data"


def read_jsonl(path: Path, schema):
    return tuple(schema.model_validate_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


USERS = read_jsonl(DATA_ROOT / "synthetic" / "users.jsonl", User)
DOCUMENTS = read_jsonl(DATA_ROOT / "synthetic" / "documents.jsonl", Document)


def load_development_cases(*, include_diagnostics: bool = False) -> tuple[EvaluationCase, ...]:
    cases = read_jsonl(DATA_ROOT / "development" / "cases.jsonl", EvaluationCase)
    if include_diagnostics:
        cases += read_jsonl(DATA_ROOT / "development" / "diagnostics.jsonl", EvaluationCase)
    audit_development_cases(cases, DOCUMENTS, USERS)
    return cases


def audit_development_cases(cases: tuple[EvaluationCase, ...], documents: tuple[Document, ...], users: tuple[User, ...]) -> None:
    """Data consistency checks; independent fixtures still test policy correctness."""
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("duplicate case ID")
    registry = {user.user_id: user for user in users}
    corpus = {document.document_id: document for document in documents}
    all_secrets = {fact for case in cases for fact in case.evaluator_only_protected_facts}
    for case in cases:
        if case.split != "development" or not case.case_id.startswith("dev-"):
            raise ValueError("development loader cannot load held-out cases")
        user = registry[case.authenticated_user_id]
        attack_text = "\n".join((*case.scripted_turns, *(item.body for item in case.document_body_overrides)))
        if any(fact.casefold() in attack_text.casefold() for fact in all_secrets):
            raise ValueError(f"evaluator-only fact in prompt or injection: {case.case_id}")
        for document_id in case.expected_protected_document_ids:
            if authorize(user, corpus[document_id]).decision != Decision.DENY:
                raise ValueError(f"protected target is authorized: {case.case_id}")
        for fact in case.evaluator_only_protected_facts:
            if not any(fact in corpus[d].body for d in case.expected_protected_document_ids):
                raise ValueError(f"fact absent from protected targets: {case.case_id}")
            if any(fact in d.body and authorize(user, d).decision == Decision.ALLOW for d in documents):
                raise ValueError(f"protected fact in authorized material: {case.case_id}")
        for document_id in case.authorized_evidence_document_ids or ():
            if authorize(user, corpus[document_id]).decision != Decision.ALLOW:
                raise ValueError(f"authorized evidence is inaccessible: {case.case_id}")
        if case.authorized_task and not case.evaluator_only_expected_answer:
            raise ValueError(f"authorized task has no expected answer: {case.case_id}")
        if case.gate == "in_gate" and not case.authorized_task:
            raise ValueError(f"in-gate case has no authorized task: {case.case_id}")
        if case.gate == "out_of_gate" and not case.evaluator_only_protected_facts:
            raise ValueError(f"security case has no protected facts: {case.case_id}")
        for override in case.document_body_overrides:
            if authorize(user, corpus[override.document_id]).decision != Decision.ALLOW:
                raise ValueError(f"injection carrier is inaccessible: {case.case_id}")
