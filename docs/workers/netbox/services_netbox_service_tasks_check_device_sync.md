---
tags:
  - netbox
---

# Netbox Check Device Sync Task

> task api name: `check_device_sync`

Checks whether NetBox data is in sync with live device state without writing to NetBox. The task runs selected sync tasks in `dry_run=True` mode and returns a per-device summary plus detailed dry-run diffs.

## How It Works

`check_device_sync` can run these read-only sub-checks:

- **inventory** — calls `sync_device_inventory(dry_run=True)`
- **interfaces** — calls `sync_device_interfaces(dry_run=True)`
- **mac_addresses** — calls `sync_mac_addresses(dry_run=True)`
- **ip_addresses** — calls `sync_device_ip(dry_run=True)`
- **bgp_peerings** — calls `sync_bgp_peerings(dry_run=True)`

Each sub-check can be enabled or disabled independently.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | No | NetBox device names to check |
| `instance` | No | NetBox instance name to target |
| `branch` | No | NetBox Branching plugin branch name to read from |
| `timeout` | No | Timeout in seconds for Nornir parse jobs |
| `check_inventory` | No | Check device inventory sync state, default `True` |
| `check_interfaces` | No | Check interface sync state, default `True` |
| `check_mac_addresses` | No | Check MAC address sync state, default `True` |
| `check_ip_addresses` | No | Check IP address sync state, default `True` |
| `check_bgp_peerings` | No | Check BGP peering sync state, default `True` |
| Nornir filters | No | Host filters such as `FL`, `FB`, `FG`, `FC`, or `FN` |

At least one explicit device or Nornir host filter must resolve to a device.

## Output

```python
{
    "result": {
        "ceos-spine-1": {
            "in_sync": False,
            "inventory": True,
            "interfaces": True,
            "mac_addresses": False,
            "ip_addresses": True,
            "bgp_peerings": True,
        },
    },
    "diff": {
        "inventory": {},
        "interfaces": {},
        "mac_addresses": {},
        "ip_addresses": {},
        "bgp_peerings": {},
    },
}
```

A category is considered in sync when the corresponding dry-run reports no pending creates, updates, or deletes.

## Notes / Gotchas

- No data is written to NetBox.
- `Result.diff` contains the raw dry-run detail from each enabled sub-task.
- Device names can be supplied directly or resolved from Nornir filters.

## Examples

=== "CLI"

    Check all sync categories for explicit devices:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 ceos-leaf-2
    ```

    Check only interface and IP address sync:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 check-inventory false check-mac-addresses false check-bgp-peerings false
    ```

    Resolve devices using a Nornir group filter:

    ```bash
    nf#netbox check-sync devices FG leafs
    ```

    Check against a NetBox branch:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 branch my-branch
    ```

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            },
        )
    ```

    Direct lifecycle:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "devices": ["ceos-leaf-1"],
                "check_inventory": False,
                "check_mac_addresses": False,
                "check_bgp_peerings": False,
            },
        )

        filtered_result = client.run_job(
            "netbox",
            "check_device_sync",
            workers="any",
            kwargs={
                "FG": "leafs",
            },
        )
    finally:
        nf.destroy()
    ```

## NORFAB Netbox Check Device Sync Command Shell Reference

NorFab shell supports these command options for Netbox `check_device_sync` task:

```bash
nf# man tree netbox.check-sync.devices
root
└── netbox:    Netbox service
    └── check-sync:    Check if Netbox data is in sync with live device state
        └── devices:    Check if device data in NetBox is in sync with live device state
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── devices:    List of NetBox devices to check sync state for
            ├── check-inventory:    Check device inventory sync state, default 'True'
            ├── check-interfaces:    Check interfaces sync state, default 'True'
            ├── check-mac-addresses:    Check MAC addresses sync state, default 'True'
            ├── check-ip-addresses:    Check IP addresses sync state, default 'True'
            ├── check-bgp-peerings:    Check BGP peerings sync state, default 'True'
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FX:    Filter hosts excluding them by name
            └── FN:    Negate the match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.devices_tasks.NetboxDevicesTasks.check_device_sync
