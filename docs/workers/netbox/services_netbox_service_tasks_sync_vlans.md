# Sync VLANs

Use `sync_vlans` to create missing VLANs and update VLAN names, descriptions,
and tagged or untagged interface assignments in Netbox from live devices.
Select devices by name or with Nornir host filters. Use a dry run to review
changes before applying them.

Devices must exist in Netbox and be reachable through the Nornir service with
a supported TTP `vlans` getter. Run
[`sync_device_interfaces`](services_netbox_service_tasks_sync_device_interfaces.md)
first if their interfaces are missing.

## Output

Each worker returns VLAN actions under `result.vlans`, grouped by scope such
as `group:CAMPUS`, `site:HQ`, or `global`. Interface actions appear under
`result.interfaces`, grouped by device and interface name.

A dry run lists `create`, `update`, `delete`, and `in_sync` actions. VLAN
`create_details` shows names and descriptions for proposed creations. Updates
show `old_value` and `new_value` for each changed field.

After applying changes, `result` lists completed actions. For example:

```json
{
  "vlans": {
    "group:CAMPUS": {
      "created": [100],
      "updated": [110],
      "deleted": [],
      "in_sync": [120]
    }
  },
  "interfaces": {
    "leaf-1": {
      "created": [],
      "updated": ["Ethernet5"],
      "deleted": [],
      "in_sync": []
    }
  }
}
```

The worker's `diff` retains the preview. Check `errors` for skipped VLANs,
missing interfaces, and conflicting live data, even when the job completes.
Membership-only changes appear under `interfaces`, not as VLAN updates.
The task does not delete VLANs, so deletion lists remain empty.

## Examples

Preview VLANs 100-199 on `leaf-1` in the existing `CAMPUS` group, keeping
existing Netbox names. Remove `dry_run` or `dry-run` to apply the changes.
Python examples assume an established NorFab client. FastAPI examples require
a running NorFab FastAPI service that has discovered the Netbox tasks.

=== "CLI"

    ```bash
    nf# netbox sync vlans devices leaf-1 vlan-ids 100-199 vlan-group CAMPUS preserve-name dry-run
    ```

    To review and approve changes interactively:

    ```bash
    nf# netbox sync vlans devices leaf-1 vlan-ids 100-199 vlan-group CAMPUS preserve-name with-approval
    ```

=== "Python"

    ```python
    result = client.run_job(
        "netbox",
        "sync_vlans",
        workers="any",
        kwargs={
            "devices": ["leaf-1"],
            "filter_by_vlan_ids": ["100-199"],
            "vlan_group": "CAMPUS",
            "preserve_name": True,
            "dry_run": True,
        },
    )
    print(result)
    ```

=== "FastAPI"

    Replace the service URL and bearer token with your deployment values.

    ```python
    import requests

    response = requests.post(
        "http://localhost:8000/api/netbox/sync_vlans/",
        headers={"Authorization": "Bearer <TOKEN>"},
        json={
            "workers": "any",
            "devices": ["leaf-1"],
            "filter_by_vlan_ids": ["100-199"],
            "vlan_group": "CAMPUS",
            "preserve_name": True,
            "dry_run": True,
        },
        timeout=660,
    )
    response.raise_for_status()
    print(response.json())
    ```

    ```bash
    curl -X POST 'http://localhost:8000/api/netbox/sync_vlans/' \
      -H 'Authorization: Bearer <TOKEN>' \
      -H 'Content-Type: application/json' \
      -d '{"workers":"any","devices":["leaf-1"],"filter_by_vlan_ids":["100-199"],"vlan_group":"CAMPUS","preserve_name":true,"dry_run":true}'
    ```

=== "MCP"

    ```text
    Use the NorFab Netbox sync_vlans tool to preview VLANs 100-199 from leaf-1
    in the CAMPUS VLAN group. Preserve existing Netbox VLAN names and report
    planned VLAN and interface changes without applying them.
    ```

## Preserve names and descriptions

`preserve_name=False` is the default. Descriptive live names replace differing
Netbox names. Set `preserve_name=True` to keep existing names. In either mode,
a generated live name such as `VLAN100` does not replace an existing Netbox
name. New VLANs always use live names.

For existing VLAN descriptions, `preserve_description=None` keeps Netbox text
when live text is empty. Use `True` to always keep Netbox text or `False` to
always use live text, including an empty string. New VLANs use live descriptions.

## VLAN Groups Mapping

VLANs are matched by VID and scope, not name. Supply `vlan_group` to select an
existing group. Its scope must apply to the device, and its allowed VID ranges
must include the VLAN IDs.

Use `vlan_map` for ordered group selection rules, supplied inline or as an
`nf://` YAML file. For example:

```yaml
- set_vlan_group: CAMPUS
  match_vlan_ids: ["100-199"]
  vlan_names: ["USERS*", "VOICE*"]
  match_device_names: ["leaf-*"]
  match_interface_names: ["Ethernet*"]
```

The first matching rule wins. All supplied criteria must match. Values within
one criterion are alternatives. Name patterns are case-sensitive, and VLAN ID
ranges must stay within 1-4094. Interface patterns match any member interface.
VLANs without a matching rule use `vlan_group`. Set `require_vlan_group=True`
to skip VLANs without either selection.

Without an explicit group, the task prefers a device-compatible group, then
a VLAN in the device's site, then a global VLAN. Equally preferred matches are
reported as ambiguous and skipped. If no match exists, it creates a site VLAN.
An invalid explicit group selection is skipped without falling back.

Group scopes support sites, regions, site groups, locations, racks, and rack
groups. Region matching includes up to five levels, starting with the site's
region. Other scopes require a direct match. If device location is unset, the
rack's location is used. Cluster scopes are ignored.

## Interface assignments

Reported tagged memberships are added to existing assignments. Empty live
membership lists do not clear assignments. A reported untagged VLAN replaces
the current untagged VLAN, even if the old VLAN is outside the selected ID range.
Interfaces with tagged VLANs use `tagged` mode. Interfaces with only an untagged
VLAN use `access` mode. Q-in-Q service VLANs are not synchronized.

If live and Netbox interface names differ, pass the same `interface_map` to
this task and `sync_device_interfaces`.

## Review and apply changes

`dry_run=True` previews changes without writing. `with_approval=True` asks for
review before applying them and is ignored during a dry run. Use `branch` to
target a branch when the Netbox Branching plugin is configured.

Bulk writes use `batch_size=1000` by default. If a request fails, earlier
successful writes remain applied. Review the error and preview again before
retrying.

## Troubleshooting

- **Missing live data:** check device connectivity and support for the TTP
  `vlans` getter on the Nornir worker.
- **Missing interface:** create it with `sync_device_interfaces`, then rerun.
- **Group not found or incompatible:** check its exact name, scope, and allowed
  VID ranges. Groups must already exist.
- **Ambiguous VLAN match:** select the intended group with `vlan_group` or
  `vlan_map`.
- **Conflicting live names or descriptions:** correct differences between
  devices sharing the VLAN. The first descriptive name and first non-empty
  description in device-name order are used. Conflicts are reported even when
  existing names are preserved.
- **Name collision:** choose a unique VLAN name within the scope, or preserve
  the existing name with `preserve_name=True`. Conflicting creations or updates
  are skipped.

## Task Command Shell Reference

```bash
nf# man tree netbox.sync.vlans

netbox.sync.vlans
|-- devices
|-- instance
|-- dry-run
|-- with-approval
|-- timeout
|-- branch
|-- vlan-group
|-- vlan-map
|-- require-vlan-group
|-- vlan-ids
|-- interface-map
|-- preserve-name
|-- preserve-description
|-- batch-size
|-- FO
|-- FB
|-- FH
|-- FC
|-- FR
|-- FG
|-- FP
|-- FL
|-- FM
|-- FX
|-- FN
|-- workers
|-- verbose-result
`-- nowait
```

## Python API Reference

::: norfab.workers.netbox_worker.vlan_tasks.NetboxVlansTasks.sync_vlans
