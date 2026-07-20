from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from resume_tailor.application.generation_diagnostics import GenerationTelemetry
from resume_tailor.domain.generated_artifact import GenerationStage
from resume_tailor.domain.models import StructuredResume
from resume_tailor.domain.resume_composition import PageFitEvaluation
from resume_tailor.infrastructure.rendering import (
    DocxPageCountProvider,
    ExactDocxPageCountProvider,
    PageCountMeasurement,
    PageCountVerificationError,
    diagnose_docx_page_utilization,
)
from resume_tailor.infrastructure.static_template_docx import render_template_v1_resume
from resume_tailor.infrastructure.template_v1 import load_template_v1_layout_profile


class TemplateV1PageFitEvaluator:
    """Render an immutable composition candidate through production Template V1."""

    def __init__(
        self,
        page_count_provider: DocxPageCountProvider | None = None,
        telemetry: GenerationTelemetry | None = None,
    ) -> None:
        self._page_count_provider = page_count_provider or ExactDocxPageCountProvider()
        self._layout_profile = load_template_v1_layout_profile()
        self._telemetry = telemetry or GenerationTelemetry()

    def evaluate(
        self,
        resume: StructuredResume,
        *,
        attempt_exact: bool = True,
    ) -> PageFitEvaluation:
        with TemporaryDirectory(prefix="resume-composition-fit-") as directory:
            path = Path(directory) / f"candidate-{uuid4().hex}.docx"
            with self._telemetry.measure(GenerationStage.DOCX_RENDERING):
                self._telemetry.increment("docx_renders")
                render_template_v1_resume(resume, path)
            failure: str | None = None
            if attempt_exact:
                try:
                    with self._telemetry.measure(GenerationStage.EXACT_WORD_PAGINATION):
                        self._telemetry.increment("pagination_attempts")
                        measurement = self._page_count_provider.measure(path)
                except PageCountVerificationError as error:
                    failure = str(error)
                else:
                    if measurement.exact:
                        return self._exact_evaluation(path, measurement)
                    failure = (
                        f"Page-count provider {measurement.provider!r} returned "
                        f"{measurement.confidence!r} confidence instead of exact pagination."
                    )
            return self._estimated_evaluation(path, failure)

    def evaluate_batch(self, resumes: list[StructuredResume]) -> list[PageFitEvaluation]:
        """Render exact finalists and paginate them through one bounded provider session."""

        if not resumes:
            return []
        with TemporaryDirectory(prefix="resume-composition-finalists-") as directory:
            paths: list[Path] = []
            for index, resume in enumerate(resumes):
                path = Path(directory) / f"finalist-{index:02d}.docx"
                with self._telemetry.measure(GenerationStage.DOCX_RENDERING):
                    self._telemetry.increment("docx_renders")
                    render_template_v1_resume(resume, path)
                paths.append(path)
            try:
                with self._telemetry.measure(GenerationStage.EXACT_WORD_PAGINATION):
                    self._telemetry.increment("pagination_attempts")
                    batch_measure = getattr(self._page_count_provider, "measure_many", None)
                    measurements = (
                        batch_measure(paths)
                        if callable(batch_measure)
                        else [self._page_count_provider.measure(path) for path in paths]
                    )
            except PageCountVerificationError as error:
                return [self._estimated_evaluation(path, str(error)) for path in paths]
            if len(measurements) != len(paths):
                raise PageCountVerificationError(
                    "Exact page-count provider returned an incomplete finalist batch."
                )
            return [
                (
                    self._exact_evaluation(path, measurement)
                    if measurement.exact
                    else self._estimated_evaluation(
                        path,
                        (
                            f"Page-count provider {measurement.provider!r} returned "
                            f"{measurement.confidence!r} confidence instead of exact pagination."
                        ),
                    )
                )
                for path, measurement in zip(paths, measurements, strict=True)
            ]

    def _exact_evaluation(
        self,
        path: Path,
        measurement: PageCountMeasurement,
    ) -> PageFitEvaluation:
        diagnostic = diagnose_docx_page_utilization(
            path,
            self._layout_profile,
            measurement,
        )
        return PageFitEvaluation(
            status=diagnostic.status,
            page_count=measurement.page_count,
            exact=True,
            provider=measurement.provider,
            utilization_ratio=diagnostic.estimated_utilization_ratio,
            fits_one_page=measurement.page_count == 1,
        )

    def _estimated_evaluation(
        self,
        path: Path,
        failure: str | None,
    ) -> PageFitEvaluation:
        provider = "deterministic Template V1 occupancy estimate"
        provisional = PageCountMeasurement(
            page_count=1,
            provider=provider,
            confidence="estimated",
            exact=False,
        )
        with self._telemetry.measure(GenerationStage.ESTIMATED_PAGINATION_FALLBACK):
            diagnostic = diagnose_docx_page_utilization(
                path,
                self._layout_profile,
                provisional,
            )
        page_count = max(1, math.ceil(diagnostic.estimated_utilization_ratio))
        return PageFitEvaluation(
            status=diagnostic.status,
            page_count=page_count,
            exact=False,
            provider=provider,
            utilization_ratio=diagnostic.estimated_utilization_ratio,
            fits_one_page=diagnostic.estimated_utilization_ratio <= 1.0,
            verification_failure=failure,
        )


__all__ = ["TemplateV1PageFitEvaluator"]
