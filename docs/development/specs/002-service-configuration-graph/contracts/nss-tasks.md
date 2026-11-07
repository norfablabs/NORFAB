# NSS Initial Task Contracts

**Status**: Proposed initial contracts, not implemented. Initial scope is baseline graph storage, sync_from, and generic graph CRUD only.

## Routing and models

Use `client.run_job("nss", task, workers=["nss-worker-1"], kwargs={...})`. Each worker owns its dataset. Reuse existing @Task, Result, Pydantic model conventions, and automatic FastAPI/MCP discovery. All task models belong in nss_models.py. No dedicated client, custom routes, or new NFCLI shell is required in this phase.

Inputs use strict scalar types, use_enum_values=True, populate_by_name=True, Union[None,T] for nullable fields, and concise field descriptions. Keep input/signature defaults aligned. Results use existing ResultStatuses and typed payloads, with documented dynamic property dictionaries. Graph dependencies must not be imported by model modules.

## Task surface

| Task | Arguments | Result |
| --- | --- | --- |
| get_inventory | none | Effective NSS inventory. |
| get_version | none | NorFab, Python, platform, Ladybug, xmltodict versions. |
| sync_from | device: str; data: str; format: xml by default; mode: merge by default or replace | Root, mode, created/updated/deleted counts. |
| create_node | root: str; parent: nullable selector, default null; node: nullable node payload, default null | Created node. Empty parent selects the root; root creation is explicitly represented by parent=null. |
| get_nodes | root: str; selector: selector, default []; recursive: bool, default false | Selected node and its direct children, or subtree when recursive=true. |
| update_node | root: str; selector: selector; value: nullable scalar, optional by presence; properties: dict, optional by presence | Updated node. Patch only supplied mutable properties. |
| delete_node | root: str; selector: selector; cascade: bool, default false | Deleted node/relationship counts. Empty selector selects the root. |
| create_relationship | source: node reference; target: node reference; type: str; properties: dict, default {} | Created relationship. |
| get_relationships | source: node reference; type: nullable str, default null; target: nullable node reference, default null | Matching outgoing relationships. |
| update_relationship | source: node reference; target: node reference; type: str; properties: dict | Relationship with supplied properties patched. |
| delete_relationship | source: node reference; target: node reference; type: str | Deleted relationship count. |

`sync_from` accepts supplied XML only. Device collection, sync_to_device, plan_reconciliation, get_plan, apply_plan, service_* tasks, and delete_device are not initial APIs.

## Node payload and contextual selection

A node payload contains namespace_uri (default empty string), local_name, kind (object, collection, or leaf), a nullable scalar value for leaves, properties (default {}), and XML attribute metadata where applicable. Entry is a containment role, not an inferred entity kind. Object/collection nodes cannot hold scalar leaf values. No semantic entity_name is required.

Root creation is create_node(root="example", parent=null, node=null). Reject an existing root without changes. Child creation requires a payload and exactly one existing parent; [] selects the root. An object/root field must be unique by namespace/local_name; collection entry duplicates are allowed. Explicitly supplied null leaf values retain a present node. update_node changes leaf value and/or patches properties; omission means unchanged and explicit null means null. Track supplied fields at validation so a null default cannot accidentally clear an omitted value. Reject structural renaming/reparenting or value updates on container nodes.

A selector is a traversal list. A field segment contains namespace_uri (default empty) and local_name. A member segment is either {"fields": [{"namespace_uri": "", "local_name": "name", "value": "Ethernet1"}]} for direct-field AND equality, or {"value": "STANDARD"} for scalar-entry equality. The two member forms are mutually exclusive. An empty fields list can read all object entries but cannot bypass exactly-one-match mutation checks. Filter conditions compare direct leaf values with exact types; missing does not equal null. Nested field paths and regex/range/OR operators are unsupported. XML leaves with attributes compare their text/null value separately from metadata.

A node reference contains root and selector. Object field traversal and collection membership preserve stored containers. Reads may return multiple matches. Individual updates/deletes, creation parents, and relationship endpoints must resolve exactly one node; zero or multiple matches fail unchanged. Never accept private storage handles, full-path identities, or positional selectors. Identical duplicates are managed through whole-collection sync replacement.

## Relationships and deletion

Contains and Member are reserved structural edge types created with nodes. It forms an acyclic tree with one containing parent per non-root node. Generic relationship tasks manage additional typed directed links, which may carry arbitrary properties and do not imply containment, ownership, or inheritance. Reserve the structural containment type from generic relationship mutations. One additional relationship per source/target/type is supported initially; duplicate creation fails. Relationship type is a validated data property, never interpolated as schema/Cypher code.

Deleting a node without cascade fails if it has children. cascade=true explicitly deletes its containment subtree through Contains and Member edges. Delete incident generic relationships on removed nodes in the same transaction; do not delete nodes merely connected by non-containment links. Deleting a relationship never deletes endpoints. Missing exact relationships produce a clear failed result; get_relationships with no matches returns an empty list.

## Sync behavior

Parse XML through NssWorker methods using namespace-aware xmltodict, disabled entity expansion, and unchanged text. Preserve all dictionary containers and collection entries without static mappings, name keys, or flattening. Preserve attributes, empty versus absent elements, namespaces, duplicate counts, and leaf values. Array order is irrelevant.

Merge recursively updates same-shape supplied object fields and preserves omitted fields. Each supplied collection replaces all its entries; an omitted collection survives. A supplied shape change replaces only that field subtree. Explicit root replacement removes omitted fields. Remove incident generic links to removed nodes, leave other roots and surviving-node links intact, and do not promise collection-entry identity retention. Malformed XML/unsupported formats fail before mutation; absent entity keys are not an input error. No service ownership, diff, device transport, or reconciliation API is added.

## Inventory, errors, and exposure

Inventory uses service=nss and optional database_path, defaulting beneath the worker runtime base directory. One process owns the writable file. Keep the base SQLite job database separate.

Each mutation is atomic and serialized within the worker. Use parameterized Cypher and boundary validation. Existing Result.failed/errors/status report validation, not-found, ambiguity, or storage failure. No raw Cypher endpoint or new authentication system.

Read tasks have read-only MCP metadata. Mutations have accurate destructive/idempotent hints. FastAPI/MCP use existing discovery rather than handwritten routes. Documentation examples must be checked against the implemented runtime. Logs and job.event messages start lowercase, use severity, and do not dump supplied data or secrets.
