---
tags:
  - netbox
---

# Netbox Sync All Task

> task api name: `sync_all`

The `sync_all` task synchronizes all device data from live devices into NetBox in a fixed
sequence:

1. **interfaces** — calls `sync_device_interfaces`
2. **mac_addresses** — calls `sync_mac_addresses`
3. **ip_addresses** — calls `sync_device_ip`
4. **bgp_peerings** — calls `sync_bgp_peerings`

Each sub-task can be individually enabled or disabled. Pass `dry_run=True` to preview the
changes that would be made without writing anything to NetBox.

## Result Format

```python
{
    # per-device results — one entry per resolved device
    "result": {
        "ceos-spine-1": {
            "interfaces": {
                "create":  { ... },
                "update":  { ... },
                "delete":  { ... },
                "in_sync": [ ... ],
            },
            "mac_addresses": {
                "created": [ ... ],
                "updated": [ ... ],
                "in_sync": [ ... ],
            },
            "ip_addresses": {
                "created": [ ... ],
                "updated": [ ... ],
                "in_sync": [ ... ],
            },
            "bgp_peerings": {
                "create":  { ... },
                "update":  { ... },
                "delete":  { ... },
                "in_sync": [ ... ],
            },
        },
        ...
    },
    "diff": {},
}
```

When `dry_run=True` the same structure is returned but no changes are written to NetBox.

## Sample Usage

## NORFAB Netbox Sync All Command Shell Reference

NorFab shell supports these command options for Netbox `sync_all` task:

```
nf# man tree netbox.sync.all
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── all:    Sync all device data: interfaces, MAC addresses, IP addresses and BGP peerings
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── devices:    List of NetBox devices to sync all data for
            ├── dry-run:    Return diff without writing to NetBox, default 'False'
            ├── process-deletions:    Process deletions for interfaces and BGP peerings, default 'False'
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

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_all
