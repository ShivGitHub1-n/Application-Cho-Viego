from resume_tailor.application.job_intake import build_job_posting
from resume_tailor.domain.models import RoleFamily
from resume_tailor.infrastructure.optimization import MultiRoleOpportunityAnalyzer


def test_multi_role_opportunity_analyzer_preserves_optimizer_role_classification():
    posting = build_job_posting(
        "posting-1",
        "Applied AI Research Engineer",
        "Develop transformer models and evaluate multimodal reasoning systems.",
    )

    result = MultiRoleOpportunityAnalyzer().analyze(posting)

    assert result.role_family == RoleFamily.AI_ML_MULTIMODAL.value
    assert result.supported is True
    assert result.signals
