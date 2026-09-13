from boundarybench.data import DOCUMENTS, USERS
from boundarybench.replay import OfflineReplay
from boundarybench.retrieval.engine import Condition, RetrievalHarness


def test_replay_state_isolated_between_episodes():
    replay = OfflineReplay(RetrievalHarness(DOCUMENTS))
    first = replay.run_searches("one", USERS[0], Condition.B, ("apple",))
    second = replay.run_searches("two", USERS[2], Condition.B, ("apple",))
    assert first.case_id == "one"
    assert second.case_id == "two"
    assert first.user_id != second.user_id
    assert len(first.searches) == len(second.searches) == 1
