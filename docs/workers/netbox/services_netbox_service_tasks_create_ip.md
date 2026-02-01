---
tags:
  - netbox
---

# Netbox Create IP Task

> task api name: `create_ip`

Task to create next available IP from prefix or get existing IP address.

Netbox service `create_ip` task integrated with Nornir service and can be called 
using [netbox.create_ip Jinja2 filter](../nornir/services_nornir_service_jinja2_filters.md#netboxcreate_ip), 
allowing to allocate IP addresses in Netbox on the fly while rendering configuration templates. 

## Branching Support

Create IP task is branch aware and can create IP addresses within the branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) need to be installed on Netbox instance.

## NORFAB Netbox Create IP Command Shell Reference

NorFab shell supports these command options for Netbox `create_ip` task:

```
nf#man tree netbox.create.ip
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── *prefix:    Prefix to allocate IP address from, can also provide prefix name or filters
            ├── device:    Device name to associate IP address with
            ├── interface:    Device interface name to associate IP address with
            ├── description:    IP address description
            ├── vrf:    VRF to associate with IP address
            ├── tags:    Tags to add to IP address
            ├── dns_name:    IP address DNS name
            ├── tenant:    Tenant name to associate with IP address
            ├── comments:    IP address comments field
            ├── role:    IP address functional role
            └── branch:    Branching plugin branch name to use
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.create_ip