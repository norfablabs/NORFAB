# Tasks: Design Context File References

**Input**: Design documents in `docs/development/specs/003-design-context-files/`.
**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [interface reference](contracts/design-context.md), and [quickstart.md](quickstart.md).
**Acceptance status**: Clarified and planned. **Implementation status**: Complete. Validation results and existing repository-wide check limitations are recorded in [plan.md](plan.md).
**Tests**: Simple public-client integration tests are requested. Write focused tests before the corresponding implementation and observe the relevant failure when services are available.
**Organization**: Tasks are grouped by user story. Paths are relative to the repository root.

## Phase 1: Setup

- [X] T001 Review current worktree and existing preview, Markdown, schema and device-local-context coverage in `tests/services/netbox/test_designs.py` against `docs/development/specs/003-design-context-files/plan.md`. Preserve unrelated changes and identify existing regression tests to reuse. Read the testing guide and `tests/netbox_data_manifest.json` before test changes. No new service, dependency or shared fixture is needed.

## Phase 2: Foundational

- [X] T002 Add `context: dict[StrictStr, StrictStr]` with default `{}` to existing `DesignDocument` in `norfab/workers/netbox_worker/netbox_models.py`. Validate all entries in initial Pydantic design metadata validation: non-empty keys, nf:// or git:// URLs, and .yaml or .yml suffixes. Unsupported URLs such as http:// must fail even if the value would later be replaced. Keep arbitrary non-empty names as dictionary keys, preserve current YAML duplicate handling, and leave public task input/output models unchanged.

**Checkpoint**: Metadata shape is available. Shared file loading is delivered in US1.

## Phase 3: User Story 1 - Reuse File-Backed Design Data (P1, MVP)

**Goal**: YAML designs load named YAML defaults through existing file services.
**Independent test**: Public `design_deploy` preview renders a value from `nf://` and from `git://`, without writes.

### Tests

- [X] T003 [US1] Add a focused YAML file-default preview test under `TestDesignDeploy` in `tests/services/netbox/test_designs.py`. Use a temporary directory under the existing inventory designs directory and inline payloads. Assert a value is read as `context.defaults.site`, without expanding source mapping entries into sibling keys.
- [X] T004 [US1] Add a small parametrized public-client preview test in `tests/services/netbox/test_designs.py` proving "Each complete YAML document becomes one value at its declared key" for dictionary, list, string, number, boolean, null and an empty document. Include a quoted Jinja string as the string case and assert it remains literal. Do not create a loader helper or full cross-product matrix.
- [X] T005 [US1] Add focused preparation-failure cases in `tests/services/netbox/test_designs.py` for invalid declaration shape or empty key, unsupported scheme or extension, missing YAML file and malformed YAML. Assert failed public task results, with the key or URL identifiable for file failures. Use preview mode and avoid mocking download internals.

### Implementation

- [X] T006 [US1] Add one public-client Git-backed YAML preview test in `tests/services/netbox/test_designs.py`, following the local repository and `create_remote_git` pattern in `tests/services/filesharing/test_git.py`. Register a unique remote, use `git://<remote>/defaults.yaml`, and remove the remote in `finally`. Keep setup inline and avoid importing another test module or creating global fixture infrastructure.
- [X] T007 [US1] Extend dictionary metadata extraction and the leading YAML metadata scan in `norfab/workers/netbox_worker/design_tasks.py` to include `context`. Preserve task input and Markdown context separately. After initial Pydantic metadata validation, fetch and parse every declared file into `design_context` using `self.fetch_file(..., raise_on_fail=True)` and `yaml.safe_load`. Merge once as `{**design_context, **markdown_context, **task_context}` before input-schema validation. Do not check whether a source will be overridden or repeat URL validation in the loader. Preserve complete parsed values, including false, zero, empty values and null. Do not use `or {}`, render loaded data, recursively fetch values, add helpers, or add public task arguments. Keep timeout checks and existing failed-Result handling, adding key/URL error context without source contents.

**Checkpoint**: Run US1 tests. YAML defaults work with both supported schemes and retain YAML value types. Preview-only file/Git resources require no Netbox manifest entry.

## Phase 4: User Story 2 - Markdown Design Support (P1)

**Goal**: Markdown design metadata declares the same sources without changing existing context blocks.
**Independent test**: Public Markdown preview resolves a declared file value in a design fence. Existing block-scope tests still pass.

### Tests

- [X] T008 [US2] Add a single Markdown metadata loading preview test under `TestMarkdownDesignDeploy` in `tests/services/netbox/test_designs.py`, reusing `preview_markdown` and existing temporary-file patterns. Declare `context` in one `yaml design` fence and reference the loaded value in another. Keep existing context-block parsing tests intact.

### Implementation

- [X] T009 [US2] Add `context` to `parse_markdown_design` metadata keys in `norfab/workers/netbox_worker/design_tasks.py`, reusing existing metadata assembly and duplicate checks. Ensure it is excluded from the derived collections set. Do not change YAML/CSV/table context rendering or provide loaded values to those blocks.

**Checkpoint**: US2 preview and existing Markdown context tests pass. Files are loaded after Markdown block processing.

## Phase 5: User Story 3 - Context Precedence And Compatibility (P2)

**Goal**: Preserve context boundaries and whole-key overrides.
**Independent test**: Task input overrides Markdown and file defaults. Markdown overrides file defaults. Every declared source is validated and loaded, including values later replaced.

### Tests

- [X] T010 [US3] Add a focused task-override preview test in `tests/services/netbox/test_designs.py`: task input replaces an entire same-key value from successfully loaded design-file and Markdown context. Assert unrelated context keys remain and nested dictionaries are not merged, using inline input and assertions. Extend the related T005 failure cases to prove unsupported URLs fail Pydantic validation and missing sources still fail fetching when task input supplies the same key.
- [X] T011 [US3] Add a focused Markdown-override preview test in `tests/services/netbox/test_designs.py`: an existing Markdown context block wins over a same-key successfully loaded YAML file value, with no task override. Reuse current block behavior rather than adding another rendering path.
- [X] T012 [US3] Run existing schema, dictionary-design preview, Markdown task-only scope and device-local-context regression cases in `tests/services/netbox/test_designs.py`. Extend a related case only if coverage of a touched behavior is missing. Confirm effective defaults reach schema validation, dictionary previews remain unchanged, and `config_context`/`local_context_data` are not reinterpreted. Do not add a new mutating test solely for unchanged handlers.

### Integration

- [X] T013 [US3] Review and, only if the focused tests reveal a gap, adjust context preparation in `norfab/workers/netbox_worker/design_tasks.py` to load every declared file and merge in design-file, Markdown, task-input order before schema validation. Preserve schema transformations, task arguments, results, Markdown block scope, rendering and deployment handlers. No override checks, repeated source validation, duplicate URL loading or alternative merge implementation.

**Checkpoint**: All three stories meet their independent test criteria using the same preparation path.

## Phase 6: Documentation And Final Validation

- [X] T014 Update `design_deploy` and parser Google-style docstrings in `norfab/workers/netbox_worker/design_tasks.py` to describe file metadata, YAML-only data, whole-key precedence, validation and loading of every declared source, preparation failures and unchanged Markdown scope. Keep every public argument accurate. Fix spelling in changed text.
- [X] T015 [P] Update relevant sections of `docs/workers/netbox/services_netbox_service_tasks_design_deploy.md` with concise YAML and Markdown examples, metadata placement, `.yaml`/`.yml` sources, complete value assignment, no source rendering, precedence and errors. Preserve API reference last, add no Inputs section, and retain existing public interface examples and command arguments.
- [X] T016 [P] Add one numbered FEATURES entry under the latest draft release in `docs/norfab_changelog.md` describing delivered YAML context sources for YAML and Markdown designs. Leave published releases unchanged and avoid an implemented claim before the code is complete.
- [X] T017 Run focused public-client tests from `tests/services/netbox/test_designs.py`, `uv run inv checks`, `uv run inv docs-build` and the applicable scenarios in `docs/development/specs/003-design-context-files/quickstart.md`. Use configured services and documented Docker selectors where needed. Inspect actual summaries and reports. Record failures or unavailable prerequisites honestly, without weakening checks.
- [X] T018 Review the final diff for surgical scope and update acceptance/implementation status and validation evidence in `docs/development/specs/003-design-context-files/spec.md`, `docs/development/specs/003-design-context-files/plan.md` and this `tasks.md`. Mark tasks complete only when verified. Confirm preview-only tests add no unrelated Netbox manifest entries.

## Dependencies And Execution Order

```text
T001 -> T002 -> US1 (T003-T007) -> US2 (T008-T009)
                                      |
                                      v
                               US3 (T010-T013)
                                      |
                                      v
                            T014-T016 -> T017 -> T018
```

US2 depends on the US1 loader. US3 checks the combined YAML/Markdown behavior.
These are explicit dependencies because the feature uses one existing preparation path.
Within each story, add the focused tests before the corresponding behavior change.
Run each story's checks before advancing. Keep edits to the shared application and test files sequential.

## Parallel Execution Examples

- US1: Tests and implementation touch shared files and should be sequential. Read-only comparison with `tests/services/filesharing/test_git.py` may occur while preparing the YAML tests.
- US2: Keep the Markdown test and parser edit sequential. A documentation draft may be prepared separately after metadata syntax is stable.
- US3: Keep override tests and any required correction sequential. Documentation tasks T015 and T016 can run independently once behavior is verified because they touch different files.

No parallel implementation agents are required. The `[P]` markers identify optional safe file separation, not a requirement to delegate.

## Implementation Strategy

Deliver US1 as the smallest working slice: named YAML defaults through the existing public task.
Then add only Markdown metadata recognition, followed by focused precedence and compatibility validation.
Finish concise documentation and release notes, run required checks, and record actual implementation status.
Do not add new endpoints, task arguments, helpers, loaders, dependencies, or unrelated refactors.
