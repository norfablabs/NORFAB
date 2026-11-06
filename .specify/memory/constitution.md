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
infrastructure fixtures. Follow the [testing guide](../../docs/development/testing/norfab_testing_framework.md)
for execution, classes, and markers; these explicit simplicity rules govern initial test scope.

Mutating Netbox tests MUST own distinct records/address space and clean up only their own data,
including after partial failure. Shared seeds may be read-only. Maintain the
[Netbox manifest](../../tests/netbox_data_manifest.json) only for Netbox records/address space,
not files or caches; tests using no Netbox data need no entry.

### IV. Accurate Documentation and Operational Messages

Before writing or updating documentation, identify its primary audience: users or developers.
Language, examples, and depth MUST suit that audience. User-facing documentation MUST focus on
how to use a feature, what to use it for, and why to choose it. Implementation details MUST be
omitted unless essential to using the feature or understanding a limitation; keep any necessary
details minimal. Developer documentation may explain implementation, contracts, and design
rationale needed to maintain or extend the project.

Follow the [documentation guide](../../docs/development/documentation_style_guide.md). Keep user
instructions concise and verified against actual behavior. Google-style task docstrings MUST
cover arguments, results, behavior, limitations, and errors. Task pages omit Inputs and end with
the API reference. Correct spelling in changed text/names. Logs and job.event messages MUST start
lowercase; use severity for event severity.

Every new feature and every change to existing code MUST have a short, one-line numbered entry
in [norfab_changelog.md](../../docs/norfab_changelog.md), under the latest release marked `(draft)`.
If none exists, create the next bugfix release by incrementing the latest release's patch version
and mark its heading `(draft)`. Use the appropriate section: FEATURES, BUGS, ENHANCEMENTS, or another
established category. Describe the concrete change concisely, without implementation walkthroughs.

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
without semantic change. Version 3.2.0 requires documentation tailored to its primary user or developer audience.

**Version**: 3.2.0 | **Ratified**: 2026-11-06 | **Last Amended**: 2026-11-06
