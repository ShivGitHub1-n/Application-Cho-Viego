from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from resume_tailor.domain.job_discovery.queries import (
    APPROVED_EXPLORE_SECTORS,
    ExploreJobQuery,
)
from resume_tailor.domain.job_discovery.source_scheduling import select_due_sources
from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.dependencies import create_job_discovery_services
from resume_tailor.infrastructure.job_discovery_sqlite import (
    read_existing_source_runtime_states,
)
from resume_tailor.infrastructure.job_sources.registry import (
    SourceConfigurationError,
    compile_runtime_sources,
    load_company_source_registry,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resume-tailor-job-sources")
    parser.add_argument("--registry", type=Path, default=Path("config/approved-job-sources.json"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)
    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--source-id")
    refresh.add_argument("--all", action="store_true", dest="force_all")
    refresh.add_argument("--force", action="store_true")
    refresh.add_argument("--dry-run", action="store_true")
    subparsers.add_parser("health")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        registry = load_company_source_registry(
            args.registry, reference_date=datetime.now(UTC).date()
        )
        compiled = compile_runtime_sources(registry)
    except (OSError, SourceConfigurationError, ValueError):
        _write(
            {
                "status": "failed",
                "code": "source_plan_invalid",
                "message": "approved source registry is invalid",
            },
            args.format,
        )
        return 1

    all_by_id = {source.source_id: source for source in registry.list_all()}
    compiled_by_id = {source.source_id: source for source in compiled}
    if args.command == "health":
        payload = [
            {
                "source_id": source.source_id,
                "company_name": source.canonical_company_name,
                "mechanism": source.source_plan.mechanism.value,
                "enabled": source.enabled,
                "runnable": source.enabled and source.source_plan.audit_date is not None,
                "audit_version": source.source_plan.audit_version,
            }
            for source in sorted(registry.list_all(), key=lambda item: item.source_id)
        ]
        _write(payload, args.format)
        return 0

    settings = Settings(job_discovery_source_registry_path=args.registry)
    runtime_database = settings.app_data_directory / settings.profile_store_filename
    runtime_states = read_existing_source_runtime_states(
        runtime_database, [source.source_id for source in compiled]
    )

    if args.source_id is not None:
        source = all_by_id.get(args.source_id)
        if source is None:
            _write({"status": "failed", "code": "unknown_source"}, args.format)
            return 1
        if not source.enabled:
            _write(
                {"status": "failed", "code": "source_not_runnable", "source_id": args.source_id},
                args.format,
            )
            return 1
        selected_source = compiled_by_id.get(args.source_id)
        if selected_source is None:
            _write(
                {"status": "failed", "code": "source_not_runnable", "source_id": args.source_id},
                args.format,
            )
            return 1
        selected = [selected_source]
    elif args.force_all:
        selected = compiled
    else:
        selected = select_due_sources(
            compiled,
            runtime_states,
            now=datetime.now(UTC),
            max_sources=len(compiled),
            force=args.force,
        )
    if args.dry_run:
        _write(
            {
                "status": "dry_run",
                "source_ids": [source.source_id for source in selected],
                "forced": bool(args.force or args.source_id or args.force_all),
            },
            args.format,
        )
        return 0
    bundle = create_job_discovery_services(
        settings
    )
    try:
        if bundle.source_refresh is None:
            _write({"status": "failed", "code": "refresh_runtime_unavailable"}, args.format)
            return 1
        summary = bundle.source_refresh.refresh(
            ExploreJobQuery(
                sectors=list(APPROVED_EXPLORE_SECTORS),
                page_size=100,
                source_restrictions=(
                    [args.source_id] if args.source_id is not None else []
                ),
            ),
            force=args.force,
            force_source_id=args.source_id,
            force_all=args.force_all,
        )
        run_payload: dict[str, Any] = summary.model_dump(mode="json")
        run_payload["status"] = "partial" if summary.partial_success else "complete"
        _write(run_payload, args.format)
        if not summary.outcomes or all(item.status == "failed" for item in summary.outcomes):
            return 1
        return 0
    except (KeyError, ValueError, OSError):
        _write({"status": "failed", "code": "refresh_failed"}, args.format)
        return 1
    finally:
        bundle.close()


def _write(payload: object, output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                print(" ".join(f"{key}={value}" for key, value in sorted(item.items())))
    else:
        if isinstance(payload, dict):
            print(" ".join(f"{key}={value}" for key, value in sorted(payload.items())))


if __name__ == "__main__":
    raise SystemExit(main())
