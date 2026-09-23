---
tags:
  - netbox
---

# NetBox Create VLAN Task

> task API name: `create_vlan`

The `create_vlan` task creates or updates one VLAN in an existing VLAN group. Supply `vid` for an explicit VLAN ID, or omit it to allocate the next available ID from the group's configured ranges.

## Inputs

| Parameter | Required | Default | Description |
| --- | ---: | --- | --- |
| `vlan_group` | Yes | — | Existing VLAN group name |
| `name` | Yes | — | VLAN name |
| `vid` | No | `None` | Explicit VLAN ID from 1 through 4094; omit to allocate |
| `status` | No | `active` | VLAN status |
| `description` | No | `None` | VLAN description |
| `tenant` | No | `None` | Tenant name |
| `role` | No | `None` | IPAM role name |
| `tags` | No | `None` | Tag names |
| `custom_fields` | No | `None` | NetBox custom-field values |
| `instance` | No | Worker default | NetBox instance to target |
| `dry_run` | No | `False` | Return the selected VID without writing |
| `branch` | No | `None` | NetBox Branching plugin branch name |

## Output

```python
{
    "vid": 1000,
    "name": "USERS",
    "vlan_group": "CAMPUS",
    "status": "created",
}
```

`status` is `create` or `update` during dry-run and `created` or `updated` after an applied operation.

## Examples

=== "CLI"

    A dedicated NFCLI command is not currently registered for `create_vlan`.

    ```bash
    # Use the Python API, REST API, MCP task interface, or design filter.
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        allocated = client.run_job(
            "netbox",
            "create_vlan",
            workers="any",
            kwargs={"vlan_group": "CAMPUS", "name": "USERS"},
        )

        explicit = client.run_job(
            "netbox",
            "create_vlan",
            workers="any",
            kwargs={
                "vlan_group": "CAMPUS",
                "name": "SERVERS",
                "vid": 1100,
            },
        )
    ```

In a NetBox design:

```yaml
{% set users_vid = "CAMPUS" | netbox.create_vlan("USERS") %}

vlans:
  - group: CAMPUS
    vid: {{ users_vid }}
    name: USERS
```

## Notes / Gotchas

- The VLAN group must already exist and have available VID ranges for allocation.
- With an explicit `vid`, identity is VLAN group plus VID.
- Without `vid`, an existing VLAN with the same group and name is reused.
- Branch writes require the NetBox Branching plugin.

## Troubleshooting

- **VLAN group not found:** verify the exact group name in NetBox.
- **No available VLAN IDs:** add or expand the group's VID ranges.
- **Ambiguous identity:** remove duplicate VLANs with the same group and identity fields.

## Task Command Shell Reference

`create_vlan` does not currently have a dedicated NFCLI command model.

## Python API Reference

::: norfab.workers.netbox_worker.vlan_tasks.NetboxVlansTasks.create_vlan
