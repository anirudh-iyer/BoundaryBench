"""Separate author/validate/run/analyze gates. No command runs implicitly."""

import argparse
import json
from pathlib import Path
import subprocess

from boundarybench.eval.records import canonical_json, write_jsonl_exclusive, RawRecordStore
from boundarybench.heldout.design import validate_bundle
from boundarybench.heldout.freeze import ROOT, check_freeze, sha


def write_exclusive(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as f:
        f.write(canonical_json(value) + "\n")


def author(freeze_path, output):
    freeze = check_freeze(freeze_path)
    relative = freeze_path.resolve().relative_to(ROOT).as_posix()
    committed = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:" + relative])
    if committed.replace(b"\r\n", b"\n") != freeze_path.read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("freeze must be committed before authoring")
    import hashlib
    for name, expected in freeze["source_sha256"].items():
        committed_source = subprocess.check_output(["git", "-C", str(ROOT), "show", "HEAD:" + name])
        normalized = committed_source.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != expected:
            raise ValueError("all frozen sources must be committed before authoring: " + name)
    if output.exists():
        raise FileExistsError("authoring output already exists")
    # Fixed receipt prevents rerunning the production generator to a new destination.
    receipt = freeze_path.with_name("V1_AUTHORING_RECEIPT.json")
    with receipt.open("x", encoding="utf-8") as reservation:
        reservation.write(canonical_json({"status": "reserved", "freeze_sha256": sha(freeze_path)}))
    from boundarybench.heldout.authoring import author_bundle
    bundle = author_bundle()
    if bundle["order_sha256"] != freeze["execution_order_sha256"]:
        raise ValueError("order changed")
    output.mkdir(parents=True, exist_ok=False)
    write_exclusive(output / "bundle.json", bundle)
    # Reservation is never rewritten, even on failure; completion is a second artifact.
    write_exclusive(output / "AUTHORING_COMPLETE.json", dict(bundle_sha256=sha(output / "bundle.json"),
        freeze_sha256=sha(freeze_path), receipt_sha256=sha(receipt), output=str(output.resolve())))


def validated_inputs(freeze_path, directory):
    freeze = check_freeze(freeze_path)
    completion = json.loads((directory / "AUTHORING_COMPLETE.json").read_text())
    if (completion["bundle_sha256"] != sha(directory / "bundle.json")
            or completion["freeze_sha256"] != sha(freeze_path)
            or completion["receipt_sha256"] != sha(freeze_path.with_name("V1_AUTHORING_RECEIPT.json"))):
        raise ValueError("authored benchmark/freeze receipt drift")
    bundle = json.loads((directory / "bundle.json").read_text())
    cases, documents, users = validate_bundle(bundle)
    if bundle["order_sha256"] != freeze["execution_order_sha256"]:
        raise ValueError("order not frozen")
    return freeze, bundle, cases, documents, users


def execute(freeze_path, directory, output):
    # Structural and file hash validation comes before runtime discovery or provider creation.
    freeze, bundle, cases, documents, users = validated_inputs(freeze_path, directory)
    if output.exists():
        raise FileExistsError("run output already exists")
    if (directory / "EXECUTION_RECEIPT.json").exists():
        raise FileExistsError("benchmark already reserved for execution; no rerun/replacement")
    from boundarybench.agents.providers.ollama import discover_local_model, OllamaProvider
    from boundarybench.agents.providers.openai import OpenAIConfig
    from boundarybench.live_dev import LocalModelProfile, profile_differences
    from boundarybench.eval.runner import EpisodeRunner
    from boundarybench.heldout.scoring import score
    from boundarybench.heldout.analysis import summarize
    profile = LocalModelProfile.model_validate({k: v for k, v in freeze["model"].items() if k != "base"})
    snapshot = discover_local_model(profile.model)
    differences = profile_differences(profile, "ollama", profile.model, snapshot)
    if differences:
        raise ValueError("runtime/model drift; no override: " + str(differences))
    provider = OllamaProvider(OpenAIConfig(model=profile.model, **freeze["sampling"]), runtime_snapshot=snapshot)
    write_exclusive(directory / "EXECUTION_RECEIPT.json", dict(freeze_sha256=sha(freeze_path),
        bundle_sha256=sha(directory / "bundle.json"), output=str(output.resolve())))
    output.mkdir(parents=True, exist_ok=False)
    write_exclusive(output / "run_manifest.json", dict(freeze_sha256=sha(freeze_path),
        bundle_sha256=sha(directory / "bundle.json"), order=bundle["order"], order_sha256=bundle["order_sha256"],
        provider=provider.metadata, human_review_status="omitted_from_deadline_constrained_primary_study"))
    runner = EpisodeRunner(documents, users, provider, RawRecordStore(output / "raw"))
    lookup = {c.case_id: c for c in cases}
    scores = []
    for item in bundle["order"]:
        check_freeze(freeze_path)
        if sha(directory / "bundle.json") != json.loads((directory / "AUTHORING_COMPLETE.json").read_text())["bundle_sha256"]:
            raise ValueError("benchmark changed during execution; stop entire run")
        record = runner.run(lookup[item["case_id"]], item["condition"], prompt_version="v2",
                            replicate_id=item["replicate_id"], execution_id=item["execution_id"])
        scores.append(score(record, documents))
        write_jsonl_exclusive(output / "scores" / (record.episode_id + ".jsonl"), [scores[-1]])
        # Conservative catastrophic definition, fixed before outcomes: provider or
        # setup failure stops the entire evaluation. Tool/protocol budget errors stay.
        if any(e.stage in ("provider", "setup") for e in record.operational_errors):
            write_exclusive(output / "INVALID_RUN.json", dict(reason="provider/setup infrastructure failure",
                failed_execution_id=record.episode_id, attempted=len(scores), primary_analysis_valid=False))
            return 1
    write_exclusive(output / "analysis.json", summarize(scores))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Frozen BoundaryBench V1; authoring and inference require separate commands")
    parser.add_argument("command", choices=("check", "author", "validate", "run", "analyze"))
    parser.add_argument("--freeze", type=Path, default=ROOT / "freeze/V1_FREEZE.json")
    parser.add_argument("--benchmark", type=Path, default=ROOT / "data/heldout/V1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-local-model", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "check":
        check_freeze(args.freeze)
    elif args.command == "author":
        author(args.freeze, args.benchmark)
    elif args.command == "validate":
        validated_inputs(args.freeze, args.benchmark)
    elif args.command == "run":
        if not args.allow_local_model or args.output is None:
            parser.error("run needs --allow-local-model and a new --output")
        return execute(args.freeze, args.benchmark, args.output)
    else:
        if args.output is None:
            parser.error("analyze needs the existing run --output")
        check_freeze(args.freeze)
        if (args.output / "INVALID_RUN.json").exists():
            raise ValueError("invalid run cannot enter primary analysis")
        from boundarybench.heldout.analysis import summarize
        rows = [json.loads(p.read_text()) for p in sorted((args.output / "scores").glob("*.jsonl"))]
        write_exclusive(args.output / "analysis.json", summarize(rows))
    print("Completed " + args.command + "; no inference unless explicitly running the run command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
