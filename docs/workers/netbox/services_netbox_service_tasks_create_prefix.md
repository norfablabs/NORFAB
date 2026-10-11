---
tags:
  - netbox
---

# Netbox Create Prefix Task

> task api name: `create_prefix`

Allocates the next available child prefix from a parent prefix, or updates an existing matching prefix. By default it creates a `/30`, which is useful for point-to-point subnets.

The task can also be called from Nornir templates through the [netbox.create_prefix Jinja2 filter](../nornir/services_nornir_service_jinja2_filters.md#netboxcreate_prefix).

## Output

Returns the created or updated prefix data. In dry-run mode, returns the candidate prefix that would be allocated.
The preview uses the first available range that can fit the requested prefix length.

```python
{
    "prefix": "10.0.0.0/30",
    "description": "leaf-1 to spine-1",
    "status": "active",
    "...": "...",
}
```

## Notes / Gotchas

!!! warning
    `create_prefix` uses the `description` argument to find existing prefixes. Use the same description for repeated calls that should refer to the same prefix.

- `parent` can be a prefix string such as `10.0.0.0/24`, a parent prefix description, or a dictionary of pynetbox prefix filters.
- To associate an existing VLAN, supply `vlan` (VID, 1-4094) and `vlan_group`
  (group name) together. A VID and site alone are unsupported; `site` scopes
  the prefix and does not identify the VLAN. Missing or ambiguous VLAN/group
  lookups fail before allocation. Omission preserves an existing association.
- VLAN changes appear in `diff.vlan` as old/new `VID (ID)` values, including
  dry-run previews. Changing VLAN updates the prefix selected by the existing
  description/scope filters rather than allocating a replacement.
- If `vrf` is provided, the parent prefix must belong to the same VRF.
- When updating an existing prefix, new tags and new items in list-valued custom
  fields are added without removing current values. Supplying `[]` leaves an
  existing custom-field list unchanged. For custom fields, `null` clears the
  value, and a new scalar value replaces the old one.
- Object and multiobject custom fields accept related object names or IDs. The
  task resolves names using each field's NetBox definition; missing or ambiguous
  names fail.
- Branch writes require the [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching).

## Examples

=== "CLI"

    Allocate the next `/30` from a parent prefix:

    ```bash
    nf#netbox create prefix parent 10.0.0.0/24 description "leaf-1 to spine-1"
    ```

    Allocate a `/31` in a VRF:

    ```bash
    nf#netbox create prefix parent 10.0.0.0/24 description "leaf-1 to spine-1" prefixlen 31 vrf PROD
    ```

    Associate VLAN 100 from an existing group:

    ```bash
    nf#netbox create prefix parent 10.0.0.0/24 description "users" vlan 100 vlan_group "LAB VLANS"
    ```

    Preview the allocation:

    ```bash
    nf#netbox create prefix parent 10.0.0.0/24 description "leaf-1 to spine-1" dry-run
    ```

    Write into a NetBox branch:

    ```bash
    nf#netbox create prefix parent 10.0.0.0/24 description "leaf-1 to spine-1" branch my-branch
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # allocate next available /30; VLAN 100 in LAB VLANS must already exist
    result = client.run_job(
        "netbox",
        "create_prefix",
        workers="any",
        kwargs={
            "parent": "10.0.0.0/24",
            "description": "leaf-1 to spine-1",
            "vlan": 100,
            "vlan_group": "LAB VLANS",
        },
    )

    # allocate from a filtered parent prefix
    result = client.run_job(
        "netbox",
        "create_prefix",
        workers="any",
        kwargs={
            "parent": {"prefix": "10.0.0.0/24", "site": "lab"},
            "description": "leaf-2 to spine-1",
            "prefixlen": 31,
            "vrf": "PROD",
            "tags": ["automation-managed"],
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Create Prefix Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```bash
nf# man tree netbox.create.prefix
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── prefix:    Allocate next available prefix from parent prefix
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── parent:    Parent prefix to allocate new prefix from
            ├── description:    Description for new prefix
            ├── prefixlen:    The prefix length of the new prefix, default '30'
            ├── vrf:    Name of the VRF to associate with the prefix
            ├── tags:    List of tags to assign to the prefix
            ├── tenant:    Name of the tenant to associate with the prefix
            ├── comments:    Comments for the prefix
            ├── role:    Role to assign to the prefix
            ├── site:    Name of the site to associate with the prefix
            ├── vlan:    Existing VLAN VID; requires vlan_group
            ├── vlan_group:    Existing VLAN group name; requires vlan
            ├── status:    Status of the prefix
            ├── branch:    Branching plugin branch name to use
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── progress:    Display progress events, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.prefix_tasks.NetboxPrefixTasks.create_prefix
