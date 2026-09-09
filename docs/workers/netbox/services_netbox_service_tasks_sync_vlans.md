# Sync VLANs

The `sync_vlans` task reconciles VLAN object names and descriptions from live
devices into NetBox. It requests the normalized TTP `vlans` getter once for the
validated device set, aggregates all successful worker results, then compares
VLANs by VID and VLAN group. Names and descriptions are synchronized values and
do not form part of a VLAN's identity.

Ordered `vlan_map` rules place matching VLANs into existing VLAN groups. VLANs
which match no rule use the scalar `vlan_group` when supplied, otherwise they
use their device site. Set `require_vlan_group=True` to skip and report VLANs
which do not resolve through either group selection mechanism. VLAN groups are
recommended for new deployments because direct VLAN-to-site assignment is
deprecated in NetBox 4.4.

This task differs from `sync_device_interfaces`: `sync_vlans` manages VLAN names
and descriptions, while `sync_device_interfaces` manages interface objects and
VLAN associations and may create placeholder VLANs. Run `sync_vlans` first when
possible. A later `sync_vlans` run updates placeholders created by interface
synchronization.

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `instance` | Worker default | NetBox instance name. |
| `dry_run` | `False` | Calculate the diff without writing to NetBox. |
| `with_approval` | `False` | Present the prepared plan for approval before writing. Ignored during dry-run. |
| `timeout` | `600` | Timeout in seconds for host resolution and TTP parsing. |
| `devices` | `None` | Explicit NetBox and Nornir device names. |
| `branch` | `None` | NetBox Branching plugin branch name. |
| `vlan_group` | `None` | Existing group for live VLANs not matched by `vlan_map`. |
| `vlan_map` | `None` | Ordered rules mapping live VLANs to existing groups, inline or in an `nf://` YAML file. |
| `require_vlan_group` | `False` | Require every VLAN to resolve through `vlan_map` or `vlan_group`; unmatched VLANs are reported and skipped. |
| `filter_by_vlan_ids` | `None` | VLAN IDs or inclusive ranges such as `100` and `200-299`. |
| `preserve_description` | `None` | Preserve NetBox descriptions only when live text is empty. Use `True` to always preserve or `False` to always use live text. |
| Nornir filters | `None` | `FO`, `FB`, `FH`, `FC`, `FR`, `FG`, `FP`, `FL`, `FM`, `FX`, and `FN`. |

Provide `devices` or at least one Nornir host filter.

## Existing NetBox VLAN resolution

For each live VLAN, the task fetches every NetBox VLAN with the same VID. VLAN
name is not part of matching; it is a value that may need to be updated.

When `vlan_map` or `vlan_group` selects a group, that selection is
authoritative:

1. Validate that the VID belongs to the selected group's VID ranges.
2. Validate the selected group scope against the device.
3. If either check fails, return an error and do not fall back.
4. Search only same-VID VLANs in that exact group.
5. If none exists, prepare a new VLAN in that group.

Without an explicit group selection, same-VID candidates are checked in this
order:

1. VLAN in any device-compatible group whose VID ranges include the live VID,
   including an unscoped group.
2. VLAN assigned directly to the device site.
3. Global VLAN with neither a group nor a site.

Only the first non-empty level is considered. If that level contains more than
one VLAN, matching is ambiguous: the live VLAN is skipped, an error lists the
candidate NetBox VLAN IDs, and no arbitrary candidate is selected. If no
candidate exists, a VLAN is prepared in the device site; global VLANs are only
reused as existing fallbacks and are not created by default.

### VLAN group scope matching

A scoped group must exactly match the corresponding direct device value:

| Group scope | Device value |
|-------------|--------------|
| Site | Device site |
| Region | Device site's region |
| Site group | Device site's site group |
| Location | Device location |
| Rack | Device rack |
| Rack group | Device rack's rack group |

For location matching, the assigned rack's direct location is used when the
device location is empty. Parent regions, site groups, locations, and rack
groups are not searched. If the required device value is empty, the candidate
group is rejected. Cluster and cluster-group scopes are ignored.

### VLAN group VID range matching

A grouped VLAN is eligible only when its VID is included in the group's
inclusive `vid_ranges`, returned by NetBox as integer pairs:

```yaml
vid_ranges:
  - [1, 20]
  - [50, 100]
```

The resolver checks the live VID against each interval directly instead of
expanding the intervals into individual VLAN IDs. An automatically discovered
out-of-range group VLAN is skipped while candidate search continues. An
explicitly selected out-of-range group is an error and does not fall back to
another group, the device site, or a global VLAN.

## VLAN mapping

Each rule contains an exact NetBox VLAN group name. Additional matching
criteria are optional:

```yaml
- set_vlan_group: CAMPUS
  match_vlan_ids:
    - 100-199
  vlan_names:
    - USERS*
    - VOICE*
  match_device_names:
    - leaf-*
  match_interface_names:
    - Ethernet*
```

Rules are evaluated in list order and the first match wins. Values inside one
criterion use OR logic. Populated criteria use AND logic. VLAN and device names
use case-sensitive glob matching. VLAN ranges are inclusive and must remain
within `1..4094`. VLAN sync ignores `match_interface_names` because its live VLAN
records have no interface context. `match_vlan_ids` controls whether the rule
selects its group; after selection, the group's own `vid_ranges` are validated
separately. An unmatched VLAN uses `vlan_group` when supplied. Without either
group match, it uses its device site unless `require_vlan_group=True`; strict
mode reports and skips that VLAN instead.

The task resolves groups by exact name and does not create or update groups.
VLANs matching a group that does not exist are skipped and reported
individually. A group selected by `vlan_map` or `vlan_group` is validated against
both its VID ranges and the device scope. An incompatible selection is logged
as an error, included in `errors`, and skipped without falling back to another
VLAN; the error directs the operator to fix the group scope, VID ranges, or
mapping.

Store the same YAML list in the File Sharing service and pass its URL when the
rules are reused or maintained separately:

```yaml
vlan_map: nf://netbox/vlan_map.yaml
```

## Live data

The task runs Nornir `parse_ttp` with `get="vlans"`, which returns:

```yaml
- vid: 100
  name: USERS
  description: User access VLAN
```

Only `vid`, `name`, and `description` are managed. Names and descriptions are
trimmed, null descriptions become an empty string, and case is preserved.
`filter_by_vlan_ids` removes out-of-range records from both the complete live
device dataset and NetBox before comparison.

For existing VLANs, the default `preserve_description=None` keeps the NetBox
description when live text is empty and otherwise uses the live value. Set it
to `True` to always retain the NetBox description, or `False` to always apply
the live value, including an empty string. Newly created VLANs always use the
live description.

Identical live records from multiple devices in one scope are collapsed. Live
VLANs with the same VID but different names or descriptions are reported as
source conflicts. The first device in sorted device-name order supplies the
values to synchronize; each later conflicting device is identified in `errors`.
A conflict does not fail or skip that VLAN: the task still creates or updates it
using the first device's values. Results returned for the same device by
multiple Nornir workers are aggregated before identical live records are
collapsed.

## Output

Results are keyed by scope, for example `group:CAMPUS`, `site:NORFAB-LAB`, or
`global`.

Dry-run returns the standard sync diff shape:

```json
{
  "site:NORFAB-LAB": {
    "create": [110],
    "update": {
      "210": {
        "name": {
          "old_value": "VLAN_210",
          "new_value": "USERS"
        }
      }
    },
    "delete": [],
    "in_sync": [310]
  }
}
```

Live runs use completed-action verbs. The prepared plan remains available in
the top-level `diff` field:

```json
{
  "site:NORFAB-LAB": {
    "created": [110],
    "updated": [210],
    "deleted": [],
    "in_sync": [310]
  }
}
```

An existing VLAN with a stale name is updated directly because name is not part
of identity matching.

## Deletions

The task does not delete VLANs. Live parsing does not provide a reliable way to
identify which additional NetBox VLANs are stale. The standard result shape
therefore retains empty `delete` and `deleted` lists.

## Branches

The task obtains its NetBox client with the requested branch. Reads and writes
therefore remain inside that branch. The NetBox Branching plugin must be
installed and configured for branch use.

## Examples

=== "CLI"

    Preview site-scoped VLAN changes:

    ```bash
    nf# netbox sync vlans devices fn-ceos-lf-1 dry-run
    ```

    Select devices with a Nornir filter and restrict VLAN IDs:

    ```bash
    nf# netbox sync vlans FC leaf vlan-ids 100 200-299
    ```

    Clear existing descriptions when live descriptions are empty:

    ```bash
    nf# netbox sync vlans FC leaf vlan-ids 100 200-299 preserve-description false
    ```

    Place all unmatched VLANs into one existing group:

    ```bash
    nf# netbox sync vlans devices fn-ceos-lf-1 vlan-group CAMPUS
    ```

    Require every VLAN to select a VLAN group:

    ```bash
    nf# netbox sync vlans devices fn-ceos-lf-1 vlan-map nf://netbox/vlan_map.yaml require-vlan-group
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "netbox",
            "sync_vlans",
            workers="any",
            kwargs={
                "devices": ["fn-ceos-lf-1", "fn-ceos-lf-2"],
                "dry_run": True,
                "filter_by_vlan_ids": ["100-399"],
                "preserve_description": None,
                "vlan_map": [
                    {
                        "set_vlan_group": "CAMPUS",
                        "match_vlan_ids": ["100-199"],
                        "vlan_names": ["TEST_L*"],
                        "match_device_names": ["fn-ceos-lf-*"],
                    }
                ],
            },
        )
        print(result)
    ```

## Troubleshooting

### Missing parser data

Confirm the device platform is supported by the TTP `vlans` getter and that the
Nornir worker can run the getter's command. Missing or malformed results are
reported as errors; valid results from other devices and workers still proceed.

### Live VLAN conflicts

Select devices that share one authoritative VLAN definition or correct their
name and description differences. The first device in sorted order is used and
each later conflicting device is listed in `errors`. The task continues to
synchronize the first device's values.

### VLAN group resolution

Check that the scalar `vlan_group` and every group named in `vlan_map` exist
exactly as written. A missing group does not abort the task; each live VLAN that
selects it is skipped and reported in `errors`. Also confirm that the selected
group's site, region, site group, location, rack, or rack group scope exactly
matches the device's direct assignment. Scope mismatches are reported and never
fall back to an unrelated same-VID VLAN.

### NetBox bulk failures

NetBox validates bulk creates and updates atomically. Correct the
reported validation or dependency error and rerun the dry-run. A write failure
aborts the task and is not reported as an applied action.

## Task command shell reference

```bash
nf# man tree netbox.sync.vlans

R - required field, M - supports multiline input, D - dynamic key

root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── vlans:    Sync live VLAN configuration with NetBox
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Calculate the VLAN diff without writing to NetBox, default 'False'
            ├── branch:    NetBox branching plugin branch name to use
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            ├── FN:    Negate the match
            ├── devices:    List of NetBox devices to collect VLANs from
            ├── timeout:    Job timeout
            ├── with-approval:    Preview VLAN changes and ask for review before writing to NetBox, default 'False'
            ├── vlan-group:    Exact group name for live VLANs not matched by vlan-map
            ├── vlan-map:    Ordered rules mapping live VLANs to NetBox VLAN groups
            ├── require-vlan-group:    Require every live VLAN to resolve to a VLAN group, default 'False'
            ├── vlan-ids:    VLAN IDs or inclusive ranges to reconcile
            ├── preserve-description:    Preserve NetBox descriptions always (true), when live text is empty (null), or never (false)
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API reference

::: norfab.workers.netbox_worker.vlan_tasks.NetboxVlansTasks.sync_vlans
