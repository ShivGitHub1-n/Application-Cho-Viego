from resume_tailor.application.workflow_state import invalidate_derived_workflow


def test_invalidate_derived_workflow_clears_stale_plan_resume_and_approval() -> None:
    state = {
        "profile": "master",
        "posting": "job",
        "plan": "old-plan",
        "resume": "old-resume",
        "generated_content_reviewed": True,
        "workflow_profile_fingerprint": "old-profile",
        "workflow_posting_fingerprint": "old-posting",
    }
    invalidate_derived_workflow(state)
    assert state == {"profile": "master", "posting": "job"}


def test_invalidate_derived_workflow_clears_cover_letter_state() -> None:
    state = {
        "profile": "master",
        "posting": "job",
        "cover_letter": "draft",
        "cover_letter_reviewed": True,
        "cover_letter_plan_fingerprint": "old-plan",
    }
    invalidate_derived_workflow(state)
    assert state == {"profile": "master", "posting": "job"}
