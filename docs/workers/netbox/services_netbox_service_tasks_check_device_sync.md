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
- **vrfs** — calls `sync_vrfs(dry_run=True)` for VRFs, missing route targets and routing policies, and interface assignments
- **vlans** — calls `sync_vlans(dry_run=True)` for VLANs and interface assignments
- **prefixes** — calls `sync_device_prefixes(dry_run=True)`
- **ip_addresses** — calls `sync_device_ip(dry_run=True)`
- **bgp_peerings** — calls `sync_bgp_peerings(dry_run=True)`
- **bgp_communities** — calls `sync_bgp_community(dry_run=True)` for route targets and BGP plugin communities
- **vrrp** — calls `sync_vrrp(dry_run=True)`

Each sub-check can be enabled or disabled independently.

## Sync Task Arguments

Use `sync_kwargs` to configure how individual dry-run synchronizers calculate
drift. Supported keys are `sync_device_inventory`, `sync_device_interfaces`,
`sync_vrfs`, `sync_vlans`, `sync_device_prefixes`, `sync_device_ip`,
`sync_vrrp`, `sync_bgp_community`, and `sync_bgp_peerings`. Values are keyword
argument dictionaries accepted by the corresponding task. Keep `instance`,
`timeout`, `devices`, `branch`, and `dry_run` at the `check_device_sync` level;
all subordinate tasks are always called with `dry_run=True`.

The mapping can be supplied inline or loaded from an `nf://` YAML file:

```yaml
sync_device_interfaces:
  filter_by_name: Loopback*
sync_vlans:
  filter_by_vlan_ids:
    - 100-299
sync_bgp_peerings:
  status: active
```

## Output

Both coordinated tasks include inventory, prefixes, interfaces, VRFs, VLANs, IP addresses, VRRP, BGP communities, and BGP peerings. Every selected device has all nine category keys. Disabled categories are `None`; failed categories are `False`. Sync results contain child task summaries or dry-run previews, while checks return booleans for drift state. The `diff` dictionary retains child dry-run details under the same category keys, with `None` for unexecuted checks or stages. MAC synchronization is available through its standalone task.

```python
{
    "result": {
        "ceos-spine-1": {
            "in_sync": False,
            "inventory": True,
            "interfaces": True,
            "vrfs": True,
            "vlans": False,
            "prefixes": True,
            "ip_addresses": True,
            "bgp_peerings": True,
            "bgp_communities": True,
            "vrrp": True,
        },
    },
    "diff": {
        "inventory": {},
        "interfaces": {},
        "vrfs": {},
        "vlans": {},
        "prefixes": {},
        "ip_addresses": {},
        "bgp_peerings": {},
        "bgp_communities": {},
        "vrrp": {},
    },
}
```

A category is considered in sync when the corresponding dry-run reports no pending creates, updates, or deletes. With `ignore_deletions=True`, pending deletions remain in `Result.diff` but do not make the category out of sync.

## Notes / Gotchas

- No data is written to NetBox.
- `Result.diff` contains the raw dry-run detail from each enabled sub-task.
- Prefix, global VLAN, BGP community, and route-target drift affects every selected device; interface VLAN and VRRP drift is assessed per device.
- Device names can be supplied directly or resolved from Nornir filters.

## Examples

=== "CLI"

    Check all sync categories for explicit devices:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 ceos-leaf-2
    ```

    Check only interface and IP address sync:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 check-inventory false check-vrfs false check-vlans false check-prefixes false check-bgp-peerings false check-bgp-communities false check-vrrp false
    ```

    Resolve devices using a Nornir group filter:

    ```bash
    nf#netbox check-sync devices FG leafs
    ```

    Check against a NetBox branch:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 branch my-branch
    ```

    Load per-task arguments from the File Sharing service:

    ```bash
    nf#netbox check-sync devices devices ceos-leaf-1 sync-kwargs nf://netbox/check_sync_kwargs.yaml
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
                "sync_kwargs": {
                    "sync_device_interfaces": {"filter_by_name": "Loopback*"},
                    "sync_vlans": {"filter_by_vlan_ids": ["100-299"]},
                },
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
                "check_vrfs": False,
                "check_vlans": False,
                "check_prefixes": False,
                "check_bgp_peerings": False,
                "check_bgp_communities": False,
                "check_vrrp": False,
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
            ├── check-vrfs:    Check VRF and interface assignment sync state, default 'True'
            ├── check-vlans:    Check VLAN and interface assignment sync state, default 'True'
            ├── check-prefixes:    Check prefix sync state, default 'True'
            ├── check-ip-addresses:    Check IP addresses sync state, default 'True'
            ├── check-bgp-peerings:    Check BGP peerings sync state, default 'True'
            ├── check-bgp-communities:    Check BGP communities sync state, default 'True'
            ├── check-vrrp:    Check VRRP sync state, default 'True'
            ├── ignore-deletions:    Treat deletion-only differences as in sync, default 'False'
            ├── sync-kwargs:    Per-task sync arguments or nf:// YAML file
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
