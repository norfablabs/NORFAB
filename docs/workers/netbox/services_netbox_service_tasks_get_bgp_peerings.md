---
tags:
  - netbox
---

# Netbox Get BGP Peerings Task

> task api name: `get_bgp_peerings`

This task integrates with [Netbox BGP Plugin](https://github.com/netbox-community/netbox-bgp) and allows to fetch devices' BGP peerings.

## How It Works

- Requires NetBox BGP plugin: The worker verifies the plugin is installed on the target instance before proceeding.
- Resolves device IDs: It calls `get_devices()` to map provided device names to NetBox device IDs for accurate API queries.
- Fetches sessions via REST: Uses `pynetbox` `plugins.bgp.session.filter(device_id=...)` to retrieve sessions per device.
- Returns structured data: The result is a dictionary keyed by device name; each device contains a dictionary keyed by BGP session `name`, with the full session dict as value.
- Smart caching: Per-device cache key `get_bgp_peerings::<device>` is used. Modes:
  - `True`: Uses cache when up-to-date; performs smart update by comparing `last_updated` and fetching only changed/new sessions.
  - `False`: Bypasses cache entirely and does not write to cache.
  - `refresh`: Forces re-fetch from NetBox and overwrites cache. 
  - `force`: Returns cached data if present without freshness checks.

Sample BGP session data retrieved from Netbox:

```
"fceos4": {
    "fceos4-fceos5-eth105": {
        "comments": "",
        "created": "2025-12-31T08:17:39.168208Z",
        "custom_fields": {},
        "description": "BGP peering between fceos4 and fceos5 on eth105",
        "device": {
            "description": "",
            "display": "fceos4 (UUID-123451)",
            "id": 111,
            "name": "fceos4",
            "url": "http://192.168.1.210:8000/api/dcim/devices/111/"
        },
        "display": "fceos4 (UUID-123451):fceos4-fceos5-eth105",
        "export_policies": [],
        "id": 4,
        "import_policies": [],
        "last_updated": "2025-12-31T08:17:39.168231Z",
        "local_address": {
            "address": "10.0.2.1/30",
            "description": "",
            "display": "10.0.2.1/30",
            "family": {
                "label": "IPv4",
                "value": 4
            },
            "id": 123,
            "url": "http://192.168.1.210:8000/api/ipam/ip-addresses/123/"
        },
        "local_as": {
            "asn": 65100,
            "description": "BGP ASN for fceos4",
            "display": "AS65100",
            "id": 3,
            "url": "http://192.168.1.210:8000/api/ipam/asns/3/"
        },
        "name": "fceos4-fceos5-eth105",
        "peer_group": {
            "description": "Test BGP peer group 1 for standard peerings",
            "display": "TEST_BGP_PEER_GROUP_1",
            "id": 9,
            "name": "TEST_BGP_PEER_GROUP_1",
            "url": "http://192.168.1.210:8000/api/plugins/bgp/bgppeergroup/9/"
        },
        "prefix_list_in": null,
        "prefix_list_out": null,
        "remote_address": {
            "address": "10.0.2.2/30",
            "description": "",
            "display": "10.0.2.2/30",
            "family": {
                "label": "IPv4",
                "value": 4
            },
            "id": 124,
            "url": "http://192.168.1.210:8000/api/ipam/ip-addresses/124/"
        },
        "remote_as": {
            "asn": 65101,
            "description": "BGP ASN for fceos5",
            "display": "AS65101",
            "id": 4,
            "url": "http://192.168.1.210:8000/api/ipam/asns/4/"
        },
        "site": {
            "description": "",
            "display": "SALTNORNIR-LAB",
            "id": 16,
            "name": "SALTNORNIR-LAB",
            "slug": "saltnornir-lab",
            "url": "http://192.168.1.210:8000/api/dcim/sites/16/"
        },
        "status": {
            "label": "Active",
            "value": "active"
        },
        "tags": [],
        "tenant": {
            "description": "",
            "display": "SALTNORNIR",
            "id": 11,
            "name": "SALTNORNIR",
            "slug": "saltnornir",
            "url": "http://192.168.1.210:8000/api/tenancy/tenants/11/"
        },
        "url": "http://192.168.1.210:8000/api/plugins/bgp/bgpsession/4/",
        "virtualmachine": null
    },
    "fceos4-fceos5-eth106": {

        ...etc...
```

## Gotchas

- Supported and tested Netbox version is 4.4 onwards.
- NetBox BGP plugin required: If missing, the task fails early with an error. Confirm plugin availability and version compatibility.
- Device name must exist: Unknown devices are skipped with warnings; verify names beforehand or use `get_devices` to inspect inventory.
- Session key uniqueness: Sessions in the result are keyed by `name`. If session names are not unique per device, later entries overwrite earlier ones.
- Partial-field queries: Smart update relies on `fields="id,last_updated,name"`. Older Netbox versions may not support `fields`, impacting cache comparison.
- Large datasets: Fetching many devices or sessions may be slow; prefer cache or limit `devices` for interactive runs.

## NORFAB Netbox Get BGP Peerings Command Shell Reference

NorFab shell supports these command options for Netbox `get_bgp_peerings` task:

```
nf#man tree netbox.get.bgp_peerings
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── bgp-peerings:    Query Netbox BGP Peerings data
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Only return query content, do not run it
            ├── branch:    Branching plugin branch name to use
            ├── *devices:    Device names to query data for
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.get_bgp_peerings