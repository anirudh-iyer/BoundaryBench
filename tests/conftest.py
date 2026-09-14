import pytest
from urllib.request import OpenerDirector

from boundarybench.agents.offline import OfflineProvider
from boundarybench.data import DOCUMENTS, USERS, load_development_cases
from boundarybench.eval.records import RawRecordStore
from boundarybench.eval.runner import EpisodeRunner
from boundarybench.retrieval.engine import Condition


@pytest.fixture(autouse=True)
def block_live_http(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Live HTTP is forbidden in the offline test suite")
    monkeypatch.setattr(OpenerDirector, "open", forbidden)


@pytest.fixture
def cases():
    return {case.case_id: case for case in load_development_cases()}


@pytest.fixture
def run_episode(tmp_path, cases):
    def run(case_id="dev-answer-key", condition=Condition.B, steps=None, **options):
        return EpisodeRunner(
            DOCUMENTS, USERS, OfflineProvider(steps), RawRecordStore(tmp_path / "raw"), **options,
        ).run(cases[case_id], condition)
    return run
