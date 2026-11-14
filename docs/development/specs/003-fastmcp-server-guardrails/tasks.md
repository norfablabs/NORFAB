# Tasks: FastMCP Server Guardrails

**Input**: [Specification](spec.md), [Plan](plan.md), [Research](research.md), [Data Model](data-model.md), [Interface Reference](contracts/server-guardrails.md), and [Validation Guide](quickstart.md).

**Acceptance**: Proposed. **Implementation**: Not started. All tasks are unchecked. Task generation does not imply design acceptance or passing tests.

**Tests**: Requested. Prefer a few small tests through the public MCP and NorFab clients using existing fixtures. Each test covers one behavior. Keep payloads and expected values inline. Use focused model/serialization tests only for boundaries that are impractical through public clients. Write failing checks before the implementation they verify. Do not add a large permutation matrix, test-only production APIs, or mutable Netbox data.

## Story Mapping And Priorities

The specification numbers acceptance scenarios rather than assigning story IDs or priorities. This task list groups them by independently observable capability. These priorities describe execution order, not additional requirements.

| Story | Priority | Specification Scenarios | Requirements |
|---|---|---|---|
| US1: Bound MCP Result Size | P1, MVP | 1, 4, 5 | FR-001, FR-004 through FR-008 |
| US2: Redact Result Secrets | P1 | 2, 3, 4, 5 | FR-002, FR-003, FR-008, FR-009 |
| US3: Request Approval For Matching Calls | P2 | 6, 7, 8, existing rejection compatibility | FR-010 through FR-017 |

Shared settings support US1 and US2. US3 reuses US2 sanitization for approval summaries even when result redaction is disabled. Existing task result rules retain authored order and byte units. Server processing follows those rules, including their standalone Result early-return shape.

## Phase 1: Setup

**Goal**: Use the existing environment and capture a relevant baseline. No new dependencies or infrastructure.

- [ ] T001 Review the current boundary and fixtures in norfab/workers/fastmcp_worker/fastmcp_worker.py, norfab/workers/fastmcp_worker/fastmcp_models.py, tests/services/fastmcp/test_result_guardrails.py, tests/services/fastmcp/test_guardrails.py, tests/services/fastmcp/common.py, and tests/nf_tests_inventory/fastmcp/common.yaml. Read docs/development/norfab_developing_and_testing_framework.md and docs/development/tasks_pydantic_models_guide.md. Preserve unrelated working-tree changes and confirm job retrieval is excluded.
- [ ] T002 Establish the existing FastMCP suite baseline using uv/Invoke from the repository root and docker/norfab-docker-tests/README.md. Run uv run inv --list, then the existing FastMCP Docker suite. Inspect current reports/JUnit and record any unavailable prerequisites or pre-existing failures under ignored private/fastmcp-guardrails-validation.md. Rebuild only when required by the testing guide.

## Phase 2: Foundational Settings

**Goal**: Validate the two independent settings once before serving MCP calls. Both stories depend on this phase.

- [ ] T003 Add focused settings validation tests in tests/services/fastmcp/test_result_guardrails.py for the exact constraints: result_guardrail_size_limit is StrictInt, default 32768, "0 disables the built-in server size limit. Otherwise at least 4096 characters. Reject 1 through 4095." Reject negative values, booleans, strings, and null. result_guardrail_secrets_reduction is StrictBool, default true, "False disables built-in result redaction only." Verify unrelated tools keys remain accepted by their existing configuration path. Confirm new-setting checks fail before implementation.
- [ ] T004 Add FastMCPServerGuardrails in norfab/workers/fastmcp_worker/fastmcp_models.py and validate its two declared inventory settings during initialization in norfab/workers/fastmcp_worker/fastmcp_worker.py. Enforce T003 constraints without validating unrelated tools settings through this model. Keep settings independent of tools.disable_builtin_guardrails and preserve public task arguments.

## Phase 3: US1 - Bound MCP Result Size (Priority: P1, MVP)

**Goal**: Deliver a valid standard result-omission response when the aggregate exceeds the configured aggregate character threshold. No retrieval instructions or job API changes.

**Independent Test**: A safe public MCP call whose combined worker structure exceeds 4096 characters under len(str(delivery_result)) returns result=None, failed=false, and exactly one errors entry explaining count, limit, and configuration, with original UUID when available. No preview is returned. A disabled server cap leaves existing task/inventory rules in control.

### Tests

- [ ] T005 [US1] Add one public MCP integration test in tests/services/fastmcp/test_result_guardrails.py for a combined multi-worker structure whose individual workers fit 4096 characters but whose len(str(combined_structure)) exceeds 4096. Reuse existing safe tasks/client fixtures and isolated configuration in tests/nf_tests_inventory/fastmcp/common.yaml only if needed. Assert result=None, failed=false, exactly one actionable errors entry with actual size/limit and configuration guidance, original UUID when available, and no preview or original diff. Restore configuration and add no retrieval API.
- [ ] T006 [US1] Add focused boundary checks in tests/services/fastmcp/test_result_guardrails.py for equality retention, len(str(delivery_result)) across all worker keys/results/diffs/metadata, Unicode characters versus bytes, None, missing UUID, and failed=False for size omission after authored rules. Do not measure JSON or SDK text. Keep each check small and observe failures before T007/T008.

### Implementation

- [ ] T007 [US1] Integrate a final server delivery stage in norfab/workers/fastmcp_worker/fastmcp_worker.py after apply_task_result_guardrails. Capture the original UUID before authored transformations. Size omission uses failed=False. Support aggregates, existing standalone Result returns, and None without changing raw storage or authored rule order. Skip only server size enforcement when the configured limit is 0.
- [ ] T008 [US1] Implement combined-structure size measurement with len(str(delivery_result)) in norfab/workers/fastmcp_worker/fastmcp_worker.py. Above the configured threshold replace the whole aggregate with Result(result=None, failed=False, errors=[one meaningful message], juuid=original_uuid). State measured size, limit, omission, and how to increase tools.result_guardrail_size_limit or set 0. Return no preview/original diff. Do not budget the final diagnostic response. Ensure MCP-facing output handling permits this standard omission envelope for typed tools, preserving non-MCP output models, and add a public typed-tool check in tests/services/fastmcp/test_result_guardrails.py before changing that handling. Preserve authored byte limits and make T005/T006 pass.
- [ ] T009 [US1] Extend related public-client regression tests in tests/services/fastmcp/test_result_guardrails.py to verify 0 disables only the server threshold and existing authored byte-limit responses still enter final server enforcement. Verify size omission sets failed=False because limiting MCP delivery is not a task failure. Keep ordinary results unchanged when the server limit does not omit them. Reuse existing ordering tests. Confirm originals remain unchanged through existing test access without retrieval APIs.

**Checkpoint**: US1 can be demonstrated with the result stage in place. US2 supplies its additional default redaction behavior next.

## Phase 4: US2 - Redact Result Secrets (Priority: P1)

**Goal**: Apply built-in redaction to the complete delivery copy after authored rules and before the aggregate size check. Leave stored originals unchanged and keep the new boolean independent.

**Independent Test**: A public MCP call without task-authored rules masks recognized credentials with REDUCTED, preserves useful non-sensitive values, and leaves stored originals unchanged. Disabling the built-in redactor does not disable existing replacement rules or the size cap.

### Tests

- [ ] T010 [US2] Add a small public MCP integration test in tests/services/fastmcp/test_result_guardrails.py showing a safe result with labelled and nested structured credentials is masked even without task-authored result rules. Assert REDUCTED, useful output preservation, and unchanged original data through existing test access. Keep data inline and confirm failure before T012.
- [ ] T011 [US2] Add focused redaction boundary checks in tests/services/fastmcp/test_result_guardrails.py for diagnostic metadata, numeric values under credential keys, inline credentials in keys, sanitized-key collisions, PEM private keys, repeated application, and safe processing failure. Reuse existing tests where they cover the behavior. Keep checks independent and add no large pattern permutation matrix.

### Implementation

- [ ] T012 [US2] Add fixed precompiled credential patterns and direct delivery-copy redaction in norfab/workers/fastmcp_worker/fastmcp_worker.py. Cover password/passwd/pwd/secret/token/api_key/api-key/authorization labels with complete-label matching, whitespace/equals/colon separators, quoted values, bearer/basic values, and PEM blocks. Replace with REDUCTED, process metadata and keys as well as result/diff, replace sensitive-key values as units, and withhold mappings whose sanitized keys collide. Run after authored transformations and before the T008 combined-structure measurement. Verify redacted typed values/keys remain compatible with the MCP-facing output declaration without changing non-MCP task models. Respect result_guardrail_secrets_reduction only for result delivery. Make T010/T011 pass.
- [ ] T013 [US2] Extend public-client tests in tests/services/fastmcp/test_result_guardrails.py to verify result_guardrail_secrets_reduction=false skips only built-in masking while authored/inventory replacements and the configured size cap remain active. Verify tools.disable_builtin_guardrails does not disable server protection. Extend related cases rather than create duplicate fixtures or Cartesian combinations.
- [ ] T014 [US2] Remove raw argument dictionaries from the touched call_tool logs in norfab/workers/fastmcp_worker/fastmcp_worker.py. Log tool/request identity, counts, and outcomes only, with lowercase initial messages and severity for any events. Check fixture secrets are absent from touched-path logs using focused coverage in tests/services/fastmcp/test_result_guardrails.py. Keep broader logging refactors out of scope.

**Checkpoint**: US1 and US2 form the complete default result-protection path, with independent controls and unchanged raw storage.

## Phase 5: US3 - Request Approval For Matching Calls (Priority: P2)

**Goal**: Support explicit request_approval rules using MCP form elicitation before dispatch. No built-in approval rule for nornir.cfg or any other task.

**Independent Test**: A safe MCP operation executes exactly once only after accept with approved=true. A decline or matching reject creates no dispatched job. No matching approval rule produces no prompt.

### Models And Matching

- [ ] T015 [US3] Extend focused model checks in tests/services/fastmcp/test_guardrails.py before changing implementation. Quote and enforce "Literal reject or request_approval. Default reject." and "Required for reject. For request_approval omit all three or supply all three. Omission matches every call to the selected service/task. Explicit null is invalid." Verify the approval response requires approved: StrictBool with no default and extra=forbid, preserving existing strict strings, match lists, and regex validation.
- [ ] T016 [US3] Extend TaskMCPGuardrail and add TaskMCPApprovalResponse in norfab/workers/fastmcp_worker/fastmcp_models.py according to T015. Keep approval form fields out of public tool argument schemas and do not add action to result guardrail models. Make model checks pass.
- [ ] T017 [US3] Extend make_task_guardrails and check_tool_call_guardrails in norfab/workers/fastmcp_worker/fastmcp_worker.py to collect matching approval reasons while rejecting any matching reject first, independent of rule order. Preserve exact service/task selectors, existing predicate/list/case behavior, missing-field non-match, and task-default disable semantics. Add focused matching/discovery checks in tests/services/fastmcp/test_guardrails.py before changes. Do not install automatic approval rules or add an approval-enable flag.

### Public Interaction And Integration

- [ ] T018 [US3] Add small public MCP acceptance and refusal tests in tests/services/fastmcp/test_guardrails.py using SDK elicitation callbacks and a safe existing task. Accept with approved=true and verify one dispatch after confirmation. Decline in a separate test and verify a safe tool error and no submitted NorFab job using existing test access, not new production APIs. Reuse tests/services/fastmcp/common.py where suitable, but keep callbacks inline and preserve existing helper callers. Observe failures before T019.
- [ ] T019 [US3] Integrate await ctx.elicit(message, schema=TaskMCPApprovalResponse) via self.app.get_context() inside call_tool in norfab/workers/fastmcp_worker/fastmcp_worker.py. Snapshot arguments before matching, combine reasons into one form, explicitly check form capability including legacy empty elicitation support and URL-only rejection, and require action=accept plus validated approved is True. Apply asyncio.wait_for with 120 seconds. Dispatch the identical snapshot once. Sanitize prompt data with US2 logic regardless of the result-redaction switch, cap the full prompt at 4096 characters, and identify tool/service/task, workers=all, incomplete summaries, and unresolved references. Make T018 pass.
- [ ] T020 [US3] Add narrowly scoped negative-path checks in tests/services/fastmcp/test_guardrails.py for cancel, approved=false, missing/invalid content, unsupported form capability, timeout, and originating-request cancellation/disconnect. Prefer public SDK clients. Use a focused local boundary check only when real transport behavior cannot practically isolate the condition. Verify no job is submitted before a valid approval and avoid real 120-second sleeps or production timeout overrides for tests.
- [ ] T021 [US3] Complete safe denial and cancellation behavior in norfab/workers/fastmcp_worker/fastmcp_worker.py. Return fixed McpError reasons through the existing path without raw arguments, exceptions, or form content. Propagate request cancellation, audit identity/outcome only, create no job while waiting, and do not cache or reuse approval across calls/retries. Preserve existing synchronous run_job and document that post-dispatch cancellation does not promise rollback. Make T020 pass.
- [ ] T022 [US3] Extend related public-client tests in tests/services/fastmcp/test_guardrails.py for no-rule/no-prompt behavior, a conditional approval's non-matching call, reject precedence with zero forms, and one form for multiple matching reasons. Extend existing metadata/disable tests to cover task-authored approval rules versus persistent inventory rules and absence of any default nornir.cfg approval. Verify a repeated approved call asks again. Keep each test focused and reuse T018/T020 where possible.

**Checkpoint**: Approval is rule-driven, fail-closed, request-bound, and independent of the result-delivery settings.

## Phase 6: Documentation And Final Validation

- [ ] T023 [P] Update docs/workers/fastmcp/services_fastmcp_service_inventory.md and docs/workers/fastmcp/services_fastmcp_service.md for defaults, strict validation, independent switches, Python string character versus byte units, whole-result omission and one actionable errors entry, action examples, reject precedence, capability failures, timeout, and trusted-host limitations. State approval summaries remain sanitized when result redaction is off. Include no recovery instructions, new retrieval behavior, or claim of independently verified human identity. Keep documentation concise and accurate to the implementation.
- [ ] T024 [P] Add or amend the appropriate short numbered entry under the latest draft in docs/norfab_changelog.md, folding unreleased refinements into the relevant existing feature entry. Read release context before classifying the change. Do not claim delivery in the feature catalogue or change unrelated release notes.
- [ ] T025 Run the focused public FastMCP suite using the uv/Invoke commands in docker/norfab-docker-tests/README.md, inspect current JUnit/reports, then run uv run inv checks and uv run inv docs-build. Verify the unchanged input/result guardrail regressions and absence of changes to job_details, raw storage, task arguments, and dependencies. Record evidence and unavailable prerequisites in ignored private/fastmcp-guardrails-validation.md without suppressing failures.
- [ ] T026 Follow docs/development/specs/003-fastmcp-server-guardrails/quickstart.md for one actual interactive-host test showing a visible form, human decline, and no dispatch. Record host/version/transport and limitations in private/fastmcp-guardrails-validation.md. Update spec.md, plan.md, and checklists/requirements.md in docs/development/specs/003-fastmcp-server-guardrails/ with truthful acceptance/implementation status. Do not mark acceptance or manual verification complete without evidence.

## Dependencies And Execution Order

```text
T001 -> T002 -> T003 -> T004
                       |
                       v
US1: T005 -> T006 -> T007 -> T008 -> T009
                       |
                       v
US2: T010 -> T011 -> T012 -> T013 -> T014
                       |
                       v
US3: T015 -> T016 -> T017 -> T018 -> T019 -> T020 -> T021 -> T022
                       |
                       v
                  T023 + T024 -> T025 -> T026
```

All stories require the settings foundation. At runtime US2 redaction runs before the US1 combined-structure size check. US3 depends on US2 sanitization. Complete stories sequentially because their implementation and tests share files. Public acceptance tests precede the implementation they verify. Later regression checks extend the completed behavior without duplicating it.

## Parallel Execution Examples

- US1: No independent in-story parallel task is marked. Tests and worker integration share behavior dependencies. Review the result examples in contracts/server-guardrails.md while another reviewer checks T005 expectations, without concurrent edits to shared files.
- US2: No independent in-story parallel task is marked. Redaction must integrate with US1 before its tests can pass. Review credential coverage in spec.md alongside T010/T011 test design without simultaneous edits to tests/services/fastmcp/test_result_guardrails.py.
- US3: No independent in-story parallel task is marked. Models, matching, callbacks, and dispatch depend on one another. Review installed SDK capability behavior while checking T015 schemas, without concurrent worker edits.
- After all stories: T023 and T024 can run in parallel because the user documentation and changelog are distinct files and behavior is settled. T025 waits for both.

These are optional work-scheduling opportunities, not an instruction to spawn agents.

## Implementation Strategy

Deliver US1 as the first verifiable increment, then US2 to complete the planned default result protection, then US3 for operator-configured approval. Keep each slice simple and preserve the existing worker/client architecture. Do not merge claims of the full feature after US1 alone. Run focused validation after meaningful changes and the complete final checks once at T025 unless new failures require repetition.

Job retrieval, job_details changes, new database schemas, dependencies, rate limiting, resolved-file inspection, durable approval queues, and dispatch concurrency refactoring are excluded. No Netbox manifest entry is needed unless implementation unexpectedly introduces actual Netbox records, which this plan does not require.
