---
tags:
  - nornir
  - netbox
---

# Nornir Create Host from NetBox Task

> task api name: `create_host_from_netbox`

Creates or replaces runtime Nornir hosts from explicit NetBox device names. The
Nornir service owns the inventory write, while the NetBox service supplies
Nornir-compatible host inventory through `get_nornir_inventory`.

Hosts created by this task are in-memory runtime hosts. They are not written to
YAML inventory files and disappear after worker restart unless startup inventory
or NetBox-backed refresh also includes them.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | Yes | NetBox device names to fetch and add as Nornir hosts. |
| `instance` | No | NetBox instance name to target. |
| `netbox_workers` | No | NetBox worker or workers to query. Defaults to `any`. CLI alias: `netbox-workers`. |
| `timeout` | No | Timeout for the NetBox inventory request. Defaults to `600` seconds. |
| `interfaces` | No | Include interface data, or provide interface task kwargs. When omitted, the worker `netbox` inventory option is used if configured. |
| `connections` | No | Include connection data, or provide connection task kwargs. When omitted, the worker `netbox` inventory option is used if configured. |
| `circuits` | No | Include circuit data, or provide circuit task kwargs. When omitted, the worker `netbox` inventory option is used if configured. |
| `bgp_peerings` | No | Include BGP peering data, or provide BGP task kwargs. CLI alias: `bgp-peerings`. |
| `nbdata` | No | Include NetBox device data in host data. When omitted, the worker `netbox` inventory option is used if configured. |
| `primary_ip` | No | Primary IP family to use for hostname. CLI alias: `primary-ip`. When omitted, the worker `netbox` inventory option is used if configured. |
| `cache` | No | Cache usage mode passed to NetBox retrieval tasks. Defaults to `True` in the task. |
| `groups` | No | Additional Nornir group names to attach to created hosts. |
| `replace` | No | Delete all current runtime hosts before loading the returned NetBox hosts. Defaults to `False`. |
| `dry_run` | No | Preview created, updated, and missing hosts without changing Nornir. CLI alias: `dry-run`. |
| `progress` | No | Emit progress events. Defaults to `True`. |

The task starts with the current Nornir worker `netbox` inventory section when
present, then overlays explicit task arguments for NetBox inventory-build
options such as `interfaces`, `connections`, `circuits`, `bgp_peerings`,
`nbdata`, `primary_ip`, and `cache`. The `devices` and `instance` arguments are
always taken from the task request.

## Output

Returns created, updated, and missing host or device names:

```python
{
    "created": ["leaf-1"],
    "updated": ["leaf-2"],
    "missing": ["leaf-3"],
}
```

`created` and `updated` use the returned Nornir host names. `missing` is
calculated by comparing requested device names with returned host names.

## Examples

=== "CLI"

    ```bash
    nf# nornir inventory create-host-from-netbox devices leaf-1 leaf-2 workers nornir-worker-1
    ```

    ```bash
    nf# nornir inventory create-host-from-netbox devices leaf-1 instance prod cache refresh workers nornir-worker-1
    ```

    ```bash
    nf# nornir inventory create-host-from-netbox devices leaf-1 interfaces connections workers nornir-worker-1
    ```

    ```bash
    nf# nornir inventory create-host-from-netbox devices leaf-1 leaf-2 replace workers nornir-worker-1
    ```

    ```bash
    nf# nornir inventory create-host-from-netbox devices leaf-1 dry-run workers nornir-worker-1
    ```

=== "Python"

    ```python
    import pprint

    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    result = client.run_job(
        "nornir",
        "create_host_from_netbox",
        workers=["nornir-worker-1"],
        kwargs={
            "devices": ["leaf-1", "leaf-2"],
            "interfaces": True,
            "connections": True,
            "netbox_workers": "any",
        },
    )

    pprint.pprint(result)
    nf.destroy()
    ```

## Notes

- The returned Nornir host name can differ from the NetBox device name when
  `config_context.nornir.name` is set in NetBox. The current task reports
  `created` and `updated` using returned Nornir host names.
- If some requested devices are missing, the task emits a warning and still
  creates or updates hosts for the devices NetBox returned.
- `replace=True` deletes all current runtime hosts with `InventoryFun` before
  loading the hosts returned by NetBox.
- `dry_run=True` sets the top-level result `dry_run` flag and does not mutate
  runtime inventory.
- Runtime inventory writes are delegated to `runtime_inventory` with a `load`
  action, so host create/replace semantics remain the existing runtime
  inventory semantics.

## Python API Reference

::: norfab.workers.nornir_worker.inventory_tasks.InventoryTasks.create_host_from_netbox
