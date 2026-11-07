# Tasks: NorFab State Service (NSS)

**Input**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/nss-tasks.md](contracts/nss-tasks.md), and [quickstart.md](quickstart.md).

**Status**: Generated implementation tasks. All work is pending. Specification acceptance and implementation are separate.

**Tests**: Public-client integration tests explicitly requested. Write each focused test before its corresponding implementation, observe the expected failure, then make it pass. Use real Ladybug, existing NorFab fixtures, inline inputs, standard Result envelopes, and explicit workers=["nss-worker-1"]. Each test owns its graph roots. Early create/read slices use isolated runtime lifecycle teardown before deletion exists; later slices also remove owned roots through public deletion in finally blocks. Do not add mocks of Ladybug, a separate test server, payload builders, or a new test framework.

**Organization**: Initial milestone only. US5 is generic graph CRUD (P1) and US1 is XML sync/inspection (P1, limited to initial scenarios). Execute US5 before US1 to reuse graph storage. Broader US2-US4 and US1 drift/service-association obligations are deferred, with no implementation tasks in this file.

## Format: `[ID] [P?] [Story] Description`

Each checkbox has a sequential ID and concrete repository-relative file paths. [P] marks independent file work only, after the stated phase prerequisites. Shared worker/model/task files must be edited sequentially. No agents need to be launched to execute this list.

## Path Conventions

Run uv/Invoke from repository root. Worker files are under norfab/workers/nss_worker/, tests under tests/services/nss/, and durable design artifacts remain in this feature directory. Read AGENTS.md, the task-model guide, testing guide, and documentation guide before the relevant changes. Use private/ for temporary notes.

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Register only the NSS graph baseline and reuse existing test infrastructure.

- [ ] T001 Add nssservice with ladybug==0.22.3 and xmltodict==1.0.4, mirror pins into full, register nss=norfab.workers.nss_worker.nss_worker:NssWorker in pyproject.toml, and regenerate uv.lock without unrelated upgrades.
- [ ] T002 [P] Add service=nss inventory at tests/nf_tests_inventory/nss/common.yaml, map/start nss-worker-1 in tests/nf_tests_inventory/inventory.yaml, and register nss markers in tests/conftest.py using existing worker selection and fixtures.
- [ ] T003 [P] Register nss-service-tests in docker/norfab-docker-tests/compose.yaml and nss in tasks.py SUITES, using isolated __norfab__ runtime storage, existing report generation, and NORFAB_TEST_WORKERS restricted to required infrastructure/NSS. Do not add custom runner functions or external device dependencies.

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Establish lifecycle, storage, and shared typed payloads before either story.

- [ ] T004 Create norfab/workers/nss_worker/__init__.py and canonical norfab/workers/nss_worker/nss_models.py with inventory/version, node/reference, and contextual selector models. Use kind=object/collection/leaf, namespace_uri default empty string, nullable type-preserving leaf values, properties default {}, and no entity_name identity field. Model mutually exclusive direct-field AND filters and scalar-entry value filters, including explicit null. Keep strict types, Union[None,T], descriptions, enum/name population settings, and no graph imports in models.
- [ ] T005 Add focused failing get_inventory and get_version public-client tests in tests/services/nss/test_worker.py using tests/conftest.py's existing nfclient fixture and explicit NSS worker selection.
- [ ] T006 Implement NssWorker in norfab/workers/nss_worker/nss_worker.py following WorkflowWorker's constructor/load_inventory/init_done_event lifecycle, typed @Task inventory/version methods, and worker_exit cleanup. Keep self.db as the base SQLite JobDatabase and Ladybug as self.graph_db, with optional dependency failure confined to NSS startup. Make T005 pass.
- [ ] T007 Initialize fixed root/item, Contains/Member structural containment, and generic-relationship storage plus task-scoped connections and a worker mutation lock in norfab/workers/nss_worker/nss_worker.py. Enforce "Every item has one containing parent", "The tree is acyclic", and "one relationship per source/target/type". Use private storage keys only, parameterized Cypher, one transaction per mutation, and no service/plan/history tables.

**Checkpoint**: NSS starts through standard registration, reports inventory/versions, and owns a separate persistent graph database. Both stories can now use this foundation.

## Phase 3: User Story 5 - Manage arbitrary graph data (Priority: P1, MVP)

**Goal**: Supply generic node and relationship CRUD without XML or device knowledge.

**Independent Test**: Create a non-device root and child nodes, read/update them, manage a typed relationship and properties, and delete test-owned nodes through the public client. No sync_from task is required.

### Tests before implementation

- [ ] T008 [US5] Add focused failing create/read and selector tests in tests/services/nss/test_nodes.py. Root creation uses parent=null,node=null and rejects duplicates; object fields are unique but collection entries may duplicate. Check direct-field AND and scalar-value filters, missing-versus-null/type distinctions, and multi-match reads. For this early slice, use an isolated test-owned runtime and normal public lifecycle teardown rather than requiring not-yet-implemented delete_node. Keep inline inputs and no new shared test harness.

### Node create/read slice

- [ ] T009 [US5] Define CreateNodeInput/Result and GetNodesInput/Result in norfab/workers/nss_worker/nss_models.py: nullable parent/node default null only for name-only root creation, required payload for children, exactly one parent, selector default [], recursive default false, structural kinds and both filter forms from FR-026/FR-028/FR-030/FR-031. Reject duplicate object fields/roots while allowing duplicate collection entries.
- [ ] T010 [US5] Implement create_node/get_nodes in norfab/workers/nss_worker/graph_tasks.py and mount the mixin in norfab/workers/nss_worker/nss_worker.py. Traverse object fields and collection members without inferred keys, public IDs, indexes, or flattening. Reads return matching nodes/children or recursive subtrees. Require exactly one parent for creation, support direct leaf equality and own-value scalar selection, and make T008 pass with lifecycle-only early cleanup.

### Node update/delete slice

- [ ] T011 [US5] Add focused failing patch/delete tests in tests/services/nss/test_nodes.py for omitted values versus explicit value=null, property-key merging, and zero/multiple-match rejection without mutation. Cover a uniquely selected scalar entry as well as an object entry. Use isolated lifecycle teardown until public deletion is available.
- [ ] T012 [US5] Define UpdateNodeInput/Result and DeleteNodeInput/Result in norfab/workers/nss_worker/nss_models.py and implement them in norfab/workers/nss_worker/graph_tasks.py. Distinguish omitted fields through supplied-field tracking, retain present null leaves, merge properties, prohibit structural renaming/reparenting, and require exactly one selected node before mutation. Keep cascade default false and reject scalar-value writes on containers. Make T011 pass; subsequent test cleanup can use public deletion.

### Relationship CRUD slice

- [ ] T013 [US5] Add focused failing relationship creation/read, property-patch, and deletion tests in tests/services/nss/test_relationships.py using node CRUD for setup. Assert relationship deletion preserves endpoints, and a read with no matches returns an empty list.
- [ ] T014 [US5] Add CreateRelationship/GetRelationships/UpdateRelationship/DeleteRelationship Input/Result models in norfab/workers/nss_worker/nss_models.py with source/target references, required type on exact operations, "properties: dict, default {}" on create, and "type: nullable str, default null"/"target: nullable node reference, default null" on read.
- [ ] T015 [US5] Implement create_relationship/get_relationships in norfab/workers/nss_worker/graph_tasks.py using a validated type data property and outgoing reference matching. Enforce "One additional relationship per source/target/type is supported initially; duplicate creation fails" and reserve structural containment from generic mutation. Make T013 creation/read tests pass.
- [ ] T016 [US5] Implement update_relationship/delete_relationship in norfab/workers/nss_worker/graph_tasks.py, patch only supplied properties, fail clearly on missing exact links, and preserve endpoints. Make the remaining T013 tests pass.

### Deletion safety and persistence

- [ ] T017 [US5] Add a focused failing cascade-boundary test in tests/services/nss/test_nodes.py: deletion without cascade must fail unchanged, and explicit cascade deletes only containment descendants/incident links while retaining a node connected solely by a generic relationship.
- [ ] T018 [US5] Complete transactional deletion safeguards in norfab/workers/nss_worker/graph_tasks.py so cascade follows only Contains and Member edges, removed endpoints' incident links are deleted atomically, and generic link endpoints outside the subtree survive. Make T017 pass.
- [ ] T019 [US5] Add and run a normal-restart persistence test in tests/services/nss/test_worker.py using existing NorFab public lifecycle/client patterns and an isolated inventory/runtime for that test. Create data through public CRUD, stop/start the owning worker normally, then read it through the public client. Adjust only NSS close/open lifecycle in norfab/workers/nss_worker/nss_worker.py if this exposes a defect.

**Checkpoint**: US5 is an independently usable baseline graph service. Generic CRUD is the recommended first demonstrable MVP; the requested complete initial milestone also includes US1 below.

## Phase 4: User Story 1 - Sync supplied XML (Priority: P1, initial subset)

**Goal**: Implement only supplied-data sync_from and graph inspection, not drift comparison or device collection.

**Independent Test**: Sync inline XML into a named root, read the preserved structural graph with get_nodes, then prove default merge preserves omitted leaves and explicit replacement removes them. Run after US5 using no device lab.

### XML sync slice

- [ ] T020 [US1] Add a focused failing XML sync/read test in tests/services/nss/test_sync_from.py using inline XML with repeated objects lacking name keys and a scalar list. Assert preserved container/collection/member/leaf structure, duplicate multiplicity, unchanged values, and reading through get_nodes. Use the cEOS captures as reference, not executable dictionary text or unredacted copied secrets.
- [ ] T021 [US1] Add SyncFromInput/Result and changed-count payloads in norfab/workers/nss_worker/nss_models.py, preserving "format: xml by default", "mode: merge by default or replace", required device/data strings, and graph-only result counts without affected_services or plan fields.
- [ ] T022 [US1] Implement XML methods directly in norfab/workers/nss_worker/nss_worker.py using namespace-aware xmltodict, disabled entity expansion, and disabled whitespace stripping. Preserve objects, collections, separate duplicate entries, attributes, nulls, and text without static mappings or inferred entity keys. Follow actual singleton/repeated source shape. Do not flatten containers or create xml_plugin.py.
- [ ] T023 [US1] Implement sync_from default merge in norfab/workers/nss_worker/graph_tasks.py using worker XML methods and graph transactions: recursively merge same-shape object fields, preserve omitted fields/collections, replace supplied collections and supplied shape changes locally, and remove only links incident to removed nodes. Preserve unrelated roots and links between surviving nodes. Make T020 pass without stable entry matching.

### Merge/replacement slice

- [ ] T024 [US1] Add a few focused merge tests in tests/services/nss/test_sync_from.py for omitted object fields, supplied-versus-omitted collections, and singleton/collection shape changes. Include explicit root replacement, duplicate preservation, and generic-link deletion boundaries in separate focused methods with inline input. Map these tests to FR-018/FR-029 and SC-011.
- [ ] T025 [US1] Complete root replacement and field/collection replacement boundary handling in norfab/workers/nss_worker/graph_tasks.py: remove omitted fields on root replace, replace all supplied collection entries, remove incident generic links of removed nodes, and preserve other roots and surviving-node links. Make T024 pass without ownership checks, tombstones, or semantic matching.

### XML semantics and failure boundary

- [ ] T026 [US1] Add a few focused XML semantic tests in tests/services/nss/test_sync_from.py for namespace URI/prefix normalization, unchanged values/empty presence, and reordered collections preserving content and duplicate multiplicity. Do not assert entry-node or relationship identity across collection replacement. Fix only worker methods in norfab/workers/nss_worker/nss_worker.py as needed.
- [ ] T027 [US1] Add a focused failed-sync atomicity test in tests/services/nss/test_sync_from.py: malformed XML leaves existing public read output unchanged. Confirm unsupported formats fail at the model boundary in norfab/workers/nss_worker/nss_models.py. Missing names or other semantic keys must not reject valid structural input.

**Checkpoint**: Initial XML sync and generic graph CRUD work together. No network-service ownership, reconciliation plans, sync_to_device, NETCONF collection, or dedicated shell implementation is required.

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Verify existing interfaces and document only the initial delivered capability.

- [ ] T028 Verify NSS schemas/metadata through public list_tasks using tests/services/nss/test_worker.py and the existing FastAPI/MCP discovery paths in norfab/workers/fastapi_worker/fastapi_worker.py and norfab/workers/fastmcp_worker/fastmcp_worker.py. Check strict schemas, read/mutation hints, and existing client routing without adding handwritten routes, a new Python client, or new shell modules.
- [ ] T029 [P] Document worker setup and the implemented initial tasks in docs/workers/nss/services_nss_service.md, docs/workers/nss/services_nss_service_inventory.md, and one docs/workers/nss/services_nss_service_tasks_<task>.md page per implemented public task. Verify real output and Python/FastAPI/MCP examples. Explicitly state that dedicated CLI commands are deferred instead of inventing aliases. Keep Python API references last and add no Inputs sections.
- [ ] T030 Update mkdocs.yml navigation and the latest draft FEATURES entry in docs/norfab_changelog.md for the actual NSS graph/sync_from/CRUD delivery, and add a concise verified notable-capability entry in docs/norfab_features.md only once implemented. Preserve the original ADR and unrelated edits.
- [ ] T031 Execute docs/development/specs/002-service-configuration-graph/quickstart.md via NSS Docker build/suite, checks, and docs-build. Inspect fresh Markdown/JUnit reports under docker/norfab-docker-tests/reports/ for nonzero tests/zero errors, verify uv.lock consistency, and check model/client imports in an isolated temporary environment without nssservice. Record Windows and Linux lifecycle/CRUD evidence separately; unavailable platform runs remain unverified. Keep temporary environments/notes under ignored private/.
- [ ] T032 Record actual implementation/acceptance evidence and remaining limits in docs/development/specs/002-service-configuration-graph/spec.md, docs/development/specs/002-service-configuration-graph/quickstart.md, and docs/development/specs/002-service-configuration-graph/checklists/requirements.md. Keep deferred broader stories explicitly unimplemented and do not mark unrun tests or platforms complete.

## Dependencies & Execution Order

```text
Setup T001-T003
  -> Foundation T004-T007
    -> US5 T008-T019 (generic graph MVP)
      -> US1 T020-T027 (XML sync_from)
        -> Interface/docs/validation T028-T032
```

US5 maps to FR-025 through FR-028, FR-030/FR-031, Story 5, and SC-009. US1 maps to initial ingestion scenarios 1 and 4-10, FR-016 through FR-018, FR-022 through FR-024, FR-029, SC-010/SC-011, and the Initial Implementation Scope. T008-T010 cover entry filters and root creation; T011-T012 cover patch/null and unique mutation; T022-T025 cover collection and shape replacement. No tasks implement deferred US1 comparison scenario 2, reconciliation US2, ownership US3, or service removal US4. An identical-input sync may prove unchanged counts; it does not implement drift detection.

T002 and T003 edit different files and can be prepared concurrently after scope review; runtime checks wait for T001 and the worker. Within stories, tests precede their implementation and models precede task methods. Most story work is deliberately sequential because nss_models.py, nss_worker.py, and graph_tasks.py are shared. Do not mark those tasks parallel merely because their API names differ.

### Parallel Example: US5

After T012, the relationship tests in T013 can be prepared while T019's persistence test is drafted in test_worker.py. Both use the established node contract and touch different test files. Run/complete persistence only after deletion and lifecycle behavior are available. Keep production edits sequential.

### Parallel Example: US1

After T023, namespace/value/reordering tests from T026 can be prepared separately while T029's initial user-documentation pages are drafted. Tests and docs touch different files. Final examples and final test results still wait for the completed sync implementation.

### Cross-cutting parallel opportunity

T029 documentation can proceed after task contracts stabilize while T028 verifies discovery in test_worker.py. T030 navigation/release notes follow the task-page filenames, and final verification follows all edits.

## Implementation Strategy

Deliver the worker foundation first, then US5 as an independently testable graph MVP. Complete US1 to satisfy the requested initial milestone. Run each focused test through the public client until it passes before broadening to the suite. Keep initial tests few and focused rather than exhaustively covering every permutation. Prefer existing methods/direct execution over new one-use helpers or storage adapters.

Do not implement deferred tables, service ownership semantics, reconciliation, device I/O, history, JSON, new authentication, raw Cypher endpoints, a dedicated XML file, or dedicated NFCLI/NFWeb interfaces. Generic relationship properties remain data, not ownership behavior. No Netbox manifest update is needed because this suite uses no Netbox data.

## Notes

All task checkboxes start unchecked. Mark a task complete only after its change and relevant verification actually pass. Test setup failures do not establish a meaningful red test of the intended behavior. Preserve public client interfaces and unrelated working-tree changes. Log/event messages start lowercase, use severity, and do not expose input XML or secrets. This command generates tasks only; it does not authorize incidental changes outside the initial NSS scope.
