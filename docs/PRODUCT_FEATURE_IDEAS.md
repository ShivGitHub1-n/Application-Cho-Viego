# Product Feature Ideas and Future Direction

**Suggested repository path:** `docs/PRODUCT_FEATURE_IDEAS.md`

## Purpose

This document captures product ideas that should be preserved for later development without interrupting the current implementation sequence.

The immediate engineering workflow remains focused on safe Gemini-backed role classification. The ideas below are a product backlog and design reference, not permission to expand the current coding scope.

---

## Product Direction

The product should become an evidence-grounded career and application system for multidisciplinary engineers.

It should help a user:

1. Maintain a trustworthy master career profile.
2. Discover roles across adjacent engineering families.
3. Understand why a role fits or does not fit.
4. Tailor a resume without inventing evidence.
5. Edit the tailored resume directly.
6. Keep the final document within one page when required.
7. Track applications, gaps, projects, interview preparation, and outcomes.
8. Learn from previous decisions through persistent career memory.

The product should not become a clone of any existing resume platform. Similar products may provide useful interaction patterns, but the workflows, terminology, visual design, scoring logic, assistant identity, and implementation should remain original.

---

# 1. Tailored Resume Workspace

## 1.1 Split-screen editor and live preview

Create a resume workspace with two synchronized panels:

- **Left panel:** structured editor and AI assistance.
- **Right panel:** exact live preview of the generated resume.
- The preview should match the downloaded PDF or DOCX as closely as technically possible.
- Changes should update the preview without requiring the user to leave the page.
- The interface should clearly distinguish saved changes, unsaved changes, and generated suggestions.

Possible editing modes:

- **Manual edit**
- **AI-assisted edit**
- **Review proposed changes**
- **Compare before and after**

The AI must propose changes rather than silently rewriting the document.

## 1.2 Structured section editor

Represent the resume as editable structured data rather than an unstructured text document.

Supported sections may include:

- Contact information
- Education
- Technical skills
- Experience
- Projects
- Research
- Awards
- Leadership
- Publications
- Certifications
- Custom sections

Each section should support:

- Expand and collapse
- Add entry
- Delete entry
- Reorder entries
- Reorder sections
- Temporarily hide an entry without deleting it
- Restore hidden entries
- Edit dates, location, title, organization, and descriptive fields
- Add, remove, edit, and reorder bullets

Example experience fields:

- Job title
- Company
- Location
- Start date
- End date
- Currently work here
- Source evidence
- Bullet list
- Tailoring status
- Included in current resume
- Exclusion reason

Example education fields:

- School
- Degree
- Program
- Minor or specialization
- GPA
- Location
- Start date
- Graduation date
- Awards
- Relevant coursework
- Included details

## 1.3 Section ordering

Allow the user to move sections such as Experience above Education while preserving consistent document geometry.

The system should:

- Reorder complete semantic blocks, not individual rendered paragraphs.
- Preserve heading styles, spacing, indentation, tab stops, and alignment.
- Recalculate page fit after every structural change.
- Warn when a move creates overflow or poor visual balance.
- Never allow a move to corrupt the document structure.

## 1.4 Bullet-level controls

Every bullet should support:

- Edit manually
- Remove from current resume
- Restore from the master profile
- Move up or down
- Mark as required
- Mark as optional
- Ask AI to tighten wording
- Ask AI to emphasize outcomes
- Ask AI to align with the job
- View the source evidence supporting the claim
- Compare original, proposed, and approved versions
- Reject a suggestion without losing the original

The system should never modify dates, employers, technologies, metrics, or factual claims unless the user has provided supporting evidence.

## 1.5 Change approval

AI-generated changes should use an explicit review workflow:

1. Proposed
2. Accepted
3. Rejected
4. Manually edited
5. Applied to preview
6. Saved to this resume version
7. Optionally promoted to the master profile

A tailored resume edit should not automatically change the canonical master profile.

---

# 2. One-Page Resume Fit System

## 2.1 Hard one-page requirement

For resume formats that require one page, one page remains a hard output gate.

The system must not solve overflow by:

- Shrinking text to unreadable sizes
- Destroying spacing
- Compressing all bullets indiscriminately
- Removing evidence without informing the user
- Allowing content to spill onto a hidden second page

## 2.2 Recommended template strategy

### MVP recommendation

Use one carefully controlled template, or a very small family of approved templates, with fixed geometry:

- Page margins
- Font families
- Font sizes
- Heading hierarchy
- Tab stops
- Bullet indentation
- Line spacing
- Paragraph spacing
- Metadata alignment
- Section transition spacing

Content remains editable, but geometry stays within tested limits.

This makes live preview, one-page verification, and deterministic rendering much easier.

### Later expansion

Support importing a master resume DOCX and deriving a reusable layout profile from it:

- Fonts
- Heading styles
- Paragraph roles
- Bullet formatting
- Tab stops
- Date and location anchors
- Section spacing
- Page geometry

Imported layouts should be validated before they become selectable templates.

### Avoid initially

Do not start with a fully free-form WYSIWYG editor. Arbitrary dragging, resizing, and visual formatting would make deterministic DOCX output, ATS compatibility, and one-page verification much harder.

## 2.3 Page-fit meter

Show the user a live page-fit status:

- Fits comfortably
- Fits with limited remaining space
- Exactly filled
- Slight overflow
- Significant overflow
- Render verification unavailable

Possible supporting details:

- Estimated remaining lines
- Current page count
- Verified page count
- Most space-consuming section
- Most space-consuming bullets
- Spacing currently at minimum safe limits

## 2.4 Overflow resolution

When the resume exceeds one page, provide ranked suggestions rather than silently deleting content.

Suggested actions may include:

1. Remove the lowest-value optional bullet.
2. Tighten a verbose bullet while preserving evidence.
3. Remove a redundant skill already demonstrated in experience.
4. Hide less relevant coursework.
5. Remove a low-value project bullet.
6. Replace two similar bullets with one stronger bullet.
7. Reduce optional metadata.
8. Switch to a tested compact template variant.
9. Remove an entire low-relevance entry only with user approval.

Each suggestion should explain:

- Space recovered
- Relevance lost
- Evidence affected
- Why the content is considered lower priority
- Whether the change affects ATS matching
- Whether the change affects credibility or completeness

## 2.5 Fit decision authority

The system may recommend deletions, but the user should retain final authority over removing truthful experience.

Automatic removal may only occur when:

- The content was previously marked optional.
- The tailoring plan explicitly authorized its exclusion.
- The removal is recorded and reversible.
- The final review explains what was removed and why.

## 2.6 Exact preview contract

The preview should not be a rough HTML imitation if the downloaded document differs materially.

Preferred workflow:

1. Generate DOCX from structured resume data.
2. Render the DOCX to PDF using the approved renderer.
3. Verify page count.
4. Display the rendered PDF.
5. Download the same verified artifact.

This provides a stronger “what you see is what you download” guarantee.

---

# 3. Resume Quality Review

Add a diagnostic layer beside the resume preview.

## 3.1 Score categories

Avoid presenting one unexplained universal score.

Use grounded categories such as:

- ATS structure
- Role alignment
- Evidence strength
- Claim credibility
- Bullet quality
- Technical specificity
- Readability
- One-page and layout integrity
- Formatting consistency
- Requirement coverage

## 3.2 Explanation requirements

Every score should include:

- What is strong
- What is weak
- Supporting evidence
- Missing evidence
- Highest-value fixes
- Confidence in the assessment
- Why the issue matters for the selected job

## 3.3 Before-and-after comparison

Show:

- Original score
- Tailored score
- Category changes
- Accepted modifications
- Rejected modifications
- Remaining concerns
- Any content removed for page fit

## 3.4 Unsupported claims review

Flag:

- Claims without source evidence
- Skills listed but not demonstrated
- Metrics without provenance
- Technologies inferred but not explicitly supported
- Experience wording that overstates responsibility

The user should be able to open the source evidence for every flagged or approved claim.

---

# 4. Job Discovery Search and Filters

## 4.1 Search controls

Possible filters:

- Role or company search
- Keyword search
- City
- Region, province, or state
- Country
- Radius
- Remote
- Hybrid
- On-site
- Date posted
- Experience level
- Internship or co-op
- New graduate
- Role family
- Source
- Minimum match quality
- Saved
- Dismissed
- Applied
- Work authorization compatibility

## 4.2 Location integrity

Location must be structured and traceable.

Suggested posting fields:

- `raw_location`
- `city`
- `region`
- `country`
- `workplace_type`
- `location_source`
- `location_confidence`
- `is_location_confirmed`

The system must distinguish:

- Posting location
- Company headquarters
- Source default
- Inferred location
- Remote eligibility
- Unconfirmed location

Do not display a city such as Pittsburgh as confirmed unless the original posting supports it.

## 4.3 Debugging source errors

Preserve raw source values so incorrect normalized data can be traced back to:

- Source connector
- Company metadata
- Default location
- Duplicate resolution
- Parsing
- Normalization
- User preference fallback

---

# 5. Career Memory and Assistant

Create a career assistant with persistent, evidence-grounded memory.

It may answer questions such as:

- Which roles fit my current evidence?
- What are my strongest engineering families?
- Which missing skills appear most often?
- What should I build next?
- What is my likely market value?
- Which target companies are realistic?
- Which applications should I prioritize?
- What changed after my latest project or internship?
- Which resume version performed best?

Memory should include provenance for:

- Experience
- Projects
- Skills
- Coursework
- Approved claims
- Rejected claims
- Target roles
- Target companies
- Applications
- Interviews
- Feedback
- Resume versions
- Outcomes

The assistant must not silently convert an inference into a canonical profile fact.

---

# 6. Personalized Role Roadmaps

Generate role-readiness plans based on the user’s actual evidence and target jobs.

Inputs may include:

- Master profile
- Demonstrated skills
- Selected role families
- Target companies
- Saved job descriptions
- Repeated missing requirements
- Available weekly time
- Preferred learning style
- Existing projects that can be extended

Roadmaps should avoid generic advice such as “learn ROS.”

A stronger recommendation is:

> Add closed-loop velocity control to the existing robot, record the step response, integrate a ROS 2 command interface, and document measured performance.

Suggested roadmap elements:

- Current evidence
- Missing evidence
- Skill priority
- Project extension
- Learning resources
- Completion evidence
- Portfolio deliverable
- Resume claim unlocked
- Interview topics unlocked

---

# 7. Project Recommendations

Recommend projects that close specific evidence gaps.

The product should prefer:

1. Extending an existing project
2. Completing an unfinished project
3. Adding measurement and validation
4. Adding system integration
5. Creating a smaller original project
6. Starting a large new project only when justified

Project recommendations may be grouped by:

- Beginner
- Intermediate
- Advanced
- Time required
- Cost
- Hardware required
- Role family
- Evidence created
- Resume value
- Interview value

Each recommendation should state what hiring evidence it creates.

---

# 8. Application and Interview Loop

## 8.1 Application tracking

Track:

- Saved
- Planned
- Tailored
- Applied
- Rejected
- Interviewing
- Offer
- Withdrawn

Associate each application with:

- Job description
- Company
- Role family
- Resume version
- Cover letter version
- Tailoring decisions
- Missing requirements
- Application date
- Outcome

## 8.2 Interview preparation

Generate preparation from the exact job and submitted resume:

- Likely technical areas
- Resume claims likely to be questioned
- Project deep-dive questions
- Behavioral questions
- Company-specific preparation
- Missing fundamentals
- Mock interview sessions

## 8.3 Feedback loop

After interviews or rejections, capture:

- Questions asked
- Areas of difficulty
- Positive interviewer reactions
- Claims that attracted interest
- Missing evidence
- New project or learning recommendations
- Changes to future tailoring strategy

---

# 9. Product Differentiation

The product should not be positioned merely as a broader resume tailoring tool.

Stronger differentiation:

## Evidence-grounded engineering career system

Key ideas:

- Multidisciplinary engineering role coverage
- Evidence graph rather than flat skills
- Truth-preserving resume tailoring
- Transparent opportunity decisions
- Project recommendations tied to missing evidence
- One-page verified document generation
- Career memory with provenance
- Feedback from real outcomes
- Deterministic safeguards around LLM output

Possible positioning:

> An evidence-grounded career decision system for multidisciplinary engineers, connecting what they have actually built to the roles they should pursue, the gaps worth closing, and the applications they can truthfully submit.

---

# 10. Implementation Sequence

## Current work

Continue the existing Gemini role-classification workflow:

1. Typed role-classification contract
2. Deterministic validation
3. Safe fallback and cache
4. Resume-optimization integration behind a feature flag
5. Streamlit verification
6. Job-discovery integration only after optimization is stable

Do not begin the editor or roadmap implementation during this sequence.

## Phase A: Resume workspace foundation

- Structured resume state model
- Stable section and entry identifiers
- Manual field editing
- Bullet editing
- Reordering
- Hide and restore
- Version snapshots
- Exact preview refresh

## Phase B: One-page fit assistant

- Verified page count
- Overflow detection
- Space accounting
- Ranked removal and shortening suggestions
- User-approved fit resolution
- Before-and-after comparison

## Phase C: Resume quality review

- Deterministic formatting checks
- Semantic evidence review
- Category scores
- Prioritized fixes
- Grounded explanations

## Phase D: Job discovery improvements

- Structured location normalization
- Location source and confidence
- Search and filters
- Saved and dismissed states
- Work authorization and eligibility filters

## Phase E: Career system

- Career memory
- Target-role portfolio
- Repeated-gap analysis
- Project recommendations
- Role roadmaps
- Application tracking
- Interview preparation
- Outcome feedback

---

# 11. Design Principles

1. **Truth before optimization**  
   Never improve a resume by inventing evidence.

2. **One source of truth**  
   Structured resume data drives preview, DOCX, PDF, scoring, and tailoring.

3. **Exact output verification**  
   Preview the same artifact the user downloads.

4. **User authority**  
   AI proposes; the user approves material content changes.

5. **Reversibility**  
   Every removal, rewrite, and reorder can be undone.

6. **Deterministic guardrails**  
   LLM interpretation must pass validation before influencing the resume.

7. **Transparent decisions**  
   Explain why a job fits, why a bullet changed, and why content was removed.

8. **Evidence provenance**  
   Every important claim should point to its source.

9. **Scope discipline**  
   Store ideas now; implement them only when the current stage is stable.

10. **Original product identity**  
    Borrow broad interaction patterns, not another company’s exact design, text, assistant identity, stage names, templates, or visual system.

---

# 12. Open Product Decisions

- Should the MVP use one locked resume template or a small approved template family?
- When should imported master-resume layout extraction become available?
- Should users be allowed to manually override one-page limits for nontraditional applications?
- Which edits update only the tailored resume, and which can be promoted to the master profile?
- How should the editor display source evidence without overwhelming the user?
- Should the live preview regenerate after every keystroke or after a short debounce?
- What is the correct confidence language for semantic resume scores?
- Which job-location fields are required before a posting can be shown?
- How should career memory be corrected when an inference is wrong?
- Which product features belong in the MVP versus a later personal career operating system?

---

# 13. Immediate Non-Goals

The following are explicitly deferred while Gemini role classification is being completed:

- Full visual resume editor
- New Streamlit design system
- Career assistant
- Personalized roadmaps
- Project recommendation engine
- Resume score dashboard
- Job filter bar
- Application tracker
- Interview system
- Multiple arbitrary templates
- Free-form page-layout editing

These ideas are preserved here so they can be developed deliberately rather than introduced through uncontrolled scope expansion.
