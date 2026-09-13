"""Offline development smoke run; deliberately no live-provider option."""

import argparse
from pathlib import Path
import secrets

from boundarybench.agents.offline import OfflineProvider
from boundarybench.data import DOCUMENTS, USERS, load_development_cases
from boundarybench.eval.records import RawRecordStore, write_jsonl_exclusive
from boundarybench.eval.review import export_human_review
from boundarybench.eval.runner import EpisodeRunner
from boundarybench.eval.scoring import score_episode
from boundarybench.metrics.aggregate import aggregate_by_condition
from boundarybench.retrieval.engine import Condition


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline control-logic smoke run, not empirical model results")
    parser.add_argument("--output", type=Path, required=True, help="new directory; existing paths are refused")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    runner = EpisodeRunner(DOCUMENTS, USERS, OfflineProvider(), RawRecordStore(args.output / "raw"))
    records = tuple(runner.run(case, condition) for case in load_development_cases() for condition in Condition)
    scores = tuple(score_episode(record) for record in records)
    write_jsonl_exclusive(args.output / "automatic_scores.jsonl", list(scores))
    write_jsonl_exclusive(args.output / "offline_metrics.jsonl", [{
        "label": "OFFLINE DOUBLE: control-logic outputs, not model research results",
        "scorer_version": scores[0].scorer_version, "by_condition": aggregate_by_condition(scores),
    }])
    key = secrets.token_bytes(32)
    write_jsonl_exclusive(args.output / "private_blinding_key.jsonl", [{"key_hex": key.hex()}])
    export_human_review(
        records, args.output / "human_review.jsonl",
        private_mapping_path=args.output / "private_review_mapping.jsonl", blinding_key=key,
    )
    print(f"Wrote {len(records)} offline fixture episodes to {args.output}. No live model was called.")


if __name__ == "__main__":
    main()
