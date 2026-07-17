from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations

from resume_tailor.application.skill_selection import DeterministicSkillSelector
from resume_tailor.domain.job_discovery.role_signals import (
    ROLE_SIGNAL_CATALOG,
    classify_role_signals,
)
from resume_tailor.domain.models import (
    ClaimCandidate,
    ClaimComposition,
    ClaimSupport,
    Decision,
    DecisionReport,
    EntityKind,
    EvidenceItem,
    GeneratedSkill,
    JobPosting,
    MasterProfile,
    ProfileFitAssessment,
    ProfileFitStatus,
    ResumeItem,
    ResumeStrategy,
    ReviewedTechnicalSkill,
    RoleClassification,
    RoleClassificationDiagnostic,
    RoleClassificationFallbackReason,
    RoleClassificationSource,
    RoleSignal,
    StructuredBullet,
    StructuredResume,
    TailoringPlan,
    TemplateConstraints,
)
from resume_tailor.ports.interfaces import OpportunityAnalyzer


class UnsupportedOpportunityError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateRecord:
    candidate: ClaimCandidate
    signal_ids: frozenset[str]
    impact: float


@dataclass(frozen=True)
class EntryPackage:
    entity_id: str
    kind: EntityKind
    candidates: tuple[CandidateRecord, ...]
    signal_ids: frozenset[str]
    impact: float
    line_cost: int


class MultiRoleOpportunityAnalyzer:
    _signals = tuple(definition.as_role_signal() for definition in ROLE_SIGNAL_CATALOG)

    def analyze(self, posting: JobPosting) -> RoleClassification:
        result = classify_role_signals(posting.title, posting.description)
        if not result.supported or result.primary_family is None:
            return RoleClassification(
                role_family="unsupported",
                confidence=0.0,
                supported=False,
                reason=result.reason,
                diagnostic=RoleClassificationDiagnostic(
                    semantic_enabled=False,
                    selected_source=RoleClassificationSource.DETERMINISTIC,
                    fallback_reason=RoleClassificationFallbackReason.DISABLED,
                ),
            )
        return RoleClassification(
            role_family=result.primary_family.value,
            confidence=result.confidence,
            supported=True,
            signals=result.signals,
            secondary_role_families=result.secondary_role_families,
            diagnostic=RoleClassificationDiagnostic(
                semantic_enabled=False,
                selected_source=RoleClassificationSource.DETERMINISTIC,
                resolved_primary_family=result.primary_family,
                deterministic_primary_family=result.primary_family,
                fallback_reason=RoleClassificationFallbackReason.DISABLED,
            ),
        )

class DeterministicResumeOptimizer:
    def __init__(
        self,
        opportunity_analyzer: OpportunityAnalyzer | None = None,
        skill_selector: DeterministicSkillSelector | None = None,
    ) -> None:
        self._opportunity_analyzer = opportunity_analyzer or MultiRoleOpportunityAnalyzer()
        self._skill_selector = skill_selector or DeterministicSkillSelector()

    def create_plan(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
    ) -> TailoringPlan:
        role = self._opportunity_analyzer.analyze(posting)
        if not role.supported:
            return self._unsupported_plan(profile, posting, constraints, role)

        entities = {item.id: item for item in profile.experiences + profile.projects}
        records = self._candidate_records(profile, role, constraints)
        fit = self._assess_profile_fit(profile, records, role)
        if fit.status == ProfileFitStatus.INSUFFICIENT:
            return TailoringPlan(
                profile_id=profile.id,
                profile_version=profile.version,
                posting_id=posting.id,
                template_id=constraints.template_id,
                posting=posting,
                constraints=constraints,
                report=DecisionReport(role=role, profile_fit=fit, warnings=[fit.reason]),
            )

        packages = self._entry_packages(records, entities, constraints)
        selected_packages = self._select_packages(packages, role, constraints)
        selected_records = [record for package in selected_packages for record in package.candidates]
        selected_entity_ids = [package.entity_id for package in selected_packages]
        covered_signal_ids = set().union(*(package.signal_ids for package in selected_packages)) if selected_packages else set()
        skill_plan = self._skill_selector.select(
            profile,
            posting,
            role,
            constraints.max_skill_lines,
        )
        selected_skills = (
            skill_plan.flattened_selected_values
            if profile.technical_skills
            else self._select_skills(profile, selected_records, role)
        )
        selected_coursework = self._select_coursework(profile.coursework, role)
        estimated_lines = sum(package.line_cost for package in selected_packages)
        estimated_lines += int(bool(selected_skills)) + int(bool(selected_coursework))
        strategy = self._strategy(role, fit)
        decisions = [
            *self._build_decisions(entities, selected_packages, records, role, constraints),
            *skill_plan.decisions,
        ]
        uncovered = [signal.label for signal in role.signals if signal.id not in covered_signal_ids]
        return TailoringPlan(
            profile_id=profile.id,
            profile_version=profile.version,
            posting_id=posting.id,
            template_id=constraints.template_id,
            posting=posting,
            constraints=constraints,
            strategy=strategy,
            report=DecisionReport(
                role=role,
                profile_fit=fit,
                decisions=decisions,
                warnings=["Only confirmed, evidence-linked claims are eligible for experience and project bullets."],
                uncovered_signals=uncovered,
            ),
            selected_entity_ids=selected_entity_ids,
            selected_claim_ids=[record.candidate.id for record in selected_records],
            claim_candidates=[record.candidate for record in selected_records],
            education=profile.education,
            technical_skills=skill_plan.selected_profile_categories,
            selected_skill_categories=skill_plan.selected,
            ranked_skill_categories=skill_plan.ranked,
            selected_experiences=[
                item for entity_id in selected_entity_ids for item in profile.experiences
                if item.id == entity_id
            ],
            selected_projects=[
                item for entity_id in selected_entity_ids for item in profile.projects
                if item.id == entity_id
            ],
            selected_skills=selected_skills,
            selected_coursework=selected_coursework,
            estimated_lines=estimated_lines,
        )

    def _unsupported_plan(
        self,
        profile: MasterProfile,
        posting: JobPosting,
        constraints: TemplateConstraints,
        role: RoleClassification,
    ) -> TailoringPlan:
        return TailoringPlan(
            profile_id=profile.id,
            profile_version=profile.version,
            posting_id=posting.id,
            template_id=constraints.template_id,
            posting=posting,
            constraints=constraints,
            report=DecisionReport(role=role, warnings=[role.reason or "The posting could not be classified."]),
        )

    def _candidate_records(
        self,
        profile: MasterProfile,
        role: RoleClassification,
        constraints: TemplateConstraints,
    ) -> list[CandidateRecord]:
        records: list[CandidateRecord] = []
        evidence_by_entity: dict[str, list[EvidenceItem]] = {}
        for evidence in profile.evidence:
            if not evidence.confirmed:
                continue
            signal_ids = self._matching_signal_ids(self._evidence_text(evidence), role)
            if not signal_ids:
                continue
            candidate = ClaimCandidate(
                id=evidence.id,
                entity_id=evidence.entity_id,
                text=evidence.source_text,
                evidence_ids=[evidence.id],
                support=ClaimSupport.DIRECT,
                estimated_lines=self._estimate_lines(evidence.source_text),
                required_terms=[*evidence.technologies, *evidence.outcomes],
                max_rendered_lines=constraints.max_combined_bullet_lines,
            )
            records.append(CandidateRecord(candidate, frozenset(signal_ids), self._impact(evidence)))
            evidence_by_entity.setdefault(evidence.entity_id, []).append(evidence)
        records.extend(self._combined_records(records, evidence_by_entity, role, constraints))
        return records

    def _combined_records(
        self,
        records: list[CandidateRecord],
        evidence_by_entity: dict[str, list[EvidenceItem]],
        role: RoleClassification,
        constraints: TemplateConstraints,
    ) -> list[CandidateRecord]:
        records_by_evidence = {record.candidate.id: record for record in records}
        combined: list[CandidateRecord] = []
        for entity_id, evidence_items in evidence_by_entity.items():
            for first, second in combinations(evidence_items, 2):
                shared_terms = set(first.capabilities + first.technologies).intersection(
                    second.capabilities + second.technologies
                )
                if not shared_terms:
                    continue
                text = f"{first.source_text} {second.source_text}"
                estimated_lines = self._estimate_lines(text)
                if estimated_lines > constraints.max_combined_bullet_lines:
                    continue
                signal_ids = self._matching_signal_ids(self._evidence_text(first), role)
                signal_ids.update(self._matching_signal_ids(self._evidence_text(second), role))
                if not signal_ids:
                    continue
                first_record = records_by_evidence[first.id]
                second_record = records_by_evidence[second.id]
                candidate = ClaimCandidate(
                    id=f"combined:{first.id}:{second.id}",
                    entity_id=entity_id,
                    text=text,
                    evidence_ids=[first.id, second.id],
                    support=ClaimSupport.DIRECT,
                    estimated_lines=estimated_lines,
                    composition=ClaimComposition.COMBINED,
                    required_terms=list(dict.fromkeys([*first.technologies, *first.outcomes, *second.technologies, *second.outcomes])),
                    max_rendered_lines=constraints.max_combined_bullet_lines,
                )
                combined.append(
                    CandidateRecord(
                        candidate,
                        frozenset(signal_ids),
                        first_record.impact + second_record.impact,
                    )
                )
        return combined

    def _assess_profile_fit(
        self,
        profile: MasterProfile,
        records: list[CandidateRecord],
        role: RoleClassification,
    ) -> ProfileFitAssessment:
        direct_signal_ids = set().union(*(record.signal_ids for record in records)) if records else set()
        declared_skill_signal_ids = self._matching_declared_skill_signal_ids(profile.declared_skills, role)
        material_gaps = [
            signal.label
            for signal in role.signals
            if signal.required and signal.id not in direct_signal_ids
        ]
        primary_direct_evidence = any(
            signal.family.value == role.role_family and signal.id in direct_signal_ids for signal in role.signals
        )
        if not records:
            return ProfileFitAssessment(
                status=ProfileFitStatus.INSUFFICIENT,
                declared_skill_signal_ids=sorted(declared_skill_signal_ids),
                material_gaps=[signal.label for signal in role.signals],
                reason="The reviewed profile has no confirmed evidence that directly supports this opportunity.",
            )
        if material_gaps or not primary_direct_evidence:
            return ProfileFitAssessment(
                status=ProfileFitStatus.LIMITED,
                direct_signal_ids=sorted(direct_signal_ids),
                declared_skill_signal_ids=sorted(declared_skill_signal_ids),
                material_gaps=material_gaps,
                reason="The profile has relevant direct evidence, but important posting requirements remain unproven.",
            )
        return ProfileFitAssessment(
            status=ProfileFitStatus.SUFFICIENT,
            direct_signal_ids=sorted(direct_signal_ids),
            declared_skill_signal_ids=sorted(declared_skill_signal_ids),
            reason="The profile contains direct evidence for the opportunity's primary role signals.",
        )

    def _entry_packages(
        self,
        records: list[CandidateRecord],
        entities: dict[str, ResumeItem],
        constraints: TemplateConstraints,
    ) -> list[EntryPackage]:
        by_entity: dict[str, list[CandidateRecord]] = {}
        for record in records:
            by_entity.setdefault(record.candidate.entity_id, []).append(record)
        packages: list[EntryPackage] = []
        for entity_id, entity_records in by_entity.items():
            candidates = sorted(entity_records, key=lambda record: (-record.impact, record.candidate.id))[:8]
            overhead = (
                constraints.experience_entry_overhead_lines
                if entities[entity_id].kind == EntityKind.EXPERIENCE
                else constraints.project_entry_overhead_lines
            )
            for count in range(1, min(constraints.max_bullets_per_entry, len(candidates)) + 1):
                for option in combinations(candidates, count):
                    evidence_ids = [evidence_id for record in option for evidence_id in record.candidate.evidence_ids]
                    if len(evidence_ids) != len(set(evidence_ids)):
                        continue
                    signal_ids = frozenset().union(*(record.signal_ids for record in option))
                    line_cost = overhead + sum(record.candidate.estimated_lines for record in option)
                    packages.append(
                        EntryPackage(
                            entity_id=entity_id,
                            kind=entities[entity_id].kind,
                            candidates=option,
                            signal_ids=signal_ids,
                            impact=sum(record.impact for record in option),
                            line_cost=line_cost,
                        )
                    )
        return packages

    def _select_packages(
        self,
        packages: list[EntryPackage],
        role: RoleClassification,
        constraints: TemplateConstraints,
    ) -> list[EntryPackage]:
        selected: list[EntryPackage] = []
        remaining = list(packages)
        while remaining:
            eligible = [package for package in remaining if self._fits(package, selected, constraints)]
            if not eligible:
                break
            best = max(
                eligible,
                key=lambda package: (
                    self._marginal_utility(package, selected, role),
                    -package.line_cost,
                    package.entity_id,
                ),
            )
            if self._marginal_utility(best, selected, role) <= 0:
                break
            selected.append(best)
            remaining = [package for package in remaining if package.entity_id != best.entity_id]
        return self._local_improve(selected, packages, role, constraints)

    def _local_improve(
        self,
        selected: list[EntryPackage],
        packages: list[EntryPackage],
        role: RoleClassification,
        constraints: TemplateConstraints,
    ) -> list[EntryPackage]:
        current = selected[:]
        improved = True
        while improved:
            improved = False
            baseline = self._plan_utility(current, role)
            for index, package in enumerate(current):
                for alternative in packages:
                    if alternative.entity_id != package.entity_id:
                        continue
                    proposal = [*current[:index], alternative, *current[index + 1 :]]
                    if not self._all_fit(proposal, constraints):
                        continue
                    if self._plan_utility(proposal, role) > baseline:
                        current = proposal
                        improved = True
                        break
                if improved:
                    break
        return current

    def _fits(self, package: EntryPackage, selected: list[EntryPackage], constraints: TemplateConstraints) -> bool:
        if any(item.entity_id == package.entity_id for item in selected):
            return False
        return self._all_fit([*selected, package], constraints)

    @staticmethod
    def _all_fit(packages: list[EntryPackage], constraints: TemplateConstraints) -> bool:
        total = sum(package.line_cost for package in packages)
        experience = sum(package.line_cost for package in packages if package.kind == EntityKind.EXPERIENCE)
        project = sum(package.line_cost for package in packages if package.kind == EntityKind.PROJECT)
        return (
            total <= constraints.max_total_lines
            and experience <= constraints.max_experience_lines
            and project <= constraints.max_project_lines
        )

    def _marginal_utility(
        self,
        package: EntryPackage,
        selected: list[EntryPackage],
        role: RoleClassification,
    ) -> float:
        selected_signals = set().union(*(item.signal_ids for item in selected)) if selected else set()
        added_signal_utility = sum(
            signal.weight * 10 for signal in role.signals if signal.id in package.signal_ids - selected_signals
        )
        repeated_signal_penalty = sum(
            signal.weight * 5 for signal in role.signals if signal.id in package.signal_ids.intersection(selected_signals)
        )
        return added_signal_utility + package.impact - repeated_signal_penalty - (package.line_cost * 1.5)

    def _plan_utility(self, packages: list[EntryPackage], role: RoleClassification) -> float:
        signal_ids = set().union(*(package.signal_ids for package in packages)) if packages else set()
        signal_utility = sum(signal.weight * 10 for signal in role.signals if signal.id in signal_ids)
        return signal_utility + sum(package.impact for package in packages) - (sum(package.line_cost for package in packages) * 1.5)

    def _select_skills(
        self,
        profile: MasterProfile,
        selected_records: list[CandidateRecord],
        role: RoleClassification,
    ) -> list[str]:
        demonstrated = [
            term
            for record in selected_records
            for term in record.candidate.required_terms
            if self._term_matches_role(term, role)
        ]
        declared = [skill for skill in profile.declared_skills if self._term_matches_role(skill, role)]
        return list(dict.fromkeys([*demonstrated, *declared]))[:10]

    def _select_coursework(self, coursework: list[str], role: RoleClassification) -> list[str]:
        return [course for course in coursework if self._term_matches_role(course, role)][:3]

    def _strategy(self, role: RoleClassification, fit: ProfileFitAssessment) -> ResumeStrategy:
        primary_signal = max(role.signals, key=lambda signal: (signal.weight, signal.id))
        return ResumeStrategy(
            role_family=role.role_family,
            primary_focus=primary_signal.label,
            secondary_focuses=[family.value.replace("_", " ") for family in role.secondary_role_families],
            de_emphasized_themes=["evidence that does not add role-signal coverage after entry cost"],
            rationale=(
                f"Prioritize verified evidence for {primary_signal.label}; profile fit is {fit.status.value}."
            ),
        )

    def _build_decisions(
        self,
        entities: dict[str, ResumeItem],
        selected: list[EntryPackage],
        records: list[CandidateRecord],
        role: RoleClassification,
        constraints: TemplateConstraints,
    ) -> list[Decision]:
        selected_ids = {package.entity_id for package in selected}
        decisions: list[Decision] = []
        for package in selected:
            decisions.append(
                Decision(
                    action="emphasized",
                    entity_id=package.entity_id,
                    evidence_ids=[evidence_id for record in package.candidates for evidence_id in record.candidate.evidence_ids],
                    reason=(
                        f"Included {len(package.candidates)} bullet candidate(s) because their role coverage "
                        f"justified the {package.line_cost}-line entry cost."
                    ),
                    constraint="entry opening cost",
                )
            )
        relevant_entity_ids = {record.candidate.entity_id for record in records}
        for entity_id in entities:
            if entity_id in selected_ids:
                continue
            reason = (
                "Removed because its relevant evidence did not justify opening a new entry after page cost."
                if entity_id in relevant_entity_ids
                else "Removed because it did not cover the opportunity's recognized role signals."
            )
            decisions.append(Decision(action="removed", entity_id=entity_id, reason=reason, constraint="entry opening cost"))
        decisions.append(
            Decision(
                action="allocated_space",
                entity_id="document",
                reason="Entry costs include headings, metadata, spacing, and bullet capacity before content is selected.",
                constraint="template-neutral packing estimate",
            )
        )
        return decisions

    @staticmethod
    def _evidence_text(evidence: EvidenceItem) -> str:
        return " ".join(
            [
                evidence.source_text,
                *evidence.technologies,
                *evidence.capabilities,
                *evidence.outcomes,
            ]
        ).casefold()

    def _matching_signal_ids(self, text: str, role: RoleClassification) -> set[str]:
        return {signal.id for signal in role.signals if any(keyword in text for keyword in signal.keywords)}

    def _matching_declared_skill_signal_ids(self, skills: list[str], role: RoleClassification) -> set[str]:
        return {
            signal.id
            for skill in skills
            for signal in role.signals
            if self._term_matches_signal(skill, signal)
        }

    def _term_matches_role(self, term: str, role: RoleClassification) -> bool:
        return any(self._term_matches_signal(term, signal) for signal in role.signals)

    @staticmethod
    def _term_matches_signal(term: str, signal: RoleSignal) -> bool:
        normalized = term.casefold()
        return any(keyword in normalized or normalized in keyword for keyword in signal.keywords)

    @staticmethod
    def _estimate_lines(text: str) -> int:
        return max(1, math.ceil(len(text) / 90))

    @staticmethod
    def _impact(evidence: EvidenceItem) -> float:
        numeric_signal = any(character.isdigit() for character in evidence.source_text)
        return 2 + (1.5 * len(evidence.outcomes)) + (1 if numeric_signal else 0)


class EvidenceBoundResumeWriter:
    def write(
        self,
        plan: TailoringPlan,
        profile: MasterProfile,
        approved_claim_ids: set[str],
    ) -> StructuredResume:
        if plan.strategy is None:
            raise UnsupportedOpportunityError("Cannot generate a resume without sufficient profile fit.")
        entity_kinds = {item.id: item.kind for item in profile.experiences + profile.projects}
        experience_bullets: dict[str, list[StructuredBullet]] = {}
        project_bullets: dict[str, list[StructuredBullet]] = {}
        review_required: list[str] = []
        review_pending_bullets: list[StructuredBullet] = []
        for candidate in plan.claim_candidates:
            if candidate.support == ClaimSupport.UNSUPPORTED:
                continue
            if candidate.support == ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW and candidate.id not in approved_claim_ids:
                review_required.append(candidate.id)
                review_pending_bullets.append(
                    StructuredBullet(
                        id=candidate.id,
                        text=candidate.text,
                        evidence_ids=candidate.evidence_ids,
                        support=candidate.support,
                    )
                )
                continue
            bullet = StructuredBullet(
                id=candidate.id,
                text=candidate.text,
                evidence_ids=candidate.evidence_ids,
                support=candidate.support,
            )
            target = experience_bullets if entity_kinds[candidate.entity_id] == EntityKind.EXPERIENCE else project_bullets
            target.setdefault(candidate.entity_id, []).append(bullet)
        technical_skills = [category.model_copy(deep=True) for category in plan.technical_skills]
        review_pending_skills: list[GeneratedSkill] = []
        selected_category_ids = {category.id for category in technical_skills}
        for skill in plan.demonstrated_skills:
            if skill.category_id not in selected_category_ids:
                continue
            if skill.support == ClaimSupport.STRONG_INFERENCE_PENDING_REVIEW and skill.id not in approved_claim_ids:
                review_required.append(skill.id)
                review_pending_skills.append(skill)
                continue
            category = next(category for category in technical_skills if category.id == skill.category_id)
            if skill.value.casefold() in {value.casefold() for value in category.values}:
                continue
            category.values.append(skill.value)
            category.skills.append(
                ReviewedTechnicalSkill(value=skill.value, source_reference="generated-demonstrated-skill")
            )
        return StructuredResume(
            profile_id=profile.id,
            profile_version=profile.version,
            posting_id=plan.posting_id,
            template_id=plan.template_id,
            display_name=profile.display_name,
            contact_line=self._contact_line(profile),
            strategy=plan.strategy,
            entity_titles={item.id: item.title for item in profile.experiences + profile.projects},
            education=plan.education,
            technical_skills=technical_skills,
            experiences=plan.selected_experiences,
            projects=plan.selected_projects,
            experience_bullets=experience_bullets,
            project_bullets=project_bullets,
            selected_skills=[
                skill.value
                for category in plan.selected_skill_categories
                for skill in category.skills
            ] if plan.selected_skill_categories else plan.selected_skills,
            selected_coursework=plan.selected_coursework,
            review_required_claim_ids=review_required,
            review_pending_bullets=review_pending_bullets,
            review_pending_skills=review_pending_skills,
            demonstrated_skills=plan.demonstrated_skills,
        )

    @staticmethod
    def _contact_line(profile: MasterProfile) -> str | None:
        parts = [profile.contact.email, profile.contact.phone, profile.contact.location, *profile.contact.links]
        populated = [part for part in parts if part]
        return " | ".join(populated) or None
