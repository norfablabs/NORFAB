---
tags:
  - netbox
---

# Netbox Create IP Bulk Task

> task api name: `create_ip_bulk`

Task to allocate next available IP from prefix or get existing IP address for multiple devices and interfaces.

## Branching Support

Create IP task is branch aware and can create IP addresses within the branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) need to be installed on Netbox instance.

## NORFAB Netbox Create IP Command Shell Reference

NorFab shell supports these command options for Netbox `create_ip` task:

```
nf# man tree netbox.create.ip_bulk
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── ip-bulk:    Allocate next available IP address from prefix for multiple devices and interfaces
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── branch:    Branching plugin branch name to use
            ├── *prefix:    Prefix to allocate IP address from, can also provide prefix name or filters
            ├── *devices:    List of device names to create IP address for
            ├── interface_regex:    Regular expression of device interface names to create IP address for
            ├── interface_list:    List of interface names to create IP address for
            ├── description:    IP address description
            ├── vrf:    VRF to associate with IP address
            ├── tags:    Tags to add to IP address
            ├── dns_name:    IP address DNS name
            ├── tenant:    Tenant name to associate with IP address
            ├── comments:    IP address comments field
            ├── role:    IP address functional role
            ├── mask-len:    Mask length to use for IP address
            ├── create-peer-ip:    Create link peer IP address as well
            └── status:    IP address status
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.create_ip_bulk