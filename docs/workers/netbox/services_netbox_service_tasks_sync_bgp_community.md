---
tags:
  - netbox
---

# NetBox Sync BGP Communities Task

> task API name: `sync_bgp_community`

The NetBox Sync BGP Communities task collects named BGP communities from live
devices and reconciles them with NetBox. Route-target (`rt`) communities are
stored as IPAM route targets. Other community types are stored as NetBox BGP
plugin community objects when the plugin is installed.

Route targets are matched by community value. BGP plugin communities are
matched by value and live community-set name so NetBox can hold several
standard communities with the same value. The task creates missing objects and
extends their optional community-name custom field with missing live names. An
optional multi-object custom field associates each community with the devices
on which it was observed. The task never deletes NetBox objects or associations.

## How It Works

1. Resolve explicit device names and optional Nornir host filters.
2. Confirm the selected devices exist in NetBox.
3. Run Nornir [`parse_ttp`](../nornir/services_nornir_service_tasks_parse.md)
   with the TTP Templates `bgp_communities` getter.
4. Group route targets by community value and BGP plugin communities by
   community value plus live community-set name.
5. Compare live route targets and BGP plugin communities with matching NetBox
   objects.
6. Return the diff or apply bulk create and update operations.

For BGP plugin communities, existing NetBox objects are matched in this order:
same value with the live name contained in the configured community-name custom
field, same value with a description matching the live name, then an unlabeled
same-value object. If the community-name custom field is disabled or missing,
the task starts with the description match.

If several route-target records use different names for the same value, the
configured custom field stores the names as a comma-separated string. For
example, `65000:200` named `TENANT_BLUE` on one device and `VPN_BLUE` on
another is stored as:

```text
TENANT_BLUE, VPN_BLUE
```

Existing custom-field values are preserved. New live names are appended only
when they are missing.

## Inputs

| Parameter | Required | Default | Description |
|---|---:|---|---|
| `devices` | Conditional | `None` | NetBox device names from which to collect communities |
| Nornir filters | Conditional | `None` | Host filters such as `FB`, `FC`, `FG`, `FL`, or `FR`; may be combined with `devices` |
| `instance` | No | Worker default | NetBox instance to target |
| `branch` | No | `None` | NetBox Branching plugin branch to use |
| `dry_run` | No | `False` | Return the calculated diff without writing to NetBox |
| `with_approval` | No | `False` | Preview the diff and request approval before writing |
| `timeout` | No | `600` | Timeout in seconds for host resolution and live parsing |
| `community_name_field` | No | `community_name` | Custom field used to store live community-set names; set to `False` to disable name synchronization |
| `device_custom_field` | No | `devices` | Multi-object custom field related to `dcim.device` that stores associated devices |

At least one explicit device or Nornir host filter must select a device. Device
names from both sources are combined and deduplicated.

## Prerequisites

- Selected devices must exist in NetBox.
- The Nornir worker must support the TTP Templates `bgp_communities` getter for
  the device platform.
- The NetBox BGP plugin is required to store non-route-target communities.
- To synchronize community-set names, the configured custom field must exist
  and be assigned to `ipam.routetarget`, `netbox_bgp.community`, or both.
- To associate devices, `device_custom_field` must name a multi-object custom
  field assigned to the community models and related to `dcim.device`.

The community-name custom field is optional. If it does not exist, the task
emits a warning and continues creating community objects without updating
community names. A missing device custom field is ignored. If the BGP plugin is
unavailable, the task emits a warning and synchronizes route targets only.

## Live Data

The getter returns one record for each concrete community value:

```yaml
- value: 65000:100
  type: standard
  name: CUSTOMER_EXPORT
- value: 65000:200
  type: rt
  name: TENANT_BLUE
```

Records must contain non-empty string values for `value`, `type`, and `name`.
Malformed worker, device, or record data is reported in the task errors.

## Execution Modes

**Dry run** — `dry_run=True` returns the prepared diff and performs no NetBox
writes.

**With approval** — `with_approval=True` presents the prepared diff for review
before applying it. A declined review returns the diff with `status="skipped"`
and `dry_run=True`. When both options are enabled, dry-run behavior takes
precedence and no approval prompt is shown.

**Live run** — The default mode creates and updates NetBox objects. The prepared
plan remains available in the top-level `diff` field.

## Output

Results are separated into `route_targets` and `communities` scopes. The
`communities` scope is omitted when the NetBox BGP plugin is unavailable.

Dry-run output uses `create`, `update`, `delete`, and `in_sync` actions:

```json
{
  "route_targets": {
    "create": ["65000:200"],
    "update": {},
    "delete": [],
    "in_sync": []
  },
  "communities": {
    "create": ["65000:100::BLUE_EXPORT"],
    "update": {},
    "delete": [],
    "in_sync": []
  }
}
```

Live-run output uses `created`, `updated`, `deleted`, and `in_sync`:

```json
{
  "route_targets": {
    "created": ["65000:200"],
    "updated": [],
    "deleted": [],
    "in_sync": []
  },
  "communities": {
    "created": ["65000:100::BLUE_EXPORT"],
    "updated": [],
    "deleted": [],
    "in_sync": []
  }
}
```

Deletion lists are always empty because community objects may be shared beyond
the selected device scope.

## Branching Support

Pass `branch=<name>` to read and write objects through a NetBox Branching
plugin branch instead of the main database. The task creates the branch if it
does not exist and waits for it to become ready.

## Examples

=== "CLI"

    Preview communities collected from explicit devices:

    ```bash
    nf# netbox sync bgp-communities devices fn-ceos-lf-1 fn-ceos-lf-2 dry-run
    ```

    Select devices with a Nornir filter and use a different custom field:

    ```bash
    nf# netbox sync bgp-communities FC leaf community-name-field community_aliases
    ```

    Create objects without synchronizing community-set names:

    ```bash
    nf# netbox sync bgp-communities devices edge-1 community-name-field false
    ```

    Preview and request approval before applying changes:

    ```bash
    nf# netbox sync bgp-communities devices edge-1 with-approval
    ```

    Synchronize into a NetBox branch:

    ```bash
    nf# netbox sync bgp-communities devices edge-1 branch community-review
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "netbox",
            "sync_bgp_community",
            workers="any",
            kwargs={
                "devices": ["edge-1", "edge-2"],
                "dry_run": True,
                "community_name_field": "community_aliases",
            },
        )
        print(result)
    ```

    The same task can use Nornir filters without an explicit device list:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    try:
        client = nf.make_client()
        result = client.run_job(
            "netbox",
            "sync_bgp_community",
            workers="any",
            kwargs={"FR": "edge-[12]", "community_name_field": False},
        )
        print(result)
    finally:
        nf.destroy()
    ```

## Notes and Gotchas

- The NetBox BGP plugin must accept each non-route-target value returned by the
  getter. Unsupported values produce NetBox API validation errors.
- The selected devices define the complete live alias set written to the
  custom field. Use the full intended device scope for globally shared values.
- NetBox-only objects are retained because a scoped live query cannot prove
  that a globally shared community is stale.
- `with_approval` cannot be combined with the NFCLI `nowait` option.

## Troubleshooting

If a device has no live result, confirm its platform supports the
`bgp_communities` getter and that the Nornir worker can reach it. Also confirm
that every explicitly selected device exists in NetBox.

For custom-field warnings, confirm the field name and its object assignments.
Use a long-text field so it can hold multiple comma-separated community names.

## NORFAB NetBox Sync BGP Communities Command Shell Reference

```bash
nf# man tree netbox.sync.bgp-communities
root
└── netbox:    NetBox service
    └── sync:    Synchronize data with NetBox
        └── bgp-communities:    Sync live BGP communities with NetBox
            ├── timeout:    Job timeout, default 600
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job completion, default 'False'
            ├── instance:    NetBox instance name to target
            ├── branch:    NetBox Branching plugin branch name to use
            ├── dry-run:    Return the diff without writing to NetBox
            ├── with-approval:    Preview changes and ask for approval
            ├── devices:    NetBox devices from which to collect communities
            ├── community-name-field:    Custom field for live community-set names
            ├── FO:    Filter hosts using a Filter Object
            ├── FB:    Filter hosts by name using glob patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts by name containment
            ├── FR:    Filter hosts by name using regular expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using an IP prefix
            ├── FL:    Filter hosts by name list
            ├── FM:    Filter hosts by platform
            ├── FX:    Exclude hosts by name
            └── FN:    Negate the host filter match
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.bgp_community_tasks.NetboxBgpCommunityTasks.sync_bgp_community
