# ADR - Nornir Create Hosts from NetBox Devices

## Status

Proposed for review.

Date: 2026-07-26

## Context

NorFab already has three related inventory paths:

- `norfab/core/inventory.py` loads static YAML worker inventory at startup.
- Nornir `runtime_inventory` can create, update, read, and delete in-memory
  Nornir hosts through `InventoryFun`.
- Nornir `nornir_inventory_load_netbox` can load NetBox data during worker
  refresh, but it is driven by the worker's `netbox` inventory configuration
  and does not provide an explicit command for adding named NetBox devices on
  demand.

NetBox already exposes `get_nornir_inventory`, which accepts `devices` and
returns a Nornir-compatible inventory:

```python
{
    "hosts": {
        "leaf-1": {
            "hostname": "192.0.2.11",
            "platform": "eos",
            "groups": ["lab"],
            "data": {...},
        },
    }
}
```

The missing workflow is a Nornir inventory command that accepts a list of
NetBox device names, asks the NetBox service to build host inventory for those
devices, and adds the resulting hosts into the running Nornir inventory.

This ADR proposes that workflow as a Nornir worker task and an NFCLI shell
command.

## Decision

Add an explicit Nornir inventory task for creating runtime Nornir hosts from
NetBox device data.

Recommended public task name:

```text
create_host_from_netbox
```

Recommended shell command:

```bash
nf# nornir inventory create-host-from-netbox devices leaf-1 leaf-2 workers nornir-worker-1
```

Use the Nornir service as the owner of the write operation because the changed
state is the Nornir runtime inventory. Reuse the NetBox service only as the
source of Nornir-compatible host data through `get_nornir_inventory`.

Do not change `norfab/core/inventory.py`. That module remains responsible for
startup YAML inventory loading. This feature changes runtime Nornir inventory
state only and does not write inventory YAML files.

## Naming

Use `create_host_from_netbox` as the task name. The Nornir service boundary
already comes from the submitted service name, so the task does not need a
`nornir_inventory_` prefix.

Keep the existing `nornir_inventory_load_netbox` task for inventory-configured
startup and refresh behavior. The new task is for explicit on-demand device
creation.

## Proposed Task Interface

```python
@Task(
    fastapi={"methods": ["POST"]},
    input=CreateHostFromNetboxInput,
    output=CreateHostFromNetboxResult,
    mcp={
        "annotations": {
            "title": "Create Nornir Hosts from NetBox Devices",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": True,
        }
    },
)
def create_host_from_netbox(
    self,
    job: Job,
    devices: list[str],
    instance: str | None = None,
    netbox_workers: str | list[str] | None = None,
    timeout: int | None = None,
    interfaces: bool | dict | None = None,
    connections: bool | dict | None = None,
    circuits: bool | dict | None = None,
    bgp_peerings: bool | dict | None = None,
    nbdata: bool | None = None,
    primary_ip: str | None = None,
    cache: bool | str | None = None,
    groups: list[str] | None = None,
    dry_run: bool | None = None,
    progress: bool | None = None,
) -> Result:
    ...
```

### Input Model

Create `CreateHostFromNetboxInput` in
`norfab/workers/nornir_worker/nornir_models.py`.

All request validation must happen in the Pydantic input model. The task body
should assume it receives validated values. Invalid input, including missing or
empty `devices`, should surface as a Pydantic validation error rather than a
task-level failed `Result`.

### Model Reuse Evaluation

Existing models were evaluated before adding a Nornir-specific input model:

| Existing model | Reuse value | Why not use directly |
| --- | --- | --- |
| `netbox_worker.netbox_models.GetNornirInventoryInput` | Best field match for `devices`, `instance`, `interfaces`, `connections`, `circuits`, `bgp_peerings`, `nbdata`, `primary_ip`, and `cache`. | Its defaults are concrete values (`False`, `True`, `"ip4"`), but this task needs `None` sentinels so values can default from the current Nornir worker `netbox` inventory section. It also includes `filters`, which this create-host workflow should not expose initially. |
| `netbox_worker.netbox_models.NetboxCommonArgs` | Provides `instance` and `dry_run` aliases. | It includes NetBox task concepts such as `branch` that are not accepted by `get_nornir_inventory`, and still does not cover most inventory-build fields. |
| `nornir_worker.nornir_models.RuntimeCreateHostInput` | Models the final Nornir host shape used by `runtime_inventory create_host`. | It describes direct host creation (`name`, `hostname`, `platform`, credentials, data), not NetBox device lookup. The NetBox-derived host fields are produced internally by `get_nornir_inventory`. |
| `nornir_worker.nornir_models.NornirInventoryLoadNetboxInput` | Existing NetBox inventory-load task model. | It only exposes `progress`; startup load behavior is driven from worker inventory and is too coarse for explicit device onboarding. |
| `nornir_worker.nornir_models.NornirInventoryLoadContainerlabInput` | Good source-load pattern for `groups`, `dry_run`, and source workers. | Containerlab-specific and does not include NetBox inventory-build options. |

Recommendation:

- Keep `CreateHostFromNetboxInput` as a local Nornir worker model, but mirror
  the compatible field names, aliases, and descriptions from
  `GetNornirInventoryInput` where possible.
- Do not import `GetNornirInventoryInput` into `nornir_models.py` for the first
  implementation. It would couple the Nornir worker model module to the NetBox
  worker package while still requiring most fields to be overridden.
- Use `None` defaults for inherited NetBox inventory options. During task
  execution, resolve the effective `get_nornir_inventory` kwargs from the
  Nornir worker `netbox` inventory section and explicit task arguments.
- If the same source-inventory options are needed by more services later,
  extract a shared base model into a neutral module instead of importing models
  across worker packages.

Fields:

| Field | Required | Default | Description |
| --- | ---: | --- | --- |
| `devices` | Yes | None | Non-empty list of NetBox device names to fetch and add as Nornir hosts. |
| `instance` | No | `netbox.instance`, else `None` | NetBox instance name. |
| `netbox_workers` | No | `netbox.netbox_workers`, else `"any"` | NetBox worker or workers to query. Shell alias: `netbox-workers`. |
| `timeout` | No | `netbox.timeout`, else `100` | Timeout for the NetBox inventory request. |
| `interfaces` | No | `netbox.interfaces`, else `False` | Include interface data in host `data`. |
| `connections` | No | `netbox.connections`, else `False` | Include connection data in host `data`. |
| `circuits` | No | `netbox.circuits`, else `False` | Include circuit data in host `data`. |
| `bgp_peerings` | No | `netbox.bgp_peerings`, else `False` | Include BGP peerings in host `data`. Shell alias: `bgp-peerings`. |
| `nbdata` | No | `netbox.nbdata`, else `True` | Include NetBox device data in host `data`. |
| `primary_ip` | No | `netbox.primary_ip`, else `"ip4"` | Primary IP family to use as host `hostname`. Shell alias: `primary-ip`. |
| `cache` | No | `netbox.cache`, else `None` | Cache mode passed to NetBox data retrieval tasks. |
| `groups` | No | `netbox.groups`, else `None` | Additional Nornir groups to attach to created hosts. |
| `dry_run` | No | `netbox.dry_run`, else `False` | Return the NetBox-derived inventory without changing Nornir. Shell alias: `dry-run`. |
| `progress` | No | `netbox.progress`, else `False` | Emit progress events. |

### Default Resolution

The task should default its NetBox inventory options from the current Nornir
worker inventory `netbox` section:

```yaml
netbox:
  instance: prod
  interfaces: true
  connections: true
  circuits: false
  bgp_peerings: false
  nbdata: true
  primary_ip: ip4
  cache: refresh
  groups:
    - netbox
```

Resolution order:

1. Start with a copy of `self.nornir_worker_inventory["netbox"]` when it is a
   dictionary.
2. If the worker has no `netbox` section, or if it has `netbox: true`, start
   with an empty dictionary.
3. Overlay only task arguments whose value is not `None`. Ignore task arguments
   with value `None` so the worker `netbox` section keeps control.
4. Force `devices` from the task argument so the command only creates the
   requested NetBox devices.
5. Apply hard-coded task defaults only when neither the worker `netbox` section
   nor the task arguments define a value:

   ```python
   {
       "instance": None,
       "netbox_workers": "any",
       "timeout": 100,
       "interfaces": False,
       "connections": False,
       "circuits": False,
       "bgp_peerings": False,
       "nbdata": True,
       "primary_ip": "ip4",
       "cache": None,
       "groups": None,
       "dry_run": False,
       "progress": False,
   }
   ```

Do not maintain an allowlist of inherited `netbox` keys. Use the worker
`netbox` section as-is and substitute only task input values that are not
`None`. Split out task-control keys such as `netbox_workers`, `timeout`,
`dry_run`, and `progress` for local task behavior; pass the remaining effective
configuration to NetBox `get_nornir_inventory`.

Use `None` as the omitted-value sentinel in the task and shell models so an
explicit `False` argument overrides a `True` value from the worker inventory.

Recommended Pydantic constraints:

- `devices` must be a non-empty list of strings.
- `groups` may be a string or list of strings in the shell model and must be
  normalized to a list before calling the task.
- `interfaces`, `connections`, `circuits`, and `bgp_peerings` accept either a
  boolean or a dictionary of downstream task arguments.
- `cache` accepts `None`, booleans, or the cache modes supported by NetBox
  `get_nornir_inventory`.

### Result Model

Create `CreateHostFromNetboxResult` in
`norfab/workers/nornir_worker/nornir_models.py`.

Proposed result shape:

```python
{
    "created": ["leaf-1"],
    "updated": ["leaf-2"],
    "missing": ["leaf-3"],
}
```

Notes:

- `created` contains hosts that did not exist in the Nornir runtime inventory.
- `updated` contains hosts that already existed and were replaced by the
  NetBox-derived host data.
- `missing` contains requested NetBox device names that were not represented in
  the returned inventory.
- Do not include `dry_run` inside `Result.result`. Set the top-level
  `Result.dry_run` attribute to `True` when no Nornir runtime inventory
  mutation was made.

## Implementation Flow

1. Build NetBox `get_nornir_inventory` kwargs by resolving defaults from the
   current Nornir worker `netbox` inventory section and overlaying task inputs.
2. Call the NetBox service:

   ```python
   nb_inventory_data = self.client.run_job(
       service="netbox",
       task="get_nornir_inventory",
       workers=netbox_workers,
       kwargs=netbox_kwargs,
       timeout=timeout,
   )
   ```

3. With default `netbox_workers="any"`, expect only one NetBox worker result.
4. If NetBox returns no successful result with `result["hosts"]`, fail the task.
5. Determine `missing` by comparing requested NetBox device names with returned
   hosts. If `config_context.nornir.name` renames a host, use NetBox device
   identity from returned `host["data"]` when available and fall back to the
   returned host key.
6. Determine predicted `created` and `updated` before mutation by comparing the
   returned host names with current `self.nr.inventory.hosts`.
7. If all requested devices are missing, fail the task.
8. If `dry_run=True`, return `created`, `updated`, and `missing` without
   changing Nornir, and set the top-level `Result.dry_run=True`.
9. Build a `runtime_inventory` `load` payload with one `create_host` item per
   returned host:

   ```python
   inventory_actions = [
       {"call": "create_host", "name": "leaf-1", **host_data},
       {"call": "create_host", "name": "leaf-2", **host_data},
   ]
   ```

10. Call the existing Nornir runtime inventory task:

   ```python
   inventory_result = self.runtime_inventory(
       job=job,
       action="load",
       data=inventory_actions,
   )
   ```

   `runtime_inventory` delegates to Nornir-Salt `InventoryFun`. Its
   `create_host` action creates a new host or replaces an existing host and
   returns `{host_name: True}`. Its `load` action returns a list of these
   per-host dictionaries.
11. Use `inventory_result.result` to confirm the final list of created or
   updated host names. Do not add separate group merge or connection handling
   logic in `create_host_from_netbox`; runtime inventory behavior owns host
   replacement semantics.
12. Return only `created`, `updated`, and `missing` in `Result.result`.

The task should not call `init_nornir()` by default. A targeted runtime
inventory create avoids closing active connections for unrelated hosts.

## Shell Command Shape

Add a new command alongside the existing `create-host` command:

```bash
nf# nornir inventory create-host-from-netbox devices leaf-1 leaf-2 workers nornir-worker-1
```

Leave the existing direct host command unchanged:

```bash
nf# nornir inventory create-host name scratch hostname 192.0.2.10
```

Expanded examples:

```bash
# Create two hosts on one Nornir worker from the default NetBox instance
nf# nornir inventory create-host-from-netbox devices leaf-1 leaf-2 workers nornir-worker-1

# Target a specific NetBox instance and refresh cache
nf# nornir inventory create-host-from-netbox devices leaf-1 instance prod cache refresh workers nornir-worker-1

# Include interface and connection data
nf# nornir inventory create-host-from-netbox devices leaf-1 interfaces connections workers nornir-worker-1

# Preview generated host inventory without changing Nornir
nf# nornir inventory create-host-from-netbox devices leaf-1 dry-run workers nornir-worker-1
```

Proposed NFCLI model changes:

- Add `InventoryCreateHostFromNetboxModel`.
- Register it on `NornirInventoryShell` as `create_host_from_netbox` with alias
  `create-host-from-netbox`.
- Do not modify the existing `CreateHostModel` or the existing `create-host`
  command shape.

## Error Handling

- Input errors are handled by `CreateHostFromNetboxInput` validation and should
  return validation errors before task execution.
- If NetBox returns no inventory data, return `failed=True` with an error.
- If no returned host maps to the requested devices, return `failed=True`.
- If some requested devices are missing, add them to `missing` and emit a
  warning event, but still create hosts for devices that were returned.
- If `config_context.nornir.name` renames a host, use the returned Nornir host
  name for creation and use NetBox `nbdata.name` when available to detect
  whether the requested device was represented.
- Preserve current runtime inventory semantics: created hosts are in-memory and
  are not written to YAML inventory files.

## Files to Change

- `norfab/workers/nornir_worker/inventory_tasks.py` - add the task.
- `norfab/workers/nornir_worker/nornir_models.py` - add input and result models.
- `norfab/clients/nfcli_shell/nornir/nornir_picle_shell_inventory.py` - add the
  shell command model.
- `docs/workers/nornir/services_nornir_service_tasks_create_host_from_netbox.md`
  - new task documentation page.
- `mkdocs.yml` - add the new task documentation page to the Nornir service
  task navigation.
- `tests/services/nornir/test_runtime_inventory.py` or
  `tests/services/nornir/test_worker.py` - add service tests.
- `tests/nfcli/` - add shell parsing coverage for the new command shape.

## Testing

Add focused tests for:

Tests should use live NorFab service fixtures and a reachable NetBox test
service. Do not mock the NetBox or Nornir worker behavior for this feature.

1. Creating one host from a NetBox device name.
2. Creating multiple hosts from a device list.
3. `dry_run=True` returns predicted `created`, `updated`, and `missing`, sets
   top-level `Result.dry_run=True`, and does not change Nornir inventory.
4. Existing host is replaced and reported under `updated`.
5. Missing NetBox device is reported under `missing` while valid devices still
   create hosts.
6. Shell `groups` accepts one or more values and is normalized to a list before
   task submission.
7. NFCLI parses:

   ```bash
   nornir inventory create-host-from-netbox devices leaf-1 leaf-2 workers nornir-worker-1
   ```

## Consequences

Benefits:

- Provides the requested explicit device onboarding workflow.
- Keeps NetBox as source of truth for host connection data.
- Reuses the existing NetBox `get_nornir_inventory` task and Nornir runtime
  inventory behavior.
- Avoids modifying startup inventory loading or writing inventory files.

Tradeoffs:

- Hosts created this way are runtime-only and disappear after worker restart or
  full inventory refresh unless the worker's static inventory or NetBox-backed
  startup configuration also includes them.
- The command depends on both Nornir and NetBox workers being reachable.
- Host names may differ from NetBox device names when
  `config_context.nornir.name` is set.
