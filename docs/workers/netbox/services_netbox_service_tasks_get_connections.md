---
tags:
  - netbox
---

# Netbox Get Connections Task

> task api name: `get_connections`

## Get Connections Sample Usage

## NORFAB Netbox Get Connections Command Shell Reference

NorFab shell supports these command options for Netbox `get_connections` task:

```
nf#man tree netbox.get.connections
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
            ├── cache:    How to use cache, default 'True'
            └── add-cables:    Add interfaces directly attached cables details
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.get_connections