from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from resume_tailor.application.plan_validation import PlanIntegrityError
from resume_tailor.domain.models import (
    JobPosting,
    MasterProfile,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.infrastructure.dependencies import create_tailor_service


class HealthResponse(BaseModel):
    status: str
    service: str


class OptimizeRequest(BaseModel):
    profile: MasterProfile
    posting: JobPosting
    constraints: TemplateConstraints = Field(default_factory=TemplateConstraints)


class DocumentRequest(BaseModel):
    profile: MasterProfile
    plan: TailoringPlan
    approved_claim_ids: set[str] = Field(default_factory=set)


app = FastAPI(
    title="Resume Tailor API",
    version="0.1.0",
    description="Evidence-backed, strategy-first resume optimization service.",
)
_service = create_tailor_service()


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", service="resume-tailor")


@app.post("/optimization-plans", response_model=TailoringPlan, tags=["optimization"])
def create_optimization_plan(request: OptimizeRequest) -> TailoringPlan:
    return _service.create_plan(request.profile, request.posting, request.constraints)


@app.post("/resume-documents", response_model=StructuredResume, tags=["optimization"])
def build_resume_document(request: DocumentRequest) -> StructuredResume:
    if request.plan.profile_id != request.profile.id or request.plan.profile_version != request.profile.version:
        raise HTTPException(status_code=409, detail="The plan does not match the supplied profile version.")
    if request.plan.strategy is None:
        raise HTTPException(status_code=422, detail="The opportunity is outside the MVP's supported role family.")
    try:
        return _service.build_document(request.plan, request.profile, request.approved_claim_ids)
    except PlanIntegrityError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
