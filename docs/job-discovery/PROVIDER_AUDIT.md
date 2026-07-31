# Official provider audit

Audit date: 2026-07-24. This audit covers public, official mechanisms suitable
for retrieval of published jobs without candidate data. No provider receives a
resume, profile, evidence, scoring data, or authenticated user session.

## Toronto and Greater Toronto Area coverage

The unified registry now records typed geography metadata separately from role
fit and scoring. `toronto_gta_presence` is set only when an official office or
official job-location reference identifies Toronto or an adjacent GTA locality;
remote Canada eligibility alone is insufficient.

Geographic authority uses typed `GeographicEvidenceReference` records. Only
`official_office`, `official_hiring_presence`, and `official_job_location`
evidence with Canada and an approved GTA locality can establish Toronto/GTA
presence. Remote eligibility, Ontario-only context, and explanatory prose
cannot establish it.

Audit fixture references are POSIX-relative names beneath
`tests/fixtures/job_sources/company_audits`. The registry loader resolves them
against that fixed root, rejects traversal, absolute and drive-relative paths,
requires `.json` regular files, enforces a bounded size, and parses them as
data without executing content. Deterministic source priority is ordered by
priority tier, GTA relevance, then source ID; it is not used for scoring, feed
ordering, or scheduling.

### Enabled Toronto/GTA sources

- **Waabi** — official [careers page](https://waabi.ai/careers) links to the
  global Lever board `waabi`. The audited board lists Toronto engineering,
  embedded, autonomy, ML, perception, verification, and systems roles.
- **Tenstorrent** — official [software careers page](https://tenstorrent.com/careers/software)
  lists its North York office at 150 Ferrand Drive and links published roles to
  the Greenhouse board `tenstorrent`. The board includes Toronto AI hardware,
  compiler, embedded, silicon, and verification roles.

These two sources use the existing Lever and Greenhouse connectors. Geography
does not add evaluator points or alter fit policy; it remains source metadata
for future prioritization and existing location eligibility boundaries.

### Deferred Toronto/GTA queue

- **Cohere** — `DEFERRED_SOURCE_MECHANISM`: official careers identifies a
  Toronto office but delegates open roles to Ashby, which is not an approved
  connector in this checkpoint.
- **MDA Space** — `DEFERRED_SOURCE_MECHANISM`: official careers identifies a
  Brampton engineering presence but delegates Canada opportunities to UKG /
  UltiPro, which is not an approved connector.
- **Magna International** — GTA relevance retained through Aurora headquarters;
  retrieval authority remains unaudited.
- **Untether AI** — Toronto AI-hardware candidate retained for an identity and
  source-mechanism audit; no approved authority is configured.
- **General Motors** — source mechanism and GTA engineering presence remain
  unaudited.
- **Bombardier** — Toronto/GTA engineering presence was not established in the
  bounded audit.
- **Amazon, Meta, Google, Microsoft, NVIDIA, AMD, IBM, Intel, Siemens, GE
  Vernova, Rockwell Automation, Caterpillar, Apple, Salesforce, and Oracle** —
  retained as disabled global candidates; no new Toronto/GTA flag is asserted
  here without a source-specific official office and retrieval audit.

The existing global candidates remain disabled until their own approved source
authority and geographic evidence are completed. No Toronto-specific pipeline
or crawler is introduced.

## Rocket Lab first-party employer source

- Audit date: 2026-07-25; the source-plan audit version remains `2026-07-24.1`
  until the next registry version bump.
- Canonical employer careers entry: `https://rocketlabcorp.com/careers/`; the
  legacy `https://www.rocketlabusa.com/careers/` entry redirects to the
  `rocketlabcorp.com` employer host.
- Exact first-party listing/index URL: `https://rocketlabcorp.com/careers/positions/`.
- Navigation host: `rocketlabcorp.com`.
- Redirect host: `www.rocketlabusa.com` -> `rocketlabcorp.com`.
- Allowed listing path: `/careers/positions/`.
- Allowed detail path: `/careers/positions/<employer-slug>/`.
- Robots decision: `allow`, subject to revalidation before any future refresh.
- Listing discovery: `static_index`.
- Detail fetch: `static_http`.
- Detail extraction contract: `json_ld_then_html` is recorded for the later
  retrieval checkpoint; no extraction implementation is added here.
- Stable identity authority: the employer detail URL slug suffix, retained with
  the same-host canonical detail URL.
- Canonical detail URL authority: the same-host canonical detail URL on the
  employer detail page.
- Listing authority: `rocketlabcorp.com` listing/index pages.
- Detail-content authority: `rocketlabcorp.com` employer detail pages; the
  bounded audit observed title, location, type, and posting content on that
  host without relying on a third-party data API.
- Application URL authority: the employer detail page links the terminal Apply
  target to `https://job-boards.greenhouse.io/rocketlab/jobs/<job-id>`.
  `job-boards.greenhouse.io` is explicitly approved only as an application
  target, with the `/rocketlab/jobs/<job-id>` path shape. It is not a
  navigation, redirect, crawl, or provider retrieval authority.
- Stable identity relationship: the first-party detail URL contains the
  employer slug, while the terminal Greenhouse URL contains the numeric
  application job ID. The two are linked by the employer detail page and are
  recorded separately rather than merged by title similarity.
- Completeness boundary: the index exposes bounded `Load more`; the audit
  fixture records termination after the bounded action and repeated-card
  deduplication.
- Data authority: employer host. Greenhouse is observed only for the terminal
  application target; no Greenhouse, Lever, Workday, or unaudited API authority
  supplies the listing/detail content in the bounded evidence.
- Competing provider authority: none. No provider connector is configured for
  Rocket Lab.
- Redacted fixtures: `tests/fixtures/job_sources/company_audits/rocket_lab_index.json`
  and `rocket_lab_detail.json`; complete job descriptions are not stored.
- Decision: approved as a first-party employer-host source for Checkpoint A
  audit purposes only. Retrieval and extraction remain Checkpoint B work.

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

### Active company board identities

These are the exact provider authorities approved for the active cohort. The
employer careers entry is the audit evidence linking each company to the
provider board; the provider board remains the sole retrieval authority.

| Company | Connector | Exact board token | Lever region | Audit state |
| --- | --- | --- | --- | --- |
| Anthropic | Greenhouse | `anthropic` | — | approved |
| Anduril | Greenhouse | `andurilindustries` | — | approved |
| Palantir | Lever | `palantir` | `global` | approved |
| Zoox | Lever | `zoox` | `global` | approved |
| SpaceX | Greenhouse | `spacex` | — | approved |
| Relativity Space | Greenhouse | `relativity` | — | approved |
| Figure | Greenhouse | `figureai` | — | approved |
| Waabi | Lever | `waabi` | `global` | approved |
| Tenstorrent | Greenhouse | `tenstorrent` | — | approved |

Each row is represented by a typed `provider_configuration` in
`config/approved-job-sources.json`; no board token is inferred from a source
ID, company name, or URL. Rocket Lab is intentionally absent from this table
because it has no provider authority and is audited separately above.

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

## Batch 3.5 first-party runtime limitations

Rocket Lab is compiled as `FIRST_PARTY`, not Greenhouse. Static retrieval uses
the audited employer index and `/careers/positions/...` detail paths. JSON-LD
is bounded and deterministic; HTML fallback is declarative and excludes
scripts, styles, hidden content, arbitrary anchors, and full-document text.
Greenhouse application URLs are terminal provenance and are never retrieved.

Browser fallback is allowed only after static `browser_required` for an
explicitly audited first-party plan. It uses an isolated context, no cookies,
authentication, profiles, extensions, downloads, uploads, or application
navigation, plus bounded requests/actions/render time and host/path/resource
allowlisting. Static HTTP validates destination IPs; browser execution retains
a DNS TOCTOU residual risk because the browser owns socket resolution. The
mitigation is interception and rejection of unapproved navigation, redirects,
frames, XHR/fetch, scripts, popups, and application hosts. This is not claimed
to be equivalent to static SSRF controls. Playwright `1.55.0` is a direct
 dependency; Chromium installation is explicit and separate from Python package
installation. The local real-browser gate was externally verified with managed
Chromium 140.0.7339.16 (build v1187); three controlled-local tests passed,
including JavaScript-rendered listing/detail extraction. Browser fallback
remains first-party-only, static-first, bounded, and subject to the same robots
and source-plan policy. Greenhouse and Lever never use it.
