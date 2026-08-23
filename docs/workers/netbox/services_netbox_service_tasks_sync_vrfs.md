# Sync VRFs

The `sync_vrfs` task reconciles VRFs from live devices with global NetBox VRF
objects. A VRF name is its identity. The task synchronizes its description and
adds live import and export route targets to the existing NetBox associations.
Route-target and device associations are additive.

The task creates missing NetBox route targets before it creates or updates
VRFs. Route distinguishers and import/export route policies returned by the TTP
getter are not stored in NetBox.

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `instance` | Worker default | NetBox instance name. |
| `dry_run` | `False` | Calculate the diff without writing to NetBox. |
| `with_approval` | `False` | Present the prepared plan for approval before writing. Ignored during dry-run. |
| `timeout` | `600` | Timeout in seconds for host resolution and TTP parsing. |
| `devices` | `None` | Explicit NetBox and Nornir device names. |
| `branch` | `None` | NetBox Branching plugin branch name. |
| `device_custom_field` | `devices` | Multi-object VRF custom field related to `dcim.device`. |
| Nornir filters | `None` | `FO`, `FB`, `FH`, `FC`, `FR`, `FG`, `FP`, `FL`, `FM`, `FX`, and `FN`. |

Provide `devices` or at least one Nornir host filter.

## NetBox VRF Device Custom Field

By default, the task uses a VRF custom field named `devices`. Configure it as a
multi-object field assigned to `ipam.vrf` and related to `dcim.device`. Use
`device_custom_field` to select another field with the same configuration.

The task adds devices on which the VRF was observed and preserves existing
associations. It does not remove devices during a scoped run. If the configured
field exists but has no value on an existing VRF, it is treated as an empty
association list. If the configured field does not exist, the task continues
without device association changes.

For example, when `device_custom_field="vrf_devices"` is requested but NetBox
does not have a custom field named `vrf_devices`, VRFs and route targets are
still synchronized. The task does not fail and does not add a device custom
field value to the VRF.

## Live data

The task runs Nornir `parse_ttp` with `get="vrfs"`, which returns:

```yaml
- name: TENANT_A
  description: Tenant A services
  rd: 65000:201
  rt_import:
    - 65000:201
    - 65000:301
  rt_export:
    - 65000:201
    - 65000:302
  route_policy_import: TENANT_A_IMPORT
  route_policy_export: TENANT_A_EXPORT
```

Only `name`, `description`, `rt_import`, and `rt_export` are used. Description
text and route-target values are used without string normalization, and null
descriptions become an empty string.

For each VRF, devices are ordered alphabetically. The first non-empty
description in that order becomes the NetBox description; the description is
empty when no device supplies one. Different descriptions from multiple
devices are resolved by this rule and are not reported as conflicts.

Import and export route-target lists from every reporting device are
concatenated to form the live aggregate. The shared `make_diff` method compares
that aggregate with NetBox and ignores route-target order. If it finds an
import or export route-target difference for an existing VRF, the task combines
the current NetBox list with live targets that are not already in that list and
places the combined list in the update. For a new VRF, or an existing VRF with
an empty target set, the live aggregate populates the association. Route-target
differences are not reported as errors, and all reporting devices are added to
the device custom field.

## Multi-device aggregation example

Assume the selected devices return the following records for the same VRF:

=== "edge-a"

    ```yaml
    - name: TENANT_A
      description:
      rt_import:
        - 65000:100
        - 65000:200
      rt_export:
        - 65000:100
    ```

=== "edge-b"

    ```yaml
    - name: TENANT_A
      description: Tenant A services
      rt_import:
        - 65000:100
        - 65000:300
      rt_export:
        - 65000:100
        - 65000:400
    ```

The task processes `edge-a` before `edge-b` because device names are sorted.
The empty description from `edge-a` is skipped, so `Tenant A services` from
`edge-b` becomes the desired description. It concatenates the live lists as
follows:

```yaml
TENANT_A:
  description: Tenant A services
  import_targets:
    - 65000:100
    - 65000:200
    - 65000:100
    - 65000:300
  export_targets:
    - 65000:100
    - 65000:100
    - 65000:400
  devices:
    - edge-a
    - edge-b
```

The task does not sort or deduplicate these aggregate lists. NetBox stores VRF
route targets as object relationships, so the resulting VRF is associated with
import targets `65000:100`, `65000:200`, and `65000:300`, and export targets
`65000:100` and `65000:400`. Repeated live references do not create duplicate
route-target objects or relationships.

If NetBox initially associates `TENANT_A` with import target `65000:999` and
export targets `65000:100` and `65000:999`, the task produces this state:

| NetBox item | Result |
|-------------|--------|
| `TENANT_A` description | Changed to `Tenant A services`. |
| Import associations | Extended to `65000:999`, `65000:100`, `65000:200`, and `65000:300`. |
| Export associations | Extended to `65000:100`, `65000:999`, and `65000:400`. |
| Missing route-target objects | Created before the VRF is updated; existing objects are reused. |
| Existing `65000:999` associations | Retained on `TENANT_A`. |
| Route-target object `65000:999` | Retained in NetBox. |
| Device associations | `edge-a` and `edge-b` are added; devices already recorded on the VRF are retained. |

The shared `make_diff` method initially detects the difference between the raw
live aggregate and the current NetBox VRF. The task then replaces the
route-target value in that update plan with the combined list. An order-only
difference does not update the VRF. A missing live membership extends the
existing relationship and does not add an error to the result. A NetBox-only
membership is retained in the merged update.

Because the comparison uses the raw live aggregate before the merge, a
NetBox-only route target remains a difference on later runs. The task can report
the VRF as updated again, but the NetBox-only association remains attached and
is never removed.

## Output

Results use one `global` scope. Dry-run returns the standard sync diff:

```json
{
  "global": {
    "create": ["TENANT_A"],
    "update": {
      "TENANT_B": {
        "export_targets": {
          "old_value": ["65000:999"],
          "new_value": ["65000:999", "65000:202"]
        }
      }
    },
    "delete": [],
    "in_sync": ["CONTROL_PLANE"]
  }
}
```

Live runs use completed-action verbs. The prepared plan remains available in
the top-level `diff` field:

```json
{
  "global": {
    "created": ["TENANT_A"],
    "updated": ["TENANT_B"],
    "deleted": [],
    "in_sync": ["CONTROL_PLANE"]
  }
}
```

## Deletions

The task does not delete VRFs, route-target objects, route-target associations,
or device associations. A selected device set does not prove that existing
NetBox data is stale, so `delete` and `deleted` remain empty.

| Condition | Action |
|-----------|--------|
| Live VRF is missing from NetBox | Create the VRF. |
| Live route target is missing from NetBox | Create the route-target object and associate it with the VRF. |
| NetBox VRF association is absent from the live aggregate | Keep the existing association on the VRF. |
| Existing route-target object is not reported by live data | Keep the route-target object. |
| NetBox VRF is absent from the selected devices | Keep the NetBox VRF. |

## Branches

The task obtains its NetBox client with the requested branch. Reads and writes
therefore remain inside that branch. The NetBox Branching plugin must be
installed and configured for branch use.

## Examples

=== "CLI"

    Preview VRF changes:

    ```bash
    nf# netbox sync vrfs devices fn-ceos-lf-1 dry-run
    ```

    Select devices with a Nornir filter and use another custom field:

    ```bash
    nf# netbox sync vrfs FC leaf device-custom-field vrf_devices
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "netbox",
            "sync_vrfs",
            workers="any",
            kwargs={
                "devices": ["fn-ceos-lf-1", "fn-ceos-lf-2"],
                "dry_run": True,
                "device_custom_field": "devices",
            },
        )
        print(result)
    ```

## Troubleshooting

### Missing parser data

Confirm the device platform is supported by the TTP `vrfs` getter and that the
Nornir worker can run the getter's command. Missing or malformed results are
reported as errors; valid results from other devices and workers still proceed.

### Live VRF aggregation

Every selected device contributes its import and export route targets. Check
the selected device set when the aggregate contains an unexpected target. For
descriptions, the first non-empty value in sorted device-name order is used.

### Device custom field

Confirm that the field is assigned to `ipam.vrf`, uses the multi-object type,
and relates to `dcim.device`. The field name must match `device_custom_field`
exactly.

### NetBox write failures

Confirm route-target values are valid NetBox route-target names and that the
custom field accepts device object IDs. Correct the validation error and rerun
the dry-run before applying changes.

## Task command shell reference

```bash
nf# man tree netbox.sync.vrfs

R - required field, M - supports multiline input, D - dynamic key

root
└── netbox:    Netbox service
    └── sync:    Sync Netbox data
        └── vrfs:    Sync live VRF configuration with NetBox
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Calculate the VRF diff without writing to NetBox, default 'False'
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
            ├── devices:    List of NetBox devices to collect VRFs from
            ├── timeout:    Job timeout
            ├── with-approval:    Preview VRF changes and ask for review before writing to NetBox, default 'False'
            ├── device-custom-field:    VRF custom field that stores associated NetBox devices, default 'devices'
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── nowait:    Do not wait for job to complete, default 'False'
nf#
```

## Python API reference

::: norfab.workers.netbox_worker.vrf_tasks.NetboxVrfsTasks.sync_vrfs
