# Implementation Plan: Design Context File References

**Branch**: `003-design-context-files` | **Date**: 2026-11-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `docs/development/specs/003-design-context-files/spec.md`

**Acceptance status**: Clarified design. **Implementation status**: Implemented and validated. Repository-wide quality findings remain as documented below.

## Summary

Add optional top-level design metadata `context: {name: file_url}`. Fetch each
declared YAML file with existing `self.fetch_file`, parse with
`yaml.safe_load`, and assign the complete value to `context[name]`.
Keep explicit task input above Markdown context above file defaults.
Existing Markdown context blocks continue using task input only.

## Technical Context

**Language/Version**: Python >=3.10,<3.15. Use Python 3.12 for development and services.

**Primary Dependencies**: Existing PyYAML 6.0.3, Jinja2 3.1.6, Pydantic 2.14.1,
markdown-it-py 4.2.0. No dependency changes.

**Storage**: Existing worker file cache, FileSharing and Git services. No new persistence.

**Testing**: Existing pytest public-client integration tests in
`tests/services/netbox/test_designs.py`.

**Target Platform**: Existing cross-platform NorFab workers, with Docker integration validation.

**Project Type**: Worker-service feature with unchanged Python, CLI, FastAPI and MCP task arguments.

**Performance Goals**: Reuse existing cache and timeout behavior. Load every declared file.
No new latency or throughput guarantee.

**Constraints**: Minimal direct changes. No new helper, client argument, rendering pass,
nested merge, recursive file resolution, or Markdown context evaluation changes.

**Scale/Scope**: Two application files, focused existing tests and small data fixtures,
task documentation and a draft release note.

## Constitution Check

Pre-research and post-design gates pass:

- Surgical scope: extend existing model, metadata lists and preparation flow only.
- Boundary validation: metadata types, non-empty keys, supported URL schemes and
  YAML suffixes are validated by `DesignDocument` in `netbox_models.py`.
  Fetch and YAML parsing errors remain in the existing failed-Result path.
- Public interfaces: `DesignDeployInput`, task signature, output and client shells are preserved.
- Tests: few focused public-client tests. Reuse existing fixtures and parser test helper.
  Preview-only tests need no Netbox manifest entry.
- Documentation: update relevant task sections and docstrings, API reference last.
  Add the delivered feature note only during implementation, not as an implemented claim now.
- Honest state: this plan generates no application implementation or executed feature results.
- No constitution exceptions or new architectural layers are needed.

## Project Structure

### Documentation (This Feature)

```text
docs/development/specs/003-design-context-files/
  spec.md
  plan.md
  research.md
  data-model.md
  quickstart.md
  contracts/design-context.md
  checklists/requirements.md
```

Execution progress is recorded in [tasks.md](tasks.md).

### Source Code (Repository Root)

```text
norfab/workers/netbox_worker/netbox_models.py
norfab/workers/netbox_worker/design_tasks.py
tests/services/netbox/test_designs.py
tests/nf_tests_inventory/netbox/designs/
docs/workers/netbox/services_netbox_service_tasks_design_deploy.md
docs/norfab_changelog.md
```

**Structure Decision**: Extend existing design code and tests in place.

## Phase 0: Research

See [research.md](research.md). Existing source inspection resolves the evaluation order,
metadata handling, YAML loading, public interfaces and test approach. No unresolved
clarification blocks implementation.

## Phase 1: Design

1. Add `context: dict[StrictStr, StrictStr]` with an empty default to
   `DesignDocument`, following local model style. Reject empty keys at this
   metadata boundary. Validate every URL as nf:// or git:// with a .yaml or .yml
   suffix, including entries later replaced by Markdown or task input. Unsupported
   URLs such as http:// fail initial Pydantic design metadata validation.
   Preserve arbitrary non-empty keys through dictionary access.
2. Add `context` to the Markdown parser's `metadata_keys`, before collections.
   This automatically removes it from the derived collection set. Reuse existing
   duplicate metadata rejection and assembly. Do not alter context block parsing.
3. Include `context` in dictionary-design metadata extraction and the YAML
   leading metadata scan. YAML authors place metadata before collections, matching
   current schema/function metadata rules. Markdown authors use a `yaml design` fence.
4. Preserve task input separately while processing Markdown context with the
   existing parser. After initial Pydantic metadata validation, load every declared
   file directly in `design_deploy`, with no override checks and no repeated URL
   validation. Fetch with `self.fetch_file(url, raise_on_fail=True)`, then assign
   `yaml.safe_load(source)` directly to `design_context[key]`.
   Merge once as `{**design_context, **markdown_context, **task_context}`.
   Later sources replace whole top-level keys without nested merging. Every file
   must load successfully even if its value is later replaced.
   Do not use `or {}`, which would lose false, zero, empty and null values.
   Add contextual error information naming the key and URL without dumping file contents.
   Keep timeout checks around preparation using existing `job.check_timeout`.
5. Run existing input-schema validation afterward. Its current defaults, coercion
   and extra-field behavior remain authoritative. Loaded data is never rendered,
   recursively fetched or installed as Jinja globals.
6. Leave rendering, flattening and handlers intact. The document metadata remains
   allowed by `DesignDocument` but is not a collection. Do not re-fetch during final
   document validation. Dictionary designs retain their no-template behavior and
   unchanged `dry_run_render` result while effective context reaches existing
   schema validation and deployment functions.
7. Update task docstring and focused documentation with precedence, supported YAML
   values, URL rules, failures and unchanged Markdown-block scope. Preserve current
   command arguments. Add a single FEATURES note under the latest draft release.

See [data-model.md](data-model.md), [interface reference](contracts/design-context.md)
and [validation guide](quickstart.md).

## Validation Strategy

Extend existing preview tests for YAML loading and Markdown metadata support.
Use simple separate cases for whole-key overrides and literal Jinja preservation.
A small parametrized case may check YAML root value preservation. Cover invalid URL,
fetch and YAML errors through failed public task results. Reuse existing Git setup
for one Git-backed loading case rather than testing Git internals.
Retain existing schema, dictionary preview, Markdown scope and device-local-context
tests as regression coverage. Add a dedicated regression only when an existing
case does not cover the touched behavior. No new mutating Netbox test is required.

Run focused design tests in the configured environment, `uv run inv checks`
and `uv run inv docs-build` during implementation. Inspect test summaries and report
unavailable prerequisites honestly. Planning validation is `git diff --check`
and consistency review of these artifacts.

## Complexity Tracking

No violations. No new helpers, models beyond the existing metadata field, services,
dependencies or client paths.

## Validation Evidence

Validated on 2026-11-15 with Docker Python 3.12 and existing public-client fixtures.

- Initial failing preview confirmed the missing file-backed context behavior before implementation.
- Feature selection: 16 passed. Report: `docker-tests-netbox-designs-20261115-173118-337663.md`.
- After adding schema-required context to the value test: 7 passed.
  Report: `docker-tests-netbox-designs-20261115-173302-792474.md`.
- Broader design suite: 137 passed, 4 skipped, 1 failed. The failure was the Git test's
  original cross-mount publication setup, corrected and passed in the later feature selection.
  Existing skips reflect reserved test data already present. No tests were disabled.
  Report: `docker-tests-netbox-designs-20261115-172813-793622.md`.
- Reports and JUnit summaries were inspected under `docker/norfab-docker-tests/`.
- `uv run inv docs-build` passed. Changed-file Black and Ruff checks passed.
- `uv run inv checks` stopped on pre-existing Black findings in seven untouched files:
  `tests/services/fakenos/test_inspect.py`, `tests/conftest.py`,
  `norfab/clients/nfcli_shell/netbox/netbox_picle_shell.py`,
  `norfab/clients/nfcli_shell/nfcli_shell_client.py`,
  `norfab/workers/netbox_worker/bgp_community_tasks.py`,
  `norfab/workers/netbox_worker/ip_tasks.py`, and `norfab/core/client.py`.
  Separately executed repository-wide lint and dead-code checks also report existing findings.
  No suppressions, unrelated formatting changes or threshold changes were introduced.
- `git diff --check` passed. No Netbox manifest entries were added for file-only preview tests.

The Git test publishes beneath its unique runtime mount so snapshot publication does
not cross Docker filesystem boundaries. The registered remote is removed in `finally`.

