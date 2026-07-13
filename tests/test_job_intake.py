import pytest

from resume_tailor.application.job_intake import (
    InvalidJobDescriptionError,
    build_job_posting,
    normalize_job_description,
)


def test_job_description_normalization_preserves_paragraphs_and_lists() -> None:
    assert normalize_job_description("  Build systems\r\n\r\n- Python  \r\n- Testing\n") == (
        "  Build systems\n\n- Python\n- Testing"
    )


def test_empty_job_description_is_rejected() -> None:
    with pytest.raises(InvalidJobDescriptionError):
        normalize_job_description(" \r\n\n ")
    with pytest.raises(InvalidJobDescriptionError):
        build_job_posting("posting", "Engineer", "\n")


def test_build_job_posting_uses_normalized_existing_planning_input() -> None:
    posting = build_job_posting("posting", " Engineer ", "Build systems\r\n\r\n- Test")
    assert posting.title == "Engineer"
    assert posting.description == "Build systems\n\n- Test"
