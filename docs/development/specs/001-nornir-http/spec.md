# Feature Specification: Nornir RESTCONF Tasks

## Status

**Created**: 2026-11-06

Accepted for planning; not implemented.

**Input**: Design Nornir RESTCONF tasks using nornir-salt's requests-backed http_call,
following netconf_task.py's shared runner and exposed operation pattern. Configure HTTP
connections in inventory and query RESTCONF on ceos-spine-1 and ceos-spine-2.

## Clarifications

### Session 2026-11-07

- Public tasks are restconf_get, restconf_put, restconf_patch, and restconf_delete.
  These replace the earlier http_* naming and seven-operation scope. POST, HEAD, and OPTIONS
  are outside this feature. Backend http_call and the http inventory connection remain unchanged.

### Session 2026-11-06

- Q: Should RESTCONF tasks retry requests after failures? → A: No retries in RESTCONF tasks at all;
  NorFab RESTCONF tasks must not implement or manage retrying for any operation.

- Q: Should resource paths and payloads support per-host rendering? → A: Payloads support
  per-host Jinja2 rendering and nf:// template-file downloads; resource paths remain literal.

- Q: Should the first version offer named resource shortcuts? → A: Explicit RESTCONF resource
  paths and payloads only; no named resource shortcuts.

- Q: How should users invoke operations? ? A: Separate public restconf_get, restconf_put,
  restconf_patch, and restconf_delete tasks sharing one internal runner, as revised on 2026-11-07.

## Implementation and Test Simplicity

Reuse existing methods and utilities, with one direct shared HTTP runner and thin public verbs.
Ask confirmation before altering existing application code unless that specific change is already
authorized. Do not introduce rendering adapters, cache locks, diagnostic frameworks or a test
server merely for completeness. Use existing rendering and execution conventions.

The scenarios below describe supported behavior, not a mandate to implement one test per scenario.
Initial acceptance uses a few short public-client tests, one behavior per test. Inline all inputs,
expected values and plain payloads; repeat values rather than extract shared data or builders.
Result variables and ownership-safe cleanup are permitted. No JSON null-body support is required.
Do not test Requests defaults/override behavior or build edge-case matrices. Retain basic failure
visibility and the no-retry contract without adding a retry implementation.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Retrieve Device Data From Inventory (Priority: P1)

An operator configures each device's HTTP endpoint and credentials once, then queries the
same RESTCONF resource across selected devices without repeating connection details.

**Why this priority**: Inventory-driven retrieval is the main requested capability.

**Independent Test**: Through the public NorFab client, retrieve a known operational resource
from both ceos-spine-1 and ceos-spine-2 and verify device-specific values.

**Acceptance Scenarios**:

1. **Given** reachable RESTCONF endpoints and HTTP inventory settings for both spines,
   **When** the operator requests the same relative resource from both,
   **Then** results contain each selected host and its actual resource data.
2. **Given** inherited group settings and a host-specific endpoint override,
   **When** a read targets that host, **Then** the override is used without changing SSH settings.
3. **Given** a filter matching one spine or no hosts, **When** a read is submitted,
   **Then** only that spine is contacted or the existing no_match result is returned with no I/O.
4. **Given** an absolute HTTP(S) URL, **When** a selected-host request uses it,
   **Then** the URL is used directly rather than prefixed with an inventory base path.

---

### User Story 2 - Perform Explicit RESTCONF Operations (Priority: P2)

An operator selects a RESTCONF operation and supplies its resource, parameters, headers, and
optional payload through the same Nornir job interface used for other device operations.

**Why this priority**: Standard operations make the capability useful beyond one retrieval.

**Independent Test**: Exercise supported verbs against an endpoint that supports each operation,
checking the response and read-back of a test-owned resource for mutations.

**Acceptance Scenarios**:

1. **Given** a resource supporting inspection, **When** GET is selected,
   **Then** that operation is sent and its supported response is returned without inventing a body.
2. **Given** a test-owned resource and a supported endpoint, **When** PUT, PATCH, or DELETE
   is explicitly selected, **Then** only the requested operation is executed with its supplied
   payload and the resulting state can be verified and cleaned up.
3. **Given** request-specific headers, query parameters, authentication, TLS verification, or
   timeout settings, **When** an operation runs, **Then** explicit values take precedence over
   inventory defaults according to the underlying plugin's semantics.
4. **Given** a payload template inline or in an nf:// file and host-specific inventory values,
   **When** PUT or PATCH runs, **Then** each host receives its rendered payload while the
   resource path is used literally; a failed download, rendering, or invalid rendered JSON does
   not send that invalid payload.
5. **Given** an unsupported operation or invalid typed argument, **When** it is submitted,
   **Then** validation rejects it before device I/O.

---

### User Story 3 - Diagnose Failures and Reuse Nornir Results (Priority: P2)

An operator receives identifiable per-host successes and failures, and uses existing result
formatting and processing controls without switching workflows.

**Why this priority**: Mixed outcomes must remain usable in multi-device automation.

**Independent Test**: Submit a public-client request with one healthy endpoint and one deliberately
invalid endpoint; verify the healthy result survives and the other host is marked failed.

**Acceptance Scenarios**:

1. **Given** one successful host and one authentication, connection, timeout, or HTTP error,
   **When** a job completes, **Then** the successful result is retained and the failing host and
   overall failure state are visible through normal Nornir result conventions.
2. **Given** JSON, non-JSON, malformed JSON, or empty successful responses,
   **When** returned, **Then** valid JSON is structured, other bodies remain text, and empty
   responses remain empty; behavior follows the chosen backend rather than a fabricated schema.
3. **Given** supported processors and dictionary/list or detailed serialization options,
   **When** a RESTCONF job runs, **Then** existing Nornir processing and formatting behavior applies.
4. **Given** a completed or failed job, **When** a subsequent job runs,
   **Then** it does not inherit temporary request payloads from the earlier job.

---

### Operational Limitations (Not an Initial Test Matrix)

- Relative paths with leading/trailing slashes; absolute base URLs; missing endpoint settings;
  omitted URL follows backend root/base-URL behavior and does not imply a device-specific getter.
- Invalid credentials, unreachable ports, self-signed certificates, timeouts, and HTTP 4xx/5xx;
  failed requests are reported without automatic repetition.
- Valid JSON scalars/lists, malformed JSON, text/XML and 204 responses.
- Distinct host ports behind one lab hostname; inherited settings must not route both to one spine.
- No matching hosts and mixed host failures; device errors must not become successful empty data.
- Explicit headers replace defaults according to backend rules; do not promise a deep merge.
- RESTCONF tasks do not implement or manage retries for any operation, including reads and mutations.
- A reachable eAPI endpoint is not evidence of RESTCONF availability.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Expose a Nornir `restconf` operation family with GET, PUT, PATCH, and DELETE
  operations, using public task names restconf_get, restconf_put, restconf_patch, and restconf_delete.
  POST, HEAD, OPTIONS, and public http_* aliases are outside this feature.
- **FR-002**: Follow the existing NETCONF pattern: exposed operation tasks share one internal
  call/run path, rather than implement separate execution pipelines for every verb. Use the
  requests-backed nornir-salt `http_call` and its `http` inventory connection; no alternative
  backend is required. Public tasks are restconf_get, restconf_put, restconf_patch, and
  restconf_delete for RESTCONF network-device management.
- **FR-003**: Resolve HTTP hostname, port, credentials, transport, base URL, TLS verification,
  and headers from host/group/default inventory without altering other connection settings.
- **FR-004**: Accept relative resources and absolute HTTP(S) URLs with the backend's documented
  resolution rules; reject unresolvable requests as failures rather than silently selecting a target.
  The first version accepts explicit resource paths and payloads only, with no named getters or
  vendor/YANG resource shortcuts.
- **FR-005**: Accept explicit request parameters, headers, JSON or data payloads, authentication,
  certificate verification, and request timeouts supported by the backend. Preserve backend
  precedence, response decoding, and HTTP-error behavior; document relevant limitations.
- **FR-016**: RESTCONF tasks must not implement retry loops, retry options, or operation-specific
  retry policies for any HTTP verb. They must not initiate a retry after a failed or timed-out
  request. Planning must verify that the execution path does not automatically repeat failed
  HTTP operations; failures are returned to the caller.
- **FR-015**: PUT and PATCH payloads must support per-host Jinja2 rendering from inline
  templates or nf:// template files, following existing NETCONF template-context and job_data
  conventions. Resource paths must remain literal. Template download or rendering failures must
  remain visible failures, must not send an unrendered payload, and must not leave temporary
  payload state for later jobs. Rendered JSON payloads must be valid JSON before being sent.
- **FR-006**: Preserve standard host filters, no_match behavior, processors, non-retry runner controls,
  per-host failure reporting, and to_dict/add_details result options. Common job controls must
  not leak into request-library arguments.
- **FR-007**: Serialize actual response payloads using existing Nornir conventions; do not require
  response headers or status metadata absent from the selected backend's public result.
- **FR-008**: Integrate with existing connection synchronization, activity tracking, and cleanup;
  temporary per-host request state must be removed after success and failure.
- **FR-009**: Provide explicit task models and accurate Google-style docstrings under existing
  conventions, maintaining task/shell defaults and public compatibility. Existing unrelated
  Nornir tasks and interfaces must retain their behavior.
- **FR-010**: Provide NFCLI `nornir restconf get/put/patch/delete` operation commands and Python public-client usage following existing
  conventions. Any automatically exposed service metadata must distinguish read and mutation
  operations; the outer service transport method is distinct from the device HTTP verb.
- **FR-011**: Verify real RESTCONF retrieval through the public client on both named spines,
  asserting known host-specific data rather than only successful status. Readiness requires verified
  RESTCONF support, enablement, reachable ports, and a known resource on the actual lab image.
- **FR-012**: Use a small number of simple public-client integration tests for core RESTCONF
  reads, a supported owned mutation, and payload rendering. Each test covers one behavior with
  inline inputs and payloads. Reuse existing test infrastructure; do not add Requests override
  tests, exhaustive edge-case matrices, or a general controlled server for initial delivery.
  Both spine RESTCONF reads remain mandatory. Unsupported device operations remain documented
  limitations, not a reason to build additional test infrastructure.
- **FR-013**: Mutating tests must use owned resources, verify resulting state, and clean up after
  partial failures; they must not alter shared spine configuration. No Netbox manifest entry is
  needed unless tests actually use Netbox database data.
- **FR-014**: Document inventory configuration, supported operations, result shapes, errors,
  TLS choices, and CLI/Python examples in relevant task pages and record the capability in the
  changelog. Do not expose credentials or authorization values in new task messages or examples;
  planning must assess backend diagnostic logging as well as wrapper logging.

### Key Entities *(include if feature involves data)*

- **HTTP connection profile**: Per-host effective endpoint, credentials, transport, and request
  defaults, inherited from inventory and distinct from SSH or NETCONF connections.
- **Operation request**: Selected hosts, explicit HTTP verb, resource, request options, and payload.
- **Host operation result**: Host identity, returned response content or failure, and optional
  existing Nornir serialization details.
- **RESTCONF resource**: Device-supported operational data or test-owned configuration addressed
  through an HTTP resource path; its actual schema is device dependent.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: One operator submission retrieves verified, distinct operational data from both
  ceos-spine-1 and ceos-spine-2 using inventory-held connection details and one relative resource.
- **SC-002**: All four RESTCONF operations are exposed with the correct fixed verb through the shared
  runner; a simple supported mutation check confirms read-back and owned cleanup. Separate
  end-to-end tests for every HTTP verb are not required for initial delivery.
- **SC-003**: Filtering checks contact exactly the selected devices, including zero for no match.
- **SC-004**: Operational failures remain identifiable and are not reported as successful empty
  device data. Exhaustive injected failure testing is outside initial scope.
- **SC-005**: An operator can complete the documented inventory-to-query workflow through both
  command shell and Python client without embedding device credentials in individual jobs.

## Assumptions

- This invocation produces design artifacts only; source, inventory, device configuration, and
  tests are not changed or executed. Planning will resolve argument models for the agreed task names.
- The initial scope is RESTCONF GET, PUT, PATCH, and DELETE, not a RESTCONF datastore
  transaction engine, automatic YANG discovery, vendor getters, streaming, or a new session backend.
- No generic public dispatcher beyond the operation family is required; the common runner is
  internal, matching the supplied NETCONF pattern. Payloads support per-host Jinja2 rendering
  and nf:// template downloads using existing NETCONF template-context conventions; resource
  paths are literal and are not rendered.
- Both named spines are mandatory RESTCONF read targets. Checked-in spine startup configs show
  eAPI, gNMI, and NETCONF but no explicit RESTCONF enablement. Planning must establish image support
  and the required lab setup; existing eAPI access does not fulfill SC-001. If unsupported, report
  the prerequisite failure and obtain an explicit lab/scope decision instead of substituting devices.
- All four verbs are exposed, but individual RESTCONF endpoints need not support every verb.
  Resource paths and mutation fixtures are confirmed during planning before changing device data.
- Certificate verification follows backend defaults unless explicitly configured otherwise.
  Any lab self-signed exception is scoped and documented rather than a global production default.
- Spec Kit artifacts are maintained together under docs/development/specs/001-nornir-http/.

### Reference Constraints

These sources establish user-requested integration constraints, not additional implementation work:

- [Existing NETCONF task pattern](../../../../norfab/workers/nornir_worker/netconf_task.py).
- [HTTP plugin source](https://github.com/dmulyalin/nornir-salt/blob/master/nornir_salt/plugins/tasks/http_call.py).
- [Salt-Nornir HTTP wrapper precedent](https://github.com/dmulyalin/salt-nornir/blob/3145c11d1907ab5b9f8ed4a87de3b371bc51d7a8/salt_nornir/modules/nornir_proxy_execution_module.py#L2451-L2489).
- [cEOS inventory example](https://salt-nornir.readthedocs.io/en/latest/Pillar%20and%20Inventory%20Examples.html#arista-ceos).

The wrapper's named http function is the relevant precedent; the supplied line fragment displays
a different function in the retrieved revision. Planning must check the repository's installed
backend version before relying on current upstream behavior.
