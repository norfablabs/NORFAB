# NorFab Constitution

## Core Principles

### I. Surgical Changes and Simplicity First (NON-NEGOTIABLE)

Surgical scope and simplicity MUST be the first design and review criteria. Make the smallest
coherent change; prefer less code, direct linear execution, and existing patterns. Always reuse
existing methods and utilities where possible. Avoid unrelated refactoring, speculative features,
compatibility paths, and unnecessary infrastructure.

Implementation without new helpers is HIGHLY PREFERRED. Helpers, wrappers, abstractions, or layers
MUST have a concrete necessity; convenience or hypothetical reuse is insufficient. Use existing
shared task functions rather than add layers. Reviews MUST identify removable complexity.

Before altering existing application code, ask for confirmation unless that specific alteration
is already explicitly authorized. A feature request or plan does not authorize incidental edits;
do not ask again for an already approved change. Preserve public arguments and interfaces unless
change is explicitly requested. Simplicity MUST NOT weaken correctness, ownership, or honest errors.

### II. Explicit Contracts and Boundary Validation

Follow the [task model guide](../../docs/development/tasks_pydantic_models_guide.md). Keep explicit
input/output models in service model modules, accurate defaults and CLI aliases, and typed stable
results. Reuse task models in shells. Validate at the appropriate boundary without repeating
checks deeper in the implementation. Clarify uncertain schemas instead of guessing; adding models
MUST NOT silently change behavior. All detailed model conventions remain binding.

### III. Few, Simple Public-Client Tests

Use real public-client integration through existing fixtures whenever possible. Initial delivery
MUST favor a few simple core tests over exhaustive edge cases, permutations, or dependency tests.
Each test MUST cover one behavior; do not pack unrelated scenarios together or mirror internals.

Inputs, expected values, arguments, and plain payloads MUST be inline. Do not extract shared data
variables, constants, builders, or helpers to avoid repetition: simplicity MUST prevail over DRY.
Local result/resource variables needed for assertions and safe cleanup are allowed. Reuse existing
infrastructure fixtures. Follow the [testing guide](../../docs/development/norfab_developing_and_testing_framework.md)
for execution, classes, and markers; these explicit simplicity rules govern initial test scope.

Mutating Netbox tests MUST own distinct records/address space and clean up only their own data,
including after partial failure. Shared seeds may be read-only. Maintain the
[Netbox manifest](../../tests/netbox_data_manifest.json) only for Netbox records/address space,
not files or caches; tests using no Netbox data need no entry.

### IV. Concise, Audience-Focused Documentation

- Read the [documentation guide](../../docs/development/documentation_style_guide.md), related
  task pages, implementation, models, and shell commands before writing. Verify examples and links.
- Identify the audience. User guides MUST explain what the task does, why/when to use it, and
  how to use it. Omit internal details unless essential. Overviews describe the task, not examples;
  avoid test terminology such as "resources you own". Developer docs may explain implementation.
- Prose MUST use periods instead of semicolons and plain ASCII hyphens (`-`) instead of en/em
  dashes. Preserve punctuation required by code, commands, URLs, and identifiers.
- Each task MUST have its own page: purpose, output, examples, essential notes, command reference,
  then Python API reference last. No Inputs section. Keep prose short and task-specific.
- Examples MUST use CLI, Python, FastAPI, and MCP Markdown tabs. Follow existing pages:
  multiline `client.run_job(...)` for Python; `nf#` commands for CLI; Python `requests` AND `curl`
  for FastAPI; natural-language prompts naming the NorFab service/task tool for MCP, never raw
  protocol payloads or internal tool identifiers. Show supported interfaces only; state limitations.
- Command references MUST use dotted paths: `nf# man tree nornir.restconf.get`. Check names,
  arguments, payloads, output shapes, and code-fence languages against actual behavior.
- Google-style task docstrings MUST cover every argument, result, behavior, limitation, and error.
  Fix spelling in changed text/names. Logs and `job.event` messages start lowercase; use `severity`.
- Every feature or existing-code change MUST have a short numbered one-line note in
  [the changelog](../../docs/norfab_changelog.md), under the latest `(draft)` release and appropriate
  FEATURES/BUGS/ENHANCEMENTS category. If no draft exists, create the next patch release marked
  `(draft)`. Follow existing release patterns. Leave published releases unchanged.
- Classify release notes against previously released functionality. FEATURES covers new capabilities.
  CHANGES covers changes to existing released features or workflows. BUGS covers fixes and
  ENHANCEMENTS covers improvements to existing functionality. Refinements made while developing
  a new unreleased feature MUST be folded into its FEATURES entry, not logged as separate changes,
  fixes, or enhancements. Describe the delivered result, not its development history.

### V. Preserve Architecture and Honest State

Preserve existing worker/client boundaries and accepted architecture decisions. Follow the
[NFWeb guide](../../docs/development/nfweb_developer_guide.md), including its architecture,
contracts, frontend stack, security policy, retention, and required verification. Its detailed
constraints remain binding unless explicitly replaced by an architecture decision.

Failures MUST remain visible; unknown values remain unknown. Never fabricate operational data.
Consult pyproject.toml for dependencies, Python support, entry points, and tooling configuration.

## Engineering Constraints

Read [AGENTS.md](../../AGENTS.md) and applicable linked guides before editing. Their detailed rules
remain binding; compression here does not repeal them. Read ADR status/amendments rather than
assume proposals are implemented.

Keep durable Spec Kit artifacts together under docs/development/specs/<NNN-feature-name>/:
spec.md, plan.md, research.md, data-model.md, quickstart.md, contracts/, checklists/requirements.md,
and generated tasks.md. Keep specification/checklist separate; select the folder using
feature_directory in .specify/feature.json and link spec.md from mkdocs.yml. State acceptance and
implementation status separately. ADRs record separate architecture decisions.

Temporary ad hoc plans/reports/notes belong in ignored private/; create no unrelated root tasks/,
plans/, or reports/ folders. Existing Docker-generated reports retain their documented location.

## Development Workflow and Quality Gates

Preserve unrelated working-tree changes. Use uv/Invoke and the
[Invoke decisions](../../docs/development/adr/adr_invoke_developer_automation.md) and
[Docker guide](../../docker/norfab-docker-tests/README.md); keep dependencies/lockfile synchronized
and configuration canonical. Protect secrets/private keys, isolate runtime artifacts, and clean
up distributed resources on success, failure, and interruption.

Run focused checks appropriate to the change and docs builds when applicable. Do not suppress
findings merely to pass. Inspect current Docker reports/JUnit: individual suite exit status alone
is not proof of success. Follow guide-specific commands and verification, including NFWeb browser
checks when required. Report evidence, failures, unavailable prerequisites, and limitations.

## Governance

Amendments require maintainer approval, rationale, affected rules/guides, compatibility implications,
version/date updates, and a temporary Sync Impact Report removed before commit. Preserve applicable
rules unless replacement is explicitly authorized; surface conflicts rather than weaken rules.
Review every change for compliance and evidence. Dependent workflows read this constitution live.

Use MAJOR for incompatible removals/redefinitions, MINOR for expanded principles, PATCH for wording
without semantic change. Version 3.6.0 classifies release notes against previously released functionality.

**Version**: 3.6.0 | **Ratified**: 2026-11-06 | **Last Amended**: 2026-11-07
