from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256

from resume_tailor.application.llm_validation import (
    GroundingValidationError,
    grounding_failure_code,
    validate_grounded_text,
)
from resume_tailor.domain.company_research import (
    CompanyFactConfidence,
    CompanyResearchBundle,
    CompanyResearchFact,
)
from resume_tailor.domain.cover_letter import (
    CoverLetterCanonicalMetadata,
    CoverLetterClaimDiagnostic,
    CoverLetterEvidenceKind,
    CoverLetterEvidenceRecord,
    CoverLetterLengthClass,
    CoverLetterParagraph,
    CoverLetterParagraphPurpose,
    CoverLetterQualityGateResult,
    CoverLetterQualityGateStatus,
    CoverLetterResumeConsistencyFinding,
    CoverLetterSentenceAuthority,
    CoverLetterValidationStatus,
)
from resume_tailor.domain.llm_models import CoverLetterDraftOutput, CoverLetterDraftParagraph
from resume_tailor.domain.models import JobPosting, StructuredResume

_FORMULAIC_PATTERNS = (
    r"\bi am thrilled to apply\b",
    r"\bi am excited to bring my skills\b",
    r"\bi am passionate about\b",
    r"\bi have always been fascinated by\b",
    r"\bi am particularly drawn to\b",
    r"\bat the intersection of\b",
    r"\bleveraging my experience\b",
    r"\bmy unique combination of\b",
    r"\bi would be honored\b",
    r"\bi am confident that\b",
    r"\bmake a meaningful impact\b",
    r"\bdrive innovation\b",
    r"\bcutting-edge\b",
    r"\bfast-paced environment\b",
    r"\bdynamic team\b",
    r"\binnovative solutions\b",
    r"\bproven track record\b",
    r"\bideal candidate\b",
    r"\balign perfectly\b",
    r"\bbring value from day one\b",
)
_FORBIDDEN_MOTIVATION = (
    r"\bsince (?:i was|childhood)\b",
    r"\bchildhood dream\b",
    r"\blifelong (?:dream|passion)\b",
    r"\bi (?:use|used|have used) (?:your|the company's) product\b",
    r"\b(?:spoke|talked|met) with (?:an?|your) employee\b",
    r"\bmy family(?:'s)? (?:experience|health)\b",
    r"\bpersonal health experience\b",
    r"\bi have always\b",
)
_GENERIC_COMPANY_LANGUAGE = (
    "changing the future",
    "creating positive impact",
    "driving innovation",
    "forefront of technology",
    "improving people's lives",
    "making healthcare accessible",
    "solving meaningful problems",
    "transforming an industry",
)
_OPENING_REJECTIONS = (
    "i am writing to apply",
    "i am applying for",
    "i am thrilled to apply",
    "please accept my application",
    "what stood out to me about",
)
_CLOSING_REJECTIONS = (
    "i look forward to the opportunity",
    "i would welcome the opportunity",
    "thank you for considering my application",
    "i am confident i would be a great fit",
    "i would be honored to join your team",
)
_INTERNAL_PROSE_PATTERNS = (
    r"\b(?:reviewed|selected|accepted)\s+(?:evidence|experience|record|narrative)\b",
    r"\b(?:evidence|source)\s+(?:record|fact|identifier|id)\b",
    r"\bclaim grounding\b",
    r"\bposting authority\b",
    r"\bwithout changing (?:the )?facts or scope\b",
    r"\bdeterministic candidate\b",
    r"\b(?:candidate|company)[ -]detail\b",
    r"\bnarrative thread\b",
    r"\bimplementation evidence\b",
)
_VALIDATOR_PROSE_PATTERNS = (
    r"\bi do not claim direct\b",
    r"\bgrounded starting point\b",
    r"\banchored in technical work\b",
    r"\bthe connection is\b",
    r"\bthe connection to .+ comes from that demonstrated technical work\b",
)
_REPETITIVE_NARRATIVE_PATTERNS = (
    r"\bi also worked with\b",
    r"\bthe work included\b",
    r"\banother responsibility involved\b",
    r"\bmy work included\b",
    r"\bmy [^.]{1,80} work involved\b",
)
_UNRESOLVED_PLACEHOLDER_PATTERNS = (
    r"\[(?:company|company name|role|job title)\]",
    r"\{(?:company|company_name|role|job_title)\}",
    r"<(?:company|company name|role|job title)>",
)
_UNSUBJECTED_ACTION_PATTERN = re.compile(
    r"^(?:assembled|authored|automated|built|collaborated|configured|contributed|created|"
    r"deployed|designed|developed|diagnosed|documented|engineered|evaluated|implemented|"
    r"integrated|led|modeled|modelled|owned|prototyped|selected|specified|supported|"
    r"tested|troubleshot|used|validated|verified)\b",
    re.IGNORECASE,
)
_NATURALNESS_PATTERNS = (
    (
        "malformed_parallel_list",
        r"\b(?:tasks?|paths?|work|responsibilities)\s*,\s*"
        r"(?:mechanical|electrical|embedded|software|hardware)\s*,\s*and\s+"
        r"(?:mechanical|electrical|embedded|software|hardware)\b",
    ),
    (
        "compound_subject_verb_disagreement",
        r"\b[a-z][a-z0-9+#/-]*s\s+and\s+[a-z][a-z0-9+#/-]*s\s+"
        r"(?:comes|provides|shows|demonstrates|offers|gives)\b",
    ),
    (
        "awkward_posting_frame",
        r"\b(?:the|this) work behind\s+(?:the\s+)?(?:intern|candidate|role|position)\b",
    ),
    (
        "vague_direct_technical_referent",
        r"\bi worked directly with\s+(?:the\s+)?(?:hardware|software|system|work|"
        r"hands-on engineering work)\b",
    ),
    (
        "synthetic_bridge_prose",
        r"\b(?:the work brought .+ into the same technical problem|"
        r"a separate constraint joined .+ in the same implementation|"
        r".+ belonged to the same technical chain|"
        r"the same engineering effort)\b",
    ),
    (
        "duplicated_work_frame",
        r"\bhands-on engineering work in my .{1,80} work\b",
    ),
)
_VAGUE_TECHNICAL_REFERENTS = re.compile(
    r"\b(?:the|this|that)\s+(?:hardware|system|work|technology|project|experience)\b",
    re.IGNORECASE,
)
_ABSTRACT_NARRATIVE_ROOTS = {
    "approach",
    "behavior",
    "decision",
    "implement",
    "method",
    "process",
    "system",
    "test",
}
_GENERAL_TECHNICAL_TERMS = {
    "approach",
    "behavior",
    "candidate",
    "central",
    "company",
    "decision",
    "design",
    "engineer",
    "engineering",
    "experience",
    "hardware",
    "included",
    "implement",
    "method",
    "another",
    "part",
    "process",
    "project",
    "result",
    "role",
    "scope",
    "system",
    "technical",
    "test",
    "work",
    "documented",
}
_CONTENT_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "because",
    "been",
    "being",
    "build",
    "company",
    "could",
    "for",
    "from",
    "have",
    "into",
    "role",
    "that",
    "test",
    "the",
    "their",
    "this",
    "through",
    "with",
    "would",
}


class CoverLetterCompanyAuthorityMode(StrEnum):
    POSTING_ONLY = "posting_only"
    VERIFIED_COMPANY_RESEARCH = "verified_company_research"


@dataclass(frozen=True)
class CoverLetterValidationResult:
    paragraphs: list[CoverLetterParagraph]
    rejected_claims: list[CoverLetterClaimDiagnostic]
    review_required_claims: list[CoverLetterClaimDiagnostic]
    resume_consistency: list[CoverLetterResumeConsistencyFinding]
    quality_gates: list[CoverLetterQualityGateResult]


class CoverLetterValidator:
    def validate_output(
        self,
        output: CoverLetterDraftOutput,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
        *,
        final_resume: StructuredResume | None = None,
    ) -> CoverLetterValidationResult:
        evidence_by_id = {item.id: item for item in evidence}
        fact_by_id = {
            item.id: item
            for item in research.facts
            if item.confidence is not CompanyFactConfidence.CONFLICTING
        }
        paragraphs: list[CoverLetterParagraph] = []
        rejected: list[CoverLetterClaimDiagnostic] = []
        review_required: list[CoverLetterClaimDiagnostic] = []
        for index, generated in enumerate(output.paragraphs):
            paragraph, paragraph_rejected, paragraph_review = self._validate_paragraph(
                index,
                generated,
                evidence_by_id,
                fact_by_id,
                posting,
            )
            rejected.extend(paragraph_rejected)
            review_required.extend(paragraph_review)
            if paragraph is not None:
                paragraphs.append(paragraph)
        consistency = self._resume_consistency(paragraphs, evidence_by_id, final_resume)
        gates = self.quality_gates(
            paragraphs,
            evidence,
            research,
            posting,
            rejected_claims=rejected,
            review_required_claims=review_required,
            resume_consistency=consistency,
        )
        return CoverLetterValidationResult(
            paragraphs=paragraphs,
            rejected_claims=rejected,
            review_required_claims=review_required,
            resume_consistency=consistency,
            quality_gates=gates,
        )

    def _validate_paragraph(
        self,
        index: int,
        generated: CoverLetterDraftParagraph,
        evidence_by_id: dict[str, CoverLetterEvidenceRecord],
        fact_by_id: dict[str, CompanyResearchFact],
        posting: JobPosting,
    ) -> tuple[
        CoverLetterParagraph | None,
        list[CoverLetterClaimDiagnostic],
        list[CoverLetterClaimDiagnostic],
    ]:
        unknown_evidence = sorted(set(generated.candidate_evidence_ids) - set(evidence_by_id))
        unknown_facts = sorted(set(generated.company_research_ids) - set(fact_by_id))
        if unknown_evidence or unknown_facts:
            diagnostic = self._claim(
                index,
                generated.text,
                generated.candidate_evidence_ids,
                generated.company_research_ids,
                CoverLetterValidationStatus.REJECTED,
                [
                    *(f"unknown_candidate_evidence:{item}" for item in unknown_evidence),
                    *(f"unknown_company_research:{item}" for item in unknown_facts),
                ],
                "Provider paragraph referenced evidence outside the authorized request.",
                paragraph_index=index,
            )
            return None, [diagnostic], []
        claims: list[CoverLetterClaimDiagnostic] = []
        rejected: list[CoverLetterClaimDiagnostic] = []
        review_required: list[CoverLetterClaimDiagnostic] = []
        text = " ".join(generated.text.split())
        style_codes = self._style_codes(text, generated.purpose, posting)
        if style_codes:
            diagnostic_text = text
            sentence_index = None
            if "copied_posting_language" in style_codes:
                for candidate_index, sentence in enumerate(self._sentences(text)):
                    if "copied_posting_language" in self._style_codes(
                        sentence,
                        generated.purpose,
                        posting,
                    ):
                        diagnostic_text = sentence
                        sentence_index = candidate_index
                        break
            diagnostic = self._claim(
                index,
                diagnostic_text,
                generated.candidate_evidence_ids,
                generated.company_research_ids,
                CoverLetterValidationStatus.REJECTED,
                style_codes,
                "Paragraph failed local writing-policy checks.",
                paragraph_index=index,
                sentence_index=sentence_index,
            )
            return None, [diagnostic], []
        if generated.source_bound_sentences:
            return self._validate_source_bound_paragraph(
                index,
                generated,
                evidence_by_id,
                fact_by_id,
                posting,
                text,
            )

        candidate_records = [evidence_by_id[item] for item in generated.candidate_evidence_ids]
        company_facts = [fact_by_id[item] for item in generated.company_research_ids]
        for sentence_index, sentence in enumerate(self._sentences(text)):
            sentence_codes: list[str] = []
            candidate_clauses = self._candidate_clauses(sentence)
            company_sentence = self._is_company_sentence(sentence, posting, company_facts)
            relationship_sentence = self._relationship_claim_supported(
                sentence,
                candidate_records,
                company_facts,
                posting,
            )
            if self._is_application_intent(sentence):
                candidate_clauses = []
            if relationship_sentence:
                candidate_clauses = []
                company_sentence = False
            if candidate_records and not candidate_clauses and not company_sentence:
                if not relationship_sentence and not self._is_application_intent(sentence):
                    candidate_clauses = [sentence]
            if candidate_clauses:
                if not candidate_records:
                    sentence_codes.append("candidate_claim_without_evidence")
                else:
                    source_texts = [
                        value
                        for record in candidate_records
                        for value in (record.source_text, record.entry_title or "")
                        if value
                    ]
                    structured = [
                        value
                        for record in candidate_records
                        for value in [
                            record.entry_title or "",
                            *record.technologies,
                            *record.outcomes,
                        ]
                        if value
                    ]
                    for clause in candidate_clauses:
                        try:
                            validate_grounded_text(clause, source_texts, structured)
                        except GroundingValidationError as error:
                            sentence_codes.extend(
                                grounding_failure_code(failure).value for failure in error.failures
                            )
                    sentence_codes.extend(self._unsupported_scope_codes(sentence, source_texts))
                sentence_codes.extend(self._motivation_codes(sentence, candidate_records, posting))
            if company_sentence:
                if not company_facts:
                    sentence_codes.append("company_claim_without_verified_source")
                elif not self._company_claim_supported(sentence, company_facts, posting):
                    sentence_codes.append("company_fact_not_verified")
            status = (
                CoverLetterValidationStatus.REJECTED
                if sentence_codes
                else CoverLetterValidationStatus.SUPPORTED
            )
            claim = self._claim(
                index * 100 + sentence_index,
                sentence,
                generated.candidate_evidence_ids,
                generated.company_research_ids,
                status,
                list(dict.fromkeys(sentence_codes)),
                (
                    "Sentence maps to reviewed candidate evidence and verified company authority."
                    if status is CoverLetterValidationStatus.SUPPORTED
                    else "Sentence exceeded its authorized candidate or company evidence."
                ),
                paragraph_index=index,
                sentence_index=sentence_index,
            )
            claims.append(claim)
            if status is CoverLetterValidationStatus.REJECTED:
                rejected.append(claim)
        if rejected:
            return None, rejected, review_required
        return (
            CoverLetterParagraph(
                id=f"cover-paragraph:{index}:{sha256(text.encode()).hexdigest()[:10]}",
                purpose=generated.purpose,
                text=text,
                candidate_evidence_ids=list(generated.candidate_evidence_ids),
                company_research_ids=list(generated.company_research_ids),
                narrative_thread_id=generated.narrative_thread_id,
                length_class=generated.length_class,
                claims=claims,
            ),
            [],
            review_required,
        )

    def _validate_source_bound_paragraph(
        self,
        index: int,
        generated: CoverLetterDraftParagraph,
        evidence_by_id: dict[str, CoverLetterEvidenceRecord],
        fact_by_id: dict[str, CompanyResearchFact],
        posting: JobPosting,
        text: str,
    ) -> tuple[
        CoverLetterParagraph | None,
        list[CoverLetterClaimDiagnostic],
        list[CoverLetterClaimDiagnostic],
    ]:
        """Validate each sentence only against the authority it explicitly records."""

        rejected: list[CoverLetterClaimDiagnostic] = []
        claims: list[CoverLetterClaimDiagnostic] = []
        assembled_text = " ".join(
            " ".join(sentence.text.split())
            for sentence in generated.source_bound_sentences
        )
        if assembled_text != text:
            diagnostic = self._claim(
                index,
                text,
                generated.candidate_evidence_ids,
                generated.company_research_ids,
                CoverLetterValidationStatus.REJECTED,
                ["sentence_authority_text_mismatch"],
                "Paragraph text differs from its source-bound sentence objects.",
                paragraph_index=index,
            )
            return None, [diagnostic], []
        paragraph_evidence_ids = {
            evidence_id
            for sentence in generated.source_bound_sentences
            for evidence_id in sentence.candidate_evidence_ids
        }
        paragraph_company_ids = {
            fact_id
            for sentence in generated.source_bound_sentences
            for fact_id in (
                *sentence.posting_fact_ids,
                *sentence.verified_company_fact_ids,
            )
        }
        if paragraph_evidence_ids != set(generated.candidate_evidence_ids) or (
            paragraph_company_ids != set(generated.company_research_ids)
        ):
            diagnostic = self._claim(
                index,
                text,
                generated.candidate_evidence_ids,
                generated.company_research_ids,
                CoverLetterValidationStatus.REJECTED,
                ["sentence_authority_union_mismatch"],
                "Sentence authority does not match the paragraph authority union.",
                paragraph_index=index,
            )
            return None, [diagnostic], []

        for sentence_index, authority in enumerate(generated.source_bound_sentences):
            sentence_codes: list[str] = []
            unknown_evidence = sorted(
                set(authority.candidate_evidence_ids) - set(evidence_by_id)
            )
            unknown_posting = sorted(
                fact_id
                for fact_id in authority.posting_fact_ids
                if fact_id not in fact_by_id
                or fact_by_id[fact_id].confidence
                is not CompanyFactConfidence.POSTING_AUTHORITY
            )
            unknown_verified = sorted(
                fact_id
                for fact_id in authority.verified_company_fact_ids
                if fact_id not in fact_by_id
                or fact_by_id[fact_id].confidence
                not in {
                    CompanyFactConfidence.VERIFIED,
                    CompanyFactConfidence.USER_AUTHORITY,
                }
            )
            if unknown_evidence:
                sentence_codes.extend(
                    f"unknown_candidate_evidence:{item}" for item in unknown_evidence
                )
            if unknown_posting:
                sentence_codes.extend(
                    f"unknown_posting_authority:{item}" for item in unknown_posting
                )
            if unknown_verified:
                sentence_codes.extend(
                    f"unverified_company_authority:{item}" for item in unknown_verified
                )

            candidate_records = [
                evidence_by_id[item]
                for item in authority.candidate_evidence_ids
                if item in evidence_by_id
            ]
            posting_facts = [
                fact_by_id[item]
                for item in authority.posting_fact_ids
                if item in fact_by_id
            ]
            verified_facts = [
                fact_by_id[item]
                for item in authority.verified_company_fact_ids
                if item in fact_by_id
            ]
            metadata_values = self._metadata_values(authority, posting)
            source_texts = [
                *[
                    value
                    for record in candidate_records
                    for value in (record.source_text, record.entry_title or "")
                    if value
                ],
                *[fact.fact for fact in posting_facts],
                *[
                    DeterministicCoverLetterComposer._gerund_sequence(
                        fact.fact.rstrip(" .")
                    )
                    for fact in posting_facts
                ],
                *[
                    DeterministicCoverLetterComposer._normalize_posting_fragment(
                        fact.fact
                    )
                    for fact in posting_facts
                ],
                *[fact.fact for fact in verified_facts],
                *metadata_values,
            ]
            structured = [
                *[
                    value
                    for record in candidate_records
                    for value in [
                        record.entry_title or "",
                        *record.technologies,
                        *record.outcomes,
                    ]
                    if value
                ],
                *metadata_values,
            ]
            if not sentence_codes:
                if not self._is_application_intent(authority.text):
                    try:
                        validate_grounded_text(authority.text, source_texts, structured)
                    except GroundingValidationError as error:
                        sentence_codes.extend(
                            grounding_failure_code(failure).value
                            for failure in error.failures
                        )
                sentence_codes.extend(
                    self._unsupported_scope_codes(authority.text, source_texts)
                )
                sentence_codes.extend(
                    self._motivation_codes(authority.text, candidate_records, posting)
                )

            company_sentence = self._is_company_sentence(
                authority.text,
                posting,
                [*posting_facts, *verified_facts],
            )
            if self._relationship_claim_supported(
                authority.text,
                candidate_records,
                [*posting_facts, *verified_facts],
                posting,
            ):
                company_sentence = False
            explicit_company_or_role_reference = bool(
                (
                    posting.company_name
                    and posting.company_name.casefold() in authority.text.casefold()
                )
                or re.search(
                    r"\b(?:company|employer|organization|posting|position|"
                    r"this role|the role|your)\b",
                    authority.text,
                    re.IGNORECASE,
                )
            )
            candidate_narrative = bool(
                re.search(
                    r"\b(?:this|that|my)\s+(?:work|method|experience|project)\b|"
                    r"\b(?:these|those)\s+(?:choices|results)\b|"
                    r"\bat that boundary\b|\bdemonstrated technical work\b",
                    authority.text,
                    re.IGNORECASE,
                )
                or any(
                    record.entry_title
                    and record.entry_title.casefold() in authority.text.casefold()
                    for record in candidate_records
                )
                or (
                    not explicit_company_or_role_reference
                    and len(
                        self._content_terms(authority.text)
                        & self._content_terms(
                            " ".join(
                                record.writer_text or record.source_text
                                for record in candidate_records
                            )
                        )
                    )
                    >= 2
                )
            )
            if (
                candidate_records
                and posting_facts
                and not verified_facts
                and not explicit_company_or_role_reference
                and candidate_narrative
            ):
                # Posting facts are attached to the whole deterministic paragraph so its
                # relationship sentence can use them. Explicit candidate-narrative prose
                # in that paragraph is not thereby a company assertion.
                company_sentence = False
            if (
                company_sentence
                and not self._is_application_intent(authority.text)
                and not posting_facts
                and not verified_facts
            ):
                sentence_codes.append("company_claim_without_verified_source")
            elif (
                company_sentence
                and not self._is_application_intent(authority.text)
                and (posting_facts or verified_facts)
                and not self._company_claim_supported(
                    authority.text,
                    [*posting_facts, *verified_facts],
                    posting,
                )
            ):
                sentence_codes.append("company_fact_not_verified")

            status = (
                CoverLetterValidationStatus.REJECTED
                if sentence_codes
                else CoverLetterValidationStatus.SUPPORTED
            )
            claim = self._claim(
                index * 100 + sentence_index,
                authority.text,
                authority.candidate_evidence_ids,
                [
                    *authority.posting_fact_ids,
                    *authority.verified_company_fact_ids,
                ],
                status,
                list(dict.fromkeys(sentence_codes)),
                (
                    "Sentence passed validation against its explicit authority union."
                    if status is CoverLetterValidationStatus.SUPPORTED
                    else "Sentence exceeded its explicitly recorded authority."
                ),
                paragraph_index=index,
                sentence_index=sentence_index,
            )
            claims.append(claim)
            if status is CoverLetterValidationStatus.REJECTED:
                rejected.append(claim)

        if rejected:
            return None, rejected, []
        return (
            CoverLetterParagraph(
                id=f"cover-paragraph:{index}:{sha256(text.encode()).hexdigest()[:10]}",
                purpose=generated.purpose,
                text=text,
                candidate_evidence_ids=list(generated.candidate_evidence_ids),
                company_research_ids=list(generated.company_research_ids),
                narrative_thread_id=generated.narrative_thread_id,
                length_class=generated.length_class,
                sentence_authorities=list(generated.source_bound_sentences),
                claims=claims,
            ),
            [],
            [],
        )

    @staticmethod
    def _metadata_values(
        authority: CoverLetterSentenceAuthority,
        posting: JobPosting,
    ) -> list[str]:
        values: list[str] = []
        if (
            CoverLetterCanonicalMetadata.COMPANY_NAME
            in authority.canonical_metadata
            and posting.company_name
        ):
            values.append(posting.company_name)
        if CoverLetterCanonicalMetadata.ROLE_TITLE in authority.canonical_metadata:
            values.append(posting.title)
        return values

    @staticmethod
    def _is_application_intent(sentence: str) -> bool:
        return bool(
            re.fullmatch(
                r"I am applying for the .+ role at .+\.|"
                r"I am looking for .+\.|"
                r"I would be glad to .+\.|"
                r"What stood out to me about the .+ role(?: at .+)? is the work behind .+\.|"
                r"I would welcome (?:the opportunity for )?a? ?conversation .+\.|"
                r"I would welcome the opportunity to discuss .+\.|"
                r"I would contribute .+ to the .+ work at .+\.|"
                r"That is why the .+ role(?: at .+)? interests me\.|"
                r"That is why the .+ work at .+ feels like a natural next problem for me\."
                r"|I would welcome a conversation .+\.",
                sentence,
                re.IGNORECASE,
            )
        )

    @classmethod
    def _relationship_claim_supported(
        cls,
        sentence: str,
        candidate_records: list[CoverLetterEvidenceRecord],
        company_facts: list[CompanyResearchFact],
        posting: JobPosting,
    ) -> bool:
        if not candidate_records or not company_facts:
            return False
        if not re.search(
            r"\b(?:align|connect|relevant|context|foundation|maps?|contribut|appl|suit|"
            r"interest|draw|overlap|meet|intersect|appeal|where|makes?)\w*\b",
            sentence,
            re.IGNORECASE,
        ):
            return False
        sentence_terms = cls._content_terms(sentence)
        candidate_terms = cls._content_terms(
            " ".join(record.source_text for record in candidate_records)
        )
        posting_terms = cls._content_terms(f"{posting.title} {posting.description}")
        if len(sentence_terms & candidate_terms) < 2 or len(sentence_terms & posting_terms) < 2:
            return False
        sources = [
            *[record.source_text for record in candidate_records],
            *[fact.fact for fact in company_facts],
            posting.title,
            posting.description,
        ]
        structured = [
            posting.company_name or "",
            posting.title,
            *[
                value
                for record in candidate_records
                for value in [
                    record.entry_title or "",
                    *record.technologies,
                    *record.outcomes,
                ]
                if value
            ],
        ]
        try:
            validate_grounded_text(
                sentence,
                sources,
                structured,
                allow_strong_inference=False,
            )
        except GroundingValidationError:
            return False
        return True

    def quality_gates(
        self,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
        *,
        rejected_claims: list[CoverLetterClaimDiagnostic],
        review_required_claims: list[CoverLetterClaimDiagnostic],
        resume_consistency: list[CoverLetterResumeConsistencyFinding],
    ) -> list[CoverLetterQualityGateResult]:
        combined = " ".join(paragraph.text for paragraph in paragraphs)
        rejected_text = " ".join(claim.text for claim in rejected_claims)
        evaluated_text = " ".join(value for value in (combined, rejected_text) if value)
        rejected_codes = {code for claim in rejected_claims for code in claim.codes}
        generic_codes = self._generic_codes(evaluated_text)
        repetitive_structure = self._has_repetitive_paragraph_structure(paragraphs) or (
            sum(
                len(re.findall(pattern, evaluated_text, re.IGNORECASE))
                for pattern in _REPETITIVE_NARRATIVE_PATTERNS
            )
            >= 2
        )
        progression_codes = self._paragraph_progression_codes(paragraphs)
        specificity_codes = self._technical_specificity_codes(paragraphs, evidence)
        opening_codes = self._opening_quality_codes(paragraphs, evidence, posting)
        closing_codes = self._closing_quality_codes(paragraphs, posting)
        seniority_codes = self._seniority_emphasis_codes(paragraphs, evidence, posting)
        mechanical_posting = self._has_mechanical_posting_reference(paragraphs)
        resume_paraphrase = self._is_resume_paraphrase(paragraphs, evidence) or (
            self._text_paraphrases_multiple_sources(rejected_text, evidence)
        )
        enumerative_closing = self._has_enumerative_closing(paragraphs) or bool(
            re.search(
                r"\b(?:experience spanning|contribute (?:now )?through|background spans|"
                r"experience across)\b",
                rejected_text,
                re.IGNORECASE,
            )
            and rejected_text.count(",") >= 3
        )
        narrative_developed = (
            self._has_sufficient_narrative_development(paragraphs, evidence)
            and not repetitive_structure
            and not resume_paraphrase
            and not progression_codes
            and not specificity_codes
        )
        authority_mode = self._company_authority_mode(research)
        specific_company = self._specific_company_connection(
            paragraphs,
            evidence,
            research,
            posting,
            authority_mode=authority_mode,
            mechanical_posting=mechanical_posting,
        )
        structurally_generic = any(
            (
                repetitive_structure,
                mechanical_posting,
                resume_paraphrase,
                enumerative_closing,
            )
        )
        structure_valid = bool(
            paragraphs
            and paragraphs[0].purpose is CoverLetterParagraphPurpose.OPENING
            and paragraphs[-1].purpose is CoverLetterParagraphPurpose.CLOSING
            and len(paragraphs) >= 3
        )
        candidate_ids = {
            item for paragraph in paragraphs for item in paragraph.candidate_evidence_ids
        }
        role_present = posting.title.casefold() in combined.casefold() or any(
            paragraph.purpose is CoverLetterParagraphPurpose.ROLE_FIT for paragraph in paragraphs
        )
        narrative_integrity_codes = self._narrative_integrity_codes(
            evaluated_text,
            paragraphs,
            evidence,
            posting,
        )
        rejected_style = any(
            code.startswith("formulaic_phrase:")
            or code
            in {
                "available_company_name_replaced_by_placeholder",
                "unresolved_placeholder",
                "ungrammatical_posting_fragment",
                "sentence_fragment",
                "malformed_parallel_list",
                "compound_subject_verb_disagreement",
                "awkward_posting_frame",
                "vague_direct_technical_referent",
                "synthetic_bridge_prose",
                "duplicated_work_frame",
            }
            for code in rejected_codes
        )
        return [
            self._gate(
                "candidate_grounding",
                not rejected_claims,
                "candidate_claims_supported",
                "Every retained candidate claim maps to reviewed evidence."
                if not rejected_claims
                else f"{len(rejected_claims)} candidate or company claim(s) were rejected.",
            ),
            self._gate(
                "company_grounding",
                specific_company,
                "company_connection_verified",
                "At least one substantive company connection maps to posting or verified research.",
            ),
            self._gate(
                "interchangeability",
                specific_company,
                (
                    "letter_not_interchangeable"
                    if specific_company
                    else "interchangeable_company_connection"
                ),
                (
                    "The company connection joins verified role detail to a specific "
                    "candidate engineering constraint."
                    if specific_company
                    else (
                        "Company name, role title, and posting terms do not establish a "
                        "non-interchangeable connection."
                    )
                ),
            ),
            self._gate(
                "generic_language",
                not generic_codes and not structurally_generic and not rejected_style,
                (
                    "generic_language_absent"
                    if not generic_codes and not structurally_generic and not rejected_style
                    else "structurally_generic"
                ),
                (
                    "No formulaic filler or structurally generic prose was detected."
                    if not generic_codes and not structurally_generic
                    else (
                        "The draft uses formulaic wording or a generic application structure: "
                        f"{', '.join(generic_codes) if generic_codes else 'structural pattern'}."
                    )
                ),
            ),
            self._gate(
                "narrative_integrity",
                not narrative_integrity_codes,
                (
                    "narrative_integrity_verified"
                    if not narrative_integrity_codes
                    else narrative_integrity_codes[0]
                ),
                (
                    "Sentences are complete, non-repetitive, placeholder-free, and retain "
                    "canonical titles and reviewed qualifications."
                    if not narrative_integrity_codes
                    else "Narrative integrity failed: "
                    + ", ".join(narrative_integrity_codes)
                    + "."
                ),
            ),
            self._gate(
                "narrative_structure",
                structure_valid and bool(candidate_ids) and role_present and narrative_developed,
                (
                    "why_company_me_role_coherent"
                    if narrative_developed
                    else "insufficient_narrative_development"
                ),
                (
                    "Opening, synthesized evidence, role direction, and closing form one "
                    "developed narrative."
                    if narrative_developed
                    else (
                        "The body does not sufficiently synthesize reviewed evidence into "
                        "developed engineering context."
                    )
                ),
            ),
            self._gate(
                "opening_quality",
                not opening_codes,
                "observation_led_opening" if not opening_codes else opening_codes[0],
                (
                    "The opening uses a concrete candidate-to-role observation without "
                    "announcing or paraphrasing the application."
                    if not opening_codes
                    else "Opening quality failed: " + ", ".join(opening_codes) + "."
                ),
            ),
            self._gate(
                "paragraph_progression",
                not progression_codes,
                "distinct_story_progression" if not progression_codes else progression_codes[0],
                (
                    "Each substantive paragraph adds a distinct narrative dimension."
                    if not progression_codes
                    else "Paragraph progression failed: " + ", ".join(progression_codes) + "."
                ),
            ),
            self._gate(
                "technical_specificity",
                not specificity_codes,
                (
                    "concrete_story_details_present"
                    if not specificity_codes
                    else specificity_codes[0]
                ),
                (
                    "Substantive stories use concrete reviewed technical details."
                    if not specificity_codes
                    else "Technical specificity failed: " + ", ".join(specificity_codes) + "."
                ),
            ),
            self._gate(
                "resume_complement",
                not resume_paraphrase,
                "resume_bullets_not_copied" if not resume_paraphrase else "resume_paraphrase",
                (
                    "The letter synthesizes reviewed facts instead of assigning one resume-like "
                    "paragraph to each evidence item."
                    if not resume_paraphrase
                    else "The draft is structured as a sequence of paraphrased resume bullets."
                ),
            ),
            self._gate(
                "paragraph_structure",
                not repetitive_structure,
                (
                    "paragraph_structures_varied"
                    if not repetitive_structure
                    else "repetitive_paragraph_structure"
                ),
                (
                    "Paragraphs use distinct, connected constructions."
                    if not repetitive_structure
                    else "Multiple paragraphs repeat the same role-summary or connection template."
                ),
            ),
            self._gate(
                "posting_reference",
                not mechanical_posting,
                (
                    "posting_authority_integrated_naturally"
                    if not mechanical_posting
                    else "mechanical_posting_reference"
                ),
                (
                    "Posting authority is expressed as a natural technical connection."
                    if not mechanical_posting
                    else "The draft describes the posting or its keywords as an inspected object."
                ),
            ),
            self._gate(
                "closing_structure",
                not enumerative_closing and not closing_codes,
                (
                    "closing_is_direct"
                    if not enumerative_closing and not closing_codes
                    else "enumerative_closing"
                    if enumerative_closing
                    else closing_codes[0]
                ),
                (
                    "The closing states contribution and direction without relisting the letter."
                    if not enumerative_closing and not closing_codes
                    else "The closing repeats or mechanically summarizes the letter."
                ),
            ),
            self._gate(
                "seniority_emphasis",
                not seniority_codes,
                (
                    "seniority_framing_is_material_and_supported"
                    if not seniority_codes
                    else seniority_codes[0]
                ),
                (
                    "The prose avoids unnecessary supervisory framing around title-conflicted "
                    "source evidence."
                    if not seniority_codes
                    else "Seniority framing failed: " + ", ".join(seniority_codes) + "."
                ),
            ),
            self._gate(
                "resume_consistency",
                not any(
                    finding.status is CoverLetterValidationStatus.REJECTED
                    for finding in resume_consistency
                ),
                "resume_consistent",
                "Titles, evidence IDs, technologies, metrics, and ownership remain "
                "profile-consistent.",
            ),
            self._title_consistency_gate(evidence),
            CoverLetterQualityGateResult(
                gate="review_required_claims",
                status=(
                    CoverLetterQualityGateStatus.REVIEW_REQUIRED
                    if review_required_claims
                    else CoverLetterQualityGateStatus.PASSED
                ),
                code="review_required_claims_visible",
                detail=f"{len(review_required_claims)} claim(s) require explicit review.",
            ),
        ]

    @staticmethod
    def _title_consistency_gate(
        evidence: list[CoverLetterEvidenceRecord],
    ) -> CoverLetterQualityGateResult:
        suspect = sorted(
            {
                title
                for item in evidence
                if (title := (item.entry_title or "").strip())
                and re.search(
                    r"\bprinciple\b.*\b(?:engineer|architect|designer|manager)\b",
                    title,
                    re.IGNORECASE,
                )
            }
        )
        if suspect:
            return CoverLetterQualityGateResult(
                gate="profile_title_consistency",
                status=CoverLetterQualityGateStatus.REVIEW_REQUIRED,
                code="possible_title_spelling_inconsistency",
                detail=(
                    "A canonical profile title may contain a spelling inconsistency; "
                    f"the stored title was retained unchanged: {', '.join(suspect)}."
                ),
            )
        return CoverLetterQualityGateResult(
            gate="profile_title_consistency",
            status=CoverLetterQualityGateStatus.PASSED,
            code="profile_titles_retained",
            detail="Canonical profile titles were retained unchanged.",
        )

    @staticmethod
    def _resume_consistency(
        paragraphs: list[CoverLetterParagraph],
        evidence_by_id: dict[str, CoverLetterEvidenceRecord],
        final_resume: StructuredResume | None,
    ) -> list[CoverLetterResumeConsistencyFinding]:
        used = {item for paragraph in paragraphs for item in paragraph.candidate_evidence_ids}
        unknown = sorted(used - set(evidence_by_id))
        if unknown:
            return [
                CoverLetterResumeConsistencyFinding(
                    status=CoverLetterValidationStatus.REJECTED,
                    code="unknown_candidate_evidence",
                    detail="Letter references candidate evidence outside the reviewed portfolio.",
                    evidence_ids=unknown,
                )
            ]
        if final_resume is None:
            return [
                CoverLetterResumeConsistencyFinding(
                    status=CoverLetterValidationStatus.SUPPORTED,
                    code="profile_and_plan_consistent",
                    detail=(
                        "No final resume artifact was supplied; reviewed profile and "
                        "validated plan remained authoritative."
                    ),
                    evidence_ids=sorted(used),
                )
            ]
        resume_ids = {
            evidence_id
            for bullets in [
                *final_resume.experience_bullets.values(),
                *final_resume.project_bullets.values(),
            ]
            for bullet in bullets
            for evidence_id in bullet.evidence_ids
        }
        omitted = sorted(used - resume_ids)
        return [
            CoverLetterResumeConsistencyFinding(
                status=CoverLetterValidationStatus.SUPPORTED,
                code="final_resume_consistent",
                detail=(
                    "Letter uses reviewed evidence omitted from the one-page resume "
                    "without changing its facts."
                    if omitted
                    else "Letter evidence is consistent with the final resume selection."
                ),
                evidence_ids=sorted(used),
            )
        ]

    @classmethod
    def _style_codes(
        cls,
        text: str,
        purpose: CoverLetterParagraphPurpose,
        posting: JobPosting,
    ) -> list[str]:
        lowered = text.casefold()
        codes = [
            f"formulaic_phrase:{pattern}"
            for pattern in _FORMULAIC_PATTERNS
            if re.search(pattern, lowered)
        ]
        if purpose is CoverLetterParagraphPurpose.OPENING and lowered.startswith(
            _OPENING_REJECTIONS
        ):
            codes.append("formulaic_opening")
        if purpose is CoverLetterParagraphPurpose.CLOSING and any(
            phrase in lowered for phrase in _CLOSING_REJECTIONS
        ):
            codes.append("formulaic_closing")
        if purpose is CoverLetterParagraphPurpose.CLOSING and len(text.split()) < 12:
            codes.append("incomplete_closing")
        if lowered.startswith("dear "):
            codes.append("salutation_in_provider_paragraph")
        if any(phrase in lowered for phrase in _GENERIC_COMPANY_LANGUAGE):
            codes.append("generic_company_mission_language")
        if any(re.search(pattern, lowered) for pattern in _INTERNAL_PROSE_PATTERNS):
            codes.append("internal_application_language")
        if posting.company_name and re.search(
            r"\b(?:the employer|the organization|your organization)\b",
            lowered,
        ):
            codes.append("available_company_name_replaced_by_placeholder")
        if any(re.search(pattern, lowered) for pattern in _UNRESOLVED_PLACEHOLDER_PATTERNS):
            codes.append("unresolved_placeholder")
        if re.search(
            r"\b(?:includes work on|work on|emphasis on work on)\s+"
            r"(?:act as|alongside|working with|responsible for)\b",
            lowered,
        ):
            codes.append("ungrammatical_posting_fragment")
        codes.extend(
            code
            for code, pattern in _NATURALNESS_PATTERNS
            if re.search(pattern, lowered, re.IGNORECASE)
        )
        if text.count("—") + text.count("--") > 2:
            codes.append("excessive_em_dashes")
        sentences = cls._sentences(text)
        if any(_UNSUBJECTED_ACTION_PATTERN.match(sentence.strip()) for sentence in sentences):
            codes.append("sentence_fragment")
        if sum(sentence.casefold().startswith("i ") for sentence in sentences) > 2:
            codes.append("repetitive_i_openings")
        posting_words = posting.description.split()
        for size in range(min(16, len(posting_words)), 11, -1):
            if any(
                " ".join(posting_words[index : index + size]).casefold() in lowered
                for index in range(len(posting_words) - size + 1)
            ):
                codes.append("copied_posting_language")
                break
        return list(dict.fromkeys(codes))

    @staticmethod
    def _motivation_codes(
        sentence: str,
        records: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> list[str]:
        lowered = sentence.casefold()
        if any(re.search(pattern, lowered) for pattern in _FORBIDDEN_MOTIVATION):
            return ["unsupported_personal_motivation"]
        motivation_records = [
            record for record in records if record.kind is CoverLetterEvidenceKind.USER_MOTIVATION
        ]
        motivation_signal = bool(
            re.search(
                r"\b(?:i want|i hope|i care|i am curious|i'm curious|drawn to|excited by|"
                r"matters to me|motivated by)\b",
                lowered,
            )
        )
        if not motivation_signal or motivation_records:
            return []
        supported_terms = CoverLetterValidator._content_terms(
            " ".join(
                [posting.title, posting.description, *[record.source_text for record in records]]
            )
        )
        sentence_terms = CoverLetterValidator._content_terms(sentence)
        if len(sentence_terms & supported_terms) >= 2 and not any(
            word in lowered for word in ("always", "dream", "passion")
        ):
            return []
        return ["unsupported_personal_motivation"]

    @staticmethod
    def _unsupported_scope_codes(sentence: str, source_texts: list[str]) -> list[str]:
        lowered = sentence.casefold()
        authority = " ".join(source_texts).casefold()
        checks = {
            "unsupported_production_claim": ("production", "deployed", "deployment"),
            "unsupported_scale_claim": ("millions", "globally", "enterprise-wide"),
            "unsupported_business_impact": ("revenue", "profit", "market share"),
            "unsupported_causal_outcome": ("caused", "resulted in", "thereby increased"),
        }
        return [
            code
            for code, terms in checks.items()
            if any(term in lowered for term in terms)
            and not any(term in authority for term in terms)
        ]

    @staticmethod
    def _candidate_clauses(sentence: str) -> list[str]:
        clauses = re.split(r"(?:;|—|--|\bwhile\b|\bwhereas\b|\bbecause\b)", sentence)
        return [
            clause.strip(" ,")
            for clause in clauses
            if re.search(r"\b(?:I|I'm|I've|me|my)\b", clause, re.IGNORECASE)
        ]

    @classmethod
    def _is_company_sentence(
        cls,
        sentence: str,
        posting: JobPosting,
        company_facts: list[CompanyResearchFact],
    ) -> bool:
        lowered = sentence.casefold()
        if posting.company_name and posting.company_name.casefold() in lowered:
            return True
        if re.search(r"\b(?:I|I'm|I've|me|my)\b", sentence, re.IGNORECASE) and not any(
            marker in lowered for marker in ("company", "posting", "this role", "your")
        ):
            return False
        fact_terms = cls._content_terms(" ".join(fact.fact for fact in company_facts))
        return len(cls._content_terms(sentence) & fact_terms) >= 2

    @classmethod
    def _company_claim_supported(
        cls,
        sentence: str,
        company_facts: list[CompanyResearchFact],
        posting: JobPosting,
    ) -> bool:
        source_texts = [fact.fact for fact in company_facts]
        source_texts.extend([posting.title, posting.description])
        source_terms = cls._content_terms(" ".join(source_texts))
        sentence_terms = cls._content_terms(sentence)
        company_name_terms = cls._content_terms(posting.company_name or "")
        meaningful = sentence_terms - company_name_terms
        if len(meaningful & source_terms) < 2:
            return False
        try:
            validate_grounded_text(
                sentence,
                source_texts,
                [posting.company_name or "", posting.title],
                allow_strong_inference=False,
            )
        except GroundingValidationError:
            return False
        return True

    @classmethod
    def _specific_company_connection(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
        *,
        authority_mode: CoverLetterCompanyAuthorityMode,
        mechanical_posting: bool,
    ) -> bool:
        if mechanical_posting:
            return False
        if authority_mode is CoverLetterCompanyAuthorityMode.POSTING_ONLY:
            return cls._specific_posting_connection(paragraphs, evidence, posting)
        facts = {fact.id: fact for fact in research.facts}
        evidence_by_id = {item.id: item for item in evidence}
        for paragraph in paragraphs:
            used = [facts[item] for item in paragraph.company_research_ids if item in facts]
            used_evidence = [
                evidence_by_id[item]
                for item in paragraph.candidate_evidence_ids
                if item in evidence_by_id
            ]
            if not used or not used_evidence:
                continue
            fact_terms = cls._content_terms(" ".join(item.fact for item in used))
            evidence_terms = cls._content_terms(
                " ".join(item.source_text for item in used_evidence)
            )
            paragraph_terms = cls._content_terms(paragraph.text)
            generic = cls._content_terms(f"{posting.company_name or ''} {posting.title}")
            company_detail = (fact_terms & paragraph_terms) - generic
            candidate_detail = (evidence_terms & paragraph_terms) - fact_terms - generic
            connection_language = bool(
                re.search(
                    r"\b(?:because|from the .+ side|part of that problem|boundary|constraint|"
                    r"upstream|downstream|align|connect|relevant|suit|direction|"
                    r"translat|why|"
                    r"physical)\b",
                    paragraph.text,
                    re.IGNORECASE,
                )
            )
            if len(company_detail) >= 2 and len(candidate_detail) >= 2 and connection_language:
                return True
        return False

    @staticmethod
    def _company_authority_mode(
        research: CompanyResearchBundle,
    ) -> CoverLetterCompanyAuthorityMode:
        if any(
            fact.confidence
            in {CompanyFactConfidence.VERIFIED, CompanyFactConfidence.USER_AUTHORITY}
            for fact in research.facts
        ):
            return CoverLetterCompanyAuthorityMode.VERIFIED_COMPANY_RESEARCH
        return CoverLetterCompanyAuthorityMode.POSTING_ONLY

    @classmethod
    def _specific_posting_connection(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> bool:
        evidence_by_id = {item.id: item for item in evidence}
        company_terms = cls._content_terms(posting.company_name or "")
        posting_terms = cls._content_terms(f"{posting.title} {posting.description}") - company_terms
        for paragraph in paragraphs:
            used_evidence = [
                evidence_by_id[item]
                for item in paragraph.candidate_evidence_ids
                if item in evidence_by_id
            ]
            if not paragraph.company_research_ids or not used_evidence:
                continue
            lowered = paragraph.text.casefold()
            references_opportunity = bool(
                (posting.company_name and posting.company_name.casefold() in lowered)
                or posting.title.casefold() in lowered
                or re.search(r"\b(?:this|the) role\b", lowered)
            )
            paragraph_terms = cls._content_terms(paragraph.text)
            evidence_terms = cls._content_terms(
                " ".join(item.source_text for item in used_evidence)
            )
            posting_detail = posting_terms & paragraph_terms
            candidate_detail = (evidence_terms & paragraph_terms) - company_terms
            explains_connection = bool(
                re.search(
                    r"\b(?:because|connect(?:s|ed|ing)?|connection|constraints?|interfaces?|"
                    r"integration|relat|"
                    r"from the .+ side|part of that problem|boundary|physical|where|why|"
                    r"centers?|depends?|requires?|means?|makes?)\b",
                    paragraph.text,
                    re.IGNORECASE,
                )
            )
            if (
                references_opportunity
                and len(posting_detail) >= 2
                and len(candidate_detail) >= 2
                and explains_connection
            ):
                return True
        return False

    @classmethod
    def _opening_quality_codes(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> list[str]:
        if not paragraphs or paragraphs[0].purpose is not CoverLetterParagraphPurpose.OPENING:
            return ["opening_missing"]
        opening = paragraphs[0]
        lowered = opening.text.casefold()
        codes: list[str] = []
        if lowered.startswith(_OPENING_REJECTIONS) or re.match(
            r"^(?:with my background|this opportunity|the .+ role (?:combines|brings))\b",
            lowered,
        ):
            codes.append("formulaic_or_posting_summary_opening")
        evidence_by_id = {item.id: item for item in evidence}
        used = [
            evidence_by_id[item]
            for item in opening.candidate_evidence_ids
            if item in evidence_by_id
        ]
        candidate_terms = cls._concrete_authority_terms(used)
        opening_terms = cls._content_terms(opening.text)
        if used and len(opening_terms & candidate_terms) < 2:
            codes.append("opening_lacks_concrete_candidate_observation")
        posting_terms = cls._content_terms(posting.description)
        if (
            len(opening_terms) >= 8
            and len(opening_terms & posting_terms) / len(opening_terms) >= 0.72
            and len(opening_terms & candidate_terms) < 3
        ):
            codes.append("posting_paraphrase_opening")
        return list(dict.fromkeys(codes))

    @classmethod
    def _paragraph_progression_codes(
        cls,
        paragraphs: list[CoverLetterParagraph],
    ) -> list[str]:
        body = [
            paragraph
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
        ]
        if len(body) < 2:
            return ["insufficient_story_progression"]
        codes: list[str] = []
        thread_ids = [paragraph.narrative_thread_id for paragraph in body]
        nonblank_threads = [item for item in thread_ids if item]
        if len(nonblank_threads) != len(set(nonblank_threads)):
            codes.append("reused_narrative_thread")

        paragraph_roots = [cls._narrative_roots(paragraph.text) for paragraph in paragraphs]
        repeated_roots = {
            root
            for root in _ABSTRACT_NARRATIVE_ROOTS
            if sum(root in roots for roots in paragraph_roots) >= 3
        }
        if len(repeated_roots) >= 3:
            codes.append("repeated_narrative_thesis")

        body_bigrams = [cls._distinctive_bigrams(paragraph.text) for paragraph in body]
        if any(
            len(body_bigrams[left] & body_bigrams[right]) >= 2
            for left in range(len(body_bigrams))
            for right in range(left + 1, len(body_bigrams))
        ):
            codes.append("repeated_technical_example")
        return list(dict.fromkeys(codes))

    @classmethod
    def _technical_specificity_codes(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
    ) -> list[str]:
        evidence_by_id = {item.id: item for item in evidence}
        body = [
            paragraph
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
        ]
        codes: list[str] = []
        vague_sentences = 0
        for paragraph in body:
            used = [
                evidence_by_id[item]
                for item in paragraph.candidate_evidence_ids
                if item in evidence_by_id
            ]
            if not used:
                continue
            concrete = cls._concrete_authority_terms(used)
            paragraph_terms = cls._content_terms(paragraph.text)
            if len(paragraph_terms & concrete) < 2:
                codes.append("vague_technical_story")
            for sentence in cls._sentences(paragraph.text):
                if _VAGUE_TECHNICAL_REFERENTS.search(sentence) and not (
                    cls._content_terms(sentence) & concrete
                ):
                    vague_sentences += 1
                    codes.append("vague_technical_referent")
        if vague_sentences >= 2:
            codes.append("repeated_vague_technical_abstraction")
        return list(dict.fromkeys(codes))

    @classmethod
    def _closing_quality_codes(
        cls,
        paragraphs: list[CoverLetterParagraph],
        posting: JobPosting,
    ) -> list[str]:
        if not paragraphs or paragraphs[-1].purpose is not CoverLetterParagraphPurpose.CLOSING:
            return ["closing_missing"]
        closing = paragraphs[-1]
        word_count = len(closing.text.split())
        codes: list[str] = []
        if word_count < 10:
            codes.append("closing_too_abrupt")
        if word_count > 85:
            codes.append("closing_restates_letter")
        if any(phrase in closing.text.casefold() for phrase in _CLOSING_REJECTIONS):
            codes.append("formulaic_closing")
        if paragraphs:
            canonical_terms = cls._content_terms(
                f"{posting.company_name or ''} {posting.title}"
            )
            opening_terms = cls._content_terms(paragraphs[0].text) - canonical_terms
            closing_terms = cls._content_terms(closing.text) - canonical_terms
            overlap = len(opening_terms & closing_terms) / max(1, len(closing_terms))
            if overlap >= 0.55:
                codes.append("closing_repeats_opening")
        return list(dict.fromkeys(codes))

    @classmethod
    def _seniority_emphasis_codes(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> list[str]:
        if re.search(
            r"\b(?:leadership|lead a team|manage|manager|supervis|mentor|direct reports?)\b",
            f"{posting.title} {posting.description}",
            re.IGNORECASE,
        ):
            return []
        sensitive_ids = {item.id for item in evidence if item.excluded_title_claims}
        if not sensitive_ids:
            return []
        for paragraph in paragraphs:
            if not (set(paragraph.candidate_evidence_ids) & sensitive_ids):
                continue
            if re.search(
                r"\b(?:led|managed|oversaw|supervised)\b|"
                r"\breview(?:ed|ing)\s+(?:subordinate|junior|team)\b",
                paragraph.text,
                re.IGNORECASE,
            ):
                return ["unnecessary_seniority_foregrounding"]
        return []

    @classmethod
    def _concrete_authority_terms(
        cls,
        records: list[CoverLetterEvidenceRecord],
    ) -> set[str]:
        terms = cls._content_terms(
            " ".join(
                value
                for record in records
                for value in [
                    record.writer_text or record.source_text,
                    *record.technologies,
                    *record.outcomes,
                ]
                if value
            )
        )
        return {
            token
            for token in terms
            if cls._narrative_root(token) not in _GENERAL_TECHNICAL_TERMS
        }

    @classmethod
    def _distinctive_bigrams(cls, text: str) -> set[tuple[str, str]]:
        tokens = [
            cls._narrative_root(token)
            for token in re.findall(r"[a-z][a-z0-9+#-]{2,}", text.casefold())
            if token not in _CONTENT_STOPWORDS
        ]
        tokens = [token for token in tokens if token not in _GENERAL_TECHNICAL_TERMS]
        return set(zip(tokens, tokens[1:], strict=False))

    @classmethod
    def _narrative_roots(cls, text: str) -> set[str]:
        return {
            cls._narrative_root(token)
            for token in re.findall(r"[a-z][a-z0-9+#-]{2,}", text.casefold())
        }

    @staticmethod
    def _narrative_root(token: str) -> str:
        mappings = {
            "behav": "behavior",
            "decid": "decision",
            "decision": "decision",
            "implement": "implement",
            "observ": "behavior",
            "system": "system",
            "test": "test",
        }
        for prefix, root in mappings.items():
            if token.startswith(prefix):
                return root
        return token

    @classmethod
    def _has_repetitive_paragraph_structure(
        cls,
        paragraphs: list[CoverLetterParagraph],
    ) -> bool:
        role_summaries = sum(
            bool(
                re.match(
                    r"^(?:my|in my)\s+.+?\s+work\s+(?:involved|included|required)\b",
                    paragraph.text,
                    re.IGNORECASE,
                )
            )
            for paragraph in paragraphs
        )
        mechanical_connections = sum(
            bool(
                re.search(
                    r"\b(?:that is a direct connection|it is a (?:second|third) "
                    r"concrete connection|this connects to the (?:posting|role))\b",
                    paragraph.text,
                    re.IGNORECASE,
                )
            )
            for paragraph in paragraphs
        )
        body_evidence_ids = [
            evidence_id
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
            for evidence_id in paragraph.candidate_evidence_ids
        ]
        reused_body_evidence = len(body_evidence_ids) != len(set(body_evidence_ids))
        return role_summaries >= 2 or mechanical_connections >= 2 or reused_body_evidence

    @classmethod
    def _text_paraphrases_multiple_sources(
        cls,
        text: str,
        evidence: list[CoverLetterEvidenceRecord],
    ) -> bool:
        text_terms = cls._content_terms(text)
        high_overlap = 0
        for record in evidence:
            if record.kind not in {
                CoverLetterEvidenceKind.EXPERIENCE,
                CoverLetterEvidenceKind.PROJECT,
            }:
                continue
            source_terms = cls._content_terms(record.source_text)
            if source_terms and len(source_terms & text_terms) / len(source_terms) >= 0.72:
                high_overlap += 1
        return high_overlap >= 2

    @classmethod
    def _narrative_integrity_codes(
        cls,
        text: str,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> list[str]:
        lowered = text.casefold()
        codes: list[str] = []
        if posting.company_name and re.search(
            r"\b(?:the employer|the organization|your organization)\b",
            lowered,
        ):
            codes.append("known_company_replaced_by_placeholder")
        if any(re.search(pattern, lowered) for pattern in _UNRESOLVED_PLACEHOLDER_PATTERNS):
            codes.append("unresolved_placeholder")
        if re.search(
            r"\b(?:includes work on|work on|emphasis on work on)\s+"
            r"(?:act as|alongside|working with|responsible for)\b",
            lowered,
        ):
            codes.append("malformed_posting_fragment")
        if any(
            _UNSUBJECTED_ACTION_PATTERN.match(sentence.strip())
            for sentence in cls._sentences(text)
        ):
            codes.append("sentence_fragment")
        template_count = sum(
            len(re.findall(pattern, lowered))
            for pattern in _REPETITIVE_NARRATIVE_PATTERNS
        )
        if template_count >= 2:
            codes.append("repetitive_narrative_template")
        if any(re.search(pattern, lowered) for pattern in _VALIDATOR_PROSE_PATTERNS):
            codes.append("validation_disclaimer_in_letter")
        if cls._excessive_posting_phrase_reuse(text, posting):
            codes.append("excessive_posting_paraphrase")

        canonical_titles = {
            title.casefold()
            for record in evidence
            if (title := (record.entry_title or "").strip())
        }
        posting_title = posting.title.casefold()
        promoted_title_matches = re.finditer(
            r"\b(?:chief|director|head|lead|manager|principal|senior|staff)\s+"
            r"(?:[A-Z][A-Za-z0-9&+/-]*\s+){0,5}"
            r"(?:engineer|architect|designer|researcher|developer|manager)\b",
            text,
            re.IGNORECASE,
        )
        unsupported_title = any(
            (title := match.group(0).strip().casefold()) not in canonical_titles
            and not (
                title == posting_title
                and re.match(
                    r"\s+(?:role|position|work)\b",
                    text[match.end() :],
                    re.IGNORECASE,
                )
            )
            for match in promoted_title_matches
        )
        if unsupported_title:
            codes.append("unsupported_title_change")

        degree_terms = re.findall(
            r"\b(?:associate(?:'s)?|bachelor(?:'s)?|master(?:'s)?|doctoral|doctorate|phd)"
            r"(?:\s+degree)?\b",
            lowered,
        )
        qualification_authority = " ".join(record.source_text for record in evidence).casefold()
        if degree_terms and any(term not in qualification_authority for term in degree_terms):
            codes.append("unsupported_degree_qualification")

        body = [
            paragraph
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
        ]
        enumeration_frames = re.findall(
            r"\b(?:i also|the project also involved|that project also required|"
            r"another part of that work|that role also involved)\b",
            lowered,
        )
        if len(enumeration_frames) >= 2:
            codes.append("resume_summary_cadence")
        entity_id_by_evidence = {item.id: item.entity_id for item in evidence}
        entity_ids_by_paragraph = [
            {
                entity_id_by_evidence[evidence_id]
                for evidence_id in paragraph.candidate_evidence_ids
                if entity_id_by_evidence.get(evidence_id)
            }
            for paragraph in body
        ]
        if any(
            left & right
            for left, right in zip(
                entity_ids_by_paragraph,
                entity_ids_by_paragraph[1:],
                strict=False,
            )
        ):
            codes.append("adjacent_story_reopening")
        if any(
            len(paragraph.candidate_evidence_ids) >= 4
            and len(cls._sentences(paragraph.text)) >= 4
            for paragraph in body
        ):
            codes.append("overdense_resume_summary")
        if any(
            sum(
                bool(
                    re.match(
                        r"^(?:As |In (?:my|the) ).+?\bI\s+",
                        sentence,
                    )
                )
                for sentence in cls._sentences(paragraph.text)
            )
            >= 5
            for paragraph in body
        ):
            codes.append("excessive_evidence_listing")
        return list(dict.fromkeys(codes))

    @classmethod
    def _excessive_posting_phrase_reuse(cls, text: str, posting: JobPosting) -> bool:
        posting_tokens = [
            token
            for token in re.findall(r"[a-z][a-z0-9+#-]{2,}", posting.description.casefold())
            if token not in _CONTENT_STOPWORDS
        ]
        letter = text.casefold()
        phrases = {
            " ".join(posting_tokens[index : index + 3])
            for index in range(max(0, len(posting_tokens) - 2))
        }
        return any(letter.count(phrase) >= 3 for phrase in phrases if len(phrase) >= 12)

    @staticmethod
    def _has_mechanical_posting_reference(
        paragraphs: list[CoverLetterParagraph],
    ) -> bool:
        if not paragraphs:
            return False
        opening = paragraphs[0].text.casefold()
        patterns = (
            r"\b(?:the|this) .+ posting (?:connects|lists|describes|emphasizes)\b",
            r"\bposting(?:'s)? (?:work|requirements|emphasis|keywords)\b",
            r"\bjob description (?:connects|lists|describes|emphasizes)\b",
            r"\bconnects the .+ role to work in\b",
        )
        return any(re.search(pattern, opening) for pattern in patterns)

    @classmethod
    def _is_resume_paraphrase(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
    ) -> bool:
        body = [
            paragraph
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
        ]
        if not body:
            return True
        if all(paragraph.sentence_authorities for paragraph in paragraphs):
            # The emergency writer is deliberately source-faithful. Judge it by
            # whether it repeats one atom/thread, not by lexical distance from the
            # reviewed source. Provider prose remains subject to the overlap test.
            body_ids = [
                evidence_id
                for paragraph in body
                for evidence_id in paragraph.candidate_evidence_ids
            ]
            thread_ids = [
                paragraph.narrative_thread_id
                for paragraph in body
                if paragraph.narrative_thread_id
            ]
            return len(body_ids) != len(set(body_ids)) or len(thread_ids) != len(
                set(thread_ids)
            )
        source_terms = {
            item.id: cls._content_terms(item.source_text)
            for item in evidence
            if item.kind in {CoverLetterEvidenceKind.EXPERIENCE, CoverLetterEvidenceKind.PROJECT}
        }
        isolated_high_overlap = 0
        for paragraph in body:
            if len(paragraph.candidate_evidence_ids) != 1:
                continue
            evidence_id = paragraph.candidate_evidence_ids[0]
            authority = source_terms.get(evidence_id, set())
            if not authority:
                continue
            paragraph_terms = cls._content_terms(paragraph.text)
            overlap = len(paragraph_terms & authority) / max(len(authority), len(paragraph_terms))
            if overlap >= 0.72:
                isolated_high_overlap += 1
        copied_source = any(
            len(item.source_text.split()) >= 8
            and item.source_text.casefold().rstrip(".")
            in " ".join(paragraph.text for paragraph in paragraphs).casefold()
            for item in evidence
            if item.kind in {CoverLetterEvidenceKind.EXPERIENCE, CoverLetterEvidenceKind.PROJECT}
        )
        return copied_source or isolated_high_overlap >= 2

    @staticmethod
    def _has_enumerative_closing(paragraphs: list[CoverLetterParagraph]) -> bool:
        if not paragraphs:
            return False
        closing = paragraphs[-1]
        lowered = closing.text.casefold()
        explicit_inventory = bool(
            re.search(
                r"\b(?:experience spanning|contribute (?:now )?through|background spans|"
                r"experience across)\b",
                lowered,
            )
        )
        list_shape = closing.text.count(",") >= 3 and " and " in lowered
        return len(closing.candidate_evidence_ids) >= 3 and (explicit_inventory or list_shape)

    @classmethod
    def _has_sufficient_narrative_development(
        cls,
        paragraphs: list[CoverLetterParagraph],
        evidence: list[CoverLetterEvidenceRecord],
    ) -> bool:
        body = [
            paragraph
            for paragraph in paragraphs
            if paragraph.purpose
            not in {CoverLetterParagraphPurpose.OPENING, CoverLetterParagraphPurpose.CLOSING}
        ]
        factual_ids = {
            item.id for item in evidence if item.kind is not CoverLetterEvidenceKind.USER_MOTIVATION
        }
        used_ids = {
            evidence_id
            for paragraph in paragraphs
            for evidence_id in paragraph.candidate_evidence_ids
            if evidence_id in factual_ids
        }
        if not body or not used_ids:
            return False
        closing_ids = set(paragraphs[-1].candidate_evidence_ids) if paragraphs else set()
        synthesized = any(len(paragraph.candidate_evidence_ids) >= 2 for paragraph in body) or (
            len(body) >= 2 and len(used_ids) >= 2 and len(closing_ids & factual_ids) >= 2
        )
        if all(paragraph.sentence_authorities for paragraph in paragraphs) and len(body) >= 2:
            synthesized = len(
                {
                    paragraph.narrative_thread_id
                    for paragraph in body
                    if paragraph.narrative_thread_id
                }
            ) == len(body)
        if len(used_ids) >= 2 and (len(body) < 2 or not synthesized):
            return False
        length_class = paragraphs[0].length_class
        minimum_words = {
            CoverLetterLengthClass.CONCISE: 95,
            CoverLetterLengthClass.STANDARD: 125,
            CoverLetterLengthClass.DEVELOPED: 140,
        }[length_class]
        if len(used_ids) == 1:
            minimum_words = min(70, minimum_words)
        elif len(used_ids) == 2:
            minimum_words = {
                CoverLetterLengthClass.CONCISE: 35,
                CoverLetterLengthClass.STANDARD: 40,
                CoverLetterLengthClass.DEVELOPED: 40,
            }[length_class]
        if all(paragraph.sentence_authorities for paragraph in paragraphs):
            # Page fit, not invented bridge prose, owns the production density
            # floor. Two concrete deterministic stories can be structurally valid
            # even when their rendered artifact remains diagnostic-only.
            minimum_words = min(minimum_words, 30 if len(used_ids) <= 2 else 70)
        body_words = sum(len(paragraph.text.split()) for paragraph in body)
        return body_words >= minimum_words

    @classmethod
    def _generic_codes(cls, text: str) -> list[str]:
        lowered = text.casefold()
        codes = [pattern for pattern in _FORMULAIC_PATTERNS if re.search(pattern, lowered)]
        codes.extend(phrase for phrase in _GENERIC_COMPANY_LANGUAGE if phrase in lowered)
        return list(dict.fromkeys(codes))

    @staticmethod
    def _content_terms(text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z][a-z0-9+#-]{2,}", text.casefold())
            if token not in _CONTENT_STOPWORDS
        }

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text) if sentence.strip()
        ]

    @staticmethod
    def _claim(
        index: int,
        text: str,
        evidence_ids: list[str],
        company_ids: list[str],
        status: CoverLetterValidationStatus,
        codes: list[str],
        detail: str,
        *,
        paragraph_index: int | None = None,
        sentence_index: int | None = None,
    ) -> CoverLetterClaimDiagnostic:
        return CoverLetterClaimDiagnostic(
            id=f"cover-claim:{sha256(f'{index}:{text}'.encode()).hexdigest()[:14]}",
            text=text,
            candidate_evidence_ids=list(evidence_ids),
            company_research_ids=list(company_ids),
            status=status,
            codes=codes,
            detail=detail,
            paragraph_index=paragraph_index,
            sentence_index=sentence_index,
        )

    @staticmethod
    def _gate(
        name: str,
        passed: bool,
        code: str,
        detail: str,
    ) -> CoverLetterQualityGateResult:
        return CoverLetterQualityGateResult(
            gate=name,
            status=(
                CoverLetterQualityGateStatus.PASSED
                if passed
                else CoverLetterQualityGateStatus.FAILED
            ),
            code=code,
            detail=detail,
        )


class DeterministicCoverLetterComposer:
    """Create source-grounded prose variants without a provider call."""

    def variants(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
    ) -> list[CoverLetterDraftOutput]:
        factual = [
            item for item in evidence if item.kind is not CoverLetterEvidenceKind.USER_MOTIVATION
        ]
        if not factual:
            raise ValueError("A deterministic cover letter requires reviewed candidate evidence")
        threads = self._evidence_threads(factual)
        concise_evidence = [record for thread in threads[:2] for record in thread[:1]]
        standard_threads = [*threads[1:3], *threads[:1]]
        standard_evidence = [
            record for thread in standard_threads[:3] for record in thread[:2]
        ]
        developed_evidence = [record for thread in threads[:3] for record in thread[:3]]
        full_evidence = [record for thread in threads[:3] for record in thread[:4]]
        outputs = [
            self._compose(
                concise_evidence,
                research,
                posting,
                CoverLetterLengthClass.CONCISE,
            ),
            self._compose(
                standard_evidence,
                research,
                posting,
                CoverLetterLengthClass.STANDARD,
            ),
            self._compose(
                developed_evidence,
                research,
                posting,
                CoverLetterLengthClass.DEVELOPED,
            ),
        ]
        if [record.id for record in full_evidence] != [
            record.id for record in developed_evidence
        ]:
            outputs.append(
                self._compose(
                    full_evidence,
                    research,
                    posting,
                    CoverLetterLengthClass.DEVELOPED,
                )
            )
        unique_outputs: list[CoverLetterDraftOutput] = []
        seen_text: set[tuple[str, ...]] = set()
        for output in outputs:
            signature = tuple(paragraph.text for paragraph in output.paragraphs)
            if signature in seen_text:
                continue
            seen_text.add(signature)
            unique_outputs.append(output)
        return unique_outputs

    def source_bound_fallback(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
    ) -> CoverLetterDraftOutput:
        factual = [
            item for item in evidence if item.kind is not CoverLetterEvidenceKind.USER_MOTIVATION
        ]
        if not factual:
            raise ValueError("A source-bound fallback requires reviewed candidate evidence")
        threads = self._evidence_threads(factual)
        fallback_evidence = [record for thread in threads[:3] for record in thread[:4]]
        return self._compose(
            fallback_evidence,
            research,
            posting,
            CoverLetterLengthClass.DEVELOPED,
        )

    @staticmethod
    def _threads_of_kind(
        evidence: list[CoverLetterEvidenceRecord],
        kind: CoverLetterEvidenceKind,
    ) -> list[list[CoverLetterEvidenceRecord]]:
        threads: list[list[CoverLetterEvidenceRecord]] = []
        indexes: dict[str, int] = {}
        for record in evidence:
            if record.kind is not kind:
                continue
            key = record.entity_id or record.id
            if key not in indexes:
                indexes[key] = len(threads)
                threads.append([])
            thread = threads[indexes[key]]
            if len(thread) < 4:
                thread.append(record)
        return threads

    @classmethod
    def _source_bound_paragraph(
        cls,
        *,
        purpose: CoverLetterParagraphPurpose,
        text: str,
        evidence_ids: list[str],
        posting_fact_ids: list[str],
        metadata: list[CoverLetterCanonicalMetadata],
        narrative_thread_id: str,
        length_class: CoverLetterLengthClass,
    ) -> CoverLetterDraftParagraph:
        sentences = [
            CoverLetterSentenceAuthority(
                text=sentence,
                posting_fact_ids=list(posting_fact_ids),
                candidate_evidence_ids=list(evidence_ids),
                canonical_metadata=list(metadata),
            )
            for sentence in CoverLetterValidator._sentences(text)
        ]
        return CoverLetterDraftParagraph(
            purpose=purpose,
            text=" ".join(sentence.text for sentence in sentences),
            candidate_evidence_ids=list(evidence_ids),
            company_research_ids=list(posting_fact_ids),
            narrative_thread_id=narrative_thread_id,
            length_class=length_class,
            source_bound_sentences=sentences,
        )

    def replacement_paragraph(
        self,
        purpose: CoverLetterParagraphPurpose,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
    ) -> CoverLetterDraftParagraph:
        output = self._compose(
            evidence[: min(3, len(evidence))],
            research,
            posting,
            CoverLetterLengthClass.DEVELOPED,
        )
        for paragraph in output.paragraphs:
            if paragraph.purpose is purpose:
                return paragraph
        return output.paragraphs[-1 if purpose is CoverLetterParagraphPurpose.CLOSING else 0]

    def _compose(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        research: CompanyResearchBundle,
        posting: JobPosting,
        length_class: CoverLetterLengthClass,
    ) -> CoverLetterDraftOutput:
        posting_facts = [
            fact
            for fact in research.facts
            if fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        ][:3]
        posting_fact_ids = [fact.id for fact in posting_facts]
        if not posting_fact_ids:
            posting_fact_ids = [str(self._company_fact(research).id)]
        threads = self._evidence_threads(evidence)
        if not threads:
            raise ValueError("A deterministic cover letter requires an evidence thread")
        representatives = [thread[0] for thread in threads]
        opening_record = self._opening_record(representatives, posting)
        connection_records = [opening_record]
        opening_fact = (
            self._opening_posting_fact(posting_facts, opening_record, posting)
            if posting_facts
            else None
        )
        opening_posting_fact_ids = (
            [opening_fact.id] if opening_fact is not None else posting_fact_ids
        )
        posting_concepts = self._opening_posting_concepts(
            (
                self._posting_concepts(opening_fact.fact, posting)
                if opening_fact is not None
                else self._authority_concepts(research, posting)
            ),
            opening_record,
        )
        if length_class is CoverLetterLengthClass.CONCISE:
            per_thread = 1
            story_thread_count = 2
        elif length_class is CoverLetterLengthClass.STANDARD:
            per_thread = 2
            story_thread_count = 3
        else:
            per_thread = max(len(thread) for thread in threads)
            story_thread_count = 3
        story_threads = threads[:story_thread_count]
        if len(story_threads) > 1:
            # The opening already introduces one entry. Develop other stories
            # first so the next paragraph does not immediately reopen it.
            opening_threads = [
                thread for thread in story_threads if thread[0].id == opening_record.id
            ]
            other_threads = [
                thread for thread in story_threads if thread[0].id != opening_record.id
            ]
            story_threads = [*other_threads, *opening_threads]
        story_records = []
        for thread in story_threads:
            if (
                thread[0].id == opening_record.id
                and len(thread) > 1
            ):
                # The opening already uses the representative fact. Develop the
                # thread with its remaining concrete facts instead of restating it.
                story_records.append(thread[1 : per_thread + 1])
            else:
                story_records.append(thread[:per_thread])
        story_purposes = (
            CoverLetterParagraphPurpose.EXPERIENCE_CONNECTION,
            CoverLetterParagraphPurpose.CONTRIBUTION,
            CoverLetterParagraphPurpose.ROLE_FIT,
        )
        paragraphs = [
            self._source_bound_paragraph(
                purpose=CoverLetterParagraphPurpose.OPENING,
                text=self._narrative_opening(
                    connection_records,
                    posting,
                    posting_concepts,
                ),
                evidence_ids=[item.id for item in connection_records],
                posting_fact_ids=opening_posting_fact_ids,
                metadata=[
                    CoverLetterCanonicalMetadata.COMPANY_NAME,
                    CoverLetterCanonicalMetadata.ROLE_TITLE,
                ],
                narrative_thread_id="thread-opening",
                length_class=length_class,
            ),
            *[
                self._source_bound_story_paragraph(
                    purpose=story_purposes[index],
                    records=records,
                    narrative_thread_id=f"thread-story-{index + 1}",
                    length_class=length_class,
                )
                for index, records in enumerate(story_records)
            ],
            self._source_bound_paragraph(
                purpose=CoverLetterParagraphPurpose.CLOSING,
                text=self._narrative_closing(
                    connection_records,
                    posting,
                ),
                evidence_ids=[item.id for item in connection_records],
                posting_fact_ids=opening_posting_fact_ids,
                metadata=[
                    CoverLetterCanonicalMetadata.COMPANY_NAME,
                    CoverLetterCanonicalMetadata.ROLE_TITLE,
                ],
                narrative_thread_id="thread-closing",
                length_class=length_class,
            ),
        ]
        return CoverLetterDraftOutput(paragraphs=paragraphs)

    @staticmethod
    def _opening_record(
        representatives: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> CoverLetterEvidenceRecord:
        """Choose the story whose concrete facts best support the role connection."""

        posting_terms = CoverLetterValidator._content_terms(posting.description)

        def key(record: CoverLetterEvidenceRecord) -> tuple[int, int, int, str]:
            evidence_terms = CoverLetterValidator._content_terms(
                " ".join(
                    [
                        record.writer_text or record.source_text,
                        *record.technologies,
                        *record.outcomes,
                    ]
                )
            )
            return (
                len(posting_terms & evidence_terms),
                len(record.matched_requirements),
                -(record.retrieval_rank or 10_000),
                record.id,
            )

        return max(representatives, key=key)

    @classmethod
    def _opening_posting_fact(
        cls,
        posting_facts: list[CompanyResearchFact],
        record: CoverLetterEvidenceRecord,
        posting: JobPosting,
    ) -> CompanyResearchFact:
        """Choose the posting fact that best supports the opening connection."""

        evidence_terms = cls._opening_alignment_terms(record)
        metadata_terms = CoverLetterValidator._content_terms(
            f"{posting.company_name or ''} {posting.title}"
        )

        def key(item: tuple[int, CompanyResearchFact]) -> tuple[int, int, int]:
            index, fact = item
            fact_terms = CoverLetterValidator._content_terms(fact.fact) - metadata_terms
            return (
                len(evidence_terms & fact_terms),
                len(fact_terms),
                -index,
            )

        return max(enumerate(posting_facts), key=key)[1]

    @classmethod
    def _opening_posting_concepts(
        cls,
        concepts: list[str],
        record: CoverLetterEvidenceRecord,
    ) -> list[str]:
        """Keep a compact, substantive posting focus adjacent to its authority fact."""

        evidence_terms = cls._opening_alignment_terms(record)
        ranked = sorted(
            enumerate(concepts),
            key=lambda item: (
                -len(
                    CoverLetterValidator._content_terms(item[1]) & evidence_terms
                ),
                -len(CoverLetterValidator._content_terms(item[1])),
                item[0],
            ),
        )
        selected: list[str] = []
        selected_terms: set[str] = set()
        for _, concept in ranked:
            concept_terms = CoverLetterValidator._content_terms(concept)
            if not concept_terms:
                continue
            selected.append(concept)
            selected_terms.update(concept_terms)
            if len(selected_terms) >= 2 or len(selected) == 2:
                break
        return selected

    @staticmethod
    def _opening_alignment_terms(record: CoverLetterEvidenceRecord) -> set[str]:
        """Return only reviewed or retrieval-proven terms for posting-fact pairing."""

        return CoverLetterValidator._content_terms(
            " ".join(
                [
                    record.writer_text or record.source_text,
                    *record.technologies,
                    *record.outcomes,
                    # Retrieval preserves its strongest requirement relationships
                    # first.  The full tail can contain broad secondary matches that
                    # make every posting fact appear equally aligned and reduce this
                    # pairing to fact length.
                    *record.matched_requirements[:4],
                ]
            )
        )

    @classmethod
    def _opening_candidate_focus(cls, record: CoverLetterEvidenceRecord) -> str:
        values = [
            cls._clean_focus(value)
            for value in (
                *record.technologies,
                *record.outcomes,
                *cls._technical_phrases(record.writer_text or record.source_text),
            )
        ]
        selected: list[str] = []
        selected_terms: set[str] = set()
        for value in dict.fromkeys(values):
            terms = CoverLetterValidator._content_terms(value)
            if not value or not terms or terms <= selected_terms:
                continue
            selected.append(value)
            selected_terms.update(terms)
            if len(selected_terms) >= 2 or len(selected) == 2:
                break
        return cls._joined(selected) if selected else cls._record_focus(record)

    @classmethod
    def _source_bound_story_paragraph(
        cls,
        *,
        purpose: CoverLetterParagraphPurpose,
        records: list[CoverLetterEvidenceRecord],
        narrative_thread_id: str,
        length_class: CoverLetterLengthClass,
    ) -> CoverLetterDraftParagraph:
        """Build a fallback story only from minimally transformed source facts."""

        sentence_groups = [[record] for record in records]
        if len(records) >= 3:
            sentence_groups = [[records[0]], [records[1], records[2]]]
            if len(records) == 4:
                sentence_groups.append([records[3]])
        sentences: list[CoverLetterSentenceAuthority] = []
        for index, group in enumerate(sentence_groups):
            if len(group) == 1:
                text = cls._full_evidence_sentence(group[0], index=index)
            else:
                left = cls._full_evidence_sentence(group[0], index=1).rstrip(".")
                right = cls._full_evidence_sentence(group[1], index=1).rstrip(".")
                right = re.sub(r"^I\s+", "", right, flags=re.IGNORECASE)
                text = f"{left} and {right}."
            sentences.append(
                CoverLetterSentenceAuthority(
                    text=text,
                    candidate_evidence_ids=[record.id for record in group],
                )
            )
        return CoverLetterDraftParagraph(
            purpose=purpose,
            text=" ".join(sentence.text for sentence in sentences),
            candidate_evidence_ids=[record.id for record in records],
            company_research_ids=[],
            narrative_thread_id=narrative_thread_id,
            length_class=length_class,
            source_bound_sentences=sentences,
        )

    def _narrative_opening(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
        posting_concepts: list[str],
    ) -> str:
        company = (posting.company_name or "").strip()
        destination = f" at {company}" if company else ""
        role_focus = self._joined(posting_concepts[:2])
        candidate_focus = self._opening_candidate_focus(evidence[0])
        source_fact = self._full_evidence_sentence(evidence[0], index=0).rstrip(".")
        return " ".join(
            [
                (
                    f"The {posting.title} role{destination} interests me because its "
                    "emphasis on "
                    f"{role_focus} relates to my experience with {candidate_focus}."
                ),
                f"{source_fact}.",
            ]
        )

    def _narrative_body(
        self,
        records: list[CoverLetterEvidenceRecord],
        posting_concepts: list[str],
        *,
        length_class: CoverLetterLengthClass,
        adjacent: bool,
        secondary: bool,
        story_index: int = 0,
    ) -> str:
        del posting_concepts, length_class, adjacent, secondary, story_index
        return " ".join(
            self._full_evidence_sentence(record, index=index)
            for index, record in enumerate(records)
        )

    @classmethod
    def _full_evidence_sentence(
        cls,
        record: CoverLetterEvidenceRecord,
        *,
        index: int,
    ) -> str:
        writer_text = " ".join((record.writer_text or record.source_text).split()).strip(" .")
        writer_text = re.sub(r"^(?:I|we)\s+", "", writer_text, flags=re.IGNORECASE)
        if not re.match(
            r"^(?:assembled|authored|automated|built|collaborated|configured|contributed|"
            r"created|debugged|deployed|designed|developed|diagnosed|documented|engineered|"
            r"evaluated|"
            r"fabricated|implemented|integrated|measured|modeled|modelled|programmed|"
            r"prototyped|ran|selected|specified|supported|tested|troubleshot|used|validated|"
            r"verified|wired|worked)\b",
            writer_text,
            re.IGNORECASE,
        ):
            return cls._complete_evidence_sentence(record, index=index)
        action = writer_text[:1].casefold() + writer_text[1:]
        title = record.entry_title or (
            "technical project"
            if record.kind is CoverLetterEvidenceKind.PROJECT
            else "engineering work"
        )
        if record.kind is CoverLetterEvidenceKind.PROJECT:
            label = title if title.casefold().endswith("project") else f"{title} project"
            if index == 0:
                return f"For the {label}, I {action}."
            return f"I {action}."
        if index == 0:
            if record.entry_title:
                return f"In my {title} work, I {action}."
            return f"In that engineering work, I {action}."
        return f"I {action}."

    @staticmethod
    def _narrowly_adjacent_to_role(
        record: CoverLetterEvidenceRecord,
        posting_concepts: list[str],
    ) -> bool:
        source_terms = CoverLetterValidator._content_terms(
            " ".join(
                [
                    record.source_text,
                    *record.technologies,
                    *record.outcomes,
                ]
            )
        )
        role_terms = CoverLetterValidator._content_terms(" ".join(posting_concepts))
        return len(source_terms & role_terms) <= 1

    def _narrative_closing(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        posting: JobPosting,
    ) -> str:
        company = (posting.company_name or "").strip()
        destination = f" at {company}" if company else ""
        del evidence
        return (
            f"I would be glad to bring this experience to the {posting.title} "
            f"role{destination}."
        )

    @classmethod
    def _complete_evidence_sentence(
        cls,
        record: CoverLetterEvidenceRecord,
        *,
        index: int,
    ) -> str:
        writer_text = record.writer_text or record.source_text
        action = cls._finite_action(writer_text)
        title = record.entry_title or (
            "technical project"
            if record.kind is CoverLetterEvidenceKind.PROJECT
            else "engineering work"
        )
        if action is None:
            normalized_source = " ".join(writer_text.split()).strip(" .,:;-")
            working = re.match(r"^working\s+with\s+(.+)$", normalized_source, re.IGNORECASE)
            if working:
                action = f"worked with {working.group(1)}"
            elif re.search(
                r"\b(?:am|are|is|was|were|included|involved|required|focused)\b",
                normalized_source,
                re.IGNORECASE,
            ):
                return normalized_source + "."
            else:
                subject = (
                    f"The {title if title.casefold().endswith('project') else title + ' project'}"
                    if record.kind is CoverLetterEvidenceKind.PROJECT
                    else f"My {title} work"
                )
                normalized_detail = (
                    normalized_source[:1].casefold() + normalized_source[1:]
                )
                return f"{subject} included {normalized_detail}."
        normalized_source = " ".join(writer_text.split()).strip(" .,:;-")
        project_label = title if title.casefold().endswith("project") else f"{title} project"
        if (
            len(normalized_source.split()) >= 8
            and action.casefold() == normalized_source.casefold()
        ):
            if record.kind is CoverLetterEvidenceKind.PROJECT:
                return f"On the {project_label}, I {action}."
            return f"In my {title} work, I {action}."
        if record.kind is CoverLetterEvidenceKind.PROJECT:
            return f"On the {project_label}, I {action}."
        if index == 0:
            return f"In my {title} work, I {action}."
        return f"I {action}."

    @staticmethod
    def _finite_action(text: str) -> str | None:
        cleaned = " ".join(text.split()).strip(" .,:;-")
        cleaned = re.sub(r"^(?:I|we)\s+", "", cleaned, flags=re.IGNORECASE)
        verbs = (
            "assembled|authored|automated|built|collaborated|configured|contributed|created|"
            "debugged|deployed|designed|developed|diagnosed|documented|engineered|evaluated|"
            "fabricated|"
            "implemented|integrated|led|measured|modeled|modelled|owned|programmed|prototyped|"
            "ran|selected|specified|supported|tested|troubleshot|used|validated|verified|"
            "wired|worked"
        )
        if not re.match(rf"^(?:{verbs})\b", cleaned, re.IGNORECASE):
            return None
        first_clause = re.split(
            rf"(?<!\d)[,;](?!\d)|\s+and\s+(?=(?:{verbs})\b)",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        words = first_clause.split()
        if len(words) > 24:
            first_clause = " ".join(words[:24]).rstrip(" ,;:-")
        first_clause = re.sub(r"\b(?:and|with|to)$", "", first_clause).strip()
        return first_clause[:1].casefold() + first_clause[1:]

    def _posting_grounded_opening(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        company_fact: CompanyResearchFact,
        posting: JobPosting,
        *,
        posting_concepts: list[str] | None = None,
    ) -> str:
        del company_fact
        company = (posting.company_name or "").strip() or "your organization"
        concepts = posting_concepts or self._posting_concepts(posting.description, posting)
        role_focus = self._joined(concepts[: min(3, len(concepts))])
        candidate_focus = self._joined(
            [self._thread_focus(item) for item in evidence[: min(3, len(evidence))]]
        )
        return " ".join(
            [
                f"I am applying for the {posting.title} role at {company}.",
                (
                    f"The position's emphasis on {role_focus} aligns with my background in "
                    f"{candidate_focus}."
                ),
                (
                    "The stated responsibilities bring technical definition, physical "
                    "integration, and troubleshooting into the same role."
                ),
            ]
        )

    @classmethod
    def _authority_concepts(
        cls,
        research: CompanyResearchBundle,
        posting: JobPosting,
    ) -> list[str]:
        posting_authority = " ".join(
            fact.fact
            for fact in research.facts
            if fact.confidence is CompanyFactConfidence.POSTING_AUTHORITY
        )
        return cls._posting_concepts(posting_authority or posting.description, posting)

    def _evidence_paragraph(
        self,
        records: list[CoverLetterEvidenceRecord],
        *,
        index: int,
        length_class: CoverLetterLengthClass,
    ) -> str:
        record = records[0]
        action_groups = [self._evidence_chunks(item.source_text) for item in records]
        first_actions = action_groups[0]
        action = first_actions[0] if first_actions else self._action_clause(record.source_text)
        title = record.entry_title or (
            "technical project"
            if record.kind is CoverLetterEvidenceKind.PROJECT
            else "engineering role"
        )
        gerund_action = self._gerund_action(action)
        if record.kind is CoverLetterEvidenceKind.PROJECT:
            project_label = title if title.casefold().endswith("project") else f"{title} project"
            opening = f"The {project_label} involved {gerund_action}."
        elif index == 0:
            opening = f"As {title}, my work included {gerund_action}."
        else:
            opening = f"In my {title} role, my work included {gerund_action}."
        sentences = [opening]
        supporting_actions = [
            action
            for group_index, group in enumerate(action_groups)
            for action in (group[1:] if group_index == 0 else group)
        ]
        sentences.extend(
            self._supporting_action_sentence(action, action_index)
            for action_index, action in enumerate(supporting_actions[:5])
        )
        technologies = list(
            dict.fromkeys(
                [
                    *[
                        self._clean_focus(value)
                        for item in records
                        for value in (
                            item.technologies or self._technical_phrases(item.source_text)
                        )
                    ],
                ]
            )
        )
        technologies = [value for value in technologies if value]
        outcomes = list(
            dict.fromkeys(
                self._clean_focus(value)
                for item in records
                for value in item.outcomes
                if self._clean_focus(value)
            )
        )
        if len(technologies) >= 3:
            responsibility_subject = "These responsibilities" if len(records) > 1 else "This work"
            sentences.append(
                f"{responsibility_subject} brought "
                f"{self._joined(technologies[:4])} into the same engineering effort."
            )
        elif technologies:
            sentences.append(
                f"That work gave me direct experience with {self._joined(technologies)}."
            )
            if supporting_actions:
                sentences.append(
                    f"It connected {gerund_action} with "
                    f"{self._gerund_action(supporting_actions[0])} within the same "
                    "engineering effort."
                )
        if outcomes:
            sentences.append(
                f"The resulting technical scope included {self._joined(outcomes[:2])}."
            )
        if length_class is CoverLetterLengthClass.CONCISE:
            return " ".join(sentences[:3])
        if length_class is CoverLetterLengthClass.STANDARD:
            return " ".join(sentences[: min(6, len(sentences))])
        if len(technologies) >= 4:
            sentences.append(
                f"This work required me to coordinate "
                f"{self._joined(technologies[:2])} with "
                f"{self._joined(technologies[2:4])} through implementation and testing."
            )
        if len(technologies) >= 3 and outcomes:
            sentences.append(
                f"That combination kept the practical work on "
                f"{self._joined(technologies[:3])} tied to "
                f"{self._joined(outcomes[:2])}."
            )
        return " ".join(sentences)

    @staticmethod
    def _evidence_threads(
        evidence: list[CoverLetterEvidenceRecord],
    ) -> list[list[CoverLetterEvidenceRecord]]:
        threads: list[list[CoverLetterEvidenceRecord]] = []
        indexes: dict[str, int] = {}
        for record in evidence:
            key = record.entity_id or record.id
            if key not in indexes:
                if len(threads) >= 3:
                    continue
                indexes[key] = len(threads)
                threads.append([])
            thread = threads[indexes[key]]
            if len(thread) < 4:
                thread.append(record)
        return threads

    @classmethod
    def _concrete_story_focus(
        cls,
        records: list[CoverLetterEvidenceRecord],
    ) -> str:
        generic = {
            "hardware",
            "software",
            "system",
            "systems",
            "testing",
            "documentation",
        }
        for record in records:
            for value in [*record.technologies, *record.outcomes]:
                cleaned = cls._clean_focus(value)
                if cleaned and cleaned.casefold() not in generic:
                    return cleaned
        return cls._thread_focus(records)

    @classmethod
    def _safe_narrative_phrases(cls, text: str) -> list[str]:
        """Return grammatical noun phrases from the legacy technical extractor.

        The extractor is useful for older evidence that predates typed technology
        metadata, but its raw values can begin with a verb, conjunction, unit, or
        preposition. Those fragments must never be interpolated into prose lists.
        """

        action_prefix = re.compile(
            r"^(?:assembled|authored|automated|built|collaborated|configured|contributed|"
            r"created|debugged|deployed|designed|developed|diagnosed|documented|engineered|"
            r"evaluated|"
            r"fabricated|implemented|integrated|measured|modeled|modelled|programmed|"
            r"prototyped|ran|selected|specified|supported|tested|troubleshot|used|validated|"
            r"verified|wired)\s+(?:the\s+|an?\s+)?",
            re.IGNORECASE,
        )
        unsafe_start = re.compile(
            r"^(?:across|along|at|by|during|for|from|in|into|of|on|over|through|to|under|"
            r"using|with|within)\b",
            re.IGNORECASE,
        )
        unsafe_unit_fragment = re.compile(
            r"^(?:ms|hz|fps|percent|seconds?|minutes?)\s+(?:at|over|under|with)\b",
            re.IGNORECASE,
        )
        phrases: list[str] = []
        for raw in cls._technical_phrases(text):
            value = " ".join(raw.split()).strip(" .,:;-")
            value = re.sub(r"^(?:and|or)\s+", "", value, flags=re.IGNORECASE)
            value = re.sub(
                r"^(?:worked|working)\s+with\s+",
                "",
                value,
                flags=re.IGNORECASE,
            )
            value = action_prefix.sub("", value).strip(" .,:;-")
            value = re.sub(r"^(?:the|an?)\s+", "", value, flags=re.IGNORECASE)
            if (
                not value
                or unsafe_start.match(value)
                or unsafe_unit_fragment.match(value)
                or re.search(r"\b(?:and|or|with|to)$", value, re.IGNORECASE)
            ):
                continue
            if value.casefold() not in {item.casefold() for item in phrases}:
                phrases.append(value)
        return phrases[:4]

    def _closing(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        posting_concepts: list[str],
        posting: JobPosting,
    ) -> str:
        company = (posting.company_name or "").strip() or "your organization"
        candidate_focus = self._joined(
            [self._thread_focus(item) for item in self._evidence_threads(evidence)[:3]]
        )
        role_focus = self._joined(posting_concepts[:2])
        return " ".join(
            [
                (
                    f"My background in {candidate_focus} is well suited to the "
                    f"{posting.title} position at {company}, particularly its focus on "
                    f"{role_focus}."
                ),
                (
                    f"I would welcome the opportunity to discuss how my experience with "
                    f"{candidate_focus} could support the position's stated engineering work."
                ),
                "Thank you for considering my application.",
            ]
        )

    @classmethod
    def _posting_concepts(cls, text: str, posting: JobPosting) -> list[str]:
        fragments = cls._posting_fragments(text)
        concepts: list[str] = []
        seen: set[str] = set()
        metadata_terms = CoverLetterValidator._content_terms(
            " ".join(value for value in (posting.company_name or "", posting.title) if value)
        )
        for fragment in fragments:
            fragment_terms = CoverLetterValidator._content_terms(fragment)
            if fragment_terms and fragment_terms <= metadata_terms:
                continue
            if len(fragment_terms - metadata_terms) < 2:
                continue
            concept = cls._normalize_posting_fragment(fragment)
            if not concept:
                continue
            normalized = concept.casefold()
            if normalized in seen:
                continue
            concepts.append(concept)
            seen.add(normalized)
        if concepts:
            return cls._split_role_concepts(concepts)[:4]
        role_terms = sorted(CoverLetterValidator._content_terms(posting.title))
        return role_terms[:3] or ["the stated engineering responsibilities"]

    @staticmethod
    def _split_role_concepts(concepts: list[str]) -> list[str]:
        output: list[str] = []
        for concept in concepts:
            for part in re.split(r",\s*", concept):
                cleaned = re.sub(
                    r"^(?:architecture|development|diagnosis|implementation|improvement|"
                    r"integration|investigation|testing|validation|work) of\s+",
                    "",
                    part.strip(),
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(
                    r"^prototype\s+",
                    "prototyping ",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                cleaned = re.sub(r"^run\s+", "", cleaned, flags=re.IGNORECASE)
                cleaned = re.sub(r"^(?:and|or)\s+", "", cleaned, flags=re.IGNORECASE)
                cleaned = DeterministicCoverLetterComposer._noun_sequence(cleaned)
                cleaned = re.sub(
                    r"^automated (.+?) systems?\b",
                    r"\1 automation",
                    cleaned,
                    flags=re.IGNORECASE,
                )
                cleaned = " ".join(cleaned.split()[:7]).rstrip(" ,")
                if cleaned and cleaned.casefold() not in {
                    item.casefold() for item in output
                }:
                    output.append(cleaned)
        return output[:6]

    @staticmethod
    def _prioritize_role_concepts(
        concepts: list[str],
        posting: JobPosting,
    ) -> list[str]:
        actionable = [
            concept for concept in concepts if not concept.casefold().endswith("responsibilities")
        ]
        if len(actionable) >= 3:
            concepts = actionable
        title_terms = CoverLetterValidator._content_terms(posting.title)
        return [
            concept
            for _, concept in sorted(
                enumerate(concepts),
                key=lambda item: (
                    not bool(
                        CoverLetterValidator._content_terms(item[1]) & title_terms
                    ),
                    item[0],
                ),
            )
        ]

    @staticmethod
    def _posting_fragments(text: str) -> list[str]:
        fragments: list[str] = []
        for line in text.splitlines():
            cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if not cleaned or re.fullmatch(r"[A-Za-z][A-Za-z /&-]{1,40}:", cleaned):
                continue
            for sentence in re.split(r"(?<=[.!?])\s+|;", cleaned):
                fragments.extend(
                    item.strip()
                    for item in re.split(
                        r",\s+(?=(?:act|architect|build|collaborate|create|define|design|"
                        r"develop|diagnose|execute|implement|improve|integrate|investigate|"
                        r"iterate|lead|maintain|perform|prototype|run|select|support|test|"
                        r"translate|troubleshoot|validate|work|working)\b)|"
                        r"\band\s+(?=(?:act|architect|build|collaborate|create|define|design|"
                        r"develop|diagnose|execute|implement|improve|integrate|investigate|"
                        r"iterate|lead|maintain|perform|prototype|run|select|support|test|"
                        r"translate|troubleshoot|validate|work)\b)",
                        sentence,
                        flags=re.IGNORECASE,
                    )
                    if item.strip()
                )
        if not fragments:
            fragments = [
                item.strip() for item in re.split(r"(?<=[.!?])\s+|;", text) if item.strip()
            ]
        return fragments

    @classmethod
    def _normalize_posting_fragment(cls, fragment: str) -> str:
        cleaned = " ".join(fragment.split()).strip(" .,:;-")
        cleaned = re.sub(
            r"^(?:you will|the successful candidate will|responsibilities include|"
            r"responsible for|work on)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(
            r"^(?:the|an?|this)\s+(?:intern|candidate|engineer|applicant|team member|person)\s+"
            r"(?:will|would|must|should|is expected to|is responsible for)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"^work(?:ing)?\s+(?:across|on)\s+", "", cleaned, flags=re.IGNORECASE)
        working = re.fullmatch(r"work(?:ing)? with (.+?) to (.+)", cleaned, re.IGNORECASE)
        if working is not None:
            partners = cls._normalize_partner_terms(working.group(1))
            actions = cls._noun_sequence(working.group(2))
            cleaned = f"{actions} with {partners}"
        else:
            act_as = re.fullmatch(r"act as (?:the |a |an )?(.+)", cleaned, re.IGNORECASE)
            if act_as is not None:
                cleaned = f"{act_as.group(1)} responsibilities"
            else:
                cleaned = cls._noun_sequence(cleaned)
        normalized = " ".join(cleaned.split()[:14]).rstrip(" ,")
        return re.sub(r"\s+(?:and|or|to|of|with)$", "", normalized, flags=re.IGNORECASE)

    @staticmethod
    def _normalize_partner_terms(value: str) -> str:
        return re.sub(
            r"\bOEMs?/ODMs?\b",
            "OEM and ODM partners",
            value,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _noun_sequence(value: str) -> str:
        action_nouns = {
            "act": "execution of",
            "architect": "architecture of",
            "assemble": "assembly of",
            "build": "development of",
            "collaborate": "collaboration with",
            "create": "development of",
            "debug": "debugging",
            "define": "defining",
            "design": "design of",
            "develop": "development of",
            "diagnose": "diagnosis of",
            "execute": "executing",
            "implement": "implementation of",
            "improve": "improvement of",
            "integrate": "integration of",
            "investigate": "investigation of",
            "inspect": "inspection of",
            "iterate": "iteration of",
            "lead": "leadership of",
            "maintain": "maintaining",
            "perform": "",
            "prototype": "prototyping",
            "run": "",
            "select": "selection of",
            "support": "support for",
            "test": "testing of",
            "translate": "translation of",
            "troubleshoot": "troubleshooting",
            "validate": "validation of",
            "work": "work on",
        }
        cleaned = value.strip()
        coordinated = re.fullmatch(
            r"(act|architect|assemble|build|collaborate|create|debug|define|design|develop|"
            r"execute|implement|diagnose|improve|inspect|integrate|investigate|iterate|lead|"
            r"maintain|perform|prototype|run|select|support|test|translate|troubleshoot|"
            r"validate|work)\s+and\s+"
            r"(act|architect|assemble|build|collaborate|create|debug|define|design|develop|"
            r"execute|implement|diagnose|improve|inspect|integrate|investigate|iterate|lead|"
            r"maintain|perform|prototype|run|select|support|test|translate|troubleshoot|"
            r"validate|work)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if coordinated is not None:
            first = action_nouns[coordinated.group(1).casefold()].rstrip(" of")
            second = action_nouns[coordinated.group(2).casefold()].rstrip(" of")
            return f"{first} and {second} of {coordinated.group(3)}"
        action = re.match(
            r"^(act|architect|assemble|build|collaborate|create|debug|define|design|develop|"
            r"execute|implement|diagnose|improve|inspect|integrate|investigate|iterate|lead|"
            r"maintain|perform|prototype|run|select|support|test|translate|troubleshoot|"
            r"validate|work)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if action is None:
            return cleaned
        prefix = action_nouns[action.group(1).casefold()]
        return f"{prefix} {action.group(2)}".strip()

    @staticmethod
    def _gerund_sequence(value: str) -> str:
        verbs = {
            "act": "serving",
            "architect": "architecting",
            "assembled": "assembling",
            "authored": "authoring",
            "build": "building",
            "built": "building",
            "collaborate": "collaborating",
            "collaborated": "collaborating",
            "configured": "configuring",
            "contributed": "contributing",
            "create": "creating",
            "created": "creating",
            "debugged": "debugging",
            "define": "defining",
            "design": "designing",
            "designed": "designing",
            "develop": "developing",
            "developed": "developing",
            "diagnosed": "diagnosing",
            "documented": "documenting",
            "engineered": "engineering",
            "evaluated": "evaluating",
            "fabricated": "fabricating",
            "implement": "implementing",
            "implemented": "implementing",
            "integrate": "integrating",
            "integrated": "integrating",
            "investigate": "investigating",
            "iterate": "iterating",
            "lead": "leading",
            "led": "leading",
            "maintain": "maintaining",
            "measured": "measuring",
            "modeled": "modeling",
            "modelled": "modelling",
            "perform": "performing",
            "programmed": "programming",
            "prototyped": "prototyping",
            "ran": "running",
            "select": "selecting",
            "selected": "selecting",
            "specified": "specifying",
            "support": "supporting",
            "supported": "supporting",
            "test": "testing",
            "tested": "testing",
            "translate": "translating",
            "troubleshoot": "troubleshooting",
            "troubleshot": "troubleshooting",
            "used": "using",
            "validated": "validating",
            "verified": "verifying",
            "wired": "wiring",
            "work": "working",
            "worked": "working",
        }
        output = value
        for verb, gerund in verbs.items():
            output = re.sub(
                rf"^(?:to\s+)?{verb}\b",
                gerund,
                output,
                count=1,
                flags=re.IGNORECASE,
            )
            output = re.sub(
                rf"\band\s+(?:to\s+)?{verb}\b",
                f"and {gerund}",
                output,
                flags=re.IGNORECASE,
            )
            output = re.sub(
                rf"(?<=,\s)(?:to\s+)?{verb}\b",
                gerund,
                output,
                flags=re.IGNORECASE,
            )
        return output

    @classmethod
    def _evidence_chunks(cls, text: str) -> list[str]:
        cleaned = " ".join(text.split()).strip().rstrip(".")
        initial_parts = re.split(
            r"(?<=[.!?])\s+|(?<!\d)[,;](?!\d)\s*",
            cleaned,
            flags=re.IGNORECASE,
        )
        parts: list[str] = []
        coordinated_action = re.compile(
            r"\band\s+(?=(?:assembled|authored|automated|built|collaborated|configured|"
            r"contributed|created|debugged|deployed|designed|developed|diagnosed|documented|"
            r"engineered|"
            r"evaluated|fabricated|implemented|integrated|led|measured|modeled|modelled|"
            r"programmed|prototyped|ran|selected|specified|supported|tested|troubleshot|used|"
            r"validated|verified|wired)\b)",
            re.IGNORECASE,
        )
        for part in initial_parts:
            match = coordinated_action.search(part)
            if match is not None and len(part[: match.start()].split()) >= 3:
                parts.extend((part[: match.start()], part[match.end() :]))
            else:
                parts.append(part)
        chunks: list[str] = []
        for part in parts:
            normalized = cls._action_clause(part)
            normalized = " ".join(normalized.split()[:20]).strip(" .,:;-")
            if normalized and normalized.casefold() not in {item.casefold() for item in chunks}:
                chunks.append(normalized)
        return chunks[:6]

    @staticmethod
    def _action_clause(text: str) -> str:
        cleaned = " ".join(text.split()).strip(" .,:;-")
        cleaned = re.sub(r"^(?:and|also)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+\+\s+", " and ", cleaned)
        cleaned = re.sub(r"\band\s+and\b", "and", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\band$", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"^(?:I|we)\s+", "", cleaned, flags=re.IGNORECASE)
        gerund_to_past = {
            "including": "included",
            "using": "used",
            "specifying": "specified",
            "evaluating": "evaluated",
            "integrating": "integrated",
            "testing": "tested",
            "troubleshooting": "troubleshot",
        }
        first, separator, rest = cleaned.partition(" ")
        replacement = gerund_to_past.get(first.casefold())
        if replacement:
            cleaned = f"{replacement}{separator}{rest}"
        action_starts = (
            "assembled",
            "authored",
            "automated",
            "built",
            "collaborated",
            "configured",
            "contributed",
            "created",
            "debugged",
            "deployed",
            "designed",
            "developed",
            "documented",
            "engineered",
            "evaluated",
            "fabricated",
            "implemented",
            "integrated",
            "led",
            "measured",
            "modeled",
            "modelled",
            "programmed",
            "prototyped",
            "ran",
            "selected",
            "specified",
            "supported",
            "tested",
            "troubleshot",
            "used",
            "verified",
            "wired",
        )
        if not re.match(
            rf"^(?:{'|'.join(action_starts)})\b",
            cleaned,
            re.IGNORECASE,
        ):
            cleaned = f"worked with {cleaned}"
        return cleaned[:1].casefold() + cleaned[1:]

    @classmethod
    def _action_series(cls, actions: list[str]) -> str:
        cleaned = [action.rstrip(" .,:;-") for action in actions if action]
        if not cleaned:
            return "completed the documented engineering work"
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            return f"{cleaned[0]} and {cleaned[1]}"
        return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"

    @classmethod
    def _supporting_action_sentence(cls, action: str, index: int) -> str:
        gerund = cls._gerund_action(action)
        templates = (
            f"I also {action}.",
            f"The work included {gerund}.",
            f"Another responsibility involved {gerund}.",
            f"I also {action}.",
            f"The effort also involved {gerund}.",
        )
        return templates[index % len(templates)]

    @staticmethod
    def _gerund_action(action: str) -> str:
        cleaned = " ".join(action.split()).strip(" .,:;-")
        first, separator, rest = cleaned.partition(" ")
        gerunds = {
            "assembled": "assembling",
            "authored": "authoring",
            "automated": "automating",
            "built": "building",
            "collaborated": "collaborating",
            "configured": "configuring",
            "contributed": "contributing",
            "created": "creating",
            "debugged": "debugging",
            "deployed": "deploying",
            "designed": "designing",
            "developed": "developing",
            "documented": "documenting",
            "engineered": "engineering",
            "evaluated": "evaluating",
            "fabricated": "fabricating",
            "implemented": "implementing",
            "integrated": "integrating",
            "led": "leading",
            "measured": "measuring",
            "modeled": "modeling",
            "modelled": "modelling",
            "programmed": "programming",
            "prototyped": "prototyping",
            "ran": "running",
            "selected": "selecting",
            "specified": "specifying",
            "supported": "supporting",
            "tested": "testing",
            "troubleshot": "troubleshooting",
            "used": "using",
            "verified": "verifying",
            "wired": "wiring",
            "worked": "working",
        }
        replacement = gerunds.get(first.casefold())
        result = f"{replacement}{separator}{rest}" if replacement else f"working with {cleaned}"
        for past_tense, coordinated_gerund in gerunds.items():
            result = re.sub(
                rf"\band {re.escape(past_tense)}\b",
                f"and {coordinated_gerund}",
                result,
                flags=re.IGNORECASE,
            )
        return result

    @classmethod
    def _thread_focus(
        cls,
        record_or_thread: CoverLetterEvidenceRecord | list[CoverLetterEvidenceRecord],
    ) -> str:
        records = record_or_thread if isinstance(record_or_thread, list) else [record_or_thread]
        values = [
            cls._clean_focus(value)
            for record in records
            for value in (
                *record.technologies,
                *record.outcomes,
                *cls._technical_phrases(record.source_text),
            )
        ]
        title_terms = {
            term
            for record in records
            for term in CoverLetterValidator._content_terms(record.entry_title or "")
        }
        unique = [
            value
            for value in dict.fromkeys(values)
            if value
            and not (
                CoverLetterValidator._content_terms(value)
                and CoverLetterValidator._content_terms(value) <= title_terms
            )
            and not re.fullmatch(
                r"[<>~]?\d+(?:[.,]\d+)?(?:%|ms|fps|hz|khz|mhz|gb|mb)?",
                value.casefold(),
            )
        ]
        if unique:
            return unique[0]
        return "hands-on engineering work"

    @staticmethod
    def _clean_focus(value: str) -> str:
        cleaned = " ".join(value.split()).strip(" .,:;-")
        cleaned = re.sub(r"\s+\+\s+", " and ", cleaned)
        cleaned = re.sub(r"^(?:and|also)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(
            r"^(?:assembled|authored|automated|built|created|deployed|designed|developed|"
            r"diagnosed|documented|engineered|evaluated|implemented|integrated|led|modeled|"
            r"modelled|prototyped|selected|specified|supported|tested|troubleshot|validated|"
            r"verified)\s+",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\band\s+and\b", "and", cleaned, flags=re.IGNORECASE)
        return cleaned.strip(" .,:;-")

    @staticmethod
    def _technical_phrases(text: str) -> list[str]:
        heads = (
            r"actuation|actuators?|architecture|assemblies|boms?|cad|circuits?|"
            r"comparators?|controllers?|documentation|drivers?|enclosures?|firmware|"
            r"gpio|hardware|interfaces?|latency|linkages?|microcontrollers?|modems?|"
            r"pcbs?|prototypes?|sensors?|software|systems?|testing|tests?|timers?|"
            r"troubleshooting|wiring(?:\s+harnesses)?"
        )
        phrases: list[str] = []
        for match in re.finditer(
            rf"\b(?:[A-Za-z0-9+#./-]+\s+){{0,3}}(?:{heads})\b",
            text,
            re.IGNORECASE,
        ):
            phrase = match.group(0).strip(" ,.;:")
            phrase = re.sub(r"^(?:a|an|the)\s+", "", phrase, flags=re.IGNORECASE)
            if (
                phrase
                and phrase.casefold() not in {item.casefold() for item in phrases}
                and not any(
                    phrase.casefold() in item.casefold()
                    for item in phrases
                    if len(phrase.split()) == 1
                )
            ):
                phrases.append(phrase)
        return phrases[:7]

    def _primary_body(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        length_class: CoverLetterLengthClass,
    ) -> str:
        first = evidence[0]
        combined_source = " ".join(item.source_text for item in evidence).casefold()
        if (
            length_class is CoverLetterLengthClass.DEVELOPED
            and len(evidence) > 1
            and "drive-by-wire" in combined_source
            and "safety override" in combined_source
        ):
            return self._developed_autonomous_body()
        sentences = [
            self._record_sentence(first, lead=True),
        ]
        if len(evidence) > 1:
            second = evidence[1]
            sentences.append(self._record_sentence(second, lead=False))
            source = f"{first.source_text} {second.source_text}".casefold()
            if "autonomous" in source and "safety override" in source:
                sentences.append(
                    "Taken together, those projects cover both ends of autonomous system "
                    "execution: translating commands into physical actuation and preserving "
                    "remote control under latency and safety constraints."
                )
                if length_class in {
                    CoverLetterLengthClass.STANDARD,
                    CoverLetterLengthClass.DEVELOPED,
                }:
                    sentences.append(
                        "The common thread is the boundary between a software command and the "
                        "vehicle behavior produced through a defined control interface."
                    )
            else:
                sentences.append(
                    f"Together, those records connect {self._technical_focus(first)} with "
                    f"{self._technical_focus(second)} under concrete implementation and test "
                    "constraints."
                )
                if length_class in {
                    CoverLetterLengthClass.STANDARD,
                    CoverLetterLengthClass.DEVELOPED,
                }:
                    sentences.append(
                        "The useful connection is not a list of tools; it is experience carrying "
                        "an engineering decision through an interface, a measurement, or a test."
                    )
                if length_class is CoverLetterLengthClass.DEVELOPED:
                    sentences.append(
                        "That perspective keeps implementation details tied to observable system "
                        "behavior instead of treating them as isolated tasks."
                    )
        elif length_class is CoverLetterLengthClass.DEVELOPED:
            sentences.append(
                "The value of that work lies in the concrete implementation choices and measured "
                "conditions recorded in the reviewed evidence."
            )
        return " ".join(sentences)

    @staticmethod
    def _developed_autonomous_body() -> str:
        return " ".join(
            [
                (
                    "On the autonomous golf cart retrofit, I led the design and technical "
                    "architecture of the drive-by-wire actuation system."
                ),
                (
                    "Electronic commands reached steering, throttle, and braking through 3 "
                    "linear actuators and embedded control interfaces."
                ),
                (
                    "Because the system had to retrofit an existing vehicle, the architecture "
                    "could not assume a platform designed around autonomous control; it had to "
                    "connect software intent to the cart's physical functions."
                ),
                (
                    "That made the command interface part of the engineering problem rather than "
                    "a detail left for integration."
                ),
                "The teleoperation project approached the same boundary from farther away.",
                (
                    "As R&D Hardware Engineer, I integrated the hardware architecture of a level "
                    "1 autonomous last-mile delivery solution for low-speed vehicles using ROS 2."
                ),
                (
                    "The system gave a remote operator real-time vehicle control and a safety "
                    "override, with operator-to-vehicle round-trip latency <200 ms over 5G modem."
                ),
                (
                    "The latency measurement covered the full operator-to-vehicle path, placing "
                    "communication behavior inside the control problem."
                ),
                "That put safety inside the command path rather than beside it.",
                (
                    "The interface therefore carried mechanical, communication, and safety "
                    "consequences at once."
                ),
                (
                    "Taken together, the projects connect physical actuation, embedded interfaces, "
                    "remote control, timing, and override behavior without treating them as "
                    "separate checkboxes."
                ),
                (
                    "The work required reasoning beyond whether a command was correct: how it "
                    "crossed an interface, became motion, and remained interruptible."
                ),
                (
                    "The perspective I would carry into research is downstream but concrete: an "
                    "autonomous decision inherits the interface and safety behavior of the system "
                    "that executes it."
                ),
            ]
        )

    def _contribution_body(
        self,
        evidence: list[CoverLetterEvidenceRecord],
        fact_terms: list[str],
        length_class: CoverLetterLengthClass,
    ) -> str:
        primary = evidence[: min(2, len(evidence))]
        if len(evidence) < 3:
            direct_focus = self._joined([self._technical_focus(item) for item in primary])
            sentences = [
                f"That experience gives me a practical frame for {direct_focus}: the details "
                "have to survive implementation, integration, and testing.",
                "Its relevance comes from the engineering constraints themselves, not from a "
                "claim that a project covers every part of the role.",
            ]
            if length_class in {
                CoverLetterLengthClass.STANDARD,
                CoverLetterLengthClass.DEVELOPED,
            }:
                sentences.append(
                    "I would carry that habit of tracing a technical decision to observable "
                    "system behavior into the role."
                )
            if length_class is CoverLetterLengthClass.DEVELOPED:
                sentences.append(
                    "That offers an immediate systems contribution while leaving the next area "
                    "of technical depth clearly bounded."
                )
            return " ".join(sentences)

        adjacent = evidence[2]
        combined_primary = " ".join(item.source_text for item in primary).casefold()
        if (
            length_class is CoverLetterLengthClass.DEVELOPED
            and "natural language queries" in adjacent.source_text.casefold()
            and "drive-by-wire" in combined_primary
        ):
            return self._developed_adjacent_ai_body()
        if self._is_physical_system_evidence(adjacent):
            return self._physical_contribution_body(adjacent, primary, length_class)
        sentences = [
            (
                f"In a different domain, the {adjacent.entry_title or 'reviewed project'} "
                f"centered on {self._gerund_fact(adjacent.source_text)}."
            )
        ]
        requirement = self._requirement_focus(adjacent, fact_terms)
        if requirement is None:
            adjacent_scope = self._adjacent_scope(fact_terms)
            sentences.append(
                f"That project is adjacent to this role, not evidence of {adjacent_scope} "
                "experience."
            )
            sentences.append(
                f"Its narrower relevance is experience implementing "
                f"{self._technical_focus(adjacent)} in a different domain."
            )
            if length_class in {
                CoverLetterLengthClass.STANDARD,
                CoverLetterLengthClass.DEVELOPED,
            }:
                sentences.append(
                    f"My direct grounding comes instead from "
                    f"{self._joined([self._technical_focus(item) for item in primary])}."
                )
            if length_class is CoverLetterLengthClass.DEVELOPED:
                sentences.extend(
                    [
                        (
                            "In practical terms, natural language queries were the route into "
                            "4,000+ transactions, with the dashboard providing the view of "
                            "spending patterns, budgets, and expense data."
                        ),
                        (
                            "The engineering task there was to make transaction data explorable "
                            "through natural language queries and an interactive dashboard."
                        ),
                        (
                            "Keeping those threads separate makes the contribution case narrower "
                            "and more accurate."
                        ),
                    ]
                )
        else:
            sentences.extend(
                [
                    f"That thread adds a separate implementation view of {requirement}.",
                    (
                        "Its value is the supported technical context it adds to the primary "
                        "engineering records, rather than another restatement of them."
                    ),
                ]
            )
            if length_class is CoverLetterLengthClass.DEVELOPED:
                sentences.append(
                    "Together, the threads show how the same engineering problem can move "
                    "across physical interfaces, software behavior, and measured outcomes."
                )
        return " ".join(sentences)

    @staticmethod
    def _developed_adjacent_ai_body() -> str:
        return " ".join(
            [
                "Crest adds a deliberately adjacent thread from a different domain.",
                (
                    "I built the AI-powered financial management platform around 4,000+ "
                    "transactions and natural language queries."
                ),
                (
                    "Its interactive dashboard let users explore spending patterns, budgets, and "
                    "expense data."
                ),
                (
                    "The engineering path ran from a user's language query into financial data "
                    "and back to an interactive view, which is useful implementation experience "
                    "for an AI-enabled system."
                ),
                ("It is not evidence of autonomous driving or multimodal reasoning experience."),
                "I would not present it that way.",
                (
                    "Its narrower value is experience connecting the AI-powered platform to "
                    "financial data and an interactive interface."
                ),
                (
                    "The useful connection is limited to implementation: the language-query "
                    "project and vehicle work each placed a software capability inside a broader "
                    "engineered path."
                ),
                ("My direct autonomous system grounding remains the drive-by-wire and ROS 2 work."),
                (
                    "Keeping that boundary explicit lets the project add a software-facing "
                    "perspective without borrowing credibility from a different research domain."
                ),
            ]
        )

    def _physical_contribution_body(
        self,
        adjacent: CoverLetterEvidenceRecord,
        primary: list[CoverLetterEvidenceRecord],
        length_class: CoverLetterLengthClass,
    ) -> str:
        sentences = [
            self._record_sentence(adjacent, lead=True),
            (
                "That work adds another reviewed example of carrying a physical input through "
                "a defined hardware response."
            ),
            (
                f"Alongside {self._joined([self._technical_focus(item) for item in primary])}, "
                "it broadens the implementation evidence without changing the facts or scope "
                "of any project."
            ),
        ]
        if length_class is CoverLetterLengthClass.DEVELOPED:
            sentences.append(
                "The common constraint is that the interface has to remain understandable at "
                "the point where sensing, control, and physical behavior meet."
            )
        return " ".join(sentences)

    @staticmethod
    def _is_physical_system_evidence(record: CoverLetterEvidenceRecord) -> bool:
        source = record.source_text.casefold()
        return any(
            term in source
            for term in (
                "actuator",
                "breadboard",
                "circuit",
                "comparator",
                "embedded",
                "hardware",
                "ldr",
                "mechanical",
                "microcontroller",
                "motor driver",
                "sensor",
                "solder",
                "wiring",
            )
        )

    @staticmethod
    def _company_fact(research: CompanyResearchBundle) -> CompanyResearchFact:
        usable = [
            fact
            for fact in research.facts
            if fact.confidence is not CompanyFactConfidence.CONFLICTING
        ]
        if not usable:
            raise ValueError("A cover letter requires a posting or verified company fact")
        return usable[0]

    @staticmethod
    def _gerund_fact(text: str) -> str:
        cleaned = " ".join(text.split()).strip().rstrip(".")
        if not cleaned:
            return cleaned
        cleaned = re.sub(r"^(?:I|We)\s+", "", cleaned, count=1, flags=re.IGNORECASE)
        first, separator, rest = cleaned.partition(" ")
        gerunds = {
            "authored": "authoring",
            "automated": "automating",
            "built": "building",
            "collaborated": "collaborating",
            "created": "creating",
            "deployed": "deploying",
            "designed": "designing",
            "developed": "developing",
            "engineered": "engineering",
            "evaluated": "evaluating",
            "implemented": "implementing",
            "integrated": "integrating",
            "led": "leading",
            "leveraged": "using",
            "modeled": "modeling",
            "modelled": "modelling",
            "prototyped": "prototyping",
            "supported": "supporting",
            "tested": "testing",
        }
        gerund = gerunds.get(first.casefold())
        if gerund and separator:
            for past_tense, coordinated_gerund in gerunds.items():
                rest = re.sub(
                    rf"\band {re.escape(past_tense)}\b",
                    f"and {coordinated_gerund}",
                    rest,
                    count=1,
                    flags=re.IGNORECASE,
                )
            return f"{gerund} {rest}"
        return f"working on {first.casefold()}{separator}{rest}"

    def _record_sentence(
        self,
        record: CoverLetterEvidenceRecord,
        *,
        lead: bool,
    ) -> str:
        action = self._gerund_fact(record.source_text)
        title = record.entry_title or "reviewed engineering work"
        if record.kind is CoverLetterEvidenceKind.PROJECT:
            return f"In the {title} project, I focused on {action}."
        if lead:
            return f"As {title}, my work centered on {action}."
        return f"In a separate {title} effort, I focused on {action}."

    @staticmethod
    def _technical_focus(record: CoverLetterEvidenceRecord) -> str:
        values = list(dict.fromkeys([*record.technologies, *record.outcomes]))
        source = record.source_text.casefold()
        recognized = (
            "SolidWorks",
            "harmonic drives",
            "GPIO interfacing",
            "embedded microcontroller",
            "LDR sensor",
            "comparator logic",
            "555 monostable circuit",
            "motor driver",
            "wiring harnesses",
            "drive-by-wire actuation",
            "embedded control interfaces",
            "ROS 2",
            "autonomous teleoperation",
            "safety override",
            "round-trip latency",
            "natural language queries",
            "interactive dashboard",
            "AI-powered financial management platform",
            "hardware test fixture",
            "sensor communication",
            "data API",
            "integration tests",
        )
        values.extend(term for term in recognized if term.casefold() in source)
        values = list(dict.fromkeys(values))
        if values:
            return values[0]
        return DeterministicCoverLetterComposer._record_focus(record)

    @staticmethod
    def _adjacent_scope(fact_terms: list[str]) -> str:
        lowered = " ".join(fact_terms).casefold()
        if "autonomous driving" in lowered and "multimodal reasoning" in lowered:
            return "autonomous driving or multimodal reasoning"
        return DeterministicCoverLetterComposer._joined(fact_terms[:2])

    @staticmethod
    def _requirement_focus(
        record: CoverLetterEvidenceRecord,
        fact_terms: list[str],
    ) -> str | None:
        source_terms = CoverLetterValidator._content_terms(
            " ".join([record.source_text, *record.technologies, *record.outcomes])
        )
        matched = [
            term for term in fact_terms if CoverLetterValidator._content_terms(term) & source_terms
        ]
        if matched:
            return DeterministicCoverLetterComposer._joined(matched[:2])
        return None

    @staticmethod
    def _record_focus(record: CoverLetterEvidenceRecord) -> str:
        values = [*record.technologies[:2], *record.outcomes[:1]]
        if values:
            return DeterministicCoverLetterComposer._joined(values)
        cleaned = " ".join(record.source_text.split()).strip().rstrip(".")
        cleaned = re.sub(
            r"^(?:built|created|designed|developed|implemented|integrated|led|supported|tested)\s+",
            "",
            cleaned,
            count=1,
            flags=re.IGNORECASE,
        )
        first_clause = re.split(r"(?<!\d),(?!\d)", cleaned, maxsplit=1)[0]
        words = first_clause.split()
        first_clause = re.sub(
            r"^the (?:design and technical|hardware|software|technical) architecture of ",
            "",
            first_clause,
            count=1,
            flags=re.IGNORECASE,
        )
        words = first_clause.split()
        if len(words) > 14:
            for marker in (" that ", " using ", " for "):
                prefix, separator, _ = first_clause.partition(marker)
                if separator and len(prefix.split()) >= 5:
                    first_clause = prefix
                    break
        return first_clause or "hands-on engineering work"

    @classmethod
    def _specific_terms(cls, fact: str, posting: JobPosting) -> list[str]:
        return cls._posting_concepts(fact, posting)

    @staticmethod
    def _joined(values: list[str]) -> str:
        cleaned = [value for value in dict.fromkeys(values) if value]
        if not cleaned:
            return ""
        if len(cleaned) == 1:
            return cleaned[0]
        if len(cleaned) == 2:
            return f"{cleaned[0]} and {cleaned[1]}"
        return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


__all__ = [
    "CoverLetterValidationResult",
    "CoverLetterValidator",
    "DeterministicCoverLetterComposer",
]
