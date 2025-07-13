---
tags:
  - netbox
---

# Netbox Get Circuits Task

> task api name: `get_circuits`

## NORFAB Netbox Get Circuits Command Shell Reference

NorFab shell supports these command options for Netbox `get_circuits` task:

```
nf#man tree netbox.get.circuits
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── circuits:    Query Netbox circuits data for devices
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── device-list:    Device names to query data for
            ├── dry-run:    Only return query content, do not run it
            ├── cid:    List of circuit identifiers to retrieve data for
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.get_circuits