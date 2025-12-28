---
tags:
  - netbox
---

# Netbox Create Device Interfaces Task

> task api name: `create_device_interfaces`

Task to create network interfaces on one or more devices in NetBox. This task creates interfaces in bulk and only if the interfaces do not already exist in NetBox, making it idempotent and safe to run multiple times.

The task supports alphanumeric range expansion, allowing you to create multiple interfaces with a single pattern. This is particularly useful for creating large numbers of similar interfaces efficiently.

!!! tip

    The `create_device_interfaces` task automatically skips interfaces that already exist, preventing duplicate creation attempts and allowing for safe re-runs of automation tasks.

## Interface Name Range Expansion

The task supports powerful range expansion patterns for creating multiple interfaces:

### Numeric Ranges

Use `[start-end]` syntax to expand numeric ranges:

```yaml
interface_name: "Ethernet[1-5]"
# Expands to: Ethernet1, Ethernet2, Ethernet3, Ethernet4, Ethernet5

interface_name: "Loopback[10-12]"
# Expands to: Loopback10, Loopback11, Loopback12
```

### Comma-Separated Lists

Use `[option1,option2,...]` syntax to expand lists:

```yaml
interface_name: "[ge,xe,fe]-0/0/0"
# Expands to: ge-0/0/0, xe-0/0/0, fe-0/0/0

interface_name: "Port-[A,B,C]"
# Expands to: Port-A, Port-B, Port-C
```

### Multiple Range Patterns

Combine multiple range patterns in a single interface name:

```yaml
interface_name: "[ge,xe]-0/0/[0-3]"
# Expands to: ge-0/0/0, ge-0/0/1, ge-0/0/2, ge-0/0/3,
#             xe-0/0/0, xe-0/0/1, xe-0/0/2, xe-0/0/3
```

### Multiple Interface Names

Pass a list of interface names (with or without ranges):

```yaml
interface_name: 
  - "Loopback[1-3]"
  - "Management1"
  - "[ge,xe]-0/1/0"
# Expands to: Loopback1, Loopback2, Loopback3, Management1, ge-0/1/0, xe-0/1/0
```

## Branching Support

Create Device Interfaces task is branch aware and can create interfaces within a branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) needs to be installed on the Netbox instance.

When using branches, interfaces are created in the specified branch and can be reviewed before merging into the main database.

## NORFAB Netbox Create Device Interfaces Command Shell Reference

NorFab shell supports these command options for Netbox `create_device_interfaces` task:

```
nf#man tree netbox.create.device-interfaces
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── device-interfaces:    Create devices interfaces
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── branch:    Branching plugin branch name to use
            ├── *devices:    List of device names or device objects to create interfaces for
            ├── *interface_name:    Name(s) of the interface(s) to create
            ├── interface-type:    Name(s) of the interface(s) to create, default 'other'
            ├── description:    Interface description
            ├── speed:    Interface speed in Kbps
            ├── mtu:    Maximum transmission unit size in bytes
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── progress:    Display progress events, default 'True'
nf#
```

## Usage Examples

### Basic Interface Creation

Create a single interface on one device:

```python
from norfab.core.nfapi import NorFab

nf = NorFab()
result = nf.run_job(
    service="netbox",
    task="create_device_interfaces",
    workers="any",
    kwargs={
        "devices": ["switch-01", "switch-02"],
        "interface_name": "Loopbback[0-5]",
        "interface_type": "virtual",
        "description": "Test interfaces"
    }
)
```

## Interface Types

Common interface types supported by NetBox:

- `virtual` - Virtual interfaces (loopbacks, tunnel interfaces)
- `lag` - Link Aggregation Group (Port-Channel, bond)
- `1000base-t` - 1G copper Ethernet
- `10gbase-x-sfpp` - 10G SFP+ Ethernet
- `25gbase-x-sfp28` - 25G SFP28 Ethernet
- `40gbase-x-qsfpp` - 40G QSFP+ Ethernet
- `100gbase-x-qsfp28` - 100G QSFP28 Ethernet
- `other` - Generic interface type (default)

Refer to your NetBox instance for the complete list of available interface types.

## Error Handling

Task handles several error conditions gracefully:

1. **Non-existent Device**: If a device doesn't exist in NetBox, an error is logged but processing continues for other devices
2. **Duplicate Interfaces**: Existing interfaces are automatically skipped and listed in the `skipped` array
3. **Invalid Interface Type**: NetBox will reject invalid interface types with an error message
4. **Branch Not Found**: If a specified branch doesn't exist and the branching plugin is not available, the task will fail

## Best Practices

1. **Use Dry Run First**: Always test with `dry_run: True` before creating interfaces in production
2. **Meaningful Names**: Use descriptive interface names that match your device's actual interface naming
3. **Consistent Types**: Use appropriate interface types that match the physical/virtual nature of the interfaces
4. **Batch Operations**: Create multiple interfaces in a single call for efficiency
5. **Branch Usage**: Use branches for testing bulk operations before committing to the main database
6. **Idempotency**: The task is idempotent - running it multiple times with the same parameters is safe

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.create_device_interfaces
