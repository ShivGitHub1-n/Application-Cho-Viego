from __future__ import annotations

import argparse

from resume_tailor.infrastructure.config import Settings
from resume_tailor.infrastructure.gemini_canary import (
    GeminiIsolationMode,
    run_structured_output_canary,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one manual-only Gemini structured-output isolation request."
    )
    parser.add_argument(
        "--mode",
        choices=[mode.value for mode in GeminiIsolationMode],
        default=GeminiIsolationMode.MINIMAL.value,
    )
    arguments = parser.parse_args()
    result = run_structured_output_canary(
        Settings(),
        mode=GeminiIsolationMode(arguments.mode),
    )
    print(result.model_dump_json(indent=2, exclude_none=True))
    succeeded = result.schema_valid
    if result.mode is GeminiIsolationMode.MINIMAL_PRODUCTION_WRITER:
        succeeded = all(
            (
                result.request_count == 1,
                result.candidate_count > 0,
                result.text_present,
                result.json_parsed,
                result.provider_contract_validated,
                result.evidence_ids_mapped,
                result.internal_variant_reconstructed,
                result.grounding_validation_reached,
                result.grounding_validation_passed,
                result.issue is None,
            )
        )
    return 0 if succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
