---
tags:
  - netbox
---

# Netbox Check Device Sync Task

> task api name: `check_device_sync`

The `check_device_sync` task performs a read-only sync-check against live devices and reports
whether the data stored in NetBox is in sync with the actual device state. It does this by
calling four existing sync sub-tasks in `dry_run=True` mode:

- **interfaces** — calls `sync_device_interfaces(dry_run=True)`
- **mac_addresses** — calls `sync_mac_addresses(dry_run=True)`
- **ip_addresses** — calls `sync_device_ip(dry_run=True)`
- **bgp_peerings** — calls `sync_bgp_peerings(dry_run=True)`

No data is written to NetBox. Each sub-check can be individually enabled or disabled.

## Result Format

```python
{
    # per-device summary — one entry per resolved device
    "result": {
        "ceos-spine-1": {
            "in_sync":       False,
            "interfaces":    True,
            "mac_addresses": False,
            "ip_addresses":  True,
            "bgp_peerings":  True,
        },
        ...
    },
    # per-category dry-run detail — full output from each sub-task
    "diff": {
        "interfaces":    { ... },   # dry-run result from sync_device_interfaces
        "mac_addresses": { ... },   # dry-run result from sync_mac_addresses
        "ip_addresses":  { ... },   # dry-run result from sync_device_ip
        "bgp_peerings":  { ... },   # dry-run result from sync_bgp_peerings
    },
}
```

A category is considered **in sync** when the corresponding dry-run reports no pending creates,
updates, or deletes.

## Sample Usage

## NORFAB Netbox Check Device Sync Command Shell Reference

NorFab shell supports these command options for Netbox `check_device_sync` task:

```
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

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.check_device_sync
