# Feature Specification: Nornir Test Workflows

**Created**: 2026-11-20
**Status**: Draft
**Acceptance Status**: Proposed, pending maintainer review.
**Implementation Status**: Not implemented. Examples describe proposed behavior.
**Feature Branch**: Not created. Feature selection is independent of branch naming.

**Input**: A small Jinja2/YAML DSL for testing infrastructure through public NorFab Nornir tasks. Support structured assertions, conditional tests, repeated observations, cross-host checks, aggregate result events, and persistent test snapshots. Keep existing suites supported.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Render And Execute Host-Specific Tests (Priority: P1)

As an engineer, I can render a flat suite per host and check any public Nornir task's results.

**Why this priority**: This is the core testing capability.

**Independent Test**: Submit a template through the public client for Cisco and Juniper hosts with different roles.

**Acceptance Scenarios**:

1. **Given** vendor/role-specific template branches, **When** rendered, **Then** hosts can have identical, overlapping, or entirely different tests and task arguments.
2. **Given** CLI output or parsed dictionaries/lists, **When** checked, **Then** text, regex, equality, schema, custom-function, and expression assertions produce the expected outcomes.
3. **Given** invalid task arguments, missing templates, or invalid selections, **When** processed, **Then** errors identify the host/test and cannot silently pass.

### User Story 2 - Collect Across Hosts And Publish Results (Priority: P1)

As an operator, I can run large suites using parallel device collection and receive one result event per logical test, like `pytest -vv`.

**Why this priority**: Fleet execution and visible progress make suites practical to run.

**Independent Test**: Run a test on 100 hosts, followed by a delayed test, with job events enabled.

**Acceptance Scenarios**:

1. **Given** a test selected on 100 hosts, **When** collected, **Then** Nornir runs its underlying task across matched hosts using configured host concurrency. Nornir does not execute suites.
2. **Given** all participating hosts pass, **When** the test finishes, **Then** one aggregate PASS event is emitted before later tests finish. Any host FAIL/ERROR instead produces aggregate FAIL with counts and failing hosts.
3. **Given** compatible ready CLI requests for `show version` on 100 hosts and `show ip int brief` on 50 of them, **When** batched, **Then** each host receives only its requested commands and results map back to the correct tests.

### User Story 3 - Order Tests And Correlate Evidence (Priority: P1)

As an engineer, I can compare collected outputs and run diagnostics only after a named check fails.

**Why this priority**: Dependencies support useful relationships without nested workflow syntax.

**Independent Test**: Collect ISIS/MPLS interface state, compare the interface sets, and run a conditional follow-up. Include one cross-host check.

**Acceptance Scenarios**:

1. **Given** named collection entries, **When** a dependent assertion executes, **Then** it can compare their payloads without collecting again.
2. **Given** `run_if_failed: check interface errors`, **When** the prerequisite fails on one host and passes on another, **Then** only the first host runs diagnostics.
3. **Given** an explicit dependency on another host's collector, **When** it completes, **Then** its evidence is available. Missing dependencies or cycles fail validation.

### User Story 4 - Compare Repeated Observations (Priority: P2)

As an operator, I can collect counters twice, 30 seconds apart, and test whether errors increased.

**Why this priority**: Some checks need change over time rather than one observation.

**Independent Test**: Collect two known counter values and evaluate a growth expression.

**Acceptance Scenarios**:

1. **Given** `samples: 2` and `interval: 30`, **When** executed, **Then** two chronological payloads and actual collection times are available. Collections never overlap or start earlier than scheduled.
2. **Given** an incomplete sample set, **When** evaluated, **Then** the result is ERROR. Sample progress never announces a final PASS.

### User Story 5 - Save And Compare Test Snapshots (Priority: P1)

As an operator, I can compare pre/post-change state or find checks failing now that passed three weeks ago.

**Why this priority**: Persistent evidence supports change validation and regression analysis.

**Independent Test**: Save a pre-change snapshot, restart the worker, capture post-change state, and compare configurations, ARP tables, and outcomes.

**Acceptance Scenarios**:

1. **Given** a saved snapshot, **When** the worker restarts, **Then** its per-device evidence and outcomes remain available by identifier/name.
2. **Given** configuration text and keyed ARP records, **When** compared, **Then** additions, removals, and modifications are reported. Record reordering alone is not drift.
3. **Given** `snapshot_before: 21d`, **When** resolved, **Then** one completed snapshot at or before the cutoff is selected and identified. PASS-to-FAIL changes are separated from new/removed checks and ERROR/SKIP outcomes.

### User Story 6 - Keep Existing Suites Working (Priority: P1)

As an existing user, I can keep my suites and reporting options unchanged while adopting the new syntax explicitly.

**Why this priority**: The new meaning of `task` must not break existing command selectors.

**Independent Test**: Run representative existing suites unchanged, including filters, custom functions, metadata, and output modes.

**Acceptance Scenarios**:

1. **Given** an existing suite with no new format option, **When** executed, **Then** its syntax, defaults, assertions, and reporting remain supported.
2. **Given** a dry run, **When** requested, **Then** the rendered per-host suites and dependencies are returned without device calls, executable assertions, or sampling waits.

### Edge Cases

- An absent host-specific test is not a failed test. A filtered prerequisite is distinguished from an unknown dependency.
- Missing results, empty automatic selections, failed parsing, and missing historical evidence never silently pass. Whole-payload expressions can deliberately check empty data.
- Interrupted collection/capture and timeout are visible. Saved partial data is not presented as a completed test snapshot.
- Concurrent jobs must not overwrite each other's host task state, evidence, or snapshot records.
- Reserved suite keys may collide with task arguments. Such collisions must be resolved explicitly before claiming complete public-task coverage.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 - Formats And Rendering**: `suite_format: legacy|workflow` MUST default to `legacy`. Workflow suites MUST render through existing per-host Jinja2 context, filters, job data, and asset loading into flat YAML lists. Hosts MAY produce entirely different entries and kwargs. Nested execution/check blocks and stages are excluded. Nested values required by task arguments or assertion data remain allowed. Validate rendered suites before collection.
- **FR-002 - Entries And Arguments**: Each workflow entry MUST have a nonempty name unique within its host's suite and contain `task`, `test`, or both. Task-only entries collect, test-only entries assert over existing evidence, and combined entries do both. `task` identifies a public NorFab Nornir task. Reserved keys configure testing. Remaining keys are task kwargs validated normally. Reject invalid combinations, unknown tasks, recursion, and private/lifecycle methods. Keep task permissions and mutation classifications effective.
- **FR-003 - Collection Execution**: NorFab MUST own rendering, ordering, collection dispatch, assertions, events, and snapshots. Nornir MUST only run underlying tasks across matched hosts. Support one test collection at a time with configured host concurrency as the simple execution path. Do not require concurrent calls against the same host, a custom Nornir suite runner, or a global thread-per-test scheduler. Connection and host-state safety remain required. Explicit dependencies take precedence over list order, which otherwise provides stable dispatch/report order.
- **FR-004 - Compatible Batching**: The design MUST permit grouping ready requests by task and compatible execution settings. CLI batches MAY carry different command lists per host and reuse one eligible observation for several assertions. Preserve host/test attribution, parsers, outcomes, and requested timing. Never send unrequested or condition-blocked commands, merge samples, reuse stale data, or deduplicate mutations. Batching is an optimization, not a requirement to collect every command up front.
- **FR-005 - Parsing And Selection**: Support explicit parsing tasks and `parse_ttp: true` for text-producing tasks. The convenience parser MUST use the host platform/command, preserve command identity, and default to flat-list records. Missing templates/dependencies or unmatched output yield ERROR. Reject duplicate parsing configuration. `result_task` selects a named command/task payload. Automatically unwrap one payload, preserve intrinsic dictionaries/lists, and reject ambiguous multiple results. `path` supports dictionary keys, list indexes, and list wildcards. Empty/missing automatic selections yield ERROR.
- **FR-006 - Assertions**: Support existing common assertion functions and aliases: contains, regex/multiline contains, equality, negative forms, count constraints, schema validation, custom functions, and Python expressions/assertions. Text checks require text. Equality accepts structured values. Workflow expressions MUST return booleans or use `assert`. False yields FAIL, invalid expressions/types yield ERROR, and reversion cannot turn collection/data errors into PASS. Legacy semantics remain unchanged. Expressions/custom functions are trusted executable suite content, not a sandbox.
- **FR-007 - Evidence And Dependencies**: Expose `result`, current `host`, `results["test name"]`, and `hosts["host name"].results["test name"]`. `depends_on` accepts a name or list, with `host::test name` for another selected host on the same worker. Reserve `::` in referenced host/test names. Dependencies order specific host/test instances and MUST form an acyclic graph. Forward references are allowed. Declare prerequisites for cross-entry reads rather than infer arbitrary Python references. Evidence is read-only. Successful collection remains usable even if its assertion failed. Missing, skipped, undeclared, or failed collection evidence yields ERROR.
- **FR-008 - Conditional Tests**: `run_if_failed` accepts a test name on the current host and implies a dependency. FAIL executes the entry. PASS/SKIP or filter exclusion produces explanatory SKIP. Prerequisite ERROR produces explanatory ERROR without collection. Unknown names/cycles fail validation. Ordering dependencies require completion, not PASS. Filtered ordering prerequisites cause SKIP. Follow-up success never erases an earlier failure.
- **FR-009 - Sampling**: `samples` MUST be a positive integer. Repeated sampling requires positive `interval` seconds, measured start-to-start. Omitted `samples` gives one payload. Explicit `samples` gives a chronological list, including when set to 1. Apply selection to each observation and retain timestamps. Do not overlap samples. Report overruns and incomplete samples. Stop new work on cancellation/timeout. Authors define counter reset/wrap policy. Timer waits need not hold a device connection. Other tests need not run during the wait in the simple sequential execution path.
- **FR-010 - Per-Host Results And Reporting**: Preserve groups, subset selection, severity, descriptions/comments, custom failure messages, existing output modes, retained data, rendered suites, extensive output, and Markdown reports. Per-host outcomes are PASS, FAIL, ERROR, or SKIP with reasons. Task-only success is PASS. Any executed FAIL/ERROR fails the run. Retained collection data is not an assertion failure. Output filtering does not change execution outcomes or evidence. Empty selections/runs must be identifiable as nothing executed.
- **FR-011 - Aggregate Events**: Emit one `job.event` result per logical test name per worker run after all participating hosts finish it, like `pytest -vv`. Participants are hosts where that name was rendered and selected. All PASS means aggregate PASS. Any FAIL/ERROR means aggregate FAIL. Otherwise any SKIP means aggregate SKIP. No participants means no result event. Include job/worker/test identity, timestamp, host counts by outcome, and failing/error hosts with reasons. Keep per-host detail in results/snapshots. Messages start lowercase and use event `severity`. Distinguish progress from final outcomes and do not claim snapshot commit before it occurs. Emit completed aggregate events during the run, preserving the normal final response and existing event-delivery semantics.
- **FR-012 - Durable Test Snapshots**: Workflow runs MUST save test snapshots in worker-local SQL storage, independently of job-result cleanup. Run-level `suite_id` identifies the suite. Each snapshot has an immutable ID and optional unique name within that worker/suite. Save per-device payloads, samples/timestamps, outcomes, metadata, and collection/assertion provenance without relying on report-retention flags. Preserve structured types and fail visibly on unsupported values/storage errors. Separate in-progress, completed, interrupted, and capture-error states. A completed capture may contain failed checks. Acknowledge saving only after durable commit and retain committed data across restart.
- **FR-013 - Snapshot Selection**: Support listing/inspection and selection by ID/name (`snapshot`) or latest completed capture at/before a cutoff (`snapshot_before`). Selectors are mutually exclusive. Resolve relative cutoffs once against run start, record the exact chosen snapshot/time, and exclude the current run. Never silently mix latest records from different snapshots. Match worker/suite/host/test identities explicitly. Renames require explicit mapping. Missing, incomplete, expired, or incompatible history yields a clear comparison error. Flag changed collection/parser/assertion definitions rather than presenting them as equivalent evidence.
- **FR-014 - Snapshot Comparisons**: Expose `previous` and `previous_test` for matching historical evidence/outcome, plus `snapshot_results` and `snapshot_hosts` for other selected historical entries/hosts. Historical reads do not require live dependencies or rerun saved code. Support configuration/text diffs, dictionary differences, keyed-record additions/removals/modifications, and outcome transitions. Normalization of ordering/volatile fields must be explicit. Invalid/duplicate record keys are errors. Assertions decide allowed changes. Separate PASS-to-FAIL regressions from ERROR/SKIP, changed checks, new/removed checks, and existing failures.
- **FR-015 - Snapshot Lifetime And Scope**: Provide configurable retention defaulting to at least 30 days, explicit pinning, inspection, and deletion. Naming alone does not pin. Automatic cleanup must preserve pinned/in-use snapshots. Apply existing worker storage/access protections to captured device data. Do not save credentials or executable runtime objects as metadata. Live state is isolated by job. Historical access requires an explicitly selected authorized snapshot. Cross-host and historical comparisons are worker-local initially.
- **FR-016 - Compatibility And Validation**: Preserve unchanged legacy suites by default. Before implementation, inventory existing assertion aliases, metadata, custom-function options, task-argument collisions, and result controls. Resolve flat-key collisions explicitly without silent argument loss. Dry runs render/validate only. Verify behavior through a few focused public-client integration tests and a controlled 100-host, 100-test run. Every rendered host/test instance must have one recorded outcome, with no cross-host data leakage or falsely completed snapshots.

### Suite Keys And Invocation Options

| Purpose | Reserved Entry Keys |
| --- | --- |
| Identity and reporting | `name`, `groups`, `severity`, `description`, `comments` |
| Execution | `task`, `depends_on`, `run_if_failed`, `samples`, `interval`, `parse_ttp` |
| Selection | `result_task`, `path`, `report_all`, `use_all_tasks` |
| Assertions | `test`, `pattern`, `expr`, `schema`, `err_msg`, `revert`, `use_re`, `count`, `count_ge`, `count_le`, `allow_unknown` |
| Custom assertions | `function_file`, `function_text`, `function_call`, `function_name`, `function_import`, `function_kwargs`, `globals_dictionary`, `add_host`, `globs` |
| Test snapshots | `snapshot`, `snapshot_before` |

All other entry keys are task kwargs. Test-only entries cannot carry collection kwargs. `use_all_tasks` selects all named payloads instead of `result_task`/`path`. `report_all` retains individual successful wildcard checks. Empty automatic selections remain errors. Callable arguments are limited to interfaces that can transport them.

`suite_format`, `suite_id`, optional `snapshot_name`, and existing run/filter/report controls are invocation options. Detailed comparison options and collision-free argument names belong in planning, not additional workflow syntax here.

### Example Suite

Submit with `suite_format: workflow` and a stable `suite_id`. Templates/fields below are illustrative. Real templates must produce normalized interface names and the specified types.

```yaml
- name: collect ISIS interfaces
  task: parse_ttp
  commands: show isis interface
  template: nf://templates/isis_interfaces.ttp

- name: collect MPLS interfaces
  task: parse_ttp
  commands: show mpls interfaces
  template: nf://templates/mpls_interfaces.ttp

- name: ISIS interfaces have MPLS enabled
  depends_on: [collect ISIS interfaces, collect MPLS interfaces]
  groups: [isis, mpls]
  severity: critical
  test: eval
  expr: |
    (
      bool(results["collect ISIS interfaces"]) and
      {r["interface"] for r in results["collect ISIS interfaces"]}.issubset(
        {r["interface"] for r in results["collect MPLS interfaces"] if r["enabled"]}
      )
    )

- name: check interface errors
  task: parse_ttp
  commands: show interfaces
  template: nf://templates/interface_counters.ttp
  test: eval
  expr: 'bool(result) and all(p["input_errors"] == 0 for p in result.values())'

- name: check errors increasing
  run_if_failed: check interface errors
  task: parse_ttp
  commands: show interfaces
  template: nf://templates/interface_counters.ttp
  samples: 2
  interval: 30
  test: eval
  expr: |
    (
      bool(result[0]) and result[0].keys() == result[1].keys() and
      all(result[1][p]["input_errors"] == result[0][p]["input_errors"] for p in result[0])
    )
```

The last check deliberately fails on counter increases or decreases. Cross-host reads use an explicit dependency such as `depends_on: "PE2::collect ISIS interfaces"` before reading `hosts["PE2"].results["collect ISIS interfaces"]`.

For pre/post-change comparison, capture the initial suite with `snapshot_name: before-CHG123`. In a later run, use the same host/test identity:

```yaml
- name: running configuration
  task: cli
  commands: show running-config
  snapshot: before-CHG123
  test: eval
  expr: result == previous
```

Omit the selector for initial capture. Replace it with `snapshot_before: 21d` for a historical comparison. Equality is only an example. Diff policies can allow expected configuration changes.

### Key Entities

- **Rendered suite**: One host's flat list of named collectors/assertions.
- **Collection batch**: Compatible ready requests dispatched through a NorFab task to Nornir's matched hosts.
- **Test result**: Per-host evidence/outcome and an aggregate event for the logical test name.
- **Test snapshot**: Durable capture of a run's per-device evidence, outcomes, identity, provenance, and retention state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Representative existing suites run unchanged with preserved filtering/assertion behavior and output capabilities. Retained successful collection data causes zero false failures.
- **SC-002**: A 100-host, 100-test run records all 10,000 host/test outcomes using bounded parallel host collection. Smaller mixed-vendor and disjoint-suite runs account for their actual rendered entries without requiring common names or ordering.
- **SC-003**: Compatible batching of `show version` on 100 hosts and `show ip int brief` on 50 produces exactly the 150 requested observations, correctly attributed, with no speculative commands or sample merging.
- **SC-004**: A completed test produces one aggregate event before a delayed subsequent test finishes. All-host PASS and any-host FAIL/ERROR follow the aggregation rule and match final per-host results.
- **SC-005**: Conditional diagnostics run on exactly the hosts whose prerequisite failed. Two-sample checks produce two chronological observations at least 30 seconds apart, or report timing/error details without false PASS.
- **SC-006**: After restart, committed snapshots retain every captured record and payload type. Interrupted captures are never selected as completed. Pre/post-change configuration/ARP diffs and a 21-day outcome comparison identify the expected changes and regressions.
- **SC-007**: Missing data/history, invalid expressions, failed parsing, and capture errors produce zero silent passes. Reports identify the affected host/test and reason without requiring worker logs.

## Assumptions And Scope

- NorFab owns the DSL and test execution. Nornir remains the device-task executor. Initial implementation may execute one test collection across matched hosts at a time. Compatible batching can improve collection efficiency without introducing a same-host concurrent workflow engine.
- Legacy remains the default format. New workflow runs persist snapshots with a supplied stable suite identity. Legacy capture must be explicit and must not change old calls.
- Test names identify the same logical check across hosts for aggregate events, even when commands differ by vendor/role. Unrelated checks should have distinct names.
- Existing inventory, Jinja2 rendering, task validation, events, and reporting are dependencies. The specification does not prescribe a new scheduler or database schema.
- Cross-worker aggregation/history, stages, nested workflows, general loops beyond Jinja2 rendering, expression sandboxing, and automatic replay/resume of interrupted device tasks are excluded initially.
- Renumbered requirements replace the earlier draft's overlapping scheduling and persistence requirements. This specification remains proposed, not accepted or implemented.
