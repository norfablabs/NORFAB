# ADR - Nornir SNMP Tasks

## Status

Proposed for review.

Date: 2026-06-14

## Context

NorFab's Nornir worker supports CLI, NETCONF, parsing, file copy, and generic
Nornir task execution, but it does not expose a dedicated SNMP task API or
interactive shell.

The installed project environment was inspected as the compatibility target:

- `nornir-salt==0.23.1`
- `puresnmp==2.0.1`
- Nornir-Salt task:
  `nornir_salt.plugins.tasks.puresnmp_call`
- Nornir-Salt connection:
  `nornir_salt.plugins.connections.PureSNMPPlugin`

The installed `puresnmp_call` task:

1. Opens the Nornir connection named `puresnmp`.
2. Calls a method on the puresnmp `PyWrapper`.
3. Resolves asynchronous methods and walk generators.
4. Normalizes returned values into dictionaries keyed by numeric OID where
   possible.
5. Converts `set` and `multiset` values to SNMP `OctetString` values.

The installed puresnmp client supports these operations:

- `get(oid)`
- `getnext(oid)`
- `multiget(oids)`
- `walk(oid, errors="strict")`
- `multiwalk(oids)`
- `bulkget(scalar_oids, repeating_oids, max_list_size=10)`
- `bulkwalk(oids, bulk_size=10)`
- `table(oid)`
- `bulktable(oid, bulk_size=10)`
- `set(oid, value)`
- `multiset(mappings)`

Only numeric OIDs are in scope. MIB name loading and symbolic OID resolution are
not provided by the installed puresnmp API.

## Decision

Add first-class, operation-specific NorFab tasks backed by Nornir-Salt's
`puresnmp_call` plugin.

Expose the complete set of operations supported by the installed
`puresnmp_call` task. The shared implementation makes the additional operations
low complexity, while operation-specific models and MCP metadata keep reads and
writes explicit.

Do not expose a public arbitrary `call` argument in the initial implementation.
Operation-specific tasks provide clearer validation, safer MCP annotations,
better FastAPI schemas, and a discoverable NFCLI command tree.

Use one internal SNMP runner to share host filtering, Nornir processors,
locking, result serialization, and connection cleanup.

## Public Task API

Add these Nornir service tasks:

| Task | Required arguments | Optional arguments | State |
| --- | --- | --- | --- |
| `snmp_get` | `oid` | Common Nornir arguments | Read-only |
| `snmp_getnext` | `oid` | Common Nornir arguments | Read-only |
| `snmp_multiget` | `oids` | Common Nornir arguments | Read-only |
| `snmp_walk` | `oid` | `errors`, common arguments | Read-only |
| `snmp_multiwalk` | `oids` | Common Nornir arguments | Read-only |
| `snmp_bulkget` | `repeating_oids` | `scalar_oids`, `max_list_size`, common arguments | Read-only |
| `snmp_bulkwalk` | `oids` | `bulk_size`, common arguments | Read-only |
| `snmp_table` | `oid` | Common Nornir arguments | Read-only |
| `snmp_bulktable` | `oid` | `bulk_size`, common arguments | Read-only |
| `snmp_set` | `oid`, `value` | Common Nornir arguments | State-changing |
| `snmp_multiset` | `mappings` | Common Nornir arguments | State-changing |

Argument names must match the installed puresnmp methods. In particular,
`snmp_bulkget` uses `max_list_size`, while `snmp_bulkwalk` and
`snmp_bulktable` use `bulk_size`.

### Proposed Signatures

```python
def snmp_get(self, job: Job, oid: str, **kwargs: Any) -> Result

def snmp_getnext(self, job: Job, oid: str, **kwargs: Any) -> Result

def snmp_multiget(
    self,
    job: Job,
    oids: list[str],
    **kwargs: Any,
) -> Result

def snmp_walk(
    self,
    job: Job,
    oid: str,
    errors: str = "strict",
    **kwargs: Any,
) -> Result

def snmp_multiwalk(
    self,
    job: Job,
    oids: list[str],
    **kwargs: Any,
) -> Result

def snmp_bulkget(
    self,
    job: Job,
    repeating_oids: list[str],
    scalar_oids: list[str] = None,
    max_list_size: int = 10,
    **kwargs: Any,
) -> Result

def snmp_bulkwalk(
    self,
    job: Job,
    oids: list[str],
    bulk_size: int = 10,
    **kwargs: Any,
) -> Result

def snmp_table(self, job: Job, oid: str, **kwargs: Any) -> Result

def snmp_bulktable(
    self,
    job: Job,
    oid: str,
    bulk_size: int = 10,
    **kwargs: Any,
) -> Result

def snmp_set(
    self,
    job: Job,
    oid: str,
    value: str,
    **kwargs: Any,
) -> Result

def snmp_multiset(
    self,
    job: Job,
    mappings: dict[str, Any],
    **kwargs: Any,
) -> Result
```

## Worker Architecture

Create `norfab/workers/nornir_worker/snmp_task.py` with a `SnmpTask` mixin.
Register the mixin on `NornirWorker`.

Import the Nornir-Salt plugin at module load time, following the pattern used by
`cli_task.py`:

```python
from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import puresnmp_call
```

Do not store the plugin as an import-path string and do not dynamically import
it at runtime. The imported `puresnmp_call` callable must be passed directly to
`nr.run`.

The internal runner should:

1. Pop `to_dict` and `add_details` from task keyword arguments.
2. Create a `Result` with a task name matching the public operation and an
   initial dictionary or list payload matching `to_dict`.
3. Extract and apply Nornir-Salt `FFun` host filters through
   `filter_hosts_and_validate`.
4. Return `status="no_match"` when no hosts match.
5. Add standard Nornir processors through `_add_processors`.
6. Acquire `connections_lock`.
7. Run the imported `puresnmp_call` callable with the fixed operation name:

   ```python
   result = nr.run(task=puresnmp_call, call=call, **kwargs)
   ```

8. Release `connections_lock`.
9. Serialize with `ResultSerializer`.
10. Update the `puresnmp` connection use timestamp and run watchdog cleanup.
11. Preserve `to_dict`, `add_details`, progress events, RetryRunner options, and
   other common Nornir behavior.

The shared runner should follow this structure:

```python
def _run_snmp(self, job: Job, call: str, **kwargs: Any) -> Result:
    add_details = kwargs.pop("add_details", False)
    to_dict = kwargs.pop("to_dict", True)
    ret = Result(
        task=f"{self.name}:snmp_{call}",
        result={} if to_dict else [],
    )

    filtered_nornir, _ = self.filter_hosts_and_validate(kwargs, ret)
    if ret.status == "no_match":
        return ret

    nr = self._add_processors(filtered_nornir, kwargs, job)

    with self.connections_lock:
        result = nr.run(task=puresnmp_call, call=call, **kwargs)

    ret.failed = result.failed
    ret.result = ResultSerializer(
        result,
        to_dict=to_dict,
        add_details=add_details,
    )

    self.watchdog.connections_update(nr, "puresnmp")
    self.watchdog.connections_clean()
    return ret
```

The implementation must not invoke `self.task(...)`. Calling the generic public
task would add unnecessary dynamic import handling, nested task validation,
generic task naming, and a second abstraction over behavior already required by
the SNMP task itself.

## Pydantic Models

Add SNMP models to
`norfab/workers/nornir_worker/nornir_models.py`.

Proposed models:

- `SnmpGetInput`
- `SnmpGetNextInput`
- `SnmpMultiGetInput`
- `SnmpWalkInput`
- `SnmpMultiWalkInput`
- `SnmpBulkGetInput`
- `SnmpBulkWalkInput`
- `SnmpTableInput`
- `SnmpBulkTableInput`
- `SnmpSetInput`
- `SnmpMultiSetInput`
- `SnmpResult`

All input models inherit `NornirCommonArgs`, use strict scalar types, include
descriptions and examples, and use aliases for hyphenated CLI names.

Validation rules:

- OIDs are required non-empty strings.
- OID lists must contain at least one item.
- `bulk_size` and `max_list_size` must be greater than zero.
- `snmp_bulkget` requires at least one scalar or repeating OID; the proposed
  public signature requires `repeating_oids`.
- `snmp_multiset.mappings` must contain at least one item.
- `snmp_walk.errors` accepts `strict` or `warn`.

`SnmpResult` should retain the dynamic serialized Nornir result shape:

```python
Union[dict[StrictStr, Any], list[Any]]
```

The exact payload varies by operation and by `to_dict` or `add_details`.

## Result Shape

With default serialization, results are expected to be grouped by host and
operation:

```yaml
ceos-spine-1:
  get:
    1.3.6.1.2.1.1.5.0: ceos-spine-1
```

A walk returns OID/value pairs:

```yaml
ceos-spine-1:
  walk:
    1.3.6.1.2.1.1.1.0: Arista Networks EOS
    1.3.6.1.2.1.1.5.0: ceos-spine-1
```

`bulkwalk` returns OID/value pairs like `walk`, using GETBULK for more efficient
collection:

```yaml
ceos-spine-1:
  bulkwalk:
    1.3.6.1.2.1.2.2.1.2.1: Ethernet1
    1.3.6.1.2.1.2.2.1.2.2: Ethernet2
```

`bulkget` returns separate scalar and repeating collections:

```yaml
ceos-spine-1:
  bulkget:
    scalars:
      1.3.6.1.2.1.1.5.0: ceos-spine-1
    listing:
      1.3.6.1.2.1.2.2.1.2.1: Ethernet1
```

Table operations return a list of normalized rows under the requested root
OID. Set operations return the value written, keyed by OID.

## MCP Safety Metadata

Read operations use:

```python
{
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}
```

`snmp_set` and `snmp_multiset` use:

```python
{
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": True,
    "openWorldHint": True,
}
```

Repeating the same write is idempotent, but it can change live device state and
must remain visibly destructive.

## NFCLI Shell

Create
`norfab/clients/nfcli_shell/nornir/nornir_picle_shell_snmp.py` and register it
under `NornirServiceCommands`.

Proposed command tree:

```text
nornir snmp
├── get
├── get-next
├── multi-get
├── walk
├── multi-walk
├── bulk-get
├── bulk-walk
├── table
├── bulk-table
├── set
└── multi-set
```

Examples:

```text
nf# nornir snmp get oid 1.3.6.1.2.1.1.5.0 FC spine
nf# nornir snmp walk oid 1.3.6.1.2.1.1 FC leaf
nf# nornir snmp multi-get oids 1.3.6.1.2.1.1.1.0 1.3.6.1.2.1.1.5.0
nf# nornir snmp bulk-walk oids 1.3.6.1.2.1.2.2 bulk-size 20
nf# nornir snmp table oid 1.3.6.1.2.1.2.2
nf# nornir snmp set oid 1.3.6.1.2.1.1.6.0 value "Brisbane lab"
```

The `multi-set` shell accepts a JSON object and converts it to a dictionary
before job submission:

```text
nf# nornir snmp multi-set mappings '{"1.3.6.1.2.1.1.6.0":"Brisbane lab"}'
```

## Nornir Inventory

Add the shared puresnmp connection settings to the `eos_params` group in
`tests/nf_tests_inventory/nornir/common.yaml`:

```yaml
groups:
  eos_params:
    connection_options:
      puresnmp:
        extras:
          version: v2c
          community: norfab
```

Add a host-specific UDP port to every cEOS host in worker inventories:

```yaml
connection_options:
  puresnmp:
    port: 11610
```

Proposed mapping:

| Worker | Host | Host UDP port | Container UDP port |
| --- | --- | --- | --- |
| `nornir-worker-1` | `ceos-spine-1` | `11610` | `161` |
| `nornir-worker-1` | `ceos-spine-2` | `11611` | `161` |
| `nornir-worker-2` | `ceos-leaf-1` | `11612` | `161` |
| `nornir-worker-2` | `ceos-leaf-2` | `11613` | `161` |
| `nornir-worker-2` | `ceos-leaf-3` | `11614` | `161` |

This follows the existing test inventory pattern where all devices use the lab
host address and unique published ports.

## Containerlab Changes

Update
`tests/nf_tests_inventory/containerlab/norfab-network-lab/norfab-network-lab.yml`
to publish UDP/161:

```yaml
ports:
  - 11610:161/udp
```

Use the corresponding host port from the mapping above for each cEOS node.

Add this isolated-lab configuration to all five cEOS startup configurations:

```text
snmp-server community norfab rw
```

The read-write community is limited to the isolated integration lab so tests can
exercise `snmp_set` and `snmp_multiset`. Production documentation must recommend
least-privilege access and SNMPv3.

## Documentation

Create:

- `docs/workers/nornir/services_nornir_service_tasks_snmp.md`

Add it to the Nornir task navigation in `mkdocs.yml`.

The page should include:

1. Purpose and supported SNMP versions.
2. Nornir `puresnmp` connection inventory for v1, v2c, and v3.
3. Input and output reference for every operation.
4. NFCLI and Python examples.
5. Filtering and processor examples.
6. SNMPv3 crypto dependency notes.
7. The installed Nornir-Salt behavior that converts set values to
   `OctetString`.
8. Troubleshooting for timeout, community mismatch, UDP port mapping, and
   unsupported OIDs.

Add a changelog entry only when implementation is approved and completed.

## Test Plan

### Model and Registration Tests

- Import every SNMP input and result model.
- Generate JSON schemas.
- Assert required fields, aliases, defaults, and numeric constraints.
- Assert all public SNMP tasks are registered.
- Assert read and write MCP annotations differ correctly.

### Worker Unit Tests

Mock `puresnmp_call` and verify every public task forwards:

- The correct `call` value.
- Exact operation arguments.
- Host filters.
- Processor arguments.
- `to_dict` and `add_details`.
- No-match handling.
- The imported callable is supplied directly to `nr.run`.
- `self.task` is never called.
- `connections_lock` surrounds `nr.run`.
- The watchdog is updated using connection name `puresnmp`.

These tests do not require a running lab.

### cEOS Integration Tests

Use `nornir-worker-1` and `nornir-worker-2`.

| Test | Verification |
| --- | --- |
| `snmp_get` | `sysName.0` matches each cEOS hostname |
| `snmp_getnext` | Returns an OID after the requested OID |
| `snmp_multiget` | Returns `sysDescr.0` and `sysName.0` |
| `snmp_walk` | Walks the system subtree |
| `snmp_multiwalk` | Walks system and interface subtrees |
| `snmp_bulkget` | Returns scalar and interface column data |
| `snmp_bulkwalk` | Returns interface OID/value pairs |
| `snmp_table` | Returns interface table rows |
| `snmp_bulktable` | Returns interface table rows using GETBULK |
| Host filters | `FC`, `FL`, and worker targeting restrict results |
| No match | Returns `status="no_match"` without failure |
| Invalid model | Missing OID and invalid bulk sizes fail validation |

Write tests must avoid leaving state behind:

1. Read and save `sysLocation.0` and `sysContact.0`.
2. Run `snmp_set` and verify the value using `snmp_get`.
3. Run `snmp_multiset` and verify both values.
4. Restore original values in `finally` blocks.

### NFCLI Tests

- Assert the `nornir snmp` subtree is mounted.
- Run representative read and write commands.
- Validate list parsing for `oids`.
- Validate JSON parsing for `mappings`.
- Confirm hyphenated commands and arguments map to task field names.

## Security Considerations

- SNMPv1 and SNMPv2c communities are clear-text credentials.
- Production documentation should recommend SNMPv3 where supported.
- SNMPv3 requires the puresnmp crypto extra already included by the project's
  Nornir service dependency.
- Community strings and SNMPv3 secrets should come from environment-backed or
  protected inventory, not committed production files.
- `snmp_set` and `snmp_multiset` must be documented and annotated as
  state-changing.
- The installed Nornir-Salt plugin converts set values to `OctetString`.
  Integer, counter, gauge, IP address, and OID-typed writes remain unsupported
  by the first-pass NorFab API.

## Alternatives Considered

### One Generic `snmp` Task

Expose `call` plus arbitrary keyword arguments, matching `netconf`.

Rejected for the initial implementation because it produces a broad schema,
weak validation, unsafe MCP metadata, and a less discoverable CLI.

### Use the Existing Generic `task` API Only

Users can already call:

```python
client.run_job(
    "nornir",
    "task",
    kwargs={
        "plugin": "nornir_salt.plugins.tasks.puresnmp_call",
        "call": "get",
        "oid": "1.3.6.1.2.1.1.5.0",
    },
)
```

Rejected as the primary interface because it has no SNMP-specific models,
documentation, shell, safety metadata, or guided inventory configuration.

### Implement SNMP Directly Against puresnmp

Rejected because Nornir-Salt already provides the connection plugin,
asynchronous handling, and result normalization used by the rest of this
ecosystem.

### Limit the First Pass to Common Read Operations

Considered using only `get`, `multiget`, `walk`, and `bulkwalk`.

Rejected because the remaining wrappers are small once the shared runner,
inventory, shell, and test lab exist. Implementing the full installed operation
set avoids a second API expansion while operation-specific models and metadata
still make writes explicit.

## Consequences

Positive:

- SNMP becomes a discoverable NorFab capability across Python, FastAPI, MCP,
  and NFCLI.
- Operation-specific validation catches incorrect arguments before device I/O.
- Existing Nornir filters and processors work consistently.
- cEOS integration tests exercise real UDP SNMP behavior.

Negative:

- Eleven public tasks add API and documentation surface.
- The cEOS test lab needs five additional UDP port mappings.
- SNMP write support is limited to values converted to `OctetString`.
- Real-device integration tests depend on the cEOS SNMP agent and published UDP
  ports being available.

## Proposed File Changes

| File | Proposed change |
| --- | --- |
| `norfab/workers/nornir_worker/snmp_task.py` | New shared runner and public SNMP tasks |
| `norfab/workers/nornir_worker/nornir_models.py` | Add operation-specific input and result models |
| `norfab/workers/nornir_worker/nornir_worker.py` | Register `SnmpTask` mixin |
| `norfab/clients/nfcli_shell/nornir/nornir_picle_shell_snmp.py` | Add SNMP shell subtree |
| `norfab/clients/nfcli_shell/nornir/nornir_picle_shell.py` | Register SNMP shell |
| `tests/nf_tests_inventory/nornir/common.yaml` | Add common puresnmp v2c parameters |
| `tests/nf_tests_inventory/nornir/nornir-worker-1.yaml` | Add spine SNMP ports |
| `tests/nf_tests_inventory/nornir/nornir-worker-2.yaml` | Add leaf SNMP ports |
| `tests/nf_tests_inventory/containerlab/norfab-network-lab/norfab-network-lab.yml` | Publish UDP/161 |
| `tests/nf_tests_inventory/containerlab/norfab-network-lab/ceos-*.txt` | Enable test SNMP community |
| `tests/services/nornir/test_snmp.py` | Add worker and cEOS integration tests |
| `tests/nfcli/test_shell_client.py` | Add SNMP shell tests |
| `docs/workers/nornir/services_nornir_service_tasks_snmp.md` | Add user documentation |
| `mkdocs.yml` | Add SNMP task page to navigation |
| `docs/norfab_changelog.md` | Record feature after implementation |

## Approval Decisions

1. Approve operation-specific public tasks instead of one generic `snmp` task.
2. Approve all eleven installed operations, including `snmp_set` and
   `snmp_multiset`.
3. Approve `snmp_task.py` as the filename, following existing worker naming,
   rather than `nornir_snmp.py`.
4. Approve SNMPv2c for the isolated cEOS integration lab.
5. Approve a test-only read-write `norfab` community and restoration of
   modified OIDs after write tests.
6. Approve host UDP ports `11610` through `11614`.
7. Confirm that symbolic MIB names and typed SNMP write values remain outside
   the initial scope.

No implementation should proceed until these decisions are approved.
