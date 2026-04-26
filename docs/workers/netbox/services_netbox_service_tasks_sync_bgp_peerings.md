---
tags:
  - netbox
---

# Netbox Sync BGP Peerings Task

> task api name: `sync_bgp_peerings`

Synchronises BGP sessions between live network devices and the NetBox BGP plugin. Supports idempotent create, update, and optional deletion of stale sessions.

## How it Works

**Data collection** — NetBox worker fetches existing BGP sessions from NetBox BGP plugin. In parallel, Nornir service parses BGP neighbor data from devices using `parse_ttp` with `get="bgp_neighbors"`.

**Normalisation and diff** — Both datasets are normalised to flat comparable dicts keyed by session name convention `{device_name}_{session_name}`. `DeepDiff` classifies each session as `create`, `update`, `delete`, or `in_sync`.

**NetBox writes** — Sessions are created, updated, or (when `process_deletions=True`) deleted in NetBox. IP addresses and ASNs are resolved from IPAM or created on-demand. On create, all related objects (peer groups, routing policies, prefix lists) are resolved or created by name.

**Dry run** — When `dry_run=True` no writes occur; the raw diff report is returned.

1. Client submits `sync_bgp_peerings` request to NetBox worker
2. NetBox worker fetches existing BGP sessions from NetBox BGP plugin
3. NetBox worker requests Nornir service to parse BGP neighbor data from devices
4. Nornir fetches and parses BGP state from the network
5. Nornir returns parsed BGP session data to NetBox worker
6. NetBox worker computes diff, then writes creates/updates/deletes to NetBox

## Prerequisites

- **NetBox BGP plugin** (`netbox-bgp`) must be installed and enabled on the NetBox instance.
- **Nornir service** must have a TTP getter that handles `get="bgp_neighbors"`.

## Branching Support

`sync_bgp_peerings` is branch-aware. Pass `branch=<name>` to write all changes into a [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching) branch instead of main.

## Session Naming Convention

By default, NetBox session names follow:

```
{device}_{name}
```

For example, device `ceos-leaf-1` with a parsed session `to-spine-1` becomes `ceos-leaf-1_to-spine-1`.

Use the `name_template` parameter to customise the naming scheme. The template is a Python format string with the following variables:

| Variable | Description |
|---|---|
| `device` | Device name (e.g. `ceos-leaf-1`) |
| `name` | Parsed session name |
| `description` | Session description |
| `local_address` | Local IP address string |
| `local_as` | Local AS number string |
| `remote_address` | Remote IP address string |
| `remote_as` | Remote AS number string |
| `vrf` | VRF name or `None` |
| `state` | Device-reported state (e.g. `established`) |
| `peer_group` | Peer group name or `None` |
| `import_policies` | List of import policy names or `None` |
| `export_policies` | List of export policy names or `None` |
| `prefix_list_in` | Inbound prefix list name or `None` |
| `prefix_list_out` | Outbound prefix list name or `None` |

Example:

```
name_template="{device}_BGP_{name}"
# ceos-leaf-1_BGP_to-spine-1
```

## Filtering Sessions

Three optional filters narrow which sessions are considered during sync. Filters apply to **both** the NetBox dataset and the live device dataset before the diff is computed. Sessions that do not match are silently excluded from creates, updates, and deletes.

| Parameter | Match logic | Applied to |
|---|---|---|
| `filter_by_remote_as` | Exact match — session's remote AS must equal one of the provided integer values | NetBox & live |
| `filter_by_peer_group` | Exact match — session's peer group name must equal one of the provided values | NetBox & live |
| `filter_by_description` | Glob match — session's description must match the provided glob pattern (e.g. `*uplink*`) | NetBox & live |

Multiple filters may be combined; all must pass (AND logic). `filter_by_description` uses Python `fnmatch` glob syntax — `*` matches any sequence of characters, `?` matches a single character.

!!! note
    When `process_deletions=True`, only sessions that pass the filters are candidates for deletion. Sessions excluded by a filter are never deleted.

## Dry Run Mode

`dry_run=True` returns the diff without any NetBox writes:

```python
{
    "<device>": {
        "create":  ["<session_name>", ...],
        "delete":  ["<session_name>", ...],
        "update":  {
            "<session_name>": {
                "<field>": {"old_value": ..., "new_value": ...},
            },
        },
        "in_sync": ["<session_name>", ...],
    }
}
```

## Deletion Behaviour

Default `process_deletions=False` — sessions present in NetBox but absent on the device are left untouched.

Set `process_deletions=True` to delete stale sessions. Only sessions for the explicitly targeted devices are considered.

!!! warning
    Anything the TTP getter does not return (parser gap, unreachable device) will be deleted when `process_deletions=True`. Use dry-run to check before break.

## Examples

=== "CLI"

    Sync BGP sessions for a list of devices:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 ceos-leaf-2 rir lab
    ```

    Preview changes without writing to NetBox (dry run):

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 dry-run
    ```

    Sync and delete stale sessions no longer present on devices:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 ceos-leaf-2 rir lab process-deletions
    ```

    Use a custom session naming template:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 rir lab name-template "{device}_BGP_{name}"
    ```

    Sync sessions into a NetBox branch:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 rir lab branch my-bgp-branch
    ```

    Sync using Nornir host filters instead of explicit device names:

    ```
    nf#netbox sync bgp-peerings rir lab FG spine-group
    ```

    Sync only sessions with a specific remote AS:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 rir lab filter-by-remote-as 65001
    ```

    Sync only sessions belonging to a peer group:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 rir lab filter-by-peer-group EBGP_PEERS
    ```

    Sync only sessions whose description matches a glob pattern:

    ```
    nf#netbox sync bgp-peerings devices ceos-leaf-1 rir lab filter-by-description "*spine uplink*"
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # sync BGP sessions for specific devices
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            "rir": "lab",
        },
    )

    # dry run — preview creates/updates/deletes without writing
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "dry_run": True,
        },
    )

    # sync and remove stale sessions
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            "rir": "lab",
            "process_deletions": True,
        },
    )

    # custom session name template
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "name_template": "{device}_BGP_{name}",
        },
    )

    # sync into a NetBox branch
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "branch": "my-bgp-branch",
        },
    )

    # use Nornir host filters instead of explicit device names
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "rir": "lab",
            "FG": "spine-group",
        },
    )

    # sync only sessions with a specific remote AS
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "filter_by_remote_as": [65001, 65002],
        },
    )

    # sync only sessions belonging to a peer group
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "filter_by_peer_group": ["EBGP_PEERS"],
        },
    )

    # sync only sessions whose description matches a glob pattern
    result = client.run_job(
        "netbox",
        "sync_bgp_peerings",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "rir": "lab",
            "filter_by_description": "*spine uplink*",
        },
    )

    nf.destroy()
    ```

## VRF Custom Field

The VRF reference is **always** stored in a BGP session custom field that must be
configured as type **Object** in NetBox pointing to the VRF content-type.  By default
`vrf_custom_field="vrf"` means `custom_fields["vrf"]` is used for all reads and
writes.  The parameter is forwarded to both `create_bgp_peering` and
`update_bgp_peering` internally so all normalisation, diff, and write operations
use the same field consistently.

```python
result = client.run_job(
    "netbox",
    "sync_bgp_peerings",
    workers="any",
    kwargs={
        "devices": ["ceos-leaf-1"],
        "rir": "lab",
        "vrf_custom_field": "tenant_vrf",  # Object-type custom field -> VRF
    },
)
```

## NORFAB Netbox Sync BGP Peerings Command Shell Reference

NorFab shell supports these command options for the Netbox `sync_bgp_peerings` task:

```
nf# man tree netbox.sync.bgp-peerings
root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── bgp-peerings:    Sync BGP peering sessions
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── branch:    Branching plugin branch name to use
            ├── dry-run:    Return diff without writing to NetBox
            ├── devices:    List of device names to process
            ├── status:    Status for created/updated sessions, default 'active'
            ├── process-deletions:    Delete NetBox sessions absent on device, default 'False'
            ├── rir:    RIR name for ASN creation (e.g. 'RFC 1918')
            ├── message:    Changelog message for all NetBox write operations
            ├── name-template:    Template for BGP session names in NetBox, default '{device}_{name}'
            ├── filter-by-remote-as:    Only sync sessions with matching remote AS number(s)
            ├── filter-by-peer-group:    Only sync sessions with matching peer group name(s)
            ├── filter-by-description:    Only sync sessions whose description matches this glob pattern
            ├── vrf-custom-field:    BGP session field for VRF reference, default 'vrf'
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            └── FN:    Negate the match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_peerings_tasks.NetboxBgpPeeringsTasks.sync_bgp_peerings
