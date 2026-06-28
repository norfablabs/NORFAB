---
tags:
  - netbox
---

# Netbox Get Nornir Inventory Task

> task api name: `get_nornir_inventory`

Builds a Nornir inventory from NetBox device data. Nornir workers can call this task during startup to source hosts, host data, platform, hostname, interfaces, connections, circuits, and BGP peerings from NetBox.

![Netbox get Nornir inventory](../../images/Netbox_get_nornir_inventory.jpg)

## How It Works

1. Nornir worker or client submits a `get_nornir_inventory` request to the NetBox worker
2. NetBox worker checks the target NetBox instance status
3. NetBox worker fetches device data with `get_devices`
4. NetBox worker builds a Nornir `hosts` inventory from NetBox device data and config context
5. Optional interface, connection, circuit, and BGP peering datasets are added to host data
6. NetBox worker returns the assembled Nornir inventory

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `filters` | No | NetBox device filter dictionaries |
| `devices` | No | Device names to include in inventory |
| `instance` | No | NetBox instance name to target |
| `interfaces` | No | `True` to include interfaces, or a dictionary of `get_interfaces` kwargs |
| `connections` | No | `True` to include connections, or a dictionary of `get_connections` kwargs |
| `circuits` | No | `True` to include circuits, or a dictionary of `get_circuits` kwargs |
| `bgp_peerings` | No | `True` to include BGP peerings, or a dictionary of `get_bgp_peerings` kwargs |
| `nbdata` | No | Include NetBox device data in host data, default `True` |
| `primary_ip` | No | Primary IP family to use for hostname, default `ip4` |
| `cache` | No | Cache usage mode passed to supporting data retrieval tasks |

## Output

Returns a Nornir inventory dictionary:

```python
{
    "hosts": {
        "ceos-leaf-1": {
            "hostname": "192.0.2.11",
            "platform": "eos",
            "groups": ["lab"],
            "data": {
                "site": {"name": "lab"},
                "interfaces": {},
                "connections": {},
            },
        },
    },
}
```

## Notes / Gotchas

- The host name can be overridden by `config_context.nornir.name` on the NetBox device.
- If host `platform` or `hostname` is not present in NetBox config context, the task derives them from NetBox platform and primary IP fields.
- `interfaces`, `connections`, `circuits`, and `bgp_peerings` can be `True` or dictionaries with kwargs for the related task.
- The current NFCLI command model does not expose `get_nornir_inventory` directly under `netbox get`, so this task is commonly used by Nornir worker startup or Python API callers.

## Examples

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # build inventory for specific devices
    result = client.run_job(
        "netbox",
        "get_nornir_inventory",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
        },
    )

    # build inventory from NetBox filters
    result = client.run_job(
        "netbox",
        "get_nornir_inventory",
        workers="any",
        kwargs={
            "filters": [{"site": "lab", "status": "active"}],
        },
    )

    # include related interface and connection data
    result = client.run_job(
        "netbox",
        "get_nornir_inventory",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "interfaces": {"ip_addresses": True},
            "connections": True,
            "cache": "refresh",
        },
    )

    # use IPv6 primary addresses for hostnames
    result = client.run_job(
        "netbox",
        "get_nornir_inventory",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "primary_ip": "ip6",
        },
    )

    nf.destroy()
    ```

## Python API Reference

::: norfab.workers.netbox_worker.nornir_inventory_tasks.NetboxNornirInventoryTasks.get_nornir_inventory
