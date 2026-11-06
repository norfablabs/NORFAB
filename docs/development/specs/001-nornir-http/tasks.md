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

- [ ] T001 Verify both spine image versions, RESTCONF readiness and a supported hostname resource; record evidence or blocker in docs/development/specs/001-nornir-http/research.md.
- [ ] T002 Establish minimal safe RESTCONF lab configuration and distinct ports in tests/nf_tests_inventory/containerlab/norfab-network-lab/norfab-network-lab.yml; do not overwrite shared live configuration or blindly apply old saved configs; record setup in docs/development/specs/001-nornir-http/quickstart.md.

## Phase 2: Foundation

- [ ] T003 Add HTTP inventory profiles for both spines in tests/nf_tests_inventory/nornir/nornir-worker-1.yaml using existing group conventions, explicit HTTP ports, HTTPS and restconf/data; preserve other connections and confirm real RESTCONF reads before implementation.

Checkpoint: real spine readiness is mandatory; if unavailable, report it without replacing reads
with mocks or eAPI. Confirm proposed existing application code edits before the next phase.

## Phase 3: US1 - RESTCONF Reads (P1 / MVP)

Independent test: one public-client job returns actual distinct hostname data from both spines.

- [ ] T004 [US1] Add one simple two-spine RESTCONF hostname test in tests/services/nornir/test_http.py using nfclient.run_job with inline kwargs and expected hostnames; retain only result variables needed for assertions; register nornir_http in tests/conftest.py.
- [ ] T005 [US1] Add minimal GET input/output models in norfab/workers/nornir_worker/nornir_models.py, reusing existing suitable models/mixins, strict field conventions and existing result shape; no broad model refactor or retry interface.
- [ ] T006 [US1] Implement http_get and one linear shared runner in norfab/workers/nornir_worker/http_task.py using existing filters/processors/serialization/watchdog and a local ThreadedRunner clone; no retries, custom adapters, extra error taxonomy or helper layers.
- [ ] T007 [US1] After confirmation, register the new mixin in norfab/workers/nornir_worker/nornir_worker.py; run the T004 public-client test and record actual result evidence in docs/development/specs/001-nornir-http/quickstart.md.

## Phase 4: US2 - Mutations and Payloads (P2)

Independent tests: separate simple checks for an owned mutation, inline rendering and nf://
rendering. Use a known safe supported device resource; do not change shared interfaces/hostname.

- [ ] T008 [US2] Add one short supported owned-mutation/read-back test in tests/services/nornir/test_http.py with plain inline payload and finally cleanup; keep read-back/cleanup part of that one mutation behavior, not a multi-verb scenario suite.
- [ ] T009 [US2] Add remaining verb models in norfab/workers/nornir_worker/nornir_models.py and thin http_post/http_put/http_patch/http_delete/http_head/http_options methods in norfab/workers/nornir_worker/http_task.py, each delegating to the same runner; no null-body handling or named resource shortcuts.
- [ ] T010 [US2] Add one simple inline-payload Jinja test in tests/services/nornir/test_http.py, then implement sequential rendering in norfab/workers/nornir_worker/http_task.py using existing context/job_data helpers under the connection lock; paths remain literal and temporary state is always cleaned.
- [ ] T011 [US2] Add a minimal payload template at tests/nf_tests_inventory/http/owned-resource.json.j2 and one separate nf:// rendering test in tests/services/nornir/test_http.py; reuse existing file-download utilities/publication and do not add a download/cache subsystem.

## Phase 5: US3 - Existing Result Behavior (P2)

Independent test: a single ordinary failure remains visible through the public client.

- [ ] T012 [US3] Add one short public-client failure test in tests/services/nornir/test_http.py; assert the failed host is identifiable, without a failure permutation matrix or log-inspection infrastructure.
- [ ] T013 [US3] Verify normal failure/result propagation and cleanup in norfab/workers/nornir_worker/http_task.py using existing methods; change only behavior needed by the core tests and do not add retries, logger filters or redaction wrappers.

## Phase 6: CLI and Documentation

- [ ] T014 Add the seven thin commands in norfab/clients/nfcli_shell/nornir/nornir_picle_shell_http.py reusing task input models and existing job submission; after confirmation register the group in norfab/clients/nfcli_shell/nornir/nornir_picle_shell.py, keeping request_timeout separate from CLI wait timeout.
- [ ] T015 [P] Document core usage in docs/workers/nornir/services_nornir_service_tasks_http.md with output, inline/nf:// payloads, CLI/Python examples, no retries, TLS and backend limitations; keep API references last and omit Inputs.
- [ ] T016 Update docs/workers/nornir/services_nornir_service_inventory.md, mkdocs.yml and docs/norfab_changelog.md for the HTTP capability; avoid incidental documentation reorganization.
- [ ] T017 Run the few focused public-client tests, existing related regressions, uv run inv checks and uv run inv docs-build; record commands/current reports and unresolved lab prerequisites in docs/development/specs/001-nornir-http/quickstart.md without suppressing findings.

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
