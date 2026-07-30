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


@pytest.mark.parametrize(
    "description",
    [
        "Company: TITAN Haptics\nBuild hardware prototypes.",
        "Company\nTITAN Haptics\nBuild hardware prototypes.",
    ],
)
def test_build_job_posting_retains_explicit_company_metadata(description: str) -> None:
    posting = build_job_posting("posting", "Mechatronics Engineer", description)

    assert posting.company_name == "TITAN Haptics"


def test_explicit_company_input_overrides_labelled_posting_metadata() -> None:
    posting = build_job_posting(
        "posting",
        "Engineer",
        "Company: Posting Company\nBuild systems.",
        company_name=" Validated Opportunity Company ",
    )

    assert posting.company_name == "Validated Opportunity Company"
