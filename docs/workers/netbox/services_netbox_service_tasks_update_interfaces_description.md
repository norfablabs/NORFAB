---
tags:
  - netbox
---

# Netbox Update Interfaces Description Task

> task api name: `update_interfaces_description`

Updates the description field of interfaces, console ports, and console server ports for one or more devices in NetBox. Supports two mutually usable modes: **template mode** (`description_template`) renders descriptions dynamically using Jinja2 with interface and connection context where available, and **static mode** (`descriptions`) applies a fixed mapping of interface names to description strings.

## How it Works

1. Client submits `update_interfaces_description` request to NetBox worker
2. Worker resolves the target NetBox instance and optionally the branch
3. If `description_template` is provided, the worker fetches interface connections via `get_connections` and NetBox interface objects for the selected devices
4. For each selected interface, the Jinja2 template is rendered with interface context and, when present, connection context (remote device, cable attributes, etc.)
5. If `descriptions` dict is provided, the worker iterates over the given device list and applies the fixed description values directly
6. In dry-run mode — the before (`-`) / after (`+`) diff is returned without writing to NetBox
7. Otherwise, the new description is saved to NetBox

## Prerequisites

- The devices must already exist in NetBox.
- Only interfaces, console ports, console server ports and power outlet ports are supported as port types.

## Branching Support

`update_interfaces_description` is branch-aware. Pass `branch=<name>` to write all changes into a [NetBox Branching Plugin](https://github.com/netboxlabs/netbox-branching) branch instead of main.

## Dry Run Mode

`dry_run=True` returns the before/after description diff without any NetBox writes:

```python
{
    "<device>": {
        "<interface>": {
            "-": "<current description>",
            "+": "<new description>",
        },
        ...
    },
    ...
}
```

## Template Mode

When `description_template` is provided, the Jinja2 template is rendered once per selected interface. Connected interfaces receive the full connection context. Virtual, LAG, or disconnected interfaces that have no connection data are still rendered with `device`, `interface`, and empty remote/cable fields. The template can be an inline string or a remote NorFab file reference (`nf://path/to/template.txt`).

Jinja2 context variables available in the template:

- `device` — pynetbox `dcim.device` object
- `interface` — pynetbox interface/console port/console server port object
- `remote_device` — string
- `remote_interface` — string
- `termination_type` — string
- `cable` — dictionary of directly attached cable attributes:
    - `type`
    - `status`
    - `tenant` — dictionary `{name: tenant_name}`
    - `label`
    - `tags` — list of `{name: tag_name}` dictionaries
    - `custom_fields` — dictionary with custom fields data
    - `peer_termination_type`
    - `peer_device`
    - `peer_interface`

Example template:

```
{{ remote_device }}:{{ remote_interface }}
```

## Static Mode

When `descriptions` dict is provided, the same mapping is applied to all devices in the `devices` list. Only interfaces that exist in NetBox are updated — missing interfaces are silently skipped.

```python
descriptions = {
    "Ethernet1": "uplink to spine-1",
    "Ethernet2": "uplink to spine-2",
}
```

## Examples

=== "CLI"

    Update interface descriptions using a Jinja2 template:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 description-template "{{ remote_device }}:{{ remote_interface }}"
    ```

    Update only selected interfaces:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 interfaces Ethernet1 Ethernet2 description-template "{{ remote_device }}:{{ remote_interface }}"
    ```

    Filter interfaces by regex pattern:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 description-template "{{ remote_device }}:{{ remote_interface }}" interface-regex "Ethernet.*"
    ```

    Dry run — preview changes without writing:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 description-template "{{ remote_device }}:{{ remote_interface }}" dry-run
    ```

    Apply static descriptions to matching interface names:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 descriptions {"Ethernet1":"uplink to spine-1","Ethernet2":"uplink to spine-2"}
    ```

    Update descriptions in a NetBox branch:

    ```bash
    nf#netbox update interfaces description devices ceos-leaf-1 description-template "{{ remote_device }}:{{ remote_interface }}" branch my-branch
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # update descriptions using a Jinja2 template
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            "description_template": "{{ remote_device }}:{{ remote_interface }}",
        },
    )

    # update only selected interfaces
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "interfaces": ["Ethernet1", "Ethernet2"],
            "description_template": "{{ remote_device }}:{{ remote_interface }}",
        },
    )

    # filter interfaces by regex and use a remote template
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "description_template": "nf://templates/intf_desc.j2",
            "interface_regex": "Ethernet.*",
        },
    )

    # dry run — preview diff without writing
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "description_template": "{{ remote_device }}:{{ remote_interface }}",
            "dry_run": True,
        },
    )

    # static descriptions dict applied to multiple devices
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1", "ceos-leaf-2"],
            "descriptions": {
                "Ethernet1": "uplink to spine-1",
                "Ethernet2": "uplink to spine-2",
            },
        },
    )

    # update into a NetBox branch
    result = client.run_job(
        "netbox",
        "update_interfaces_description",
        workers="any",
        kwargs={
            "devices": ["ceos-leaf-1"],
            "description_template": "{{ remote_device }}:{{ remote_interface }}",
            "branch": "my-branch",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Update Interfaces Description Command Shell Reference

NorFab shell supports these command options for the Netbox `update_interfaces_description` task:

```
nf# man tree netbox.update.interfaces.description
root
└── netbox:    Netbox service
    └── update:    Update Netbox objects
        └── interfaces:    Update interfaces
            └── description:    Updates the description of interfaces for specified devices in NetBox
                ├── timeout:    Job timeout
                ├── workers:    Filter worker to target, default 'any'
                ├── verbose-result:    Control output details, default 'False'
                ├── progress:    Display progress events, default 'True'
                ├── instance:    Netbox instance name to target
                ├── branch:    Branching plugin branch name to use
                ├── dry-run:    Return diff without writing to NetBox
                ├── devices:    Device names to update interfaces for
                ├── description-template:    Jinja2 template to render descriptions
                ├── descriptions:    Dict keyed by interface name with description string values
                ├── interfaces:    Specific interface names to update
                └── interface-regex:    Regex pattern to match interfaces and ports
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.interfaces_tasks.NetboxInterfacesTasks.update_interfaces_description
