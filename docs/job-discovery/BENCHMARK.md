# Jobs Discovery Benchmark — Batch 1 Complete

This benchmark is synthetic/deidentified development data for evaluating profile fit. Fit labels are ground truth for this benchmark, not hiring probability, interview probability, offer probability, or a prediction about an employer's decision.

## Split status and isolation

The benchmark contains exactly 60 calibration, 20 validation, and 20 locked cases. The development benchmark ground truth is 80 approved cases. Ordinary development loaders open calibration and validation only. Locked cases remain sealed, unapproved, and guarded by the dedicated locked marker plus explicit authorization; ordinary reports and metrics never load or score them.

Calibration was approved as proposed by the project owner on 2026-07-23. Labels, eligibility, provisional status, visibility, apply-worthiness, human tiers, pairwise judgments, evidence mappings, reasons, and rationales are frozen as approved fit ground truth. The approved calibration checksum is:

`962175c951442ce98637eec5b7f22b5fcf5694b1553c007200f9ce526950308f`

The approved validation checksum is `4b5b70d577420c21d993aebec436e66be93aecdf909465a5865b8b3a18d14768`, with semantic-decision digest `0746c98f278cc7a1988a9e4e5d3da0184223f4f5b95005f46872bb6ddc5b5ba7`.

The approval record is `tests/fixtures/job_discovery/benchmark/approval.json`. It preserves the proposed fixture values and records the approval authority, date, decision, frozen-label state, and immutable checksum. Presentation fields such as reviewer notes do not redefine the checksum; a semantic judgment mutation does.

Validation was approved as proposed and frozen by the project owner on 2026-07-23. Its approved checksum and semantic-decision digest are recorded in `approval.json` and `manifest.json`; the two final explanation corrections are authorized wording edits, not label changes. The overall manifest remains `partially_approved` with top-level `approved=false` because the locked split remains sealed and unapproved.

Validation cases 061–080 are approved and frozen as fit ground truth. Their historical reviewer-input fields remain blank. The two groups are independent: Group 01 covers software, data, and ML-platform generalization; Group 02 covers robotics, embedded, and systems generalization.

## Proposed fit rubric

- **Excellent:** direct responsibility alignment, every critical requirement demonstrated, no substantive required gap, and no hard eligibility conflict.
- **Good:** direct worthwhile fit with every critical requirement demonstrated and a limited required non-critical or responsibility-depth gap.
- **Weak:** critical core demonstrated with a specific material but reasonably viewable stretch.
- **Don't Match:** missing critical requirement, genuinely irrelevant responsibilities, severe level/scope mismatch, mandatory credential conflict, or hard eligibility conflict.

Eligibility (`eligible`, `unknown`, `ineligible`) is independent from substantive fit. Unknown eligibility does not lower grade automatically; it records unresolved posting or candidate authority. Hard-ineligible and Don't Match cases remain in the benchmark but are hidden from the normal feed and are never apply-worthy. Provisional is reserved for concrete posting uncertainty, such as incomplete location, date, level, or authorization facts.

Demonstrated evidence is reviewed work or responsibility held. Transferable evidence may support a neighboring boundary but cannot invent ownership. Coursework and reviewed-only skills are contextual and cannot establish production ownership. Every posting responsibility, critical requirement, required qualification, preferred qualification, positive reason, gap, and eligibility decision has atomic references.

## Human-review workflow

1. Inspect the approved validation HTML, which includes profile summary, preferences, source posting, facts, qualifications, evidence, gaps, frozen labels, rationale, pair context, and current-production diagnostics.
2. Treat the validation CSV reviewer fields as historical blank fields; they do not reopen or redefine frozen ground truth.
3. Tune the production scorer only with calibration. Validation remains an evaluation gate and must not be used as a tuning source.
4. Keep calibration and validation approval immutable. Benchmark Batch 1 is complete.

The current production comparison is diagnostic only. It reports confusion matrices, adjacent agreement, eligibility disagreement, visibility and hard-conflict leakage, pairwise ranking, precision@5, and role/level/evidence/completeness slices without changing validation labels. No locked metric is produced.

## Review artifacts

Calibration review artifacts:

- `generated/job-discovery/calibration-group-01-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/calibration-group-02-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/calibration-group-03-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/calibration-group-04-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/calibration-group-05-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/calibration-group-06-review.html`, `.csv`, `.baseline.json`

Validation review artifacts:

- `generated/job-discovery/validation-group-01-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/validation-group-02-review.html`, `.csv`, `.baseline.json`
- `generated/job-discovery/validation-review-index.html`

Locked cases may be opened once, only after scoring-policy freeze and explicit project-owner authorization. Scoring-policy redesign, provider/feed work, UI work, and locked-case evaluation are outside the completed Benchmark Batch 1 dataset phase.
