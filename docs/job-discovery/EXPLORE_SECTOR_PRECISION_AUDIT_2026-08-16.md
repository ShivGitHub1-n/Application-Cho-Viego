# Explore sector precision audit — 2026-08-16

## Scope and evidence

This audit covers sector membership only. It does not change provider pagination,
eligibility, preference weighting, Tailored fit scoring, feed ordering, or job
persistence. The evidence set was the latest persisted Hardware / Systems
Integration Explore run for `shiv-arora`, its source outcomes, and the 3,005
current normalized jobs stored from approved sources. Posting descriptions and
candidate/profile content were not emitted during the audit.

The visible 2,495-role feed was produced on 2026-08-15 before the converged
title-only matcher was running. Its retrieval admitted 2,570 of 5,991 provider
records because the former local matcher searched descriptions and company
context; deterministic normalization/deduplication then produced 2,495
recommendations. The feed is persisted by run and remains visible until the
sector is refreshed.

Applying the converged title-only matcher to those same 2,495 records yields
619 Hardware / Systems Integration members. The precision rules in this change
yield 634: 31 broad-alias matches are removed and 46 explicit PCB/PCBA, harness,
instrumentation, reliability, manufacturing-automation, power-system, or
flight-controls titles are newly recognized. The resulting count is higher
than 619 because the desired physical-system aliases add more legitimate roles
than the conditional rules remove; it is not a quota or cap.

## Root cause

The remaining false positives were caused by treating the provider-query term
list as the final sector classifier. Flat terms such as `Systems Engineer`,
`Integration Engineer`, `Test Automation Engineer`, `Automation Engineer`, and
`Platform Engineer` have useful retrieval recall but insufficient membership
precision. They admitted HPC/data-center systems, network software integration,
generic test automation, and non-controls automation/platform roles based on a
single ambiguous phrase.

Provider pushdown was also trusted as final sector membership when a connector
declared sector support. Current approved Greenhouse, Lever, and first-party
connectors do not declare that capability, but the contract allowed a future
provider's description or metadata semantics to bypass the canonical matcher.

## Corrected membership contract

Provider terms remain broad enough to retrieve candidates. Every returned
Explore record is then checked by the local, deterministic, title-only sector
authority, even when a provider reports that it pushed down a sector filter.
Descriptions and company/product identity never independently establish
membership.

- Software requires explicit software/developer/backend/frontend/full-stack,
  SRE, DevOps, or a platform-engineer title without a physical-engineering
  qualifier.
- Hardware accepts direct electrical, electronics, mechanical, hardware,
  avionics, FPGA/ASIC/silicon, PCB/PCBA, harness/wiring, instrumentation,
  manufacturing/test, sensor-integration, vehicle/power-system, and flight-
  controls evidence.
- Ambiguous systems, integration, reliability, and test-automation titles need
  explicit systems-integration wording or an adjacent physical-system title
  signal. Software/network/cloud/platform/HPC context blocks ambiguous-only
  membership, while explicit mixed titles remain eligible. Bounded physical
  qualifiers such as Starship, booster, heatshield, wireless, air defense,
  maritime, and C3 preserve legitimate integration and systems roles.
- Controls accepts controls, mechatronics, motion-control, GNC, robot-control,
  and manufacturing-automation titles. A generic automation title needs an
  industrial/manufacturing/robotics/control qualifier. Motion planning remains
  Robotics / Autonomous Systems rather than collapsing into Controls.
- Embedded/Firmware, Robotics/Autonomy, and Testing/Verification retain their
  direct title signals and intentional overlaps with explicit software,
  hardware, or verification evidence.

Against all 3,005 stored approved-source jobs, representative title-only counts
before/after this precision pass are: Software 745/745, Robotics 112/112,
Embedded 81/81, Hardware 650/672, Controls 46/45, and Testing 126/126. Sector
counts overlap for multidisciplinary titles.

Examples removed from Hardware include `Sr. High Performance Computing (HPC)
Systems Engineer`, `Network Software Integration Engineer`, `Mission
Integration Engineer, Network and Infrastructure`, generic `Test Automation
Engineer`, and `Platform Systems Engineer; Sensing and Perception, Maps and
Localization`. Examples preserved include `Embedded Software Engineer - Power
Systems`, `Software Engineer, Hardware Test & Automation`, `Robotics Software
Integration Engineer`, `Firmware Integration Engineer`, physical `Integration
Engineer (Starship)` and heatshield roles, `Wireless Systems Engineer`, and
RF-silicon software roles.
