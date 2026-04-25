---
tags:
  - netbox
---

# Netbox Update BGP Peering Task

> task api name: `update_bgp_peering`

Updates one or many existing BGP sessions in NetBox. Supports single-session mode (`name` plus field kwargs) and bulk mode (`bulk_update` list of dicts). Only non-None fields are updated. Idempotency is enforced via `DeepDiff`: sessions with no effective changes are reported in `in_sync` and no write is performed.

## How it Works

1. Client submits `update_bgp_peering` request to NetBox worker
2. NetBox worker validates that the BGP plugin is installed
3. Worker resolves the RIR ID once (when `rir` is provided) for on-demand ASN creation
4. For each session spec, the current session is fetched from NetBox by name
5. The proposed field values are compared against current NetBox values using `DeepDiff`
6. If there are no differences, the session is added to `in_sync` — no write is performed
7. In dry-run mode — the diff is returned without writing
8. Otherwise, the changed fields are resolved (IPs, ASNs, policies) and the session is updated

## Prerequisites

- **NetBox BGP plugin** (`netbox-bgp`) must be installed and enabled on the NetBox instance.
- The session must already exist in NetBox (use `create_bgp_peering` to create new sessions).

## Branching Support

`update_bgp_peering` is branch-aware. Pass `branch=<name>` to write all changes into a [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching) branch instead of main.

## Dry Run Mode

`dry_run=True` returns the diff without any NetBox writes:

```python
{
    "update": [
        {"name": "<session_name>", "diff": { ... }},
        ...
    ],
    "in_sync": ["<session_name>", ...],
}
```

Sessions with no effective changes appear in `in_sync` regardless of dry-run mode.

## Examples

=== "CLI"

    Update a single BGP session description:

    ```
    nf#netbox update bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 description "updated description"
    ```

    Update status:

    ```
    nf#netbox update bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 status planned
    ```

    Dry run — preview diff without writing:

    ```
    nf#netbox update bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 description "new desc" dry-run
    ```

    Update session in a NetBox branch:

    ```
    nf#netbox update bgp-peering name ceos-spine-1_10.0.0.1_10.0.0.2 description "branch update" branch my-bgp-branch
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # update a single BGP session
    result = client.run_job(
        "netbox",
        "update_bgp_peering",
        workers="any",
        kwargs={
            "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
            "description": "updated description",
            "status": "active",
        },
    )

    # dry run — preview diff without writing
    result = client.run_job(
        "netbox",
        "update_bgp_peering",
        workers="any",
        kwargs={
            "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
            "description": "new description",
            "dry_run": True,
        },
    )

    # bulk update
    result = client.run_job(
        "netbox",
        "update_bgp_peering",
        workers="any",
        kwargs={
            "bulk_update": [
                {
                    "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
                    "description": "spine-1 session",
                    "status": "active",
                },
                {
                    "name": "ceos-spine-2_10.0.0.3_10.0.0.4",
                    "description": "spine-2 session",
                    "import_policies": ["IMPORT_FROM_LEAF"],
                },
            ],
        },
    )

    # update into a NetBox branch
    result = client.run_job(
        "netbox",
        "update_bgp_peering",
        workers="any",
        kwargs={
            "name": "ceos-spine-1_10.0.0.1_10.0.0.2",
            "description": "branch update",
            "branch": "my-bgp-branch",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Update BGP Peering Command Shell Reference

NorFab shell supports these command options for the Netbox `update_bgp_peering` task:

```
nf# man tree netbox.update.bgp-peering
root
└── netbox:    Netbox service
    └── update:    Update Netbox objects
        └── bgp-peering:    Update BGP peering session(s)
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── dry-run:    Return diff without writing to NetBox
            ├── name:    Existing session name (single mode)
            ├── description:    New description value
            ├── status:    New status value
            ├── local-address:    New local IP address string
            ├── remote-address:    New remote IP address string
            ├── local-as:    New local AS number string
            ├── remote-as:    New remote AS number string
            ├── vrf:    New VRF name
            ├── peer-group:    New peer group name
            ├── import-policies:    New import routing policy names
            ├── export-policies:    New export routing policy names
            ├── prefix-list-in:    New inbound prefix list name
            ├── prefix-list-out:    New outbound prefix list name
            ├── bulk-update:    JSON list of session update dicts for bulk mode
            ├── rir:    RIR name for ASN creation
            └── message:    Changelog message for NetBox write operations
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.update_bgp_peering
