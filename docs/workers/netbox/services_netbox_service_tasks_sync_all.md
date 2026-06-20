---
tags:
  - netbox
---

# Netbox Sync All Task

> task api name: `sync_all`

The `sync_all` task synchronizes device data from live devices into NetBox in a
fixed sequence:

1. **inventory** — calls `sync_device_inventory`
2. **interfaces** — calls `sync_device_interfaces`
3. **mac_addresses** — calls `sync_mac_addresses`
4. **ip_addresses** — calls `sync_device_ip`
5. **bgp_peerings** — calls `sync_bgp_peerings`

## How It Works

The `sync_all` task orchestrates five subordinate sync tasks in sequence. Each task collects live device data,
compares it against NetBox state, and applies reconciliation operations. When `dry_run=True`, all tasks preview changes
without writing. When `with_review=True`, each stage waits for user confirmation before applying changes.

## Execution Modes

**Dry-run mode** (`dry_run=True`) previews all changes without writing to NetBox.

**With Review** — Pass `with_review=True` to use the interactive NFCLI workflow. Each sync stage displays its preview, and waits for review before applying that stage. Declining a stage stops `sync_all` at that point, returns the declined dry-run result, and skips later stages. Any earlier approved stages remain applied.

!!! note
    
    When both `dry-run` and `with_review` are `True`, `dry-run` logic ignored.

**Live-run mode** (`dry_run=False`, default) applies all changes to NetBox.

## Inventory Arguments

Inventory-specific options use an `inventory_` prefix in the Python API and an
`inventory-` prefix in NFCLI:

| Python argument | Purpose |
|---|---|
| `inventory_create_module_types` | Create missing NetBox module types. |
| `inventory_create_module_bays` | Create missing NetBox module bays. |
| `inventory_map` | Inline mapping or `nf://` YAML mapping file. |
| `inventory_transform` | `nf://` Python transformer file. |
| `inventory_filter_by_module` | Include normalized module types matching glob patterns. |
| `inventory_filter_by_slot` | Include normalized module bays matching glob patterns. |
| `inventory_ignore_modules` | Exclude normalized module types matching glob patterns. |
| `inventory_ignore_slots` | Exclude normalized module bays matching glob patterns. |

The shared `process_deletions` argument controls deletion behavior for
inventory, interfaces, and BGP peerings.

The shared `message` argument is used as the NetBox changelog message for both
inventory and BGP write operations.

## Result Structure

The result structure aggregates the outcomes of all five subordinate sync tasks. When `dry_run=True` the same structure is returned but no changes are written to NetBox.

```python
{
    # per-device results — one entry per resolved device
    "result": {
        "ceos-spine-1": {
            "inventory": {
                "created": [ ... ],
                "updated": [ ... ],
                "deleted": [ ... ],
                "in_sync": [ ... ],
            },
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

## Examples

=== "NFCLI"

    Preview all five sync categories:

    ```
    nf#netbox sync all devices ceos-spine-1 ceos-spine-2 dry-run
    ```

    Preview, prompt for review, and apply the changes:

    ```
    nf#netbox sync all devices ceos-spine-1 ceos-spine-2 with-review
    ```

    Create missing module bays and module types during inventory sync:

    ```
    nf#netbox sync all devices iosxr1 inventory-create-module-bays inventory-create-module-types
    ```

    Use mapping and transformer files:

    ```
    nf#netbox sync all devices iosxr1 inventory-map nf://netbox/inventory_maps/iosxr.yaml inventory-transform nf://netbox/inventory_transformers/iosxr.py dry-run
    ```

    Limit inventory sync to selected normalized modules and slots:

    ```
    nf#netbox sync all devices iosxr1 inventory-filter-by-module "A9K-*" inventory-filter-by-slot "module 0/*" inventory-ignore-modules "SFP-*"
    ```

    Enable deletions for inventory, interfaces, and BGP peerings:

    ```
    nf#netbox sync all devices iosxr1 process-deletions
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "sync_all",
        workers="any",
        kwargs={
            "devices": ["iosxr1"],
            "dry_run": True,
            "inventory_create_module_bays": True,
            "inventory_create_module_types": True,
            "inventory_map": "nf://netbox/inventory_maps/iosxr.yaml",
            "inventory_transform": (
                "nf://netbox/inventory_transformers/iosxr.py"
            ),
            "inventory_filter_by_module": ["A9K-*"],
            "inventory_filter_by_slot": ["module 0/*"],
            "inventory_ignore_modules": ["SFP-*"],
            "inventory_ignore_slots": ["power-module *"],
            "message": "sync all device data",
        },
    )
    ```

## NORFAB Netbox Sync All Command Shell Reference

NorFab shell supports these command options for Netbox `sync_all` task:

```
nf# man tree netbox.sync.all
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── all:    Sync device inventory, interfaces, MAC addresses, IP addresses and BGP peerings
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── devices:    List of NetBox devices to sync all data for
            ├── dry-run:    Return diff without writing to NetBox, default 'False'
            ├── with-review:    Preview each sync stage and ask for review before writing to NetBox
            ├── process-deletions:    Process deletions for inventory, interfaces and BGP peerings
            ├── message:    Changelog message for inventory and BGP operations
            ├── inventory-create-module-types:    Create missing module types during inventory sync
            ├── inventory-create-module-bays:    Create missing module bays during inventory sync
            ├── inventory-map:    Inventory pattern mappings or nf:// YAML file reference
            ├── inventory-transform:    nf:// Python inventory transformer file
            ├── inventory-filter-by-module:    Glob patterns selecting normalized module type names
            ├── inventory-filter-by-slot:    Glob patterns selecting normalized module bay names
            ├── inventory-ignore-modules:    Glob patterns excluding normalized module type names
            ├── inventory-ignore-slots:    Glob patterns excluding normalized module bay names
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
