# ruff: noqa: E501
"""Build the independently authored validation proposal (cases 061-080)."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "job_discovery" / "benchmark"


def _evidence(profile_ref: str, rows: list[tuple[str, str, str, str, str, bool, list[str], list[str]]]) -> list[dict[str, Any]]:
    return [
        {
            "evidence_id": f"profile:{profile_ref}:{slug}",
            "statement": statement,
            "evidence_kind": kind,
            "evidence_quality": quality,
            "provenance": "independently reviewed validation profile",
            "demonstrated": demonstrated,
            "capabilities": capabilities,
            "technologies": technologies,
        }
        for slug, kind, statement, quality, _unused, demonstrated, capabilities, technologies in rows
    ]


PROFILES: dict[str, dict[str, Any]] = {
    "val-profile-01": {
        "summary": "Backend and data-platform engineer with production service ownership, relational modeling, cloud operations, and a bounded model-serving integration project.",
        "skills": ["Python", "Java", "FastAPI", "PostgreSQL", "Kafka", "Docker", "AWS", "Prometheus", "pytest"],
        "experience_years": 6.0,
        "education_summary": "Bachelor of Computer Engineering from a deidentified Canadian university.",
        "current_location": "Toronto, ON",
        "authorized_work_locations": ["Canada"],
        "requires_sponsorship": False,
        "professional_license_status": "confirmed_none",
        "clearance_status": "unknown",
        "items": [
            ("e1", "demonstrated", "Owned Python FastAPI services for shipment events, including API contracts, retries, and production incident follow-up.", "verified", "", True, ["API ownership", "service ownership"], ["Python", "FastAPI"]),
            ("e2", "demonstrated", "Designed PostgreSQL schemas and partitioned tables for order history used by several internal services.", "verified", "", True, ["relational database design"], ["PostgreSQL", "SQL"]),
            ("e3", "demonstrated", "Built Kafka-to-warehouse batch and streaming movement with replay checks and data-quality alerts.", "verified", "", True, ["batch movement", "streaming movement"], ["Kafka", "Python"]),
            ("e4", "demonstrated", "Deployed containerized services on AWS, maintained dashboards, and investigated two production incidents through recovery.", "verified", "", True, ["cloud deployment", "monitoring", "incident investigation"], ["AWS", "Docker", "Prometheus"]),
            ("e5", "demonstrated", "Maintained pytest and Java integration suites and worked with product and operations partners during release planning.", "verified", "", True, ["automated testing", "stakeholder collaboration"], ["pytest", "Java"]),
            ("e6", "transferable_demonstrated", "Connected a limited model-inference endpoint to a customer-support prototype but did not own model training or feature pipelines.", "verified", "", True, ["ML inference integration"], ["Python", "model serving"]),
            ("e7", "reviewed_skill", "Kubernetes terminology and Helm workflows were reviewed, without production cluster ownership.", "self_reported", "", False, ["Kubernetes"], ["Kubernetes", "Helm"]),
            ("e8", "coursework", "Distributed-systems coursework covered consistency and queue semantics.", "incomplete", "", False, ["distributed systems"], []),
        ],
        "preferences": {
            "role_families": ["backend_engineering", "data_engineering", "machine_learning"],
            "target_titles": ["Backend Engineer", "Data Platform Engineer", "Platform Engineer"],
            "target_levels": ["mid", "senior"],
            "locations": ["Toronto", "Canada"],
            "work_arrangements": ["hybrid", "remote"],
            "work_authorization_status": "confirmed",
            "selected_exploration_sectors": ["software engineering", "data engineering", "AI / machine learning"],
            "preferred_companies": [],
        },
    },
    "val-profile-02": {
        "summary": "Embedded and systems-integration engineer with production C++ work, ROS 2 sensor interfaces, board bring-up, Linux diagnostics, and verification benches.",
        "skills": ["C++", "C", "ROS 2", "Linux", "CAN", "SPI", "pytest", "hardware-in-loop", "requirements traceability"],
        "experience_years": 5.5,
        "education_summary": "Bachelor of Mechatronics Engineering from a deidentified Canadian university.",
        "current_location": "Ottawa, ON",
        "authorized_work_locations": ["Canada"],
        "requires_sponsorship": False,
        "professional_license_status": "unknown",
        "clearance_status": "confirmed_none",
        "items": [
            ("e1", "demonstrated", "Maintained C++ real-time components for a sensor gateway and diagnosed timing faults on Linux targets.", "verified", "", True, ["embedded software", "real-time software", "Linux debugging"], ["C++", "Linux"]),
            ("e2", "demonstrated", "Integrated ROS 2 sensor messages with CAN and SPI devices during autonomous cart bring-up.", "verified", "", True, ["ROS 2 integration", "sensor integration", "communication protocols"], ["ROS 2", "CAN", "SPI"]),
            ("e3", "demonstrated", "Brought up controller boards, captured serial traces, and isolated power and boot faults with electrical teammates.", "verified", "", True, ["board bring-up", "hardware debugging"], ["C", "UART", "Linux"]),
            ("e4", "demonstrated", "Created a Python test bench and executed hardware-in-loop scenarios for actuator commands and sensor plausibility.", "verified", "", True, ["test benches", "data acquisition", "hardware-in-loop testing"], ["Python", "hardware-in-loop"]),
            ("e5", "demonstrated", "Maintained requirements traceability, verification records, and regression evidence for a connected controller release.", "verified", "", True, ["requirements", "verification"], ["Python", "requirements tooling"]),
            ("e6", "demonstrated", "Coordinated software, electrical, and mechanical handoffs during system integration and field-fault reproduction.", "verified", "", True, ["cross-functional hardware/software work"], ["C++", "CAN"]),
            ("e7", "coursework", "Controls coursework covered PID response and state-space examples without production loop-tuning ownership.", "incomplete", "", False, ["controls"], []),
            ("e8", "reviewed_skill", "Altium and formal schematic-review terminology were reviewed, without owning electrical design release.", "self_reported", "", False, ["electrical design"], ["Altium"]),
        ],
        "preferences": {
            "role_families": ["embedded_systems", "robotics", "hardware_systems_integration", "verification"],
            "target_titles": ["Embedded Systems Engineer", "Systems Integration Engineer", "Verification Engineer"],
            "target_levels": ["mid", "senior"],
            "locations": ["Ottawa", "Toronto", "Canada"],
            "work_arrangements": ["hybrid", "remote"],
            "work_authorization_status": "confirmed",
            "selected_exploration_sectors": ["embedded systems / firmware", "robotics / autonomous systems", "testing / verification"],
            "preferred_companies": [],
        },
    },
}


def _profile(ref: str) -> dict[str, Any]:
    source = PROFILES[ref]
    return {
        "profile_ref": ref,
        "synthetic_or_deidentified": True,
        "reviewed": True,
        "summary": source["summary"],
        "skills": source["skills"],
        "evidence_items": _evidence(ref, source["items"]),
        "experience_years": source["experience_years"],
        "education_summary": source["education_summary"],
        "date_evidence_status": "current",
        "current_location": source["current_location"],
        "authorized_work_locations": source["authorized_work_locations"],
        "requires_sponsorship": source["requires_sponsorship"],
        "professional_license_status": source["professional_license_status"],
        "clearance_status": source["clearance_status"],
    }


def _preferences(ref: str) -> dict[str, Any]:
    source = PROFILES[ref]["preferences"]
    return {
        "confirmed": True,
        **source,
        "candidate_current_location": PROFILES[ref]["current_location"],
        "authorized_work_locations": PROFILES[ref]["authorized_work_locations"],
        "requires_sponsorship": PROFILES[ref]["requires_sponsorship"],
    }


def _fact(case_id: str, slug: str, kind: str, statement: str) -> dict[str, str]:
    return {"fact_id": f"posting:{case_id}:{slug}", "kind": kind, "statement": statement}


def _ref(case_id: str, slug: str) -> str:
    return f"posting:{case_id}:{slug}"


def _evidence_ref(profile_ref: str, slug: str, statement: str, quality: str = "verified") -> dict[str, Any]:
    return {"reference": f"profile:{profile_ref}:{slug}", "provenance": "independently reviewed validation profile", "statement": statement, "evidence_quality": quality}


DESCRIPTION_SUFFIXES = {
    "validation-061": "The fare team pairs with payment operations before a route change is released, and keeps the service contract visible to every downstream consumer.",
    "validation-062": "Data engineers publish freshness and replay evidence with each backfill so analysts can distinguish a delayed source from a failed transformation.",
    "validation-063": "During seasonal peaks, the team records partition behavior and verifies that a recovered stream remains complete before warehouse users resume normal planning.",
    "validation-064": "The reliability group rotates incident ownership among platform engineers and records rollout health before an inference endpoint is promoted to the next environment.",
    "validation-065": "The operations office maintains a single decision register for launches, escalations, and budget changes across the research portfolio.",
    "validation-066": "Commercial partners receive a monthly narrative with definitions, assumptions, and an owner for every metric included in the leadership packet.",
    "validation-067": "The security floor separates deployment duties from customer-access approvals and requires a written recovery record after every production change.",
    "validation-068": "The leadership group reviews investment trade-offs across product lines and expects the director to maintain a consistent operating cadence for managers.",
    "validation-069": "Control packages are retained with filing evidence, signatory identity, and the remediation history that supports the final regulated submission.",
    "validation-070": "The small service-foundations group will confirm its operating model and location policy before it schedules the next engineering conversation.",
    "validation-071": "Each bench session records the gateway firmware revision, the observed signal timing, and the board configuration used to reproduce the fault.",
    "validation-072": "The lab links each accepted result to a test configuration and preserves the anomaly disposition so another engineer can repeat the release decision.",
    "validation-073": "Customer-trial reports include the vehicle configuration, active sensor set, and recovery sequence used when a field issue is reproduced.",
    "validation-074": "The transport group compares measured response against an acceptance envelope and records instrumentation settings before changing a control parameter.",
    "validation-075": "The coordinator's weekly packet combines supplier commitments, commercial exceptions, and decisions that need a program-director response.",
    "validation-076": "The design team maintains a released drawing baseline and links manufacturing findings to the circuit revision that addresses the observed yield issue.",
    "validation-077": "Controlled releases require configuration evidence, anomaly disposition, and a traceable handoff between the cleared verification floor and firmware owners.",
    "validation-078": "The architect maintains an interface standard that is reused by each vehicle program and records the governance board's disposition for cross-product exceptions.",
    "validation-079": "Electrical designers compare measured noise and tolerance behavior with the released calculation before sending a revised circuit package to manufacturing.",
    "validation-080": "The prototype lab records instrument settings, firmware revisions, and observed response for each trial while the missing hiring details are confirmed.",
}

REQUIRED_GAP_ADDITIONS = {
    "validation-065": ("absent_vendor_scope", "No reviewed evidence establishes the required vendor negotiation and portfolio-reporting ownership.", ["posting:validation-065:required_qualification:vendor"]),
    "validation-066": ("absent_consulting_scope", "No reviewed evidence establishes the required client-facing reporting and presentation ownership.", ["posting:validation-066:required_qualification:consulting"]),
    "validation-069": ("absent_regulated_reporting", "No reviewed evidence establishes the required audit-file ownership or regulated reporting duration.", ["posting:validation-069:required_qualification:regulated"]),
    "validation-075": ("absent_vendor_coordination", "No reviewed evidence establishes the required vendor follow-up, facilitation, or commercial risk reporting.", ["posting:validation-075:required_qualification:vendor"]),
    "validation-079": ("absent_schematic_scope", "No reviewed evidence establishes the required SPICE, tolerance-analysis, or formal schematic sign-off work.", ["posting:validation-079:required_qualification:schematic"]),
}


def _repaired_spec(original: dict[str, Any]) -> dict[str, Any]:
    """Apply explicit source-authority repairs to the affected validation cases."""
    spec = copy.deepcopy(original)
    case_id = spec["case_id"]

    if case_id == "validation-061":
        spec["description"] = spec["description"].replace(
            "Required qualifications include relational schema design, container deployment, and clear incident notes.",
            "Required qualifications include relational schema design and container deployment. Clear incident notes are part of the team's operating practice.",
        ).replace(
            "Canadian work authorization is required, and the employer can support that authorization.",
            "Canadian work authorization is required; sponsorship is available.",
        )
        spec["responsibilities"].append(("incident-notes", "Keep clear incident notes for release and recovery decisions.", "Clear incident notes support release recovery."))
        spec["preferred"].append(("java-maintenance", "Java maintenance is preferred.", ["profile:val-profile-01:e5"]))
        spec["authorization_fact"] = "Canadian work authorization is required; sponsorship is available."

    elif case_id == "validation-062":
        spec["location"] = "Canada"
        spec["location_fact"] = "The full-time remote role is available within Canada."
        spec["preferred"].append(("python-automation", "Python automation for data checks is preferred.", ["profile:val-profile-01:e1", "profile:val-profile-01:e3", "profile:val-profile-01:e5"]))

    elif case_id == "validation-063":
        spec["description"] = spec["description"].replace(
            "That high-rate operations depth is a required but non-critical boundary for this assignment.",
            "The engineer will own this high-rate recovery work during peak operating periods.",
        )
        spec["required"].insert(0, ("incident-investigation", "Incident investigation for delayed or failed loads is required.", ["profile:val-profile-01:e4"]))

    elif case_id == "validation-064":
        spec["location"] = "Canada"
        spec["location_fact"] = "The full-time remote role is available within Canada."
        spec["description"] = spec["description"].replace(
            "This remote Canadian role",
            "This remote role is available within Canada",
        ).replace(
            "within Canada owns",
            "within Canada and owns",
        ).replace(
            "Required qualifications include Kubernetes cluster operations, capacity planning, and alert ownership during a sustained on-call rotation.",
            "Required qualifications include production Kubernetes cluster operations, capacity planning, and alert ownership during a sustained on-call rotation.",
        ).replace(
            "The profile's container deployments and dashboards transfer to the service boundary, but reviewed Kubernetes terminology is not production cluster ownership. Limited model-inference integration is useful context; the role does not ask this engineer to train models.",
            "Production model-endpoint rollout support is required. Cloud deployment is preferred. Model training is not part of this role.",
        )
        spec["gaps"].append((
            "insufficient_ml_platform_depth",
            "Prototype endpoint integration provides transferable context, but it does not establish production rollout, rollback, and post-release support.",
            ["profile:val-profile-01:e6", "posting:validation-064:required_qualification:ml-platform"],
        ))
        spec["rationale"] = (
            "This is Weak because customer-facing service monitoring and incident investigation are demonstrated, while production "
            "Kubernetes cluster operations, sustained on-call ownership, and production model-endpoint rollout, rollback, and "
            "post-release support remain two material required stretches; eligibility is confirmed."
        )

    elif case_id == "validation-065":
        spec["description"] = spec["description"].replace(
            "A graduate degree in business or technology and six years of program-management leadership are critical.",
            "Six years of program-management leadership and executive-delivery ownership are critical.",
        )
        spec["positive"] = [("model_serving_context", "Limited model-inference integration matches the posting's preferred model-serving familiarity.", ["profile:val-profile-01:e6", "posting:validation-065:preferred_qualification:ai"])]

    elif case_id == "validation-066":
        spec["description"] = spec["description"].replace(
            "Required qualifications include five years of client-facing reporting, presentation ownership, and comfort translating ambiguous questions into recommendations.",
            "Required qualifications include client-facing reporting, presentation ownership, and comfort translating ambiguous questions into recommendations.",
        )
        spec["positive"] = [("technical_context", "Python service and SQL schema work match the posting's preferred technical context.", ["profile:val-profile-01:e1", "profile:val-profile-01:e2", "posting:validation-066:preferred_qualification:sql"])]

    elif case_id == "validation-067":
        spec["required"].append(("release-quality", "Cloud and container deployment with automated testing are required.", ["profile:val-profile-01:e4", "profile:val-profile-01:e5"]))
        spec["preferred"].append(("model-serving", "Model-serving integration is preferred.", ["profile:val-profile-01:e6"]))
        spec["positive"] = [("technical_overlap", "Python service ownership, relational schema design, container/cloud release work, automated testing, and incident investigation directly match the technical assignment.", ["profile:val-profile-01:e1", "profile:val-profile-01:e2", "profile:val-profile-01:e4", "profile:val-profile-01:e5", "posting:validation-067:critical_requirement:service-core", "posting:validation-067:required_qualification:database", "posting:validation-067:required_qualification:release-quality", "posting:validation-067:responsibility:platform"])]

    elif case_id == "validation-068":
        spec["positive"] = [("platform_context", "Python services and cloud operations match the posting's preferred hands-on platform context.", ["profile:val-profile-01:e1", "profile:val-profile-01:e4", "posting:validation-068:preferred_qualification:platform"])]

    elif case_id == "validation-069":
        spec["positive"] = [("data_context", "SQL modeling and data movement match the posting's preferred technical context.", ["profile:val-profile-01:e2", "profile:val-profile-01:e3", "posting:validation-069:preferred_qualification:data"])]
        spec["gaps"] = [gap for gap in spec["gaps"] if gap[0] != "credential_conflict"]
        spec["gaps"].insert(0, ("credential_conflict", "The confirmed absence of a professional designation leaves the mandatory accounting credential unsupported.", ["posting:validation-069:critical_requirement:credential", "profile:val-profile-01:professional-license-status"]))
        spec["eligibility_reasons"] = [("hard_license_conflict", "The mandatory professional accounting designation conflicts with the profile's confirmed-none professional-license status.", ["posting:validation-069:critical_requirement:credential", "profile:val-profile-01:professional-license-status"], "posting:validation-069:critical_requirement:credential", "profile:val-profile-01:professional-license-status")]

    elif case_id == "validation-070":
        spec["description"] = spec["description"].replace(
            "Required work includes relational persistence and containerized deployment, while event replay is preferred.",
            "Required work includes relational persistence, containerized deployment, and service-level event-replay recovery ownership. Integration-test maintenance is preferred.",
        )
        spec["grade"] = "good"
        spec["human_ranking_tier"] = "tier_2"

    elif case_id == "validation-071":
        spec["description"] = spec["description"].replace(
            "Canadian work authorization is required and the employer supports it.",
            "Canadian authorization is required; the employer offers sponsorship for this appointment.",
        )
        spec["authorization_fact"] = "Canadian authorization is required; the employer offers sponsorship for this appointment."

    elif case_id == "validation-074":
        spec["description"] = spec["description"].replace(
            "The reviewed profile demonstrates acquisition and HIL execution, while controls coursework supplies academic context without production loop-tuning ownership.",
            "The role includes physical actuator-bench commissioning, real-plant loop tuning, instrumentation selection, verification, and release duties.",
        )

    elif case_id == "validation-075":
        spec["positive"] = [("robotics_context", "ROS 2 integration matches the posting's preferred robotics familiarity.", ["profile:val-profile-02:e2", "posting:validation-075:preferred_qualification:ros"])]

    elif case_id == "validation-076":
        spec["positive"] = [("embedded_context", "Embedded software, CAN/SPI integration, and board bring-up match the posting's preferred embedded context.", ["profile:val-profile-02:e1", "profile:val-profile-02:e2", "profile:val-profile-02:e3", "posting:validation-076:preferred_qualification:bringup"])]
        spec["gaps"] = [gap for gap in spec["gaps"] if gap[0] != "absent_electrical_design"]
        spec["gaps"].append((
            "insufficient_electrical_design",
            "Reviewed electrical-design terminology does not establish released schematic ownership, PCB or circuit-design ownership, analog measurement and derating, safety documentation, or certification authority.",
            ["profile:val-profile-02:e8", "posting:validation-076:critical_requirement:design-core", "posting:validation-076:required_qualification:hardware"],
        ))

    elif case_id == "validation-077":
        spec["positive"] = [("technical_overlap", "HIL execution, requirements traceability, Linux debugging, and cross-functional verification directly match the technical assignment.", ["profile:val-profile-02:e1", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "profile:val-profile-02:e6", "posting:validation-077:critical_requirement:verification-core", "posting:validation-077:responsibility:secure-verification"])]

    elif case_id == "validation-078":
        spec["positive"] = [("integration_context", "Embedded integration, traceability, and HIL work match the posting's preferred systems context.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "posting:validation-078:preferred_qualification:integration"])]

    elif case_id == "validation-079":
        spec["positive"] = [("embedded_context", "Embedded firmware, serial debugging, and Python bench work match the posting's preferred controller context.", ["profile:val-profile-02:e1", "profile:val-profile-02:e3", "profile:val-profile-02:e4", "posting:validation-079:preferred_qualification:embedded"])]

    elif case_id == "validation-080":
        spec["description"] = spec["description"].replace(
            "Required work includes physical actuator-bench commissioning, calibration setup, and closed-loop tuning during prototype trials; the available profile evidence demonstrates acquisition and HIL execution but not full physical commissioning ownership.",
            "Required work includes physical actuator-bench commissioning, calibration setup, and closed-loop tuning during prototype trials.",
        )

    return spec


def _make_case(spec: dict[str, Any]) -> dict[str, Any]:
    spec = _repaired_spec(spec)
    case_id = spec["case_id"]
    profile_ref = spec["profile_ref"]
    profile = _profile(profile_ref)
    description = f"{spec['description']} {DESCRIPTION_SUFFIXES[case_id]}"
    description = description.replace("The profile's container deployments", "Existing container deployments")
    description = description.replace("to a review board", "to a governance board")
    description = description.replace("The reviewed profile demonstrates", "Existing bench work demonstrates")
    description = description.replace("the available profile evidence demonstrates", "existing bench work demonstrates")
    authorization_wording = {
        "validation-066": "Canadian authorization is required; sponsorship is available.",
        "validation-068": "The employer accepts Canadian authorization and can sponsor this Toronto appointment.",
        "validation-069": "The employer requires Canadian authorization and cannot sponsor this Toronto appointment.",
        "validation-072": "Meridian Loom supports Canadian work authorization and offers sponsorship.",
        "validation-073": "Lantern Vale will sponsor an engineer who meets the Canadian authorization condition.",
        "validation-074": "Prairie Current accepts Canadian authorization with sponsorship available.",
        "validation-075": "Moss Lantern welcomes Canadian-authorized applicants and can provide sponsorship.",
        "validation-076": "Stonebridge accepts Canadian authorization and provides sponsorship for the hire.",
        "validation-078": "Cedar Meridian requires Canadian authorization; sponsorship is available for this role.",
        "validation-079": "Blue Trestle hires with Canadian authorization and makes sponsorship available.",
    }
    for original in ("Canadian work authorization is required and sponsorship is available.", "Canadian authorization is required and sponsorship is available.", "Canadian authorization is required and sponsorship is not available."):
        if case_id in authorization_wording:
            description = description.replace(original, authorization_wording[case_id], 1)
    if case_id == "validation-061":
        description += " Blue Orchard scopes this opening at the mid-level."
    evidence_by_slug = {item["evidence_id"].rsplit(":", 1)[-1]: item for item in profile["evidence_items"]}
    facts: list[dict[str, str]] = []
    for row in spec["responsibilities"]:
        slug, statement = row[0], row[-1]
        facts.append(_fact(case_id, f"responsibility:{slug}", "responsibility", statement))
    for importance, rows in (("critical_requirement", spec["critical"]), ("required_qualification", spec["required"]), ("preferred_qualification", spec["preferred"])):
        for slug, text, _refs in rows:
            facts.append(_fact(case_id, f"{importance}:{slug}", importance, text))
    facts.extend([
        _fact(case_id, "location", "location", spec["location_fact"]),
        _fact(case_id, "authorization", "authorization", spec["authorization_fact"]),
        _fact(case_id, "level", "level", spec["level_fact"]),
        _fact(case_id, "employment_type", "employment_type", "The appointment is full-time employment."),
    ])
    if spec["date"]:
        facts.append(_fact(case_id, "posting_date:posting-date", "posting_date", f"{spec['company']} published the opening on {spec['date']}."))
    else:
        facts.append(_fact(case_id, "posting_date:posting-date", "posting_date", f"{spec['company']} has not stated the publication date."))
    requirements = {
        "critical_requirements": [
            {"requirement_id": _ref(case_id, f"critical_requirement:{slug}"), "text": text, "importance": "critical", "evidence_references": refs, "fact_id": _ref(case_id, f"critical_requirement:{slug}")}
            for slug, text, refs in spec["critical"]
        ],
        "required_qualifications": [
            {"qualification_id": _ref(case_id, f"required_qualification:{slug}"), "text": text, "evidence_references": refs, "fact_id": _ref(case_id, f"required_qualification:{slug}")}
            for slug, text, refs in spec["required"]
        ],
        "preferred_qualifications": [
            {"qualification_id": _ref(case_id, f"preferred_qualification:{slug}"), "text": text, "evidence_references": refs, "fact_id": _ref(case_id, f"preferred_qualification:{slug}")}
            for slug, text, refs in spec["preferred"]
        ],
    }
    important_evidence = [
        _evidence_ref(profile_ref, slug, evidence_by_slug[slug]["statement"], evidence_by_slug[slug]["evidence_quality"])
        for slug in spec["evidence"]
    ]
    positive = [{"code": code, "statement": statement, "evidence_references": refs} for code, statement, refs in spec["positive"]]
    gap_specs = [*spec["gaps"]]
    if case_id in REQUIRED_GAP_ADDITIONS:
        gap_specs.append(REQUIRED_GAP_ADDITIONS[case_id])
    gaps = [{"code": code, "statement": statement, "evidence_references": refs} for code, statement, refs in gap_specs]
    eligibility = [{"code": code, "statement": statement, "evidence_references": refs, "posting_fact": posting_fact, "profile_fact": profile_fact} for code, statement, refs, posting_fact, profile_fact in spec["eligibility_reasons"]]
    assessment_refs = important_evidence or [_evidence_ref(profile_ref, "e1", evidence_by_slug["e1"]["statement"], evidence_by_slug["e1"]["evidence_quality"])]
    return {
        "case_id": case_id,
        "scenario_id": spec["group"],
        "split": "validation",
        "scenario_category": spec["category"],
        "ranking_group": spec["group"],
        "stage": "A",
        "proposal_status": "proposed",
        "profile": profile,
        "preferences": _preferences(profile_ref),
        "posting": {
            "normalized_id": f"normalized-synthetic-{case_id}",
            "title": spec["title"],
            "company": spec["company"],
            "description": description,
            "location": spec["location"],
            "work_arrangement": spec["arrangement"],
            "employment_type": "full_time",
            "posted_date": spec["date"],
            "responsibilities": [row[-1] for row in spec["responsibilities"]],
            "requirements_text": [text for _slug, text, _refs in [*spec["critical"], *spec["required"], *spec["preferred"]]],
            "posting_sponsorship_available": spec["sponsorship"],
            "enrollment_requirement": None,
            "graduation_window": None,
            "posting_level": spec["level"],
            "posting_facts": facts,
        },
        "source": {
            "provider": "synthetic_ats",
            "source_id": f"validation-board-{spec['group'][-2:]}",
            "external_job_id": f"job-synthetic-{case_id}",
            "source_url": f"https://jobs.example.test/validation/{case_id}",
            "retrieved_at": "2026-07-21T12:00:00Z",
            "provider_position": spec["provider_position"],
            "verification_status": "verified_active",
        },
        "expected_eligibility": spec["eligibility"],
        "proposed_eligibility_reasons": eligibility,
        "proposed_grade": spec["grade"],
        "proposed_provisional": spec["provisional"],
        "provisional_reason_codes": spec["provisional_codes"],
        **requirements,
        "important_evidence": important_evidence,
        "evidence_assessment": {"quality": "verified", "provenance": assessment_refs},
        "important_gaps": gaps,
        "proposed_positive_reasons": positive,
        "proposed_material_gap_reasons": gaps,
        "proposed_reasons": [*positive, *gaps],
        "rationale": spec["rationale"],
        "proposal_confidence": "high" if not spec["provisional"] else "medium",
        "review_tags": ["deidentified_profile", spec["category"], *spec["tags"], *( ["provider_order"] if case_id == "validation-061" else []), *( ["duplicate_identity"] if case_id == "validation-062" else [])],
        "review_required": True,
        "apply_worthy": spec["apply_worthy"],
        "normal_feed_visible": spec["visible"],
        "human_ranking_tier": {"excellent": "tier_1", "good": "tier_2", "weak": "tier_3", "dont_match": "not_ranked"}[spec["grade"]] if spec["grade"] == "dont_match" or spec["visible"] else "not_ranked",
        "comparable_pair_annotations": [],
        "reviewer_decision": "",
        "reviewer_notes": "",
        "approval_status": "unapproved",
    }


def _s(case_id: str, profile_ref: str, group: str, category: str, title: str, company: str, location: str, arrangement: str, level: str, date: str | None, sponsorship: bool | None, description: str, responsibilities: list[tuple[str, str, str]], critical: list[tuple[str, str, list[str]]], required: list[tuple[str, str, list[str]]], preferred: list[tuple[str, str, list[str]]], evidence: list[str], positive: list[tuple[str, str, list[str]]], gaps: list[tuple[str, str, list[str]]], eligibility: str, eligibility_reasons: list[tuple[str, str, list[str], str, str]], grade: str, provisional: bool, provisional_codes: list[str], visible: bool, apply_worthy: bool, tags: list[str], rationale: str, provider_position: int, location_fact: str, authorization_fact: str, level_fact: str) -> dict[str, Any]:
    return locals()


SPECS: list[dict[str, Any]] = [
_s("validation-061", "val-profile-01", "validation-group-01", "backend_engineering", "Backend Services Engineer", "Blue Orchard Transit", "Toronto, ON", "hybrid", "mid", "2026-07-10", True, "Blue Orchard Transit is adding a full-time Backend Services Engineer to the fare-platform team in Toronto. The hybrid schedule combines two office days with remote delivery. You will own Python API endpoints, define service contracts, trace production incidents, and partner with operations when a release affects payment events. The critical qualification is production ownership of a Python service with automated tests. Required qualifications include relational schema design, container deployment, and clear incident notes. Preferred experience includes Kafka replay tooling and Java maintenance. The opening was published on 2026-07-10. Canadian work authorization is required, and the employer can support that authorization. The team keeps operational decisions in versioned runbooks and expects engineers to explain failure recovery to non-specialist partners.", [("api", "responsible", "Own Python API endpoints, service contracts, and production incident follow-up.")], [("service-ownership", "Production ownership of a Python service with automated tests is critical.", ["profile:val-profile-01:e1", "profile:val-profile-01:e5"])], [("relational", "Relational schema design is required.", ["profile:val-profile-01:e2"]), ("containers", "Container deployment is required.", ["profile:val-profile-01:e4"])], [("stream-replay", "Kafka replay tooling is preferred.", ["profile:val-profile-01:e3"])], ["e1", "e2", "e4", "e5"], [("direct_service_match", "Python API ownership, automated testing, and incident follow-up are directly demonstrated by the service and release evidence.", ["profile:val-profile-01:e1", "profile:val-profile-01:e5", "posting:validation-061:critical_requirement:service-ownership", "posting:validation-061:responsibility:api"])], [], "eligible", [("no_known_hard_conflict", "The Toronto hybrid location and Canadian authorization requirement agree with the confirmed Canadian preference.", ["posting:validation-061:location", "posting:validation-061:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-061:authorization", "preferences:val-profile-01:work_authorization")], "excellent", False, [], True, True, ["direct_match"], "The case is Excellent because Python service ownership, automated tests, schema work, and incident follow-up cover the critical and required duties with verified production evidence; eligibility is confirmed for Toronto and Canadian authorization.", 1, "The full-time hybrid position is based in Toronto, Ontario.", "Canadian work authorization is required; the employer supports authorization.", "The opening is a mid-level engineering role.") ,
_s("validation-062", "val-profile-01", "validation-group-01", "data_engineering", "Data Platform Engineer", "Riverglass Analytics", "Montreal, QC", "remote", "senior", "2026-07-11", True, "Riverglass Analytics is hiring a full-time Senior Data Platform Engineer for its lakehouse foundations group. The role is remote within Canada and owns reliable movement from transactional systems into analytical tables. You will design PostgreSQL models, operate Kafka and batch backfills, add replay and data-quality controls, and work with application teams when a schema change reaches production. A production data-movement system is the critical qualification. Required qualifications are relational modeling, streaming or batch operations, and incident investigation for failed loads. Experience with containerized cloud services and Python automation is preferred. Riverglass published this opening on 2026-07-11. Canadian work authorization is required and sponsorship is available for this role. The team publishes recovery procedures alongside each pipeline and measures freshness before declaring a feed healthy.", [("movement", "Own reliable movement from transactional systems into analytical tables.")], [("data-platform", "Production ownership of a data-movement system is critical.", ["profile:val-profile-01:e2", "profile:val-profile-01:e3"])], [("modeling", "Relational modeling is required.", ["profile:val-profile-01:e2"]), ("streaming", "Streaming or batch operations and failed-load investigation are required.", ["profile:val-profile-01:e3", "profile:val-profile-01:e4"])], [("cloud", "Containerized cloud-service experience is preferred.", ["profile:val-profile-01:e4"])], ["e2", "e3", "e4"], [("direct_data_match", "PostgreSQL modeling, Kafka and batch movement, replay controls, and incident investigation directly cover the data-platform responsibilities.", ["profile:val-profile-01:e2", "profile:val-profile-01:e3", "profile:val-profile-01:e4", "posting:validation-062:critical_requirement:data-platform", "posting:validation-062:responsibility:movement"])], [], "eligible", [("no_known_hard_conflict", "The remote Canada arrangement and sponsorship availability are compatible with the confirmed Canadian work location.", ["posting:validation-062:location", "posting:validation-062:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-062:authorization", "preferences:val-profile-01:work_authorization")], "excellent", False, [], True, True, ["direct_match"], "This is Excellent because data movement, relational modeling, replay controls, and failed-load investigation are demonstrated production responsibilities across the critical and required qualifications; eligibility is confirmed for remote work within Canada.", 2, "The full-time remote role is available within Canada.", "Canadian work authorization is required; sponsorship is available.", "The opening is scoped at the senior level.") ,
_s("validation-063", "val-profile-01", "validation-group-01", "data_engineering", "Streaming Reliability Engineer", "Kite Harbor Foods", "Toronto, ON", "hybrid", "senior", "2026-07-12", True, "Kite Harbor Foods needs a full-time Senior Streaming Reliability Engineer for the inventory signals team. The hybrid Toronto role owns Kafka topics, replay procedures, and freshness alerts that support warehouse replenishment. You will investigate delayed events, coordinate schema changes with service owners, and maintain Python checks around batch recovery. Production streaming and data-quality ownership is the critical qualification. Required qualifications include incident investigation and relational data modeling. The posting also asks for sustained ownership of high-volume partition balancing and consumer-lag remediation during peak season. That high-rate operations depth is a required but non-critical boundary for this assignment. Experience with AWS containers is preferred. Kite Harbor Foods published the role on 2026-07-12 and requires Canadian authorization; sponsorship is available. Engineers document the evidence used to reopen a feed after a disruption.", [("streaming", "Own Kafka topics, replay procedures, freshness alerts, and delayed-event investigation.")], [("streaming-core", "Production streaming and data-quality ownership is critical.", ["profile:val-profile-01:e3"])], [("modeling", "Relational data modeling is required.", ["profile:val-profile-01:e2"]), ("peak-depth", "High-volume partition balancing and consumer-lag remediation during peak season are required.", ["profile:val-profile-01:e3", "profile:val-profile-01:e4"])], [("aws", "AWS container operations are preferred.", ["profile:val-profile-01:e4"])], ["e2", "e3", "e4"], [("direct_streaming_match", "Kafka movement, replay checks, freshness alerts, and delayed-event investigation directly match the streaming core.", ["profile:val-profile-01:e3", "profile:val-profile-01:e4", "posting:validation-063:critical_requirement:streaming-core", "posting:validation-063:responsibility:streaming"])], [("insufficient_peak_depth", "Kafka and incident evidence is transferable, but it does not explicitly establish sustained high-volume partition balancing and consumer-lag remediation ownership.", ["profile:val-profile-01:e3", "profile:val-profile-01:e4", "posting:validation-063:required_qualification:peak-depth"])], "eligible", [("no_known_hard_conflict", "The Toronto hybrid location and Canadian authorization condition match the confirmed preference.", ["posting:validation-063:location", "posting:validation-063:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-063:authorization", "preferences:val-profile-01:work_authorization")], "good", False, [], True, True, ["good_boundary"], "This is Good: the production streaming core is directly demonstrated, while the required peak-season partition and consumer-lag depth is a limited insufficiency rather than a critical failure; eligibility is confirmed.", 3, "Kite Harbor Foods offers a full-time hybrid engineering role in Toronto.", "Canadian authorization is required and sponsorship is available.", "The role is senior level.") ,
_s("validation-064", "val-profile-01", "validation-group-01", "machine_learning", "Reliability and Model Platform Engineer", "Northline Signal", "Vancouver, BC", "remote", "senior", "2026-07-13", True, "Northline Signal is looking for a full-time Senior Reliability and Model Platform Engineer to keep inference services healthy after release. This remote Canadian role owns service telemetry, incident response, model-endpoint rollouts, and post-incident remediation. The critical qualification is production monitoring and incident investigation for a customer-facing service. Required qualifications include Kubernetes cluster operations, capacity planning, and alert ownership during a sustained on-call rotation. The profile's container deployments and dashboards transfer to the service boundary, but reviewed Kubernetes terminology is not production cluster ownership. Limited model-inference integration is useful context; the role does not ask this engineer to train models. Northline published the opening on 2026-07-13, requires Canadian authorization, and offers sponsorship. The team writes a failure narrative before changing a rollout.", [("reliability", "Own service telemetry, incident response, inference-endpoint rollouts, and remediation.")], [("service-observability", "Production monitoring and incident investigation for a customer-facing service are critical.", ["profile:val-profile-01:e4"])], [("kubernetes", "Production Kubernetes cluster operations, capacity planning, and on-call alert ownership are required.", ["profile:val-profile-01:e7"]), ("ml-platform", "Model-endpoint rollout support is required.", ["profile:val-profile-01:e6"])], [("cloud", "Cloud deployment experience is preferred.", ["profile:val-profile-01:e4"])], ["e4", "e6", "e7"], [("adjacent_reliability_match", "Production dashboards, incident investigation, and limited model-serving integration provide direct service-side overlap with the reliability and inference boundary.", ["profile:val-profile-01:e4", "profile:val-profile-01:e6", "posting:validation-064:critical_requirement:service-observability", "posting:validation-064:responsibility:reliability"])], [("insufficient_cluster_depth", "Container deployment and reviewed Kubernetes terminology do not establish production cluster operations, capacity planning, or sustained on-call alert ownership.", ["profile:val-profile-01:e4", "profile:val-profile-01:e7", "posting:validation-064:required_qualification:kubernetes"])], "eligible", [("no_known_hard_conflict", "The remote Canadian location and sponsorship availability are compatible with confirmed Canadian authorization.", ["posting:validation-064:location", "posting:validation-064:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-064:authorization", "preferences:val-profile-01:work_authorization")], "weak", False, [], True, True, ["adjacent_stretch"], "This is Weak because the customer-service observability core is demonstrated and the model-serving overlap is limited but real, while production Kubernetes operations and sustained on-call ownership remain a material required stretch; eligibility is confirmed.", 4, "The full-time remote appointment serves teams across Vancouver and Canada.", "Canadian authorization is required; sponsorship is available.", "The job is senior level.") ,
_s("validation-065", "val-profile-01", "validation-group-01", "machine_learning", "AI Program Operations Manager", "Lumen Orchard", "Toronto, ON", "hybrid", "senior", "2026-07-14", False, "Lumen Orchard is hiring a full-time Senior AI Program Operations Manager for its Toronto office. The hybrid team coordinates model-risk meetings, vendor statements of work, launch calendars, and executive status packets. This is not a software delivery position: the manager owns program cadence, budget checkpoints, and escalations across legal and product leaders. A graduate degree in business or technology and six years of program-management leadership are critical. Required qualifications include vendor negotiation, portfolio reporting, and executive communication. Familiarity with model-serving terminology is preferred but does not change the daily program mandate. Lumen Orchard published the opening on 2026-07-14. Canadian work authorization is required and sponsorship is not available. The successful hire will maintain decision logs and prepare quarterly planning material for the leadership team.", [("program", "Coordinate model-risk meetings, vendor statements of work, launch calendars, and executive status packets.")], [("program-leadership", "Six years of program-management leadership and ownership of executive delivery cadence are critical.", [])], [("vendor", "Vendor negotiation and portfolio reporting are required.", [])], [("ai", "Model-serving familiarity is preferred.", ["profile:val-profile-01:e6"])], ["e6"], [("peripheral_ai_context", "Limited model-inference integration is peripheral terminology overlap only and does not establish program-management or executive-delivery ownership.", ["profile:val-profile-01:e6", "posting:validation-065:preferred_qualification:ai"])], [("absent_program_leadership", "The reviewed profile contains no demonstrated program-management leadership for the critical portfolio responsibility.", ["posting:validation-065:critical_requirement:program-leadership"])], "eligible", [("no_known_hard_conflict", "The Toronto hybrid location and no-sponsorship condition are compatible with the confirmed Canadian work preference.", ["posting:validation-065:location", "posting:validation-065:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-065:authorization", "preferences:val-profile-01:work_authorization")], "dont_match", False, [], False, False, ["keyword_trap", "role_irrelevance"], "This is Don't Match because the daily work is program governance, vendor coordination, and executive reporting rather than engineering responsibilities; model-serving language is only peripheral and does not overcome the absent critical program-leadership evidence.", 5, "The full-time hybrid appointment is based in Toronto.", "Canadian authorization is required and sponsorship is unavailable.", "The position is senior level.") ,
_s("validation-066", "val-profile-01", "validation-group-01", "data_engineering", "Data Insights Consultant", "Marble Quay Retail", "Montreal, QC", "hybrid", "mid", "2026-07-15", True, "Marble Quay Retail seeks a full-time mid-level Data Insights Consultant for its Montreal commercial team. The hybrid consultant prepares weekly revenue narratives, builds slide decks for category leaders, gathers requirements from sales, and coordinates a reporting calendar with an external agency. The role's critical responsibility is business-report production and executive storytelling, not database or pipeline engineering. Required qualifications include five years of client-facing reporting, presentation ownership, and comfort translating ambiguous questions into recommendations. SQL and Python exposure are preferred, but they support analysis rather than software delivery. Marble Quay published this opening on 2026-07-15. Canadian work authorization is required and sponsorship is available. The consultant will facilitate workshops and maintain a catalog of business metrics used in quarterly reviews.", [("insights", "Prepare revenue narratives, executive slide decks, and a reporting calendar for commercial leaders.")], [("reporting-core", "Business-report production and executive storytelling are critical.", [])], [("consulting", "Client-facing reporting and presentation ownership are required.", [])], [("sql", "SQL and Python exposure are preferred.", ["profile:val-profile-01:e2", "profile:val-profile-01:e1"])], ["e1", "e2"], [("peripheral_data_context", "SQL schema and Python service evidence are peripheral tool overlap and do not establish the critical consulting and executive-reporting responsibilities.", ["profile:val-profile-01:e1", "profile:val-profile-01:e2", "posting:validation-066:preferred_qualification:sql"])], [("absent_reporting_ownership", "No reviewed evidence establishes client-facing business-report ownership or executive storytelling as the critical work.", ["posting:validation-066:critical_requirement:reporting-core"])], "eligible", [("no_known_hard_conflict", "The Montreal hybrid location and Canadian authorization requirement match the confirmed preference.", ["posting:validation-066:location", "posting:validation-066:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-066:authorization", "preferences:val-profile-01:work_authorization")], "dont_match", False, [], False, False, ["title_trap", "keyword_trap"], "This is Don't Match because a data title and SQL/Python preference obscure a reporting-consulting job whose critical responsibilities are not demonstrated by backend or data-platform ownership.", 6, "The full-time hybrid role is based in Montreal.", "Canadian work authorization is required; sponsorship is available.", "The opening is mid-level.") ,
_s("validation-067", "val-profile-01", "validation-group-01", "backend_engineering", "Platform Engineer", "Cobalt Mesa Security", "Austin, TX, United States", "onsite", "senior", "2026-07-16", False, "Cobalt Mesa Security is hiring a full-time Senior Platform Engineer for its Austin data-security floor. The onsite engineer will own Python services, PostgreSQL schemas, container releases, and incident response for a customer authorization platform. Production service and relational-data ownership are critical, with cloud deployment and automated tests required. Kafka recovery and model-serving integration are preferred. The posting was published on 2026-07-16. The position requires existing United States work authorization, does not sponsor immigration, and requires daily presence at the Austin site. The team handles sensitive customer records and expects engineers to document every release rollback. Canadian-only authorization is not sufficient for this appointment.", [("platform", "Own Python services, PostgreSQL schemas, container releases, and incident response.")], [("service-core", "Production Python service ownership is critical.", ["profile:val-profile-01:e1"])], [("database", "Relational schema design and container releases are required.", ["profile:val-profile-01:e2", "profile:val-profile-01:e4"])], [("kafka", "Kafka recovery is preferred.", ["profile:val-profile-01:e3"])], ["e1", "e2", "e4"], [("technical_overlap", "Python service, relational schema, container, and incident evidence directly cover the technical duties, but it is peripheral to the decisive authorization decision.", ["profile:val-profile-01:e1", "profile:val-profile-01:e2", "profile:val-profile-01:e4", "posting:validation-067:critical_requirement:service-core"])], [("authorization_conflict", "The Austin onsite job requires existing United States authorization without sponsorship, while the confirmed candidate authorization is Canada only.", ["posting:validation-067:location", "posting:validation-067:authorization", "preferences:val-profile-01:work_authorization"])], "ineligible", [("hard_authorization_conflict", "The Austin onsite location and no-sponsorship authorization condition conflict with the candidate's confirmed Canada-only work authorization.", ["posting:validation-067:location", "posting:validation-067:authorization", "preferences:val-profile-01:work_authorization"], "posting:validation-067:authorization", "preferences:val-profile-01:work_authorization")], "dont_match", False, [], False, False, ["work_authorization", "hard_conflict"], "The technical responsibilities are a strong profile match, but the case is Don't Match because the Austin onsite position requires United States work authorization without sponsorship, conflicting with the candidate's confirmed Canadian authorization.", 7, "The full-time onsite appointment is in Austin, Texas, United States.", "Existing United States work authorization is mandatory and sponsorship is unavailable.", "The position is senior level.") ,
_s("validation-068", "val-profile-01", "validation-group-01", "backend_engineering", "Director of Data Platforms", "Granite Lattice Health", "Toronto, ON", "hybrid", "director", "2026-07-17", True, "Granite Lattice Health is seeking a full-time Director of Data Platforms for its Toronto hybrid leadership group. The director sets a multi-year platform roadmap, manages several engineering managers, owns hiring plans, and presents investment decisions to the executive team. The critical qualification is organization-wide people leadership for a data-platform portfolio. Required qualifications include budget ownership, vendor strategy, and director-level delivery accountability. Hands-on Python services, SQL design, and cloud operations are useful context but are not the primary assignment. Granite Lattice published the opening on 2026-07-17. Canadian work authorization is required and sponsorship is available. The role oversees several product lines and expects an executive operating rhythm rather than individual-contributor implementation.", [("director", "Set a multi-year platform roadmap, manage engineering managers, and present investment decisions.")], [("leadership", "Organization-wide people leadership for a data-platform portfolio is critical.", [])], [("scope", "Budget ownership, vendor strategy, and director-level delivery accountability are required.", [])], [("platform", "Python service and cloud-platform experience is preferred.", ["profile:val-profile-01:e1", "profile:val-profile-01:e4"])], ["e1", "e4"], [("peripheral_platform_context", "Python services and cloud operations provide only peripheral platform context and do not establish director-level organizational leadership.", ["profile:val-profile-01:e1", "profile:val-profile-01:e4", "posting:validation-068:preferred_qualification:platform"])], [("level_scope_gap", "The profile targets mid and senior individual-contributor roles and contains no evidence of managing engineering managers, budgets, or a multi-year portfolio.", ["profile:val-profile-01:experience-years", "posting:validation-068:critical_requirement:leadership", "posting:validation-068:required_qualification:scope", "preferences:val-profile-01:target_level"])], "ineligible", [("level_conflict", "The posting requires director-level portfolio leadership, while the candidate target levels are mid and senior and the reviewed duration does not establish director scope.", ["posting:validation-068:level", "posting:validation-068:responsibility:director", "posting:validation-068:required_qualification:scope", "preferences:val-profile-01:target_level", "profile:val-profile-01:experience-years"], "posting:validation-068:level", "preferences:val-profile-01:target_level")], "dont_match", False, [], False, False, ["level_mismatch", "scope_conflict"], "This is Don't Match because the director role requires organization-wide people and budget leadership beyond the candidate's confirmed target levels and reviewed individual-contributor scope; service keywords are peripheral.", 8, "The full-time hybrid leadership role is based in Toronto.", "Canadian authorization is required and sponsorship is available.", "The position is director level and owns a platform portfolio.") ,
_s("validation-069", "val-profile-01", "validation-group-01", "data_engineering", "Data Compliance Engineer", "Harbor Needle Bank", "Toronto, ON", "hybrid", "senior", "2026-07-18", False, "Harbor Needle Bank is adding a full-time Senior Data Compliance Engineer to its Toronto hybrid controls team. The engineer owns Python data checks, schema controls, and remediation evidence for regulated reporting. The critical qualification is an active professional accounting designation or equivalent statutory reporting authority, because the role signs the final control package. Required qualifications include audit-file ownership and five years of regulated reporting. Data movement, SQL, and cloud deployment are preferred technical context. Harbor Needle published the opening on 2026-07-18. Canadian authorization is required and sponsorship is not available. The team works with legal and finance to certify evidence before a filing is released, and the signatory must hold the stated professional credential.", [("compliance", "Own Python data checks, schema controls, and final remediation evidence for regulated reporting.")], [("credential", "An active professional accounting designation or equivalent statutory reporting authority is critical.", [])], [("regulated", "Audit-file ownership and five years of regulated reporting are required.", [])], [("data", "Data movement and SQL are preferred.", ["profile:val-profile-01:e2", "profile:val-profile-01:e3"])], ["e2", "e3"], [("peripheral_data_context", "SQL and data-movement evidence is only peripheral technical context and does not satisfy the mandatory statutory reporting credential.", ["profile:val-profile-01:e2", "profile:val-profile-01:e3", "posting:validation-069:preferred_qualification:data"])], [("credential_conflict", "The reviewed profile does not record the mandatory accounting designation or statutory reporting authority required for final sign-off.", ["posting:validation-069:critical_requirement:credential", "profile:val-profile-01:education"])], "ineligible", [("hard_degree_or_license_conflict", "The mandatory professional credential is a posting condition, while the reviewed education record does not establish that designation and the profile license status is unknown.", ["posting:validation-069:critical_requirement:credential", "profile:val-profile-01:education"], "posting:validation-069:critical_requirement:credential", "profile:val-profile-01:education")], "dont_match", False, [], False, False, ["credential_conflict", "critical_gap"], "This is Don't Match because a mandatory statutory reporting credential controls the sign-off authority and is not established by the reviewed profile; data-platform experience remains peripheral.", 9, "The full-time hybrid role is based in Toronto.", "Canadian authorization is required and sponsorship is unavailable.", "The role is senior level and carries statutory sign-off.") ,
_s("validation-070", "val-profile-01", "validation-group-01", "backend_engineering", "Backend Engineer, Service Foundations", "Dawn Quarry Systems", "Remote geography unstated", "remote", "unknown", None, None, "Dawn Quarry Systems has supplied a shortened full-time Backend Engineer advertisement for its service-foundations team. The engineer would maintain Python APIs, write integration tests, trace failed requests, and help application teams recover a release. API ownership is the critical technical qualification. Required work includes relational persistence and containerized deployment, while event replay is preferred. The employer says the job is remote, but the country, exact work-authorization rule, posting date, and level are not stated in the available copy. Dawn Quarry asks applicants to clarify those conditions before scheduling a technical conversation. The small team values concise incident notes and expects the engineer to pair with service owners during recovery. Details about sponsorship and the reporting line remain unresolved.", [("foundations", "Maintain Python APIs, write integration tests, trace failed requests, and support release recovery.")], [("api-core", "Python API ownership is critical.", ["profile:val-profile-01:e1"])], [("persistence", "Relational persistence and containerized deployment are required.", ["profile:val-profile-01:e2", "profile:val-profile-01:e4"]), ("replay", "Event replay ownership is required.", ["profile:val-profile-01:e3"])], [("testing", "Integration-test maintenance is preferred.", ["profile:val-profile-01:e5"])], ["e1", "e2", "e4"], [("direct_api_match", "Python API ownership, relational persistence, container deployment, and incident evidence match the stated service-foundations work.", ["profile:val-profile-01:e1", "profile:val-profile-01:e2", "profile:val-profile-01:e4", "posting:validation-070:critical_requirement:api-core", "posting:validation-070:responsibility:foundations"])], [("insufficient_replay_depth", "The profile shows Kafka movement but does not establish ownership of the advertised event-replay boundary for this service team.", ["profile:val-profile-01:e3", "posting:validation-070:required_qualification:replay"])], "unknown", [("eligibility_unknown", "The remote geography, authorization policy, sponsorship rule, posting date, and level are unresolved in the source, while the confirmed profile supplies Canadian authorization and mid/senior targets.", ["posting:validation-070:location", "posting:validation-070:authorization", "posting:validation-070:posting_date:posting-date", "posting:validation-070:level", "preferences:val-profile-01:work_authorization", "preferences:val-profile-01:target_level"], "posting:validation-070:location", "preferences:val-profile-01:work_authorization")], "weak", True, ["incomplete_description", "unresolved_authorization", "missing_date", "uncertain_level", "remote_ambiguity"], True, True, ["incomplete_posting", "unknown_eligibility"], "This is Weak because the Python API core is directly demonstrated, but event-replay depth is insufficient and the remote geography, date, level, and authorization facts remain unresolved; eligibility is therefore unknown and the proposal is provisional.", 10, "The full-time remote job has no stated country or city.", "Authorization and sponsorship conditions are unstated.", "The posting does not state the level.") ,
_s("validation-071", "val-profile-02", "validation-group-02", "embedded_systems", "Embedded Gateway Engineer", "Copper Ridge Mobility", "Ottawa, ON", "hybrid", "mid", "2026-07-10", True, "Copper Ridge Mobility is recruiting a full-time mid-level Embedded Gateway Engineer for its Ottawa integration floor. The hybrid team maintains C++ sensor-gateway components, handles CAN and SPI messages, and diagnoses timing faults on Linux targets. You will bring up controller boards, add automated regression tests, and explain interface behavior to electrical partners. The critical qualification is production embedded software ownership on a constrained target. Required qualifications include protocol integration, Linux debugging, and hardware-software fault isolation. Hardware-in-loop testing is preferred. Copper Ridge published the opening on 2026-07-10. Canadian work authorization is required and the employer supports it. Engineers rotate through bench and vehicle trials, recording the firmware revision and measured signal conditions for each issue.", [("gateway", "Maintain C++ sensor-gateway components, handle CAN and SPI messages, and diagnose Linux timing faults.")], [("embedded-core", "Production embedded software ownership on a constrained target is critical.", ["profile:val-profile-02:e1"])], [("protocols", "Protocol integration and Linux debugging are required.", ["profile:val-profile-02:e2", "profile:val-profile-02:e3"]), ("faults", "Hardware-software fault isolation is required.", ["profile:val-profile-02:e3", "profile:val-profile-02:e6"])], [("hil", "Hardware-in-loop testing is preferred.", ["profile:val-profile-02:e4"])], ["e1", "e2", "e3", "e6"], [("direct_embedded_match", "Production C++ gateway work, CAN/SPI integration, Linux timing diagnosis, and board fault isolation directly cover the embedded duties.", ["profile:val-profile-02:e1", "profile:val-profile-02:e2", "profile:val-profile-02:e3", "posting:validation-071:critical_requirement:embedded-core", "posting:validation-071:responsibility:gateway"])], [], "eligible", [("no_known_hard_conflict", "The Ottawa hybrid location and Canadian authorization condition agree with the confirmed preference.", ["posting:validation-071:location", "posting:validation-071:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-071:authorization", "preferences:val-profile-02:work_authorization")], "excellent", False, [], True, True, ["direct_match"], "This is Excellent because production embedded ownership, CAN/SPI integration, Linux debugging, and board fault isolation cover the critical and required duties; eligibility is confirmed for Ottawa.", 1, "The full-time hybrid position is based in Ottawa.", "Canadian work authorization is required and supported.", "The position is mid-level.") ,
_s("validation-072", "val-profile-02", "validation-group-02", "verification", "Systems Verification Engineer", "Meridian Loom Robotics", "Toronto, ON", "hybrid", "senior", "2026-07-11", True, "Meridian Loom Robotics is hiring a full-time Senior Systems Verification Engineer for its Toronto robotics lab. The hybrid engineer will turn system requirements into verification cases, operate Python data-acquisition benches, execute hardware-in-loop scenarios, and carry failures through root-cause investigation. Requirements traceability and repeatable system verification are the critical qualifications. Required experience includes sensor and actuator integration, bench instrumentation, and evidence-based release reporting. ROS 2 integration is preferred because the product connects autonomous carts to safety controllers. Meridian Loom published the opening on 2026-07-11. Canadian authorization is required and sponsorship is available. Verification engineers work beside software and electrical teams, recording test configuration and observed behavior before accepting a correction.", [("verification", "Turn system requirements into cases, operate data-acquisition benches, execute HIL scenarios, and investigate failures.")], [("verification-core", "Requirements traceability and repeatable system verification are critical.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("bench", "Sensor and actuator integration, bench instrumentation, and release reporting are required.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("ros", "ROS 2 integration is preferred.", ["profile:val-profile-02:e2"])], ["e2", "e4", "e5", "e6"], [("direct_verification_match", "Requirements traceability, Python acquisition benches, HIL execution, root-cause work, and cross-team release evidence directly match the verification assignment.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5", "profile:val-profile-02:e6", "posting:validation-072:critical_requirement:verification-core", "posting:validation-072:responsibility:verification"])], [], "eligible", [("no_known_hard_conflict", "The Toronto hybrid location and Canadian authorization with sponsorship available are compatible with the confirmed preference.", ["posting:validation-072:location", "posting:validation-072:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-072:authorization", "preferences:val-profile-02:work_authorization")], "excellent", False, [], True, True, ["direct_match"], "This is Excellent because system verification, requirements traceability, Python bench work, HIL execution, and cross-functional release evidence directly cover the critical and required duties; eligibility is confirmed.", 2, "The full-time hybrid lab role is based in Toronto.", "Canadian authorization is required and sponsorship is available.", "The posting is senior level.") ,
_s("validation-073", "val-profile-02", "validation-group-02", "robotics", "Robot Integration Engineer", "Lantern Vale Automation", "Waterloo, ON", "onsite", "mid", "2026-07-12", True, "Lantern Vale Automation needs a full-time mid-level Robot Integration Engineer at its Waterloo test floor. The onsite engineer will connect ROS 2 messages to sensor and actuator interfaces, reproduce field faults, and document the conditions under which a vehicle accepts a release. The critical qualification is production robotics integration across software and hardware boundaries. Required qualifications include CAN diagnostics, Linux fault analysis, and verification records. The team also expects ownership of multi-robot regression orchestration and recovery from concurrent sensor failures during customer trials; that depth is required but non-critical. Python bench tooling is preferred. Lantern Vale published the role on 2026-07-12. Canadian authorization is required and sponsorship is available. Integration engineers work with mechanical and electrical partners at the test floor before a release moves to customers.", [("integration", "Connect ROS 2 messages to sensor and actuator interfaces, reproduce faults, and document release conditions.")], [("robotics-core", "Production robotics integration across software and hardware boundaries is critical.", ["profile:val-profile-02:e2", "profile:val-profile-02:e6"])], [("diagnostics", "CAN diagnostics, Linux fault analysis, and verification records are required.", ["profile:val-profile-02:e2", "profile:val-profile-02:e3", "profile:val-profile-02:e5"]), ("regression-depth", "Multi-robot regression orchestration and concurrent sensor-failure recovery during trials are required.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4"])], [("python", "Python bench tooling is preferred.", ["profile:val-profile-02:e4"])], ["e2", "e3", "e5", "e6"], [("direct_robotics_match", "ROS 2 sensor and actuator integration, CAN diagnostics, Linux fault analysis, and cross-functional handoff directly cover the robotics core.", ["profile:val-profile-02:e2", "profile:val-profile-02:e3", "profile:val-profile-02:e6", "posting:validation-073:critical_requirement:robotics-core", "posting:validation-073:responsibility:integration"])], [("insufficient_trial_depth", "The integration evidence is strong, but it does not explicitly establish multi-robot regression orchestration and concurrent sensor-failure recovery during customer trials.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "posting:validation-073:required_qualification:regression-depth"])], "eligible", [("no_known_hard_conflict", "The Waterloo onsite location and Canadian authorization condition match the confirmed preference.", ["posting:validation-073:location", "posting:validation-073:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-073:authorization", "preferences:val-profile-02:work_authorization")], "good", False, [], True, True, ["good_boundary"], "This is Good because the software-hardware robotics core is demonstrated directly, while concurrent trial-failure recovery and multi-robot regression depth remain a limited required gap; eligibility is confirmed.", 3, "The full-time onsite appointment is at the Waterloo test floor.", "Canadian authorization is required and sponsorship is available.", "The role is mid-level.") ,
_s("validation-074", "val-profile-02", "validation-group-02", "controls", "Controls Test Engineer", "Prairie Current Transport", "Ottawa, ON", "hybrid", "senior", "2026-07-13", True, "Prairie Current Transport is looking for a full-time Senior Controls Test Engineer in Ottawa. The hybrid engineer will build Python acquisition fixtures, execute hardware-in-loop scenarios, inspect sensor plausibility, and prepare evidence for vehicle release. System verification and repeatable test execution are critical. Required qualifications include commissioning physical actuator benches, tuning closed-loop response on the real plant, and selecting instrumentation for noisy signals. The reviewed profile demonstrates acquisition and HIL execution, while controls coursework supplies academic context without production loop-tuning ownership. CAN test experience is preferred. Prairie Current published the opening on 2026-07-13. Canadian authorization is required and sponsorship is available. The controls group works with electrical and mechanical owners when a measured response diverges from the acceptance envelope.", [("controls-test", "Build acquisition fixtures, execute HIL scenarios, inspect sensor plausibility, and prepare release evidence.")], [("verification-core", "System verification and repeatable test execution are critical.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("bench-depth", "Physical actuator-bench commissioning, real-plant loop tuning, and noisy-signal instrumentation are required.", ["profile:val-profile-02:e4", "profile:val-profile-02:e7"]), ("release", "Evidence preparation for vehicle release is required.", ["profile:val-profile-02:e5"])], [("can", "CAN test experience is preferred.", ["profile:val-profile-02:e2"])], ["e4", "e5", "e7"], [("direct_test_match", "Python acquisition, HIL scenarios, sensor plausibility checks, and verification records directly cover the system-test core.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5", "posting:validation-074:critical_requirement:verification-core", "posting:validation-074:responsibility:controls-test"])], [("insufficient_controls_depth", "The Python bench and HIL evidence plus controls coursework do not establish production actuator-bench commissioning, real-plant loop tuning, or instrumentation selection.", ["profile:val-profile-02:e4", "profile:val-profile-02:e7", "posting:validation-074:required_qualification:bench-depth"])], "eligible", [("no_known_hard_conflict", "The Ottawa hybrid location and Canadian authorization condition match the confirmed preference.", ["posting:validation-074:location", "posting:validation-074:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-074:authorization", "preferences:val-profile-02:work_authorization")], "weak", False, [], True, True, ["adjacent_stretch", "coursework_boundary"], "This is Weak because the verification core is directly demonstrated, but physical actuator-bench commissioning and production loop tuning are a material controls stretch beyond the bench and coursework evidence; eligibility is confirmed.", 4, "The full-time hybrid controls role is based in Ottawa.", "Canadian authorization is required and sponsorship is available.", "The opening is senior level.") ,
_s("validation-075", "val-profile-02", "validation-group-02", "robotics", "Robotics Product Operations Coordinator", "Moss Lantern Supply", "Toronto, ON", "hybrid", "mid", "2026-07-14", True, "Moss Lantern Supply is hiring a full-time mid-level Robotics Product Operations Coordinator for its Toronto office. The hybrid coordinator maintains launch calendars, collects supplier status, prepares executive summaries, and tracks purchase-order exceptions for a warehouse automation program. The critical responsibility is cross-company operations coordination rather than robot software, test, or hardware integration. Required qualifications include vendor follow-up, meeting facilitation, and commercial risk reporting. Familiarity with ROS terminology is preferred because the coordinator attends technical briefings, but it is not ownership of an engineering system. Moss Lantern published the role on 2026-07-14. Canadian authorization is required and sponsorship is available. The coordinator keeps a weekly decision register and escalates missed supplier dates to the program director.", [("operations", "Maintain launch calendars, supplier status, executive summaries, and purchase-order exceptions.")], [("coordination-core", "Cross-company operations coordination is critical.", [])], [("vendor", "Vendor follow-up, facilitation, and commercial risk reporting are required.", [])], [("ros", "ROS terminology is preferred.", ["profile:val-profile-02:e2"])], ["e2"], [("peripheral_ros_context", "ROS 2 integration experience is peripheral terminology overlap only and does not establish supplier or commercial operations ownership.", ["profile:val-profile-02:e2", "posting:validation-075:preferred_qualification:ros"])], [("absent_operations_ownership", "The reviewed profile contains no demonstrated commercial operations coordination or vendor-risk ownership for the critical assignment.", ["posting:validation-075:critical_requirement:coordination-core"])], "eligible", [("no_known_hard_conflict", "The Toronto hybrid location and Canadian authorization condition match the confirmed preference.", ["posting:validation-075:location", "posting:validation-075:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-075:authorization", "preferences:val-profile-02:work_authorization")], "dont_match", False, [], False, False, ["keyword_trap", "role_irrelevance"], "This is Don't Match because the daily assignment is supplier and commercial program coordination; robotics terminology is peripheral and does not overcome the missing critical operations responsibility.", 5, "The full-time hybrid coordinator role is based in Toronto.", "Canadian authorization is required and sponsorship is available.", "The opening is mid-level.") ,
_s("validation-076", "val-profile-02", "validation-group-02", "hardware_systems_integration", "Electrical Design Engineer", "Stonebridge Power Devices", "Kitchener, ON", "onsite", "senior", "2026-07-15", True, "Stonebridge Power Devices seeks a full-time Senior Electrical Design Engineer for its Kitchener lab. The onsite engineer owns schematics, PCB layout, circuit simulation, design-for-manufacture reviews, and compliance submissions for a power-conversion product. The critical qualification is released electrical design ownership from schematic through certification. Required qualifications include Altium, analog measurement, component derating, and formal safety documentation. Embedded software, CAN diagnostics, and board bring-up are preferred adjacency but do not replace circuit-design authority. Stonebridge published this opening on 2026-07-15. Canadian authorization is required and sponsorship is available. Designers work with manufacturing and safety specialists to release drawing packages and respond to certification findings before production.", [("electrical", "Own schematics, PCB layout, circuit simulation, manufacturing reviews, and compliance submissions.")], [("design-core", "Released electrical design ownership from schematic through certification is critical.", ["profile:val-profile-02:e8"])], [("hardware", "Altium, analog measurement, component derating, and safety documentation are required.", ["profile:val-profile-02:e8"])], [("bringup", "Embedded software, CAN diagnostics, and board bring-up are preferred.", ["profile:val-profile-02:e1", "profile:val-profile-02:e2", "profile:val-profile-02:e3"])], ["e1", "e2", "e3"], [("peripheral_bringup_context", "Embedded, CAN, and board-bring-up evidence is peripheral context and does not establish schematic, PCB, or certification ownership.", ["profile:val-profile-02:e1", "profile:val-profile-02:e2", "profile:val-profile-02:e3", "posting:validation-076:preferred_qualification:bringup"])], [("absent_electrical_design", "The reviewed profile has no demonstrated schematic, PCB layout, or certification ownership for the critical electrical-design boundary.", ["posting:validation-076:critical_requirement:design-core"])], "eligible", [("no_known_hard_conflict", "The Kitchener onsite location and Canadian authorization condition match the confirmed preference.", ["posting:validation-076:location", "posting:validation-076:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-076:authorization", "preferences:val-profile-02:work_authorization")], "dont_match", False, [], False, False, ["sector_boundary", "critical_gap"], "This is Don't Match because the work is released electrical design and certification authority, while embedded bring-up and CAN experience are only peripheral and do not satisfy the critical design requirement.", 6, "The full-time onsite lab role is based in Kitchener.", "Canadian authorization is required and sponsorship is available.", "The role is senior level.") ,
_s("validation-077", "val-profile-02", "validation-group-02", "verification", "Secure Systems Verification Engineer", "Pine Atlas Defense", "Colorado Springs, CO, United States", "onsite", "senior", "2026-07-16", False, "Pine Atlas Defense is hiring a full-time Senior Secure Systems Verification Engineer for its Colorado Springs facility. The onsite engineer will execute hardware-in-loop scenarios, maintain requirements traceability, analyze Linux logs, and coordinate evidence with firmware and electrical teams. System verification and HIL execution are critical, with Python bench tooling required. ROS 2 and CAN integration are preferred technical context. Pine Atlas published the role on 2026-07-16. The appointment requires United States citizenship and an active Secret clearance; no sponsorship is available. Daily work occurs inside the cleared facility, and Canadian authorization alone cannot satisfy the access condition. The verification team records test configuration and anomaly disposition for every controlled release.", [("secure-verification", "Execute HIL scenarios, maintain traceability, analyze Linux logs, and coordinate evidence with firmware and electrical teams.")], [("verification-core", "System verification and hardware-in-loop execution are critical.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("bench", "Python bench tooling and controlled-release evidence are required.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("robotics", "ROS 2 and CAN integration are preferred.", ["profile:val-profile-02:e2"])], ["e2", "e4", "e5"], [("technical_overlap", "HIL, traceability, Linux debugging, and cross-functional verification evidence directly match the technical assignment, but do not provide the required citizenship or clearance.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "posting:validation-077:critical_requirement:verification-core"])], [("clearance_conflict", "The posting requires United States citizenship and an active Secret clearance, while the reviewed candidate has Canada-only authorization and confirmed no clearance.", ["posting:validation-077:location", "posting:validation-077:authorization", "preferences:val-profile-02:work_authorization", "profile:val-profile-02:clearance-status"])], "ineligible", [("hard_clearance_conflict", "The Colorado Springs cleared location, citizenship condition, and active Secret requirement conflict with the candidate's confirmed Canadian authorization and confirmed absence of clearance.", ["posting:validation-077:location", "posting:validation-077:authorization", "preferences:val-profile-02:work_authorization", "profile:val-profile-02:clearance-status"], "posting:validation-077:authorization", "profile:val-profile-02:clearance-status")], "dont_match", False, [], False, False, ["clearance_conflict", "work_authorization"], "The technical verification fit is direct, but this is Don't Match because the cleared Colorado Springs appointment requires United States citizenship and an active Secret clearance that the candidate does not have.", 7, "The full-time onsite facility role is in Colorado Springs, United States.", "United States citizenship and an active Secret clearance are mandatory; sponsorship is unavailable.", "The position is senior level.") ,
_s("validation-078", "val-profile-02", "validation-group-02", "hardware_systems_integration", "Principal Systems Integration Architect", "Cedar Meridian Rail", "Ottawa, ON", "hybrid", "principal", "2026-07-17", True, "Cedar Meridian Rail is seeking a full-time Principal Systems Integration Architect for its Ottawa hybrid engineering office. The principal owns an enterprise interface architecture, sets standards across several programs, mentors technical leads, and signs cross-product integration decisions. The critical qualification is organization-wide architecture authority for rail systems. Required qualifications include principal-level influence, staff development, supplier governance, and responsibility for program-wide risk acceptance. Embedded integration, requirements traceability, and HIL evidence are preferred context but are not principal architecture ownership. Cedar Meridian published the opening on 2026-07-17. Canadian authorization is required and sponsorship is available. The architect presents cross-program decisions to a review board and maintains the interface standard for every vehicle platform.", [("architecture", "Own enterprise interface architecture, set standards, mentor leads, and sign cross-product decisions.")], [("principal-core", "Organization-wide architecture authority for rail systems is critical.", [])], [("scope", "Principal influence, staff development, supplier governance, and program-wide risk acceptance are required.", [])], [("integration", "Embedded integration, requirements traceability, and HIL evidence are preferred.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5"])], ["e2", "e4", "e5"], [("peripheral_integration_context", "Embedded integration, traceability, and HIL work provide peripheral systems context but do not establish principal architecture or program governance.", ["profile:val-profile-02:e2", "profile:val-profile-02:e4", "profile:val-profile-02:e5", "posting:validation-078:preferred_qualification:integration"])], [("level_scope_gap", "The confirmed target levels are mid and senior, and the reviewed evidence does not establish enterprise architecture authority, staff development, or program-wide risk acceptance.", ["profile:val-profile-02:experience-years", "posting:validation-078:critical_requirement:principal-core", "posting:validation-078:required_qualification:scope", "preferences:val-profile-02:target_level"])], "ineligible", [("level_conflict", "The principal posting requires enterprise architecture and program-wide scope, while the candidate targets mid and senior levels and the reviewed duration does not establish principal authority.", ["posting:validation-078:level", "posting:validation-078:responsibility:architecture", "posting:validation-078:required_qualification:scope", "preferences:val-profile-02:target_level", "profile:val-profile-02:experience-years"], "posting:validation-078:level", "preferences:val-profile-02:target_level")], "dont_match", False, [], False, False, ["level_mismatch", "scope_conflict"], "This is Don't Match because principal enterprise architecture and program-wide risk authority exceed the candidate's confirmed target levels and reviewed integration scope; the technical overlap is peripheral.", 8, "The full-time hybrid office is based in Ottawa.", "Canadian authorization is required and sponsorship is available.", "The role is principal level and spans several programs.") ,
_s("validation-079", "val-profile-02", "validation-group-02", "embedded_systems", "Analog Controls Hardware Engineer", "Blue Trestle Instruments", "Toronto, ON", "onsite", "mid", "2026-07-18", True, "Blue Trestle Instruments is adding a full-time mid-level Analog Controls Hardware Engineer to its Toronto onsite lab. The engineer designs analog signal paths, selects amplifiers, validates noise margins, and releases schematics for precision instruments. The critical qualification is production analog circuit design ownership from calculation through board release. Required qualifications include SPICE simulation, component tolerance analysis, and formal schematic sign-off. Embedded firmware, serial debugging, and Python benches are preferred because the hardware exchanges data with a controller. Blue Trestle published the role on 2026-07-18. Canadian authorization is required and sponsorship is available. Electrical designers work with manufacturing to resolve yield issues and maintain the released circuit baseline.", [("analog", "Design analog signal paths, select amplifiers, validate noise margins, and release schematics.")], [("analog-core", "Production analog circuit design ownership from calculation through board release is critical.", [])], [("schematic", "SPICE simulation, tolerance analysis, and formal schematic sign-off are required.", [])], [("embedded", "Embedded firmware, serial debugging, and Python benches are preferred.", ["profile:val-profile-02:e1", "profile:val-profile-02:e3", "profile:val-profile-02:e4"])], ["e1", "e3", "e4"], [("peripheral_embedded_context", "Firmware, serial debugging, and Python bench work are peripheral context and do not establish analog circuit design or schematic authority.", ["profile:val-profile-02:e1", "profile:val-profile-02:e3", "profile:val-profile-02:e4", "posting:validation-079:preferred_qualification:embedded"])], [("missing_critical_design", "No reviewed evidence establishes analog circuit calculation, SPICE work, tolerance analysis, or released schematic sign-off.", ["posting:validation-079:critical_requirement:analog-core"])], "eligible", [("no_known_hard_conflict", "The Toronto onsite location and Canadian authorization condition match the confirmed preference.", ["posting:validation-079:location", "posting:validation-079:authorization", "preferences:val-profile-02:work_authorization"], "posting:validation-079:authorization", "preferences:val-profile-02:work_authorization")], "dont_match", False, [], False, False, ["critical_gap", "sector_boundary"], "This is Don't Match because analog circuit design and schematic sign-off are the critical daily responsibilities, and embedded firmware or Python benches cannot substitute for that missing design ownership.", 9, "The full-time onsite lab role is based in Toronto.", "Canadian authorization is required and sponsorship is available.", "The role is mid-level.") ,
_s("validation-080", "val-profile-02", "validation-group-02", "verification", "Systems Test Engineer, Prototype Lab", "Willow Crest Devices", "Remote geography unstated", "remote", "unknown", None, None, "Willow Crest Devices has provided an incomplete full-time Systems Test Engineer advertisement for a prototype lab. The engineer would translate requirements into test cases, collect Python bench data, execute hardware-in-loop scenarios, and work with firmware and electrical partners when a result fails. System verification is the critical qualification. Required work includes physical actuator-bench commissioning, calibration setup, and closed-loop tuning during prototype trials; the available profile evidence demonstrates acquisition and HIL execution but not full physical commissioning ownership. The posting says remote, yet the country, exact location, date, level, authorization policy, and sponsorship rule are not stated. Willow Crest asks applicants to confirm those details before a technical screen. The lab records instrument settings and firmware revisions for each trial.", [("prototype", "Translate requirements into cases, collect Python bench data, execute HIL scenarios, and investigate failed trials.")], [("verification-core", "System verification is critical.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5"])], [("bench-commissioning", "Physical actuator-bench commissioning, calibration setup, and closed-loop tuning are required.", ["profile:val-profile-02:e4", "profile:val-profile-02:e7"])], [("cross-functional", "Firmware and electrical collaboration is preferred.", ["profile:val-profile-02:e6"])], ["e4", "e5", "e6"], [("direct_verification_match", "Requirements traceability, Python acquisition, HIL execution, and firmware/electrical collaboration directly cover the stated verification core.", ["profile:val-profile-02:e4", "profile:val-profile-02:e5", "profile:val-profile-02:e6", "posting:validation-080:critical_requirement:verification-core", "posting:validation-080:responsibility:prototype"])], [("insufficient_commissioning_depth", "Bench acquisition and HIL execution are genuine evidence, but they do not establish physical actuator-bench commissioning, calibration setup, and closed-loop tuning ownership.", ["profile:val-profile-02:e4", "profile:val-profile-02:e7", "posting:validation-080:required_qualification:bench-commissioning"])], "unknown", [("eligibility_unknown", "The remote geography, date, level, authorization, and sponsorship facts are unresolved, while the candidate supplies confirmed Canadian authorization and mid/senior target levels.", ["posting:validation-080:location", "posting:validation-080:posting_date:posting-date", "posting:validation-080:level", "posting:validation-080:authorization", "preferences:val-profile-02:work_authorization", "preferences:val-profile-02:target_level"], "posting:validation-080:location", "preferences:val-profile-02:work_authorization")], "weak", True, ["incomplete_description", "unresolved_authorization", "missing_date", "uncertain_level", "remote_ambiguity"], True, True, ["incomplete_posting", "unknown_eligibility"], "This is Weak because system verification, acquisition, and HIL work directly match the critical core, while full physical-bench commissioning and loop tuning remain insufficient and eligibility facts are unresolved; the proposal is provisional.", 10, "The full-time remote job has no stated country or city.", "Authorization and sponsorship conditions are unstated.", "The level is not stated.") ,
]


PAIR_RATIONALES = {
    "validation-group-01": {
        ("validation-061", "validation-062"): "Blue Orchard is preferred because service ownership and release recovery are the clearer backend core, while Riverglass is a similarly direct data-platform Excellent case.",
        ("validation-061", "validation-063"): "Blue Orchard is preferred because it has complete critical and required coverage, while Kite Harbor retains a peak streaming-depth gap.",
        ("validation-061", "validation-064"): "Blue Orchard is preferred because its API core and required qualifications are fully demonstrated, while Northline has a Kubernetes operations stretch.",
        ("validation-061", "validation-070"): "Blue Orchard is preferred because its posting authority and eligibility are complete, while Dawn Quarry is provisional with unresolved conditions and a replay gap.",
        ("validation-062", "validation-063"): "Riverglass is preferred because its data-platform responsibilities are fully demonstrated, while Kite Harbor has a limited high-volume operations gap.",
        ("validation-062", "validation-064"): "Riverglass is preferred because direct data-platform ownership is stronger than Northline's adjacent reliability and model-platform stretch.",
        ("validation-062", "validation-070"): "Riverglass is preferred because its remote Canada conditions are confirmed and its required coverage is complete, while Dawn Quarry remains provisional.",
        ("validation-063", "validation-064"): "Kite Harbor is preferred because its streaming responsibilities are closer to the profile's data movement than Northline's Kubernetes and inference-platform adjacency.",
        ("validation-063", "validation-070"): "Kite Harbor is preferred because its senior streaming scope and eligibility are specified, while Dawn Quarry leaves date, level, and authorization unresolved.",
        ("validation-064", "validation-070"): "Dawn Quarry is preferred because its direct backend core and limited event-replay depth gap support a Good grade, while Northline has two material required stretches in production Kubernetes operations and model-endpoint rollout support.",
    },
    "validation-group-02": {
        ("validation-071", "validation-072"): "Copper Ridge is preferred because constrained embedded ownership is the sharper direct match, while Meridian Loom is a similarly complete verification Excellent case.",
        ("validation-071", "validation-073"): "Copper Ridge is preferred because its gateway ownership has complete required coverage, while Lantern Vale has a trial-regression depth gap.",
        ("validation-071", "validation-074"): "Copper Ridge is preferred because production embedded responsibilities are direct, while Prairie Current is a controls adjacency with commissioning depth missing.",
        ("validation-071", "validation-080"): "Copper Ridge is preferred because its level, date, location, and authorization are confirmed, while Willow Crest remains provisional.",
        ("validation-072", "validation-073"): "Meridian Loom is preferred because verification ownership is complete, while Lantern Vale has a limited multi-robot trial depth gap.",
        ("validation-072", "validation-074"): "Meridian Loom is preferred because requirements and HIL verification cover the role without the physical controls-depth gap in Prairie Current.",
        ("validation-072", "validation-080"): "Meridian Loom is preferred because its verification posting and eligibility facts are complete, while Willow Crest is provisional with bench-commissioning insufficiency.",
        ("validation-073", "validation-074"): "Lantern Vale is preferred because ROS 2 hardware integration is closer to the profile's production boundary than Prairie Current's controls-tuning stretch.",
        ("validation-073", "validation-080"): "Lantern Vale is preferred because its integration scope is specified and eligible, while Willow Crest has unresolved metadata and a larger bench-depth uncertainty.",
        ("validation-074", "validation-080"): "Prairie Current is preferred because its controls-test scope and eligibility are specified, while Willow Crest remains provisional with unresolved posting authority.",
    },
}


def _add_pairs(cases: list[dict[str, Any]], order: list[str], rationales: dict[tuple[str, str], str]) -> None:
    visible = {case["case_id"] for case in cases if case["normal_feed_visible"]}
    by_id = {case["case_id"]: case for case in cases}
    for left_index, left_id in enumerate(order):
        for right_id in order[left_index + 1:]:
            if left_id not in visible or right_id not in visible:
                continue
            rationale = rationales[tuple(sorted((left_id, right_id)))]
            preferred_id = left_id
            by_id[preferred_id]["comparable_pair_annotations"].append({"other_case_id": right_id, "relationship": "preferred_to_other", "rationale": rationale})


def build() -> None:
    cases = [_make_case(spec) for spec in SPECS]
    _add_pairs(cases[:10], ["validation-061", "validation-062", "validation-063", "validation-070", "validation-064"], PAIR_RATIONALES["validation-group-01"])
    _add_pairs(cases[10:], ["validation-071", "validation-072", "validation-073", "validation-074", "validation-080"], PAIR_RATIONALES["validation-group-02"])
    path = ROOT / "validation.json"
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["splits"]["validation"] = {
        "path": "validation.json",
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "case_count": 20,
        "proposed_case_ids": [case["case_id"] for case in cases],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
