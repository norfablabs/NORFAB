---
tags:
  - netbox
---

# Netbox Get Interfaces Task

> task api name: `get_interfaces`

## Get Interfaces Sample Usage

## NORFAB Netbox Get Interfaces Command Shell Reference

NorFab shell supports these command options for Netbox `get_interfaces` task:

```
nf#man tree netbox.get.interfaces
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── interfaces:    Query Netbox device interfaces data
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── *devices:    Devices to retrieve interface for
            ├── ip-addresses:    Retrieves interface IP addresses
            ├── inventory-items:    Retrieves interface inventory items
            └── dry-run:    Only return query content, do not run it
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.get_interfaces