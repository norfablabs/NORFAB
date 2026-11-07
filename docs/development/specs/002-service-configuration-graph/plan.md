# Implementation Plan: NorFab State Service (NSS)

**Date**: 2026-11-07 | **Spec**: [spec.md](spec.md)
**Feature directory**: docs/development/specs/002-service-configuration-graph/
**Status**: Initial implementation design only. Not implemented. This scope supersedes the earlier full-feature delivery plan.

## Summary

Implement the baseline `NssWorker`, persistent graph storage, XML `sync_from`, and generic node/relationship CRUD. Nothing else from the broader service-ownership and reconciliation specification belongs in this initial implementation.

`sync_from` accepts supplied XML independently of device transport, converts it through xmltodict, and merges or explicitly replaces a device-rooted graph. Generic CRUD works on graph nodes and relationships without device-specific task names. Do not implement delete_device, service declarations, ownership enforcement, drift comparison, saved plans, sync to devices, or NETCONF collection.

## Technical Context

**Language/Version**: Existing Python >=3.10,<3.15 support. Service validation on Python 3.12.
**Dependencies**: Existing NFPWorker, NFPClient, Pydantic. Proposed nssservice extra: ladybug==0.22.3 and xmltodict==1.0.4, also included in full with uv.lock updated during implementation.
**Storage**: One writable Ladybug database per NSS worker instance, separate from the base SQLite JobDatabase. Use self.graph_db, never replace self.db.
**Testing**: Small public-client integration tests using real Ladybug, existing fixtures, and Docker/Invoke suite infrastructure. No device lab or Netbox required.
**Target Platform**: Windows and Linux, validated on Python 3.12 before claiming support.
**Project Type**: Existing NorFab worker service. Reuse public job routing and automatic FastAPI/MCP task discovery.
**Performance Goals**: No accepted numerical SLA. Record representative input size/node counts and timings without inventing thresholds.
**Constraints**: Preserve namespace distinctions and leaf values. Ignore ordering. Preserve object/collection containers and duplicate entries without semantic entity keys. No public node IDs or stored full-path identities. Atomic graph mutations. Format support is pluggable, XML only initially.
**Scale/Scope**: One authority worker per dataset. No shared writable database, replication, history, or high availability.

## Constitution Check

| Gate | Result |
| --- | --- |
| Simplicity | Pass. One worker with XML handling methods, canonical models, and graph task group. No ORM or repository layer. |
| Existing patterns | Pass. Reuse worker lifecycle, task decorators, Result, inventory, discovery, and client routing. |
| Boundary contracts | Pass. Typed inputs/results in nss_models.py; validate before mutation. |
| Tests | Pass by design. Few public-client tests, one behavior per test, inline inputs, existing fixture. Runtime validation is pending implementation. |
| Honest state | Pass. Broader requirements are explicitly deferred, not claimed as delivered. |
| Future history | Pass. Keep extension/migration considerations in research, with no unused versioning tables. |

Pre- and post-design review use the same gates. User-selected xmltodict details remain an intentional specification constraint. Entity-key inference is unnecessary for ingestion. CRUD uses exact direct-field AND filters for object entries and exact value filters for scalar entries. Individual mutations require exactly one match; no positional or public storage-ID selection.

## Project Structure

### Documentation

Keep spec.md, plan.md, research.md, data-model.md, contracts/nss-tasks.md, quickstart.md, and checklists/requirements.md together in this feature directory. tasks.md contains the pending initial implementation sequence.

### Source Code (repository root)

```text
norfab/workers/nss_worker/
  __init__.py
  nss_worker.py       # lifecycle, inventory/version, database ownership, XML handling methods
  nss_models.py      # all task/inventory/payload models
  graph_tasks.py     # sync_from and generic node/relationship CRUD
pyproject.toml       # entry point and optional/full extras
uv.lock
tests/services/nss/
tests/nf_tests_inventory/nss/common.yaml
tests/nf_tests_inventory/inventory.yaml
tests/conftest.py    # nss markers and existing fixture integration
tasks.py            # NSS entry in existing SUITES mapping
docker/norfab-docker-tests/compose.yaml
docs/workers/nss/    # initial task and inventory documentation
```

**Structure Decision**: Follow WorkflowWorker lifecycle and existing service model/task-package patterns. Implement XML parsing and normalization as methods on NssWorker in nss_worker.py, called by sync_from. Future format support can add worker methods using the same normalized graph representation. No dedicated XML module or plugin framework is needed. No service_tasks.py, reconciliation_tasks.py, dedicated NFCLI shell, or NFWeb page in this delivery.

## Phase 0: Research

[research.md](research.md) records Ladybug compatibility, private storage keys, worker threading, format handling, and integration patterns. Technical decisions are bounded to the initial scope.

## Phase 1: Design

[data-model.md](data-model.md) defines root/item nodes, containment and generic relationship properties. [contracts/nss-tasks.md](contracts/nss-tasks.md) defines sync_from and generic CRUD. [quickstart.md](quickstart.md) validates this scope only.

One NSS process owns one writable Database object. Use task-scoped connections and a mutation lock, retaining the base executor. Each sync or CRUD mutation is one transaction. Close only NSS resources in worker_exit. Keep optional graph imports out of task-model/client imports.

`sync_from` takes supplied XML; callers may collect it using any existing client or worker outside NSS. Default merge recursively patches same-shape object fields and preserves omissions. Supplied collections replace all entries; a supplied shape change replaces that field subtree. Explicit replace removes omitted data for the selected root. Preserve containers as nodes and XML attributes as metadata. Generic CRUD uses contextual traversal selectors and parameterized Cypher, without a raw query endpoint.

## Delivery Sequence

1. Register nss, optional dependencies, inventory/version tasks, database initialization and shutdown. Verify persistence and optional-dependency isolation.
2. Implement generic node and relationship CRUD, selectors, transactional validation, and explicit cascade semantics.
3. Implement XML handling methods on NssWorker and sync_from merge/replacement using the same graph mutation rules. Verify namespace, value, empty-element, container preservation, collection replacement, shape changes, and reorder behavior.
4. Add focused public-client integration tests, existing suite registration, initial task docs, and update the draft release note to describe actual delivered scope.

## Validation and Limitations

Run the NSS Docker suite through existing Invoke infrastructure, inspect new JUnit/Markdown reports, and run checks/docs-build. No NETCONF lab, service ownership tests, or device write tests are part of initial acceptance.

Broad requirements retained in spec.md remain later scope. Do not create ServiceDefinition, ServiceInstance, Uses/DefinedBy ownership structures, inconsistency evaluators, disappearance tombstones, Plan tables, or device transport adapters. Generic relationships can store arbitrary properties without implementing ownership behavior.

## Complexity Tracking

No additional architecture layer is justified. Ladybug private storage keys and source attribute metadata remain implementation details, not public node identities. Existing client interfaces remain unchanged.

## Initial contract and validation details

Root creation uses parent=null and node=null; duplicate roots fail. Children require exactly one parent and a structural node payload. Node kinds are object, collection, and leaf; an entry is a node connected through a collection membership edge. Updates preserve omitted fields, allow explicit null leaf values, and merge supplied property keys. Collection entries may have identical content. Reads return every match; individual mutations and relationship endpoints require exactly one resolved node. XML parsing remains NssWorker methods, not a dedicated module.

Early create/read tests run an isolated test-owned runtime whose normal teardown cleans it before delete_node exists. After deletion is implemented, tests also clean their owned roots through the public API. Validate optional-dependency isolation with an NSS-free environment import check and record Windows/Linux validation separately; unavailable platform execution stays unverified.
