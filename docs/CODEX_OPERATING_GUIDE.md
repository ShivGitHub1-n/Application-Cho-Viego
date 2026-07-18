# Codex operating guide

Use this procedure to continue Application Viego work without reconstructing
repository state or accidentally broadening a stage's scope. Pair it with
[PROJECT_STATUS.md](PROJECT_STATUS.md) and [ROADMAP.md](ROADMAP.md).

## Canonical paths

Repository:

```text
C:\Users\Shiv\Documents\Downloads\Application-viego-resume-ui-stabilization
```

Python:

```text
C:\Users\Shiv\AppData\Local\Programs\Python\Python311\python.exe
```

When a task specifies this interpreter, do not substitute `python`, `py`,
another virtual environment, or another installed version.

## Standard Codex launch

Run from PowerShell:

```powershell
codex `
  --cd "C:\Users\Shiv\Documents\Downloads\Application-viego-resume-ui-stabilization" `
  --sandbox workspace-write `
  --ask-for-approval never
```

If the interpreter directory is not readable inside the session, add it with:

```text
/sandbox-add-read-dir C:\Users\Shiv\AppData\Local\Programs\Python\Python311
```

## Standard offline suite

```powershell
& "C:\Users\Shiv\AppData\Local\Programs\Python\Python311\python.exe" -m pytest -q -m "not gemini_integration and not job_source_integration"
```

The marker expression intentionally excludes live Gemini and live job-source
integration tests. Do not weaken tests or production behavior to make an
environment-specific run pass.

## Git procedure

- Verify the repository root, `git status --short`, active branch, and HEAD
  before editing.
- Never silently switch branches. If a requested branch is not active, report
  the mismatch and follow the task's explicit authority.
- Never push unless the user explicitly requests it.
- Do not commit until the user requests a commit and the stated acceptance
  gates pass.
- Inspect the staged file list and staged diff before committing.
- Never use `git add .` or `git add -A` for checkpoint commits. Stage only the
  reviewed paths explicitly.
- Exclude generated resumes, reference resumes, application databases,
  caches, credentials, secrets, environment files, and Microsoft Word lock
  files from commits unless a task explicitly identifies a sanitized,
  reviewed source asset.
- Preserve unrelated user changes in a dirty worktree.
- A Codex sandbox may be unable to write `.git`; an approved commit may need
  to be completed from normal PowerShell.

Recommended pre-edit audit:

```powershell
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git status --short
```

Recommended pre-handoff audit:

```powershell
git diff --check
git status --short
git diff --stat
git diff --name-only
```

## Testing procedure

1. Run focused tests for the behavior being changed.
2. Run affected domain, application, infrastructure, API, frontend, and
   regression suites.
3. Run the full offline suite last.
4. Perform Word-dependent pagination and visual verification in normal
   interactive Windows when sandboxed COM fails.
5. Do not alter production behavior to conceal Word COM, LibreOffice, network,
   filesystem, or sandbox limitations. Report the exact typed failure.
6. Run `git diff --check`.
7. Run Ruff on changed Python and test files.
8. Run targeted mypy on changed typed modules.

Use the canonical Python executable for pytest, Ruff, mypy, and repository
scripts. Live integration tests require separate explicit authority and
configuration; they are not part of the standard offline suite.

## Implementation-prompt contract

Every implementation prompt should state:

- the canonical repository path;
- the required branch;
- the exact scope and expected deliverables;
- protected systems and behavior that must not change;
- authority boundaries between domain, application, ports, infrastructure,
  API, and UI;
- truthfulness, evidence, provenance, and provider-call constraints;
- controlled acceptance cases and regression requirements;
- the exact Python executable and exact test command;
- the required final-report fields;
- commit and push policy; and
- the exact recommended model configuration, including model, reasoning
  level, and Fast mode state.

Prompts should distinguish diagnosis from implementation, exact page
verification from estimation, committed behavior from uncommitted work, and
accepted behavior from experimental behavior.

## Durable model-budget policy

Do not record transient weekly usage percentages in repository
documentation.

Use **GPT-5.6 Sol with Extra High reasoning and Fast mode Off** for:

- architecture;
- ranking and search design;
- evidence-safe generation;
- role-classification repair;
- editor domain boundaries;
- chatbot tool architecture; and
- difficult cross-system regression repair.

Use **GPT-5.6 Sol with High reasoning and Fast mode On** for:

- documentation;
- test additions within an established architecture;
- Git and file audits;
- packaging;
- narrow deterministic refactors; and
- UI wording and straightforward frontend work.

Use Extra High only where its cost is justified by architectural ambiguity,
truthfulness risk, search/ranking complexity, or cross-system impact.

## Systems disabled or deferred during resume stabilization

Unless the active roadmap stage explicitly requires them, keep unrelated LLM
generation, cover-letter generation, role classification, and Job Discovery
disabled while testing resume stabilization. In particular:

- run composition acceptance with all LLM flags disabled;
- do not call Gemini or another provider unless the stage explicitly owns
  provider behavior;
- do not change cover-letter prompts or behavior during resume-only work;
- do not use role-family classification as the primary composition authority;
  and
- do not enable or alter Job Discovery sources or ranking during resume-only
  work.

The subsystems may already have implementation and tests. “Disabled or
deferred” here is an operating boundary for the active stabilization stage,
not a claim that every subsystem is absent from the repository.
