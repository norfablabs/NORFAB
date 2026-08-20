# Sync VLANs

The `sync_vlans` task reconciles VLAN object names and descriptions from live
devices into NetBox. It requests the normalized TTP `vlans` getter once for the
validated device set, aggregates all successful worker results, then compares
VLANs using scope-aware identities.
VLAN groups use `vid:vlan_group_name`; sites use
`vid:vlan_name:site_name`, allowing differently named VLANs with the same VID
to coexist at one site.

Ordered `vlan_map` rules place matching VLANs into existing VLAN groups. VLANs
which match no rule use the scalar `vlan_group` when supplied, otherwise they
use their device site. VLAN groups are recommended for new deployments because
direct VLAN-to-site assignment is deprecated in NetBox 4.4.

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
| `vlan_map` | `None` | Ordered rules mapping live VLANs to existing groups. |
| `filter_by_vlan_ids` | `None` | VLAN IDs or inclusive ranges such as `100` and `200-299`. |
| Nornir filters | `None` | `FO`, `FB`, `FH`, `FC`, `FR`, `FG`, `FP`, `FL`, `FM`, `FX`, and `FN`. |

Provide `devices` or at least one Nornir host filter.

## VLAN mapping

Each rule contains an exact NetBox VLAN group name. Additional matching
criteria are optional:

```yaml
- vlan_group: CAMPUS
  vlan_ids:
    - 100-199
  vlan_names:
    - USERS*
    - VOICE*
  device_names:
    - leaf-*
  interface_names:
    - Ethernet*
```

Rules are evaluated in list order and the first match wins. Values inside one
criterion use OR logic. Populated criteria use AND logic. VLAN and device names
use case-sensitive glob matching. VLAN ranges are inclusive and must remain
within `1..4094`. VLAN sync ignores `interface_names` because its live VLAN
records have no interface context. Every rule also uses its NetBox VLAN group's
configured `vid_ranges`; explicit `vlan_ids` narrow those ranges. An unmatched
VLAN uses `vlan_group` when supplied, otherwise it uses its device site.

Every group referenced by `vlan_map` or `vlan_group` must already exist. The
task resolves groups by exact name and does not create or update groups. Mapping
rules are constrained by their group's configured VID ranges. The scalar
`vlan_group` is an unconditional fallback and does not filter live VLANs by the
group's configured ranges; NetBox validates the resulting writes.

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

Identical observations from multiple devices in one scope are collapsed. VLAN
group observations with the same VID but different names or descriptions are
reported as a source conflict. Site observations with the same VID and
different names remain separate VLAN identities; a description disagreement
for the same VID and name is a source conflict. Results returned for the same
device by multiple Nornir workers are aggregated before identical observations
are collapsed.

## Output

Results are keyed by scope, for example `group:12:CAMPUS` or
`site:1:NORFAB-LAB`.

Dry-run returns the standard sync diff shape:

```json
{
  "site:1:NORFAB-LAB": {
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
  "site:1:NORFAB-LAB": {
    "created": [110],
    "updated": [210],
    "deleted": [],
    "in_sync": [310]
  }
}
```

NetBox VLANs are resolved in multiple passes from most to least specific. The
task first reserves matches by VID, name, and group or site. Remaining live
VLANs fall back to VID and group or site, allowing an existing VLAN with a stale
name to be updated. VLAN groups already enforce VID uniqueness.

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

    Place all unmatched VLANs into one existing group:

    ```bash
    nf# netbox sync vlans devices fn-ceos-lf-1 vlan-group CAMPUS
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
                "vlan_map": [
                    {
                        "vlan_group": "CAMPUS",
                        "vlan_ids": ["100-199"],
                        "vlan_names": ["TEST_L*"],
                        "device_names": ["fn-ceos-lf-*"],
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
name and description differences. The error lists every conflicting device.

### VLAN group resolution

Check that the scalar `vlan_group` and every group named in `vlan_map` exist
exactly as written. Group resolution finishes before live collection or writes.

### NetBox bulk failures

NetBox validates bulk creates and updates atomically. Correct the
reported validation or dependency error and rerun the dry-run. A write failure
aborts the task and is not reported as an applied action.

## Task command shell reference

```bash
nf# man tree netbox.sync.vlans
```

```bash
netbox sync vlans
├── devices
├── dry-run
├── with-approval
├── vlan-group
├── vlan-map
├── vlan-ids
├── branch
├── instance
├── timeout
└── FO | FB | FH | FC | FR | FG | FP | FL | FM | FX | FN
```

## Python API reference

::: norfab.workers.netbox_worker.vlan_tasks.NetboxVlansTasks.sync_vlans
