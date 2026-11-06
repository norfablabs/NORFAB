# Tasks: Nornir HTTP and RESTCONF Tasks

**Input**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md).

## Rules

Small surgical changes; existing utilities first. Before altering existing application code,
ask for confirmation of the exact edits unless already explicitly approved. This task list is
not blanket authorization. All tests use the public client and existing nfclient fixture.
Inline inputs, expected values and payloads; local result variables and safe cleanup are allowed.
No shared data constants/builders, new test server, Requests behavior suite or edge-case matrix.
Each test covers one behavior; repetition is fine. No source changes occur during task generation.

## Phase 1: Setup

- [X] T001 Verify both spine image versions, RESTCONF readiness and a supported hostname resource; record evidence or blocker in docs/development/specs/001-nornir-http/research.md.
- [X] T002 Establish minimal safe RESTCONF lab configuration and distinct ports in tests/nf_tests_inventory/containerlab/norfab-network-lab/norfab-network-lab.yml; do not overwrite shared live configuration or blindly apply old saved configs; record setup in docs/development/specs/001-nornir-http/quickstart.md.

## Phase 2: Foundation

- [X] T003 Add HTTP inventory profiles for both spines in tests/nf_tests_inventory/nornir/nornir-worker-1.yaml using existing group conventions, explicit HTTP ports, HTTPS and restconf/data; preserve other connections and confirm real RESTCONF reads before implementation.

Checkpoint: real spine readiness is mandatory; if unavailable, report it without replacing reads
with mocks or eAPI. Confirm proposed existing application code edits before the next phase.

## Phase 3: US1 - RESTCONF Reads (P1 / MVP)

Independent test: one public-client job returns actual distinct hostname data from both spines.

- [X] T004 [US1] Add one simple two-spine RESTCONF hostname test in tests/services/nornir/test_restconf.py using nfclient.run_job with inline kwargs and expected hostnames; retain only result variables needed for assertions; reuse the existing nornir marker.
- [X] T005 [US1] Add minimal GET input/output models in norfab/workers/nornir_worker/nornir_models.py, reusing existing suitable models/mixins, strict field conventions and existing result shape; no broad model refactor or retry interface.
- [X] T006 [US1] Implement restconf_get and one linear shared runner in norfab/workers/nornir_worker/restconf_task.py using existing filters/processors/serialization/watchdog and the configured Nornir runner; no NorFab-owned retries, custom adapters, extra error taxonomy or helper layers.
- [X] T007 [US1] After confirmation, register the new mixin in norfab/workers/nornir_worker/nornir_worker.py; run the T004 public-client test and record actual result evidence in docs/development/specs/001-nornir-http/quickstart.md.

## Phase 4: US2 - Mutations and Payloads (P2)

Independent tests: separate simple checks for an owned mutation, inline rendering and nf://
rendering. Use a known safe supported device resource; do not change shared interfaces/hostname.

- [X] T008 [US2] Add one short supported owned-mutation/read-back test in tests/services/nornir/test_restconf.py with plain inline payload and finally cleanup; keep read-back/cleanup part of that one mutation behavior, not a multi-verb scenario suite.
- [X] T009 [US2] Add remaining verb models in norfab/workers/nornir_worker/nornir_models.py and thin restconf_put/restconf_patch/restconf_delete methods in norfab/workers/nornir_worker/restconf_task.py, each delegating to the same runner; no null-body handling or named resource shortcuts.
- [X] T010 [US2] Add one simple inline-payload Jinja test in tests/services/nornir/test_restconf.py, then implement sequential rendering in norfab/workers/nornir_worker/restconf_task.py using existing context/job_data helpers under the connection lock; paths remain literal and temporary state is always cleaned.
- [X] T011 [US2] Add a minimal payload template at tests/nf_tests_inventory/http/owned-resource.json.j2 and one separate nf:// rendering test in tests/services/nornir/test_restconf.py; reuse existing file-download utilities/publication and do not add a download/cache subsystem.

## Phase 5: US3 - Existing Result Behavior (P2)

Independent test: a single ordinary failure remains visible through the public client.

- [X] T012 [US3] Add one short public-client failure test in tests/services/nornir/test_restconf.py; assert the failed host is identifiable, without a failure permutation matrix or log-inspection infrastructure.
- [X] T013 [US3] Verify normal failure/result propagation and cleanup in norfab/workers/nornir_worker/restconf_task.py using existing methods; change only behavior needed by the core tests and do not add retries, logger filters or redaction wrappers.

## Phase 6: CLI and Documentation

- [X] T014 Add the four thin commands in norfab/clients/nfcli_shell/nornir/nornir_picle_shell_restconf.py reusing task input models and existing job submission; after confirmation register the group in norfab/clients/nfcli_shell/nornir/nornir_picle_shell.py, keeping request_timeout separate from CLI wait timeout.
- [X] T015 [P] Document each RESTCONF task separately in docs/workers/nornir/services_nornir_service_tasks_restconf_get.md, services_nornir_service_tasks_restconf_post.md, services_nornir_service_tasks_restconf_put.md, services_nornir_service_tasks_restconf_patch.md and services_nornir_service_tasks_restconf_delete.md with output, inline/nf:// payloads, and tabbed Python/CLI/FastAPI/MCP examples, Nornir-owned retries, TLS and backend limitations; keep API references last and omit Inputs.
- [X] T016 Update docs/workers/nornir/services_nornir_service_inventory.md, mkdocs.yml and docs/norfab_changelog.md for the HTTP capability; avoid incidental documentation reorganization.
- [X] T017 Run the few focused public-client tests, existing related regressions, uv run inv checks and uv run inv docs-build; record commands/current reports and unresolved lab prerequisites in docs/development/specs/001-nornir-http/quickstart.md without suppressing findings.

## Dependencies and Parallel Opportunities

T001 -> T002 -> T003 -> US1 -> US2 -> US3 -> CLI/docs -> verification.
US3 may follow US1 before mutations, since its simple failure test needs no payload feature.
T015 can be authored alongside T014 after contracts stabilize; source/model/test edits otherwise
share files and remain sequential. No parallel agents are required.

## Implementation Strategy

Deliver GET first, then the smallest mutation/rendering increments. Do not add tests for every
Requests option, HTTP response shape, retry permutation or device-unsupported operation merely
for coverage. Keep all required operations exposed, but verify core NorFab integration with a few
plain tests. Stop if a supported owned mutation cannot be identified; obtain a scope/lab decision
rather than create a general fixture server. Never mark unexecuted tests or blocked gates passed.

## Completion ? 2026-11-07

Core implementation and verification completed. The five public-client tests passed against
actual spines; GET/PUT/PATCH/DELETE use the configured Nornir runner, without task-owned retries.
Existing-code model/registration edits were explicitly confirmed. Repository-wide quality
findings remain reported in quickstart.md rather than hidden; no unrelated remediation performed.

## POST Addition ? 2026-11-07

- [X] T018 Add explicit RestconfPostInput in norfab/workers/nornir_worker/nornir_models.py, restconf_post in restconf_task.py, CLI POST routing, and one owned-resource public-client test in tests/services/nornir/test_restconf.py; update task docs and draft changelog. All six RESTCONF tests pass.

## Proposed Extension: OpenConfig GET Getters

Interfaces-only increment delivered on 2026-11-07. T019-T023 remain the broader
proposal for LLDP, system and BGP. Their BGP prerequisite does not block interfaces.
See the merged review in plan.md for resource mappings and decisions.

- [ ] T019 Verify four raw OpenConfig resources and proposed BGP fields projection through the public client on both spines. Record actual evidence in quickstart.md. Resolve BGP support before implementation.
- [ ] T020 Obtain required confirmation for specific existing-code edits. Add four GET selector fields and one selection validator in nornir_models.py. Make PUT's existing arguments explicit to prevent GET selector inheritance.
- [ ] T021 Add explicit getter arguments, accurate docstrings and direct resource selection to restconf_get, reusing its runner. Preserve headers and parameters. No new helper, runner changes or discovery.
- [ ] T022 Add four simple public-client tests, one per getter on both spines, with inline arguments and meaningful assertions. Retain explicit URL tests and existing markers. Check GET CLI help and PUT schema.
- [ ] T023 Update the GET guide and draft FEATURES note if unreleased. Run focused tests/checks and docs build. Record actual evidence and implementation status.

Dependencies: T019 -> T020 -> T021 -> T022 -> T023.

### Interfaces-only increment - 2026-11-07

- [X] T024 Add only the OpenConfig interfaces selector and boundary validation,
  follow the NETCONF selection pattern and preserve the existing runner. Keep PUT
  fields explicit. Add one public-client test on both spines, update the GET guide
  and fold the capability into the draft FEATURES entry. Seven RESTCONF tests pass.

LLDP, system and BGP are deferred. See quickstart.md for verification evidence.

### LLDP and system increment - 2026-11-07

- [X] T025 Add openconfig_lldp and openconfig_system to RESTCONF_GETTERS,
  explicit GET arguments and input model fields. Keep NETCONF names, CLI aliases
  and the selection loop. Reject multiple getters or getter with URL. Add one
  public-client test per getter on both spines. Update the GET guide and draft
  FEATURES note. BGP remains deferred.
