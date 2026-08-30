---
tags:
  - netbox
---

# Netbox Sync All Task

> task api name: `sync_all`

The `sync_all` task synchronizes device data from live devices into NetBox in a
fixed sequence:

1. **inventory** — calls `sync_device_inventory`
2. **vlans** — calls `sync_vlans`
3. **prefixes** — calls `sync_device_prefixes`
4. **vrfs** — calls `sync_vrfs`
5. **interfaces** — calls `sync_device_interfaces`
6. **mac_addresses** — calls `sync_mac_addresses`
7. **ip_addresses** — calls `sync_device_ip`
8. **bgp_peerings** — calls `sync_bgp_peerings`

## How It Works

The `sync_all` task orchestrates eight subordinate sync tasks in sequence. Each task collects live device data,
compares it against NetBox state, and applies reconciliation operations. When `dry_run=True`, all tasks preview changes
without writing. When `with_approval=True`, each stage waits for user confirmation before applying changes.

## Execution Modes

**Dry-run mode** (`dry_run=True`) previews all changes without writing to NetBox.

**With Approval** — Pass `with_approval=True` to use the interactive NFCLI workflow. Each sync stage displays its preview, and waits for review before applying that stage. Declining a stage stops `sync_all` at that point, returns the declined dry-run result, and skips later stages. Any earlier approved stages remain applied.

!!! note
    
    When both `dry-run` and `with_approval` are `True`, `dry-run` logic ignored.

**Live-run mode** (`dry_run=False`, default) applies all changes to NetBox.

## Sync Task Arguments

Use `sync_kwargs` to pass arguments to individual sync tasks. It accepts an
inline dictionary, an `nf://` URL to a YAML file containing that dictionary, or
`None`. The dictionary keys are task API names and each value is passed to that
task as keyword arguments:

```yaml
sync_device_inventory:
  create_module_types: true
  create_module_bays: true
  inventory_map: nf://netbox/inventory_maps/iosxr.yaml
  message: sync all device data

sync_vlans:
  filter_by_vlan_ids:
    - 100-299

sync_device_prefixes:
  ignore_vrf: true
  ignore_site: true

sync_vrfs:
  device_custom_field: devices

sync_device_interfaces:
  process_deletions: true
  interface_map: nf://netbox/interface_map.yaml
  vlan_map: nf://netbox/vlan_map.yaml

sync_mac_addresses:
  filter_by_name: Ethernet*

sync_device_ip:
  ignore_vrf: false
  ignore_ranges:
    - 192.0.2.0/24

sync_bgp_peerings:
  process_deletions: true
  status: active
  message: sync all device data
```

The supported keys are `sync_device_inventory`, `sync_vlans`,
`sync_device_prefixes`, `sync_vrfs`, `sync_device_interfaces`,
`sync_mac_addresses`, `sync_device_ip`, and `sync_bgp_peerings`. Refer to each
task's documentation for its accepted arguments. Missing keys run with the
subordinate task's defaults. Set a key to `false` to skip that task and continue
with the next stage:

```yaml
sync_device_interfaces: false
```

Skipped tasks are omitted from each device's result categories.

Keep `instance`, `timeout`, `devices`, `branch`, `dry_run`, and `with_approval`
at the `sync_all` level rather than repeating them inside a task dictionary.

## Output

The result structure aggregates the outcomes of all eight subordinate sync tasks. When `dry_run=True` the same structure is returned but no changes are written to NetBox. VLAN, prefix, and VRF results describe shared NetBox objects, so the same shared result is included under each selected device.

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
            "vlans": {
                "site:DC1": {
                    "create": [ ... ],
                    "update": { ... },
                    "delete": [],
                    "in_sync": [ ... ],
                },
            },
            "prefixes": {
                "created": [ ... ],
                "updated": [ ... ],
                "in_sync": [ ... ],
            },
            "vrfs": {
                "global": {
                    "create": [ ... ],
                    "update": { ... },
                    "delete": [],
                    "in_sync": [ ... ],
                },
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

=== "CLI"

    Preview all eight sync categories:

    ```
    nf#netbox sync all devices ceos-spine-1 ceos-spine-2 dry-run
    ```

    Preview, prompt for review, and apply the changes:

    ```
    nf#netbox sync all devices ceos-spine-1 ceos-spine-2 with-approval
    ```

    Load per-task arguments from the File Sharing service:

    ```
    nf#netbox sync all devices iosxr1 sync-kwargs nf://netbox/sync_all_kwargs.yaml dry-run
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
            "sync_kwargs": {
                "sync_device_inventory": {
                    "create_module_bays": True,
                    "create_module_types": True,
                    "inventory_map": "nf://netbox/inventory_maps/iosxr.yaml",
                },
                "sync_vlans": {"filter_by_vlan_ids": ["100-299"]},
                "sync_device_prefixes": {"ignore_vrf": True},
                "sync_vrfs": {"device_custom_field": "devices"},
                "sync_device_interfaces": {
                    "interface_map": "nf://netbox/interface_map.yaml",
                    "vlan_map": "nf://netbox/vlan_map.yaml",
                },
                "sync_device_ip": {"ignore_vrf": False},
                "sync_bgp_peerings": False,
            },
        },
    )
    ```

    The same configuration can be stored in YAML and referenced with
    `"sync_kwargs": "nf://netbox/sync_all_kwargs.yaml"`.

## NORFAB Netbox Sync All Command Shell Reference

NorFab shell supports these command options for Netbox `sync_all` task:

```
nf# man tree netbox.sync.all
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── all:    Sync inventory, VLANs, prefixes, VRFs, interfaces, MAC addresses, IP addresses and BGP peerings
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── devices:    List of NetBox devices to sync all data for
            ├── dry-run:    Return diff without writing to NetBox, default 'False'
            ├── with-approval:    Preview each sync stage and ask for review before writing to NetBox
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

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_all
