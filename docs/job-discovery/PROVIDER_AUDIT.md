# Official provider audit

Audit date: 2026-07-24. This audit covers public, official mechanisms suitable
for retrieval of published jobs without candidate data. No provider receives a
resume, profile, evidence, scoring data, or authenticated user session.

## Greenhouse

- Official mechanism and owner: Greenhouse Job Board API, owned and documented by Greenhouse: https://developers.greenhouse.io/job-board.html
- Access or authentication requirements: Published Job Board GET endpoints are public and do not require authentication; application submission is outside this feature and requires authentication.
- Public-job access boundary: The board token returns the organization's published job posts; internal/prospect behavior follows the Job Board API contract.
- Stable job ID authority: The response `id` is the stable job-post identifier; `internal_job_id` identifies the underlying job and is retained only as source payload data.
- Description quality: `content=true` returns the full published description and board-managed content.
- Location authority: The provider's `location.name` field and published office fields.
- Application URL authority: The provider's `absolute_url` field, canonicalized without changing its authority.
- Posted/update timestamp authority: `updated_at` is authoritative in list/detail records; `first_published` is authoritative only from the official job-detail response. The list adapter does not invent `posted_at`.
- Pagination: The published jobs list documents no paging cursor or page-size control; the adapter makes one bounded request and declares pagination unsupported.
- Supported query filters: Only the documented `content=true` option is used. Title, sector, location, arrangement, level, employment type, and date filters are local or unsupported according to capabilities.
- Rate-limit or retry guidance: The adapter uses the shared bounded retry policy for transient transport/server failures and maps rate limiting to a structured source error.
- Availability-check behavior: A direct official job-detail GET verifies identity and published state when the source returns status information; a missing posting is unavailable, not a transport success.
- Offline fixture testability: `tests/fixtures/job_sources/greenhouse_valid.json`, `greenhouse_malformed_record.json`, and `greenhouse_malformed_envelope.json` cover valid, record, and envelope behavior.
- Terms or access concerns: Public GET access is documented; no application submission, authenticated data, or scraping is used.
- Decision: approved
- Exact reason for the decision: The official public Job Board API supplies stable IDs, descriptions, location authority, official URLs, timestamp fields, and an offline-testable access boundary. Its missing list pagination/filter controls are explicitly declared and handled locally.
- Date accessed: 2026-07-24

## Lever

- Official mechanism and owner: Lever public Postings API and official Lever developer documentation: https://hire.lever.co/developer/support and https://hire.lever.co/developer/documentation
- Access or authentication requirements: The public Postings API exposes published company postings without an authenticated candidate session. Lever's private Data API requires API-key/OAuth authorization and is not used for this feature.
- Public-job access boundary: Only published postings intended for the public job site are in scope; internal, closed, draft, rejected, and confidential private records are not requested.
- Stable job ID authority: The provider `id` field is the posting UID.
- Description quality: Published posting description fields are returned by the public posting endpoint; `descriptionPlain` is preferred when present.
- Location authority: The provider categories location field.
- Application URL authority: The provider `hostedUrl` field, canonicalized without changing its authority.
- Posted/update timestamp authority: The current public fixture contract does not provide a verified posted timestamp, so `posted_at` remains `None`. A provider `updatedAt` field is accepted only as `source_updated_at`; `createdAt` is never used as posted time.
- Pagination: The official Lever list contract documents bounded `limit` and opaque `offset` pagination; the adapter uses a bounded skip/offset compatibility form for the public endpoint and stops on a short page or missing next cursor.
- Supported query filters: The adapter requests only the public postings list and pagination controls. Title, sector, location, arrangement, level, employment type, and date filters are local or unsupported according to capabilities.
- Rate-limit or retry guidance: Lever documents 429 responses and recommends bounded exponential retry; the shared adapter retries at most three attempts and never loops unboundedly.
- Availability-check behavior: A direct region-specific posting GET checks identity and published status; 404 is unavailable and transport/rate-limit errors remain errors.
- Offline fixture testability: `tests/fixtures/job_sources/lever_global_page.json`, `lever_global_page_2.json`, `lever_eu_page.json`, and `lever_malformed_record.json` cover global/EU, paging, and malformed records.
- Terms or access concerns: Only official public postings mechanisms are used. The private authenticated Lever Data API is explicitly outside this feature.
- Decision: approved
- Exact reason for the decision: Lever provides an official public published-posting boundary, stable posting IDs, official hosted URLs, location/description authority, documented bounded pagination, and region-specific offline-testable behavior.
- Date accessed: 2026-07-24

## Ashby

- Official mechanism and owner: Ashby `jobPosting.list` and `job.list` APIs, owned and documented by Ashby: https://developers.ashbyhq.com/reference/jobpostinglist and https://developers.ashbyhq.com/reference/joblist
- Access or authentication requirements: The official documentation requires the `jobsRead` permission and Basic authentication; this project has no approved employer credential or source configuration for Ashby.
- Public-job access boundary: `listedOnly=true` can constrain job postings to listed jobs, but the authenticated endpoint still requires an employer-authorized integration.
- Stable job ID authority: The official endpoint supplies job/posting identifiers, but no adapter is authorized in this batch.
- Description quality: Not implemented or accepted for this batch.
- Location authority: The official endpoint documents location filters, but no adapter is authorized for this batch.
- Application URL authority: Not implemented or accepted for this batch.
- Posted/update timestamp authority: The job API documents created/opened timestamps, but no adapter is authorized for this batch.
- Pagination: The official API documents opaque cursor pagination and bounded limits.
- Supported query filters: Official location, department, listed-only, and job-board controls exist; they do not establish an approved public access boundary for this product.
- Rate-limit or retry guidance: No approved runtime configuration exists for this batch.
- Availability-check behavior: Not implemented.
- Offline fixture testability: No fixture path is authorized because no Ashby adapter is approved.
- Terms or access concerns: Employer-authorized `jobsRead` access and unknown operator authorization make this unsuitable for the current profile-free public retrieval boundary.
- Decision: deferred
- Exact reason for the decision: The official mechanism requires authenticated employer permission and no approved credential or source configuration exists; expansion is deferred rather than implemented or scraped.
- Date accessed: 2026-07-24

## SmartRecruiters

- Official mechanism and owner: SmartRecruiters Posting API, owned and documented by SmartRecruiters: https://developers.smartrecruiters.com/docs/posting-api and https://developers.smartrecruiters.com/reference/v1listpostings
- Access or authentication requirements: The official Posting API requires API-key authentication; no approved SmartRecruiters key or employer authorization exists for this batch.
- Public-job access boundary: The API describes postings made public through SmartRecruiters, but access remains an authenticated customer API boundary.
- Stable job ID authority: The official posting response supplies a job-ad identifier; no adapter is authorized for this batch.
- Description quality: Not implemented or accepted for this batch.
- Location authority: Official location type, country, region, and city filters are documented; no adapter is authorized for this batch.
- Application URL authority: Not implemented or accepted for this batch.
- Posted/update timestamp authority: Not established for an approved adapter.
- Pagination: The official endpoint documents bounded limit and offset/page controls.
- Supported query filters: Official title/location query, destination, location type, country, region, city, department, and job-ad controls exist.
- Rate-limit or retry guidance: No approved runtime configuration exists for this batch.
- Availability-check behavior: Not implemented.
- Offline fixture testability: No fixture path is authorized because no SmartRecruiters adapter is approved.
- Terms or access concerns: API-key-only customer access is outside the approved public, profile-free connector boundary; generic scraping is prohibited.
- Decision: deferred
- Exact reason for the decision: The official mechanism is authenticated customer API access without approved authorization, so expansion is deferred and no connector is implemented.
- Date accessed: 2026-07-24

## Expansion decision

Greenhouse and Lever remain the only approved and implemented connectors. No
additional provider meets every mandatory access, timestamp, URL, availability,
pagination, and offline-testability requirement with an approved configuration
in this batch. LinkedIn, Indeed, generic ATS HTML, search engines, browser
scraping, reverse-engineered endpoints, and authenticated user-session scraping
are not candidates and are not implemented.

