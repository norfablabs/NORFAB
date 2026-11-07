# NSS Initial Quickstart Validation

**Status**: Planned validation for baseline graph storage, sync_from, and generic CRUD. Tasks and the NSS suite do not exist yet. No NSS runtime tests have run during planning.

## Setup

Use Python 3.12 and existing uv/Invoke/Docker infrastructure. Add nssservice/full dependencies, nss worker registration, tests/services/nss/, an isolated worker inventory/runtime, and the NSS entry in the existing SUITES/Compose setup during implementation. No network device, Nornir, or Netbox is needed.

Run from repository root after implementation:

```bash
uv sync --locked --python 3.12 --extra full --extra docs
uv run inv docker-tests-build --suite=nss
uv run inv docker-tests-nss
uv run inv checks
uv run inv docs-build
```

Inspect the new JUnit and Markdown report: nonzero collected tests, zero failures/errors. The NSS command is a planned suite addition. An individual Invoke exit status alone is not proof of success.

## Sync supplied XML

Using an established client:

```python
result = client.run_job(
    "nss", "sync_from",
    workers=["nss-worker-1"],
    kwargs={
        "device": "nss-validation-device",
        "data": '<interfaces xmlns="http://openconfig.net/yang/interfaces"><interface><name>Ethernet1</name><config><mtu>1500</mtu><enabled>true</enabled></config></interface></interfaces>',
    },
)

result = client.run_job(
    "nss", "get_nodes",
    workers=["nss-worker-1"],
    kwargs={"root": "nss-validation-device", "recursive": True},
)
```

Expect preserved dictionary containment. For repeated interfaces: root -> interfaces object -> interface collection -> entry -> config -> mtu. For one interface, xmltodict produces an object instead of a collection. Preserve strings `1500` and `true`. Containers are stored nodes; XML attributes remain metadata. Result uses standard worker-keyed NorFab envelopes with failed=false and no private node IDs.

Repeat sync_from with only mtu=9000 in the same singleton object shape: merge preserves enabled. Separately supply a repeated-element array: that collection replaces all its entries. Omitted collections survive, and object/collection shape changes replace only that field subtree. Repeat using mode=replace: enabled is removed. Repeat identical XML: no duplicate nodes. Restart the worker and verify persistence through get_nodes.

## Generic CRUD validation

Use the [contracts](contracts/nss-tasks.md) to create a generic root via create_node with parent=null and node=null, then an entity and leaf beneath it. Read them using get_nodes, patch the leaf value/properties using update_node, and read again. Create a typed relationship with properties between two nodes, read it, patch its properties, and delete it. Endpoints must remain.

A delete_node call on a parent with children and cascade=false must fail without mutation. cascade=true deletes only that containment subtree and its incident links, preserving nodes reached solely through generic relationships. Remove each test-owned root in a finally block:

```python
result = client.run_job(
    "nss", "delete_node",
    workers=["nss-worker-1"],
    kwargs={"root": "nss-validation-device", "selector": [], "cascade": True},
)
```

## Focused acceptance checks

Keep tests small, use the public client and existing fixture, and keep test payloads inline.

| Check | Expected outcome |
| --- | --- |
| Worker lifecycle | NSS discovered with inventory/version tasks; other services and model imports work without graph dependencies. |
| Node CRUD | Create, read, update, delete and explicit cascade semantics work through public tasks. |
| Relationship CRUD | Type/properties persist; deleting links preserves endpoints; containment is protected. |
| Sync modes | Merge preserves omissions; replace removes them only beneath the selected root. |
| XML semantics | Namespaces distinguish types, prefix changes/reordering preserve content and duplicate counts, values remain unchanged, empty differs from absent. |
| Generic data | Non-device CRUD and non-OpenConfig XML require no static key mappings, name fields, or platform/schema rules. |
| Atomicity | Invalid XML and ambiguous individual mutations leave previous graph state intact. |
| Persistence | Data survives a normal worker restart. |

Verify existing FastAPI/MCP discovery exposes the typed initial tasks. Dedicated NFCLI commands, ownership, service declarations, drift, plan/apply, sync to devices, and NETCONF integration are outside this validation scope.

## Clarified CRUD checks

Add small public-client checks for direct-field AND selection, scalar-entry value selection, zero/ambiguous mutation rejection, and duplicate preservation. Updates must distinguish omitted value from explicit null and preserve unsupplied property keys. Root creation uses no child payload and duplicate roots fail. Collection replacement removes links to replaced entries but preserves unrelated endpoints. Do not test stable entity matching or add public JSON input.

Early create/read slices use a test-owned isolated runtime with normal teardown for cleanup before delete_node exists. Once deletion is available, use public deletion for root cleanup as well. Verify model/client imports without the NSS optional extra in an isolated temporary environment. Run lifecycle/CRUD checks on Windows and Linux where available and record unavailable platform checks as unverified rather than passing.
