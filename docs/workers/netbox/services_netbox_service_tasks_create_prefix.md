---
tags:
  - netbox
---

# Netbox Create Prefix Task

> task api name: `create_prefix`

Task to create next available prefix of given prefix length within parent prefix or get existing prefix. By default prefix length is `30` resulting in ptp subnet allocation.

Netbox service `create_prefix` task integrated with Nornir service and can be called 
using [netbox.create_prefix Jinja2 filter](../nornir/services_nornir_service_jinja2_filters.md#netboxcreate_prefix), 
allowing to allocate prefixes in Netbox on the fly while rendering configuration templates. 

!!! warning

    Netbox `create_prefix` task uses prefix description argument to deduplicate prefixes, calls to `create_prefix` task should contain identical prefix description value for same prefix.

## Branching Support

Create Prefix task is branch aware and can create IP addresses within the branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) need to be installed on Netbox instance.

## NORFAB Netbox Create Prefix Command Shell Reference

NorFab shell supports these command options for Netbox `create_prefix` task:

```
nf#man tree netbox.create.prefix
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
            ├── instance:    Netbox instance name to target
            ├── dry-run:    Do not commit to database
            ├── *parent:    Parent prefix to allocate new prefix from
            ├── *description:    Description for new prefix
            ├── prefixlen:    The prefix length of the new prefix, default '30'
            ├── vrf:    Name of the VRF to associate with the prefix
            ├── tags:    List of tags to assign to the prefix
            ├── tenant:    Name of the tenant to associate with the prefix
            ├── comments:    Comments for the prefix
            ├── role:    Role to assign to the prefix
            ├── site:    Name of the site to associate with the prefix
            ├── status:    Status of the prefix
            ├── branch:    Branching plugin branch name to use
            ├── timeout:    Job timeout
            ├── workers:    Filter worker to target, default 'any'
            ├── verbose-result:    Control output details, default 'False'
            └── progress:    Display progress events, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.create_prefix