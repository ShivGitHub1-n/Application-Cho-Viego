from __future__ import annotations

from resume_tailor.domain.job_discovery.evidence import (
    EvidenceLedger,
    EvidenceQuality,
    RequirementCriticality,
    canonical_requirement_set,
)
from resume_tailor.domain.job_discovery.models import (
    JobRequirement,
    ProfileCapabilityEvidence,
    ProfileCapabilityIndex,
    RequirementCategory,
    RequirementImportance,
)


def test_overlapping_aliases_form_one_canonical_requirement() -> None:
    requirements = [
        JobRequirement(
            term="python",
            category=RequirementCategory.TECHNOLOGY,
            importance=RequirementImportance.REQUIRED,
            source_text="Python experience is required.",
            source_start=0,
            source_end=6,
        ),
        JobRequirement(
            term="python",
            category=RequirementCategory.TECHNOLOGY,
            importance=RequirementImportance.REQUIRED,
            source_text="Experience with Python services.",
            source_start=7,
            source_end=13,
        ),
    ]

    canonical = canonical_requirement_set(requirements)

    assert len(canonical) == 1
    assert canonical[0].criticality is RequirementCriticality.IMPORTANT
    assert canonical[0].aliases == ["python"]


def test_one_demonstrated_evidence_item_has_one_full_allocation() -> None:
    requirement = canonical_requirement_set(
        [
            JobRequirement(
                term="python",
                category=RequirementCategory.TECHNOLOGY,
                importance=RequirementImportance.REQUIRED,
                source_text="Python is required.",
                source_start=0,
                source_end=6,
            ),
            JobRequirement(
                term="api",
                category=RequirementCategory.TECHNOLOGY,
                importance=RequirementImportance.REQUIRED,
                source_text="API ownership is required.",
                source_start=7,
                source_end=10,
            ),
        ]
    )
    index = ProfileCapabilityIndex(
        terms={
            "python": [
                ProfileCapabilityEvidence(
                    source_type="confirmed_evidence",
                    source_id="e-python-api",
                    source_text="Built Python APIs",
                    demonstrated=True,
                )
            ],
            "api": [
                ProfileCapabilityEvidence(
                    source_type="confirmed_evidence",
                    source_id="e-python-api",
                    source_text="Built Python APIs",
                    demonstrated=True,
                )
            ],
        }
    )

    ledger = EvidenceLedger.allocate(requirement, index)
    allocations = [item for item in ledger.allocations if item.full_strength]

    assert len(allocations) == 1
    assert allocations[0].evidence_id == "e-python-api"
    assert sum(match.scored for match in ledger.matches) == 1
    assert EvidenceQuality.DEMONSTRATED in {match.evidence_quality for match in ledger.matches}
