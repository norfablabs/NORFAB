# NSS Research

**Date**: 2026-11-07. Planning evidence only. No NSS implementation or database benchmark was performed.

**Initial delivery scope**: baseline graph worker, supplied-XML sync_from, and generic node/relationship CRUD only. This scope supersedes earlier service/reconciliation planning. No device collection or writes, ownership, service declarations, saved plans, or dedicated client shell in the initial delivery.

## Worker ownership and client reuse

**Decision**: Add NssWorker as an NFPWorker subclass, entry point `nss`, using WorkflowWorker's constructor/inventory/version shape and existing service task mixins. Store Ladybug as graph_db separately from the base job database. Reuse public NFPClient routing and task discovery.

**Rationale**: NFPWorker already owns job persistence, events, execution threads, and lifecycle. FastAPI and FastMCP discover decorated task schemas. Dedicated NFCLI shell registration is deferred; initial tasks reuse existing job routing and automatic FastAPI/MCP discovery. Worker-local datasets require callers to select the authority NSS worker explicitly.

**Alternatives considered**: Replacing the worker loop, adding custom REST routes, and creating an NSS-specific Python client duplicate existing infrastructure.

Repository evidence: norfab/core/worker.py, norfab/core/nfapi.py, norfab/workers/workflow_worker/workflow_worker.py, norfab/workers/fastapi_worker/fastapi_worker.py, norfab/workers/fastmcp_worker/fastmcp_worker.py, norfab/clients/nfcli_shell/nfcli_shell_client.py, and docs/development/tasks_pydantic_models_guide.md.

## Embedded storage and compatibility

**Decision**: Retain the ADR's Ladybug choice. Propose ladybug==0.22.3 in nssservice/full with xmltodict==1.0.4, which already appears in NorFab's other extras. Installation remains an implementation check, not a completed check.

**Rationale**: The [release metadata](https://pypi.org/pypi/ladybug/json) identifies distribution/import `ladybug`, Python >=3.10,<3.15, and Python 3.12 Windows/Linux wheels. Pin and resolve with uv during implementation. Metadata and published wheels are stronger compatibility evidence than the older Python versions on the requirements overview.

**Alternatives considered**: SQLite edges, DuckPGQ, and FalkorDBLite were already rejected in the preserved ADR. Do not revisit storage selection without a demonstrated blocker.

## Storage keys are not domain identities

**Decision**: Use fixed generic graph tables with private auto-generated SERIAL keys. Keep namespace URI, local type, name, kind, and value as properties. Match incoming items by traversal and parent context, never by generated keys or concatenated full paths.

**Rationale**: Ladybug [requires a node-table primary key and supports SERIAL keys](https://docs.ladybugdb.com/cypher/data-definition/create-table/). This is a physical storage requirement, not a public identity contract. One Item table avoids executing schema DDL for untrusted XML tag names. Generic relationships store arbitrary type/properties without ownership behavior in this milestone.

**Alternatives considered**: Per-tag tables couple arbitrary input to database schema. Full-path keys conflict with the clarified graph model. Private keys are never exposed as selectors.

## Connections, mutations, and shutdown

**Decision**: One Database object per worker process, graph connections scoped to tasks, one worker mutation lock, atomic graph transactions. Explicitly target one authority worker per dataset. Close NSS resources in worker_exit.

**Rationale**: NFPWorker's task executor is concurrent even with one process. Ladybug documents [shared connections over one writable database object](https://docs.ladybugdb.com/concurrency/) and [a single active writer transaction](https://docs.ladybugdb.com/cypher/transaction/). Keep device I/O outside database transactions and distinguish database rollback from the deferred device rollback feature.

**Alternatives considered**: Multiple writable objects/processes sharing one database are unsuitable. Replacing the scheduler or adding a separate graph server is unnecessary.

## Structural XML conversion without mappings

**Decision**: Preserve dictionary objects, collection fields, separate entries, scalar values, and null presence. XML handling remains NssWorker methods. Do not flatten containers or infer entity keys. Exact caller-supplied direct-field filters select object entries; exact value filters select scalar entries. Individual mutations require exactly one match.

**Rationale**: The cEOS captures contain singleton named config containers, repeated objects with varied/composite keys, and scalar lists. Structural storage represents them without static model knowledge. xmltodict determines singleton versus repeated shapes; supplied collections and shape changes replace their local subtree during merge. Duplicate multiplicity remains intact and stable entry identity is not promised.

**Alternatives considered**: The earlier flattening/name-key plan is superseded. Inferred keys cannot guarantee entity identity. Private storage keys remain physical handles only. Structural diff is feasible but diff APIs, semantic matching, and public JSON input remain deferred. XML parsing uses namespace processing, disabled entity expansion, and disabled whitespace stripping as documented in the previously reviewed xmltodict source.

## Generic graph CRUD

**Decision**: Expose direct node and typed-relationship create/read/update/delete tasks, using contextual traversal selectors and parameterized database statements. Keep containment structural and protect it from generic relationship updates. Deletion follows containment only when cascade is explicit.

**Rationale**: NSS represents arbitrary data, so delete_device and service-specific operations are not the baseline API. Root names need not identify network devices. Sync and CRUD share the same graph storage and transaction rules.

**Alternatives considered**: A raw Cypher endpoint exposes unnecessary database internals. Service ownership helpers and a generic repository framework exceed initial scope. Public storage IDs and full-path identities contradict the agreed traversal model.

## Deferred capabilities

NETCONF collection, sync to devices, drift detection, review/application plans, service definitions and instances, owns/depends_on behavior, inconsistency reporting, history, JSON, high availability, and dedicated NFCLI commands are later work. Do not create their tables, task modules, or tests in the initial implementation. Existing decisions remain in the broader spec for future planning. Additional matching rules are deferred, not silently inferred.