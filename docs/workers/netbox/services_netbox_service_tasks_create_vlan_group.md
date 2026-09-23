---
tags:
  - netbox
---

# NetBox Create VLAN Group Task

> task API name: `create_vlan_group`

The `create_vlan_group` task creates or updates one VLAN group scoped to a NetBox site. The design engine uses it before allocating VLANs for a site.

## Inputs

| Parameter | Required | Default | Description |
| --- | ---: | --- | --- |
| `name` | Yes | — | VLAN group name |
| `site` | Yes | — | Existing site used as the group scope |
| `vid_ranges` | Yes | — | Inclusive VLAN ID ranges, such as `[[10, 99]]` |
| `instance` | No | Worker default | NetBox instance to target |
| `dry_run` | No | `False` | Return the proposed action without writing |
| `branch` | No | `None` | NetBox Branching plugin branch name |

## Example

```python
result = client.run_job(
    "netbox",
    "create_vlan_group",
    workers="any",
    kwargs={
        "name": "SITE-001 VLANS",
        "site": "SITE-001",
        "vid_ranges": [[10, 99]],
    },
)
```

In a design:

```jinja2
{% set vlan_group = netbox.create_vlan_group(name=context.site ~ " VLANS", site=context.site, vid_ranges=[[10, 99]]) %}
```

The site must exist before the task runs.

## Python API Reference

::: norfab.workers.netbox_worker.vlan_tasks.NetboxVlansTasks.create_vlan_group
