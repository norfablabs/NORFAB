---
tags:
  - netbox
---

# Netbox Create IP Task

> task api name: `create_ip`

## NORFAB Netbox Create IP Command Shell Reference

NorFab shell supports these command options for Netbox `create_ip` task:

```
nf#man tree netbox.create.ip
root
└── netbox:    Netbox service
    └── create:    Create objects in Netbox
        └── ip:    Allocate next available IP address from prefix
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── verbose-result:    Control output details, default 'False'
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
            └── dry-run:    Do not commit to database
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.create_ip