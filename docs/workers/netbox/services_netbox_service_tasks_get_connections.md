---
tags:
  - netbox
---

# Netbox Get Connections Task

> task api name: `get_connections`

Retrieves connection details for interfaces and ports on one or more devices from NetBox. The task returns physical links, virtual and LAG-derived links, console connections, provider network connections, cable details, and remote MAC addresses where NetBox has that data.

## How It Works

1. Client submits a `get_connections` request to the NetBox worker
2. Worker resolves the target NetBox instance
3. Worker queries NetBox GraphQL for interface and port objects on the selected devices
4. Optional `interfaces` and `interface_regex` filters narrow the ports included in the GraphQL result
5. Worker normalises physical, virtual, LAG, console, and provider network connections into a device/interface keyed dictionary
6. In dry-run mode, the raw GraphQL query result is returned instead of the normalised connection map

## Prerequisites

- Target devices must exist in NetBox.
- NetBox version must be `4.4.0` or newer.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `devices` | Yes | List of device names to retrieve connections for |
| `interfaces` | No | Exact interface or port names to include |
| `interface_regex` | No | Case-insensitive regex pattern to match interface and port names |
| `instance` | No | NetBox instance name to target |
| `dry_run` | No | Return raw GraphQL query content instead of processed connection data |
| `cache` | No | Cache usage mode accepted by the command model |

## Output

Normal mode returns connection data keyed by device name and interface or port name:

```python
{
    "<device>": {
        "<interface>": {
            "breakout": False,
            "remote_device": "<peer-device>",
            "remote_device_status": "active",
            "remote_interface": "<peer-interface>",
            "remote_interface_label": "<peer-label>",
            "remote_termination_type": "interface",
            "termination_type": "interface",
            "remote_mac_addresses": ["00:11:22:33:44:55"],
            "cable": {
                "type": "smf",
                "status": "connected",
                "label": "",
                "tags": [],
                "custom_fields": {},
                "peer_termination_type": "interface",
                "peer_device": "<peer-device>",
                "peer_interface": "<peer-interface>",
            },
        },
    },
}
```

Provider network connections include `provider` instead of remote device/interface details.

## Filtering

Use `interfaces` when you know exact port names. Use `interface_regex` when you want to match a group of ports. If both are provided, NetBox returns only ports matching the explicit names and the regex.

## Dry Run Mode

`dry_run=True` returns the raw GraphQL result used by the task. This is useful when checking the NetBox query output or troubleshooting why a connection was not normalised.

## Examples

=== "CLI"

    Query all connections for two devices:

    ```bash
    nf#netbox get connections devices fceos4 fceos5
    ```

    Query selected interface names only:

    ```bash
    nf#netbox get connections devices fceos4 fceos5 interfaces eth101 eth103
    ```

    Query connections matching an interface regex:

    ```bash
    nf#netbox get connections devices fceos4 interface-regex "eth10[1-4]"
    ```

    Return the raw GraphQL query result:

    ```bash
    nf#netbox get connections devices fceos4 dry-run
    ```

    Query a specific NetBox instance:

    ```bash
    nf#netbox get connections devices fceos4 instance lab
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    nf.start()
    client = nf.make_client()

    # query all connections for two devices
    result = client.run_job(
        "netbox",
        "get_connections",
        workers="any",
        kwargs={
            "devices": ["fceos4", "fceos5"],
        },
    )

    # query selected interface names only
    result = client.run_job(
        "netbox",
        "get_connections",
        workers="any",
        kwargs={
            "devices": ["fceos4", "fceos5"],
            "interfaces": ["eth101", "eth103"],
        },
    )

    # query connections matching an interface regex
    result = client.run_job(
        "netbox",
        "get_connections",
        workers="any",
        kwargs={
            "devices": ["fceos4"],
            "interface_regex": "eth10[1-4]",
        },
    )

    # return raw GraphQL query result
    result = client.run_job(
        "netbox",
        "get_connections",
        workers="any",
        kwargs={
            "devices": ["fceos4"],
            "dry_run": True,
        },
    )

    # query a specific NetBox instance
    result = client.run_job(
        "netbox",
        "get_connections",
        workers="any",
        kwargs={
            "devices": ["fceos4"],
            "instance": "lab",
        },
    )

    nf.destroy()
    ```

## NORFAB Netbox Get Connections Command Shell Reference

NorFab shell supports these command options for Netbox `get_connections` task:

!!! note
    The command model accepts `cache`, but the current task implementation does not use it when running the GraphQL query.

```bash
nf# man tree netbox.get.connections
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── connections:    Query Netbox connections data for devices
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Only return query content, do not run it
            ├── devices:    Device names to query data for
            ├── interfaces:    Interface and port names to query data for
            ├── interface-regex:    Regex pattern to match interfaces and ports
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.connections_tasks.NetboxConnectionsTasks.get_connections
