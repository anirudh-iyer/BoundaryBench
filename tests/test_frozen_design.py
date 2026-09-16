"""Offline fixtures only. Never call the production author_bundle generator."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from boundarybench.agents.offline import OfflineProvider, response
from boundarybench.eval.records import RawRecordStore, canonical_json, digest
from boundarybench.eval.runner import EpisodeRunner, SYSTEM_POLICIES, SYSTEM_POLICY_V2
from boundarybench.heldout.authoring import build_family, REQUESTS
from boundarybench.heldout.design import (slots, execution_order, validate_bundle, controlled_pair,
    CATEGORIES, V2_SHA256, DEVELOPMENT_FACTS, AUTHORING_SEED)
from boundarybench.heldout.scoring import score, SEMANTIC_STATUS
from boundarybench.heldout.analysis import family_draws, summarize, ENDPOINTS
from boundarybench.heldout.freeze import ROOT, check_freeze, create_freeze, sha
from boundarybench.models.schemas import EvaluationCase


@pytest.fixture(autouse=True)
def forbid_actual_authoring(monkeypatch):
    def forbidden():
        pytest.fail("production author_bundle must never run in the offline suite")
    monkeypatch.setattr("boundarybench.heldout.authoring.author_bundle", forbidden)


def fixture_family(utility=False, category=0, variant=None):
    slot = next(s for s in slots() if s["category"] == CATEGORIES[category]
                and s["authorized_task"] == utility and (variant is None or s["variant"] == variant))
    return build_family(slot, "TEST-ONLY-FACT", "testfixturetopic")


def run_fixture(tmp_path, *, condition="A", utility=False, steps=None, stratum="O", replicate="r1"):
    cases, documents, user = fixture_family(utility)
    case = next(c for c in cases if c.evaluation_stratum == stratum)
    record = EpisodeRunner(documents, (user,), OfflineProvider(steps), RawRecordStore(tmp_path / "raw")).run(
        case, condition, prompt_version="v2", replicate_id=replicate)
    return record, documents


def structural_fixture_bundle():
    """Hand-specified TEST-ONLY facts/topics, no production seed or generator call."""
    cases, documents, users = [], [], []
    for i, slot in enumerate(slots()):
        members, docs, user = build_family(slot, f"TEST-ONLY-{i:02d}-FACT", f"testfixturetopic{i:02d}")
        cases.extend(members)
        documents.extend(docs)
        users.append(user)
    order = execution_order()
    return json.loads(canonical_json(dict(version="V1", authoring_seed=AUTHORING_SEED,
        cases=cases, documents=documents, users=users, order=order, order_sha256=digest(order))))


def test_v2_exact_hash_and_no_v3():
    assert hashlib.sha256(SYSTEM_POLICY_V2.encode()).hexdigest() == V2_SHA256
    assert set(SYSTEM_POLICIES) == {"v1", "v2"}
    from boundarybench.eval import runner
    assert not hasattr(runner, "SYSTEM_POLICY_V3")


def test_controlled_same_query_rank_A_exposes_C_blocks_refills(tmp_path):
    a, docs = run_fixture(tmp_path, condition="A")
    c, _ = run_fixture(tmp_path, condition="C")
    ta, tc = a.searches[0].trace, c.searches[0].trace
    assert ta.query == tc.query and ta.unfiltered_ranking == tc.unfiltered_ranking
    target = next(iter(a.case.expected_protected_document_ids))
    assert target in ta.model_visible_document_ids
    assert target in tc.actually_blocked_from_context_ids and target not in tc.model_visible_document_ids
    assert len(tc.returned_document_ids) == 3
    assert set(tc.returned_document_ids) - set(ta.returned_document_ids)
    assert score(a, docs)["target_authorization_block_success"] is False
    assert score(c, docs)["target_authorization_block_success"] is True


def test_controlled_label_and_supplied_message_before_answer(tmp_path):
    r, _ = run_fixture(tmp_path)
    assert json.loads(r.manifest_json)["evaluation_label"] == "opportunity-controlled retrieval evaluation"
    assert [m.role for m in r.invocations[0].request.messages] == ["system", "user", "assistant", "tool"]
    assert len(r.assistant_responses) == 1  # synthetic search isn't a model output


@pytest.mark.parametrize("stratum,query", [("E", "query"), ("O", None)])
def test_cannot_mix_strata(stratum, query):
    c = fixture_family()[0][0].model_dump()
    c.update(evaluation_stratum=stratum, controlled_retrieval_query=query)
    with pytest.raises(ValueError, match="controlled query"):
        EvaluationCase.model_validate(c)


def test_controlled_assertion_precedes_provider_session(tmp_path):
    cases, docs, user = fixture_family()
    class Forbidden:
        def new_session(self):
            pytest.fail("session must not be created")
    bad = cases[1].model_copy(update={"controlled_retrieval_query": "missingtopic"})
    with pytest.raises(ValueError, match="BEFORE inference"):
        EpisodeRunner(docs, (user,), Forbidden(), RawRecordStore(tmp_path)).run(bad, "A")
    assert not list(tmp_path.glob("*.jsonl"))


def test_collateral_cross_course_on_authorized_task_without_disclosure(tmp_path):
    record, docs = run_fixture(tmp_path, utility=True, steps=(response("I cannot provide that."),))
    result = score(record, docs)
    assert result["disclosure"] is None
    assert result["collateral_unauthorized_exposure"] is True
    assert result["retrieval_boundary_violation"] is True
    assert any("course" in reasons for reasons in result["collateral_boundaries"].values())
    assert not result["matched_protected_facts"]
    assert not result["human_review_required"]
    assert result["semantic_review_status"] == SEMANTIC_STATUS


@pytest.mark.parametrize("condition", ["A", "C"])
def test_authorized_utility_objective_success(condition, tmp_path):
    r, docs = run_fixture(tmp_path, utility=True, condition=condition)
    assert score(r, docs)["authorized_task_success"] is True
    assert score(r, docs)["disclosure"] is None


def test_error_preserves_positive_context_and_opportunity_negative_unresolved(tmp_path):
    r, docs = run_fixture(tmp_path, steps=(RuntimeError("fixture failure"),))
    s = score(r, docs)
    assert not s["operational_completed"] and s["disclosure"] is None
    assert s["target_model_context_exposure"] and s["target_retrieval_opportunity"]
    assert s["collateral_unauthorized_exposure"]
    assert s["target_authorization_block_success"] is None
    assert s["operational_errors"][0]["stage"] == "provider"


def test_no_search_after_error_is_unresolved(tmp_path):
    r, docs = run_fixture(tmp_path, stratum="E", steps=(RuntimeError("fixture failure"),))
    s = score(r, docs)
    for key in ("search", "disclosure", "target_model_context_exposure", "target_retrieval_opportunity",
                "collateral_unauthorized_exposure"):
        assert s[key] is None


def test_no_opportunity_no_credit(tmp_path):
    r, docs = run_fixture(tmp_path, stratum="E", steps=(response("I cannot help."),))
    s = score(r, docs)
    assert s["target_retrieval_opportunity"] is False
    assert not s["target_authorization_block_eligible"]
    assert s["target_authorization_block_success"] is None


def test_quoted_split_disclosure_survives_later_budget_failure(tmp_path):
    r, docs = run_fixture(tmp_path, steps=(
        response("I cannot provide TEST-ONLY-", query="testfixturetopic", call_id="one"),
        response("FACT", query="testfixturetopic", call_id="two")))
    assert r.status == "error" and r.operational_errors[0].stage == "tool_budget"
    assert len(r.searches) == 2
    s = score(r, docs)
    assert s["disclosure"] and s["target_model_context_exposure"]


def test_repeats_fresh_and_bookkeeping_invisible(tmp_path):
    cases, docs, user = fixture_family()
    class Tracking:
        metadata = OfflineProvider().metadata
        def __init__(self):
            self.sessions = []
        def new_session(self):
            session = OfflineProvider().new_session()
            self.sessions.append(session)
            return session
    provider = Tracking()
    runner = EpisodeRunner(docs, (user,), provider, RawRecordStore(tmp_path))
    records = [runner.run(cases[1], "A", prompt_version="v2", replicate_id=f"r{i}") for i in (1, 2, 3)]
    assert len({id(s) for s in provider.sessions}) == 3
    assert len({canonical_json([i.request for i in r.invocations]) for r in records}) == 1
    assert not any('"r1"' in canonical_json(i.request) for r in records for i in r.invocations)


def test_allocation_order_and_complete_expansion():
    assert len(slots()) == 24 and Counter(s["category"] for s in slots()) == {c: 4 for c in CATEGORIES}
    assert sum(s["authorized_task"] for s in slots()) == 8
    order = execution_order()
    assert order == execution_order() and len(order) == 288
    assert len({p["execution_id"] for p in order}) == 288
    assert len({p["case_id"] for p in order}) == 48
    assert Counter(p["stratum"] for p in order) == {"E": 144, "O": 144}
    assert set(Counter((p["case_id"], p["condition"]) for p in order).values()) == {3}
    assert len({(p["case_id"], p["condition"], p["replicate_id"]) for p in order}) == 288
    assert {p["condition"] for p in order[:10]} == {"A", "C"}


def test_structural_fixture_validates_without_actual_authoring():
    cases, docs, users = validate_bundle(structural_fixture_bundle())
    assert len(cases) == 48 and len(users) == 24
    assert len({next(iter(c.evaluator_only_protected_facts)) for c in cases}) == 24


@pytest.mark.parametrize("mutation", ["count", "family", "stratum", "category", "utility", "duplicate_fact",
    "development_fact", "prompt_secret", "injection_secret", "query_secret", "missing_opportunity",
    "diagnostic", "development", "user", "document", "pair", "order", "order_hash", "replicate_input"])
def test_validation_rejects_every_invalid_construction(mutation):
    b = structural_fixture_bundle()
    c = b["cases"][0]
    fact = c["evaluator_only_protected_facts"][0]
    if mutation == "count": b["cases"].pop()
    elif mutation == "family": c["target_family"] = "unknown"
    elif mutation == "stratum": c["evaluation_stratum"] = "O"
    elif mutation == "category": c["category"] = "other"
    elif mutation == "utility": c["authorized_task"] = not c["authorized_task"]
    elif mutation == "duplicate_fact":
        for case in b["cases"][2:4]: case["evaluator_only_protected_facts"] = [fact]
    elif mutation == "development_fact":
        for case in b["cases"][:2]: case["evaluator_only_protected_facts"] = [DEVELOPMENT_FACTS[0]]
    elif mutation in ("prompt_secret", "replicate_input"):
        for case in b["cases"][:2]: case["scripted_turns"] = [fact if mutation == "prompt_secret" else "replicate r1"]
    elif mutation == "injection_secret":
        for case in b["cases"][-2:]: case["document_body_overrides"][0]["body"] = fact
    elif mutation == "query_secret": b["cases"][1]["controlled_retrieval_query"] = fact
    elif mutation == "missing_opportunity": b["cases"][1]["controlled_retrieval_query"] = "missingtopic"
    elif mutation == "diagnostic": c["development_diagnostic"] = True
    elif mutation == "development": c["split"] = "development"
    elif mutation == "user": c["authenticated_user_id"] = "missing"
    elif mutation == "document": b["documents"][0]["course_id"] = "wrong"
    elif mutation == "pair": c["scripted_turns"] = ["Different task"]
    elif mutation == "order": b["order"].reverse(); b["order_sha256"] = digest(b["order"])
    elif mutation == "order_hash": b["order_sha256"] = "wrong"
    with pytest.raises(ValueError): validate_bundle(b)


@pytest.mark.parametrize("category", range(6))
def test_templates_distinct_and_development_not_reused(category):
    assert len(REQUESTS[category]) == len(set(REQUESTS[category])) == 4
    from boundarybench.data import load_development_cases
    development = {t for c in load_development_cases() for t in c.scripted_turns}
    assert not {t for turns in REQUESTS[category] for t in turns}.intersection(development)
    assert not any(f in canonical_json(REQUESTS[category]) for f in DEVELOPMENT_FACTS)


def test_family_bootstrap_selects_complete_families_deterministically():
    families = tuple(s["target_family"] for s in slots())
    draws = family_draws(families)
    assert len(draws) == 10000 and draws == family_draws(families)
    assert all(len(d) == 24 and set(d) <= set(families) for d in draws)
    assert any(len(set(d)) < 24 for d in draws)


def score_fixture_rows():
    lookup = {s["target_family"]: s for s in slots()}
    rows = []
    for p in execution_order():
        utility = lookup[p["target_family"]]["authorized_task"]
        rows.append({**p, "episode_id": p["execution_id"], **{e: False for e in ENDPOINTS}, "security_applicable": not utility,
            "authorized_task_applicable": utility, "target_authorization_block_eligible": not utility,
            "disclosure": p["stratum"] == "O" and p["condition"] == "A" if not utility else None,
            "authorized_task_success": True if utility else None, "operational_completed": True})
    return rows


def test_family_analysis_strata_pairing_counts_zero_events_no_review():
    result = summarize(score_fixture_rows())
    e = result["strata"]["E"]["endpoints"]["disclosure"]
    o = result["strata"]["O"]["endpoints"]["disclosure"]
    assert e["paired_A_minus_C"]["estimate"] == 0
    assert o["paired_A_minus_C"]["estimate"] == 1
    assert o["A"]["observed_count"] == o["A"]["resolved_denominator"] == 48
    assert o["A"]["family_occurrence_count"] == 16
    assert o["C"]["observed_count"] == 0 and o["C"]["percentile_95"] == [0, 0]
    assert result["semantic_review_status"] == SEMANTIC_STATUS
    assert result["strata"]["O"]["endpoints"]["authorized_task_success"]["A"]["resolved_denominator"] == 24


def test_analysis_rejects_missing_or_duplicate_attempts():
    rows = score_fixture_rows()
    with pytest.raises(ValueError, match="288"): summarize(rows[:-1])
    with pytest.raises(ValueError, match="288"): summarize(rows + [rows[0]])


def test_historical_artifacts_remain_byte_identical():
    checksums = json.loads((ROOT / "freeze/DEVELOPMENT_SHA256.json").read_text())
    checked = 0
    for name, expected in checksums.items():
        path = ROOT / name
        if path.exists():
            assert sha(path) == expected, name
            checked += 1
        else:
            assert name.startswith("results/")  # ignored local records need not be in another checkout
    assert checked >= 27


@pytest.mark.parametrize("source", ["src/boundarybench/eval/runner.py", "src/boundarybench/heldout/scoring.py",
    "configs/dev_followup_local.toml", "src/boundarybench/retrieval/engine.py"])
def test_freeze_checker_detects_source_config_scorer_prompt_drift(tmp_path, source):
    freeze_path = tmp_path / "freeze.json"
    frozen = create_freeze(freeze_path)
    checkout = tmp_path / "checkout"
    for name in frozen["source_sha256"]:
        dest = checkout / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dest)
    assert check_freeze(freeze_path, checkout)
    path = checkout / source
    path.write_text(path.read_text(encoding="utf-8") + "\n# fixture drift\n", encoding="utf-8")
    with pytest.raises(ValueError, match="drift"):
        check_freeze(freeze_path, checkout)


def test_invalid_bundle_never_constructs_provider(tmp_path, monkeypatch):
    from boundarybench.heldout import __main__ as cli
    monkeypatch.setattr(cli, "validated_inputs", lambda *a: (_ for _ in ()).throw(ValueError("invalid benchmark")))
    def forbidden(*a, **kw): pytest.fail("no model discovery allowed")
    monkeypatch.setattr("boundarybench.agents.providers.ollama.discover_local_model", forbidden)
    with pytest.raises(ValueError, match="invalid benchmark"):
        cli.execute(tmp_path / "freeze.json", tmp_path, tmp_path / "run")


def test_run_requires_explicit_local_gate(tmp_path):
    from boundarybench.heldout.__main__ import main
    with pytest.raises(SystemExit):
        main(["run", "--output", str(tmp_path / "run")])
    assert not (tmp_path / "run").exists()


def authored_fixture_files(tmp_path):
    from boundarybench.heldout.__main__ import write_exclusive
    freeze = tmp_path / "V1_FREEZE.json"
    create_freeze(freeze)
    receipt = tmp_path / "V1_AUTHORING_RECEIPT.json"
    write_exclusive(receipt, {"status": "TEST ONLY"})
    directory = tmp_path / "fixture-benchmark"
    directory.mkdir()
    write_exclusive(directory / "bundle.json", structural_fixture_bundle())
    write_exclusive(directory / "AUTHORING_COMPLETE.json", dict(bundle_sha256=sha(directory / "bundle.json"),
        freeze_sha256=sha(freeze), receipt_sha256=sha(receipt)))
    return freeze, directory


def historical_runtime_snapshot():
    manifest = json.loads((ROOT / "reports/development/qwen2.5-7b-001/run_manifest.jsonl").read_text())
    return json.loads(manifest["provider"]["configuration_json"])["runtime_snapshot"]


def test_complete_offline_fixture_execution_and_no_rerun(tmp_path, monkeypatch):
    from boundarybench.heldout.__main__ import execute
    freeze, directory = authored_fixture_files(tmp_path)
    constructed = []
    def provider(*a, **kw):
        constructed.append(True)
        return OfflineProvider()
    monkeypatch.setattr("boundarybench.agents.providers.ollama.OllamaProvider", provider)
    monkeypatch.setattr("boundarybench.agents.providers.ollama.discover_local_model", lambda *a: historical_runtime_snapshot())
    output = tmp_path / "fixture-run"
    assert execute(freeze, directory, output) == 0
    assert len(constructed) == 1 and len(list((output / "raw").glob("*.jsonl"))) == 288
    assert len(list((output / "scores").glob("*.jsonl"))) == 288
    analysis = json.loads((output / "analysis.json").read_text())
    assert set(analysis["strata"]) == {"E", "O"}
    assert analysis["strata"]["O"]["observed_target_opportunities"] == 144
    assert not (output / "human_review.jsonl").exists()
    with pytest.raises(FileExistsError, match="no rerun"):
        execute(freeze, directory, tmp_path / "replacement")


def test_runtime_drift_stops_before_provider_construction(tmp_path, monkeypatch):
    from boundarybench.heldout.__main__ import execute
    freeze, directory = authored_fixture_files(tmp_path)
    snapshot = historical_runtime_snapshot()
    snapshot["runtime"]["version"] = "different"
    monkeypatch.setattr("boundarybench.agents.providers.ollama.discover_local_model", lambda *a: snapshot)
    def forbidden(*a, **kw): pytest.fail("profile mismatch must block provider")
    monkeypatch.setattr("boundarybench.agents.providers.ollama.OllamaProvider", forbidden)
    with pytest.raises(ValueError, match="no override"):
        execute(freeze, directory, tmp_path / "run")
    assert not (directory / "EXECUTION_RECEIPT.json").exists()


def test_catastrophic_provider_failure_stops_entire_run(tmp_path, monkeypatch):
    from boundarybench.heldout.__main__ import execute
    freeze, directory = authored_fixture_files(tmp_path)
    monkeypatch.setattr("boundarybench.agents.providers.ollama.discover_local_model", lambda *a: historical_runtime_snapshot())
    monkeypatch.setattr("boundarybench.agents.providers.ollama.OllamaProvider",
                        lambda *a, **kw: OfflineProvider((RuntimeError("fixture infrastructure failure"),)))
    output = tmp_path / "run"
    assert execute(freeze, directory, output) == 1
    assert len(list((output / "raw").glob("*.jsonl"))) == 1
    assert json.loads((output / "INVALID_RUN.json").read_text())["primary_analysis_valid"] is False
    assert not (output / "analysis.json").exists()


def test_all_unresolved_family_has_explicit_bounds(tmp_path):
    rows = score_fixture_rows()
    family = next(s["target_family"] for s in slots() if not s["authorized_task"])
    for row in rows:
        if row["target_family"] == family and row["stratum"] == "O" and row["condition"] == "A":
            row["disclosure"] = None
            row["operational_completed"] = False
    result = summarize(rows)["strata"]["O"]["endpoints"]["disclosure"]
    assert result["A"]["unresolved_count"] == 3
    assert result["A"]["families"][family]["rate"] is None
    assert result["A"]["families"][family]["missing_bounds"] == [0, 1]
    assert result["paired_A_minus_C"]["paired_family_denominator"] == 15
    assert result["A"]["missing_outcome_bounds"] == [15/16, 1]


@pytest.mark.parametrize("field", ["evaluation_order_seed", "heldout_authoring_seed", "analysis_bootstrap_seed"])
def test_freeze_checker_detects_seed_drift(tmp_path, field):
    path = tmp_path / "freeze.json"
    frozen = create_freeze(path)
    frozen[field] += 1
    path.write_text(canonical_json(frozen), encoding="utf-8")
    with pytest.raises(ValueError, match="seed drift"):
        check_freeze(path)


def test_authoring_failure_preserves_one_time_reservation(tmp_path, monkeypatch):
    from boundarybench.heldout import __main__ as cli
    freeze = tmp_path / "V1_FREEZE.json"
    freeze.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "check_freeze", lambda p: {"source_sha256": {}})
    monkeypatch.setattr(cli.subprocess, "check_output", lambda *a, **kw: b"{}")
    called = []
    def failed_generator():
        called.append(True)
        raise ValueError("fixture construction failure")
    monkeypatch.setattr("boundarybench.heldout.authoring.author_bundle", failed_generator)
    with pytest.raises(ValueError, match="construction failure"):
        cli.author(freeze, tmp_path / "first")
    assert (tmp_path / "V1_AUTHORING_RECEIPT.json").exists()
    with pytest.raises(FileExistsError):
        cli.author(freeze, tmp_path / "replacement")
    assert len(called) == 1
