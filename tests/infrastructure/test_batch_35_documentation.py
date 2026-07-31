from pathlib import Path


def test_batch_35_plan_states_current_ten_source_cohort() -> None:
    plan = Path(
        "docs/superpowers/plans/2026-07-24-jobs-autonomous-company-discovery.md"
    ).read_text(encoding="utf-8")

    assert "exactly the ten active companies" in plan
