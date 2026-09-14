"""Explicitly gated small DEVELOPMENT ONLY pilot; never a held-out entry point."""

import argparse
import os
from pathlib import Path
import secrets
import sys
import tomllib
from typing import Literal

from pydantic import Field, model_validator

from boundarybench.agents.providers.openai import OpenAIConfig, OpenAIProvider, OpenAISettings
from boundarybench.agents.providers.ollama import OllamaProvider, discover_local_model
from boundarybench.data import DOCUMENTS, USERS, load_development_cases
from boundarybench.eval.dev_audit import export_development_audit, export_development_report
from boundarybench.eval.records import RawRecordStore, canonical_json, digest, write_jsonl_exclusive
from boundarybench.eval.review import export_human_review
from boundarybench.eval.runner import EpisodeRunner, now
from boundarybench.eval.scoring import score_episode
from boundarybench.models.diagnostics import DiagnosticMode
from boundarybench.models.llm import FrozenModel, ProviderError
from boundarybench.retrieval.engine import Condition


WARNING = "DEVELOPMENT RUN — NOT HELD-OUT RESEARCH RESULTS"
ACCEPTANCE_PATH = Path(__file__).resolve().parents[2] / "docs" / "development_pilot.md"


class Budgets(FrozenModel):
    max_results: int = Field(default=3, ge=1, le=3)
    max_searches_per_turn: int = Field(default=2, ge=1, le=2)
    max_model_iterations_per_turn: int = Field(default=3, ge=1, le=3)


class DiagnosticSelection(FrozenModel):
    case_id: str
    condition: Literal["A"] = "A"
    mode: Literal["no-policy", "empty-context", "deny-all"]


class PilotManifest(FrozenModel):
    development_only: Literal[True]
    conditions: tuple[Literal["A", "C", "D"], Literal["A", "C", "D"]]
    case_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    diagnostics: tuple[DiagnosticSelection, ...] = Field(min_length=3, max_length=3)
    provider_settings: OpenAISettings
    budgets: Budgets

    @model_validator(mode="after")
    def small_development_plan(self):
        if set(self.conditions) not in ({"A", "C"}, {"A", "D"}):
            raise ValueError("select A and exactly one external condition C or D")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("duplicate pilot case")
        if {d.mode for d in self.diagnostics} != {"no-policy", "empty-context", "deny-all"}:
            raise ValueError("select each of the three diagnostics once")
        return self


class PlannedEpisode(FrozenModel):
    case_id: str
    condition: Condition
    diagnostic_mode: DiagnosticMode = DiagnosticMode.NORMAL


def load_plan(path: Path):
    source = path.read_text(encoding="utf-8")
    manifest = PilotManifest.model_validate(tomllib.loads(source))
    cases = {case.case_id: case for case in load_development_cases()}
    plan = tuple(PlannedEpisode(case_id=case_id, condition=condition)
                 for case_id in manifest.case_ids for condition in manifest.conditions) + tuple(
        PlannedEpisode(case_id=d.case_id, condition=d.condition, diagnostic_mode=d.mode)
        for d in manifest.diagnostics
    )
    for item in plan:
        if item.case_id not in cases or cases[item.case_id].split != "development":
            raise ValueError("pilot accepts only known development cases: " + item.case_id)
    return source, manifest, cases, plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=WARNING)
    parser.add_argument("--provider", choices=("openai", "ollama"), required=True)
    parser.add_argument("--model", required=True, help="explicit Chat Completions model supporting the recorded settings")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-live-api", action="store_true", help="explicit authorization for paid live requests")
    parser.add_argument("--allow-local-model", action="store_true", help="explicit authorization for local Ollama inference")
    args = parser.parse_args(argv)
    print("\n" + "=" * 72 + "\n" + WARNING + "\n" + "=" * 72, flush=True)
    try:
        source, manifest, cases, plan = load_plan(args.manifest)
        config = OpenAIConfig(model=args.model, **manifest.provider_settings.model_dump())
        if args.output.exists():
            raise FileExistsError("refusing existing output directory: " + str(args.output))
        max_calls = sum(len(cases[p.case_id].scripted_turns) for p in plan) * manifest.budgets.max_model_iterations_per_turn
        normal_count = sum(item.diagnostic_mode == DiagnosticMode.NORMAL for item in plan)
        print(f"Planned episodes: {len(plan)} ({normal_count} normal + {len(plan) - normal_count} diagnostics).", flush=True)
        print(f"Provider: {args.provider}; model: {config.model}", flush=True)
        print(f"Settings: {canonical_json(config)}", flush=True)
        print(f"Upper bounds: {max_calls} model invocations; {max_calls * (1 + config.max_retries)} HTTP attempts including retries.", flush=True)
        local = args.provider == "ollama"
        allowed = args.allow_local_model if local else args.allow_live_api
        required_flag = "--allow-local-model" if local else "--allow-live-api"
        if not allowed:
            print(f"No requests made. Explicit {required_flag} authorization is required.", flush=True)
            return 2
        if not local and not os.environ.get("OPENAI_API_KEY", "").strip():
            raise ValueError("OPENAI_API_KEY is not configured; no requests made")
        acceptance = ACCEPTANCE_PATH.read_text(encoding="utf-8")
        provider = (OllamaProvider(config, runtime_snapshot=discover_local_model(config.model))
                    if local else OpenAIProvider(config))
        run_manifest = {
            "development_only": True, "warning": WARNING, "created_at": now(),
            "provider": provider.metadata, "pilot_manifest_source": source,
            "resolved_configuration": manifest, "episodes": plan, "planned_episode_count": len(plan),
            "max_model_invocations": max_calls, "max_http_attempts": max_calls * (1 + config.max_retries),
            "acceptance_criteria_source": acceptance, "acceptance_criteria_hash": digest(acceptance),
            "selected_cases": tuple(cases[case_id] for case_id in dict.fromkeys(p.case_id for p in plan)),
            "base_corpus": DOCUMENTS, "users": USERS,
            "human_review_status": "pending", "allow_live_api": args.allow_live_api,
            "allow_local_model": args.allow_local_model,
        }
        args.output.mkdir(parents=True, exist_ok=False)
        write_jsonl_exclusive(args.output / "run_manifest.jsonl", [run_manifest])
        private = args.output / "private"
        private.mkdir()
        key = secrets.token_bytes(32)
        with (private / "review_blinding_key.hex").open("x", encoding="utf-8") as handle:
            handle.write(key.hex() + "\n")
        runner = EpisodeRunner(DOCUMENTS, USERS, provider, RawRecordStore(args.output / "raw"), **manifest.budgets.model_dump())
        records = []
        for index, item in enumerate(plan, 1):
            print(f"Episode {index}/{len(plan)}: {item.case_id} {item.condition.value} / {item.diagnostic_mode.value}", flush=True)
            records.append(runner.run(cases[item.case_id], item.condition, item.diagnostic_mode))
            print(f"  {records[-1].status}", flush=True)
        records = tuple(records)
        scores = tuple(score_episode(record) for record in records)
        write_jsonl_exclusive(args.output / "auto_scores.jsonl", [s for s in scores if s.diagnostic_mode == DiagnosticMode.NORMAL])
        write_jsonl_exclusive(args.output / "diagnostic_auto_scores.jsonl", [s for s in scores if s.diagnostic_mode != DiagnosticMode.NORMAL])
        export_human_review(records, args.output / "human_review.jsonl",
                            private_mapping_path=private / "review_mapping.jsonl", blinding_key=key)
        export_development_audit(records, private / "development_audit.jsonl")
        export_development_report(records, run_manifest, private / "DEVELOPMENT_PILOT_REPORT.md")
        errors = sum(record.status == "error" for record in records)
        print(f"Development episodes attempted: {len(records)}; completed: {len(records) - errors}; errors: {errors}.", flush=True)
        print("Human review pending. Share only human_review.jsonl with initial reviewers.", flush=True)
        return 1 if errors else 0
    except (OSError, ValueError, ProviderError) as exc:
        print(f"Development pilot stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
