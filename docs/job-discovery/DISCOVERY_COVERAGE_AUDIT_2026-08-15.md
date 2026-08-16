# Job Discovery coverage audit — 2026-08-15

## Scope

This audit used the production approved-source registry, connector
implementations, the canonical reviewed profile `shiv-arora`, the application
SQLite database, and read-only requests to the approved employer/provider
surfaces. It did not add postings, enable deferred companies, relax eligibility,
change scoring, or use unapproved aggregators. Counts below are point-in-time
observations and sector counts overlap for genuinely multidisciplinary titles.

## Findings

The active registry contains ten companies: nine Greenhouse/Lever boards and
one audited Rocket Lab first-party source. All ten source definitions include a
software tag, while only subsets include embedded, robotics, controls,
mechanical, testing, or systems tags. Those tags are descriptive metadata and
are not used to select runtime sources, so they did not suppress roles.

The nine reachable provider boards returned 5,991 current records:

| Source | Records | Examples of exposed breadth |
| --- | ---: | --- |
| Anduril | 2,205 | embedded flight software, systems integration, electrical, FPGA test, GNC, robotics |
| Anthropic | 441 | data-center mechanical/electrical, silicon, hardware systems architecture |
| Figure | 127 | perception, electrical, robot operations, manufacturing |
| Palantir | 308 | software and autonomous-systems roles |
| Relativity Space | 362 | controls, mechanical automation, avionics test, integration/test |
| SpaceX | 2,115 | avionics systems, electrical, mechanical, controls, firmware, test |
| Tenstorrent | 131 | AI hardware, RTL/design verification, PCIe validation |
| Waabi | 58 | electrical, motion planning/control, perception, autonomy |
| Zoox | 244 | embedded software, systems verification/validation, manufacturing, perception |

Rocket Lab's safe production path first exposed two implementation defects: the
approved trailing-slash index URL was rejected as a normalization change, and
the synchronous connector opened each request on a new event loop even though
the HTTP client pools connections. After correcting those generic boundaries,
the official index returned HTTP 403 on the audit date. The source therefore
remains a sanitized `detail_fetch_failed` outcome; it is not treated as an
empty or successful source and no browser/crawling permission was widened.

The stored database already contained 3,005 normalized jobs, including 332
hardware/electrical-titled, 382 mechanical/manufacturing-titled, 241
systems/integration/test-titled, 135 robotics/autonomy-titled, and 67
embedded/firmware-titled records. Deduplication and discovered-job persistence
therefore retained multidisciplinary inventory. The skew occurred primarily
before feed construction:

- the canonical profile's generated search vocabulary had only two embedded
  aliases and three robotics/mechatronics aliases, with no hardware,
  electrical, systems integration, hardware test, avionics, FPGA, mechanical,
  manufacturing, controls, sensor integration, or GNC breadth;
- the local title filter searched full descriptions, admitting postings such
  as recruiting or unrelated engineering roles when boilerplate mentioned a
  target title;
- the local level filter also searched full descriptions, so the profile's
  entry/intern preference rejected an otherwise unlabelled role whenever its
  description mentioned a senior, staff, or lead colleague;
- Software Explore included the bare term `engineer`, accepting 2,943 of 3,005
  stored jobs in a direct audit; Hardware and Testing also scanned generic
  description prose, accepting 2,600 and 2,235 respectively rather than useful
  title-bounded sector sets;
- the scheduled source-refresh CLI hardcoded `Software Engineering`, an
  implicit software-first inventory boundary.

Greenhouse returned each full board in one provider page. Lever pagination is
bounded to 20 pages of 100 and the current approved Lever boards were well below
that limit. The observed skew was therefore not caused by current Lever page
exhaustion. Source-qualified identity, deterministic deduplication, SQLite
upserts, and backend feed ordering did not preferentially remove hardware jobs.

## Corrected contracts

The centralized search taxonomy now supplies specific, bounded provider terms
for software, data, AI, vision, robotics/autonomy, embedded/firmware,
hardware/systems integration, controls/mechatronics, and testing/verification.
Profile-derived search terms include evidence-gated mechanical, manufacturing,
controls, and test titles only when reviewed profile content supports them.

Local title and sector filtering now evaluates posting titles rather than
description boilerplate. It retains mixed titles such as embedded software,
robotics software integration, software/hardware test, GNC, and sensor
integration. Software still retrieves software roles, but no sector uses the
bare word `engineer` as its discriminator.

Against the same 5,991 live provider titles, the corrected Explore taxonomy
matched 985 software, 24 data, 64 AI/ML, 20 vision, 150 robotics/autonomy, 92
embedded/firmware, 957 hardware/systems integration, 101 controls/mechatronics,
and 207 testing/verification records. These overlapping counts represent
available source breadth, not quotas or ranking manipulation.
