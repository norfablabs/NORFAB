---
tags:
  - netbox
---

# Netbox Get Devices Task

> task api name: `get_devices`

## Get Devices Sample Usage

## NORFAB Netbox Get Devices Command Shell Reference

NorFab shell supports these command options for Netbox `get_devices` task:

```
nf#man tree netbox.get.devices
root
└── netbox:    Netbox service
    └── get:    Query data from Netbox
        └── devices:    Query Netbox devices data
            ├── instance:    Netbox instance name to target
            ├── workers:    Filter worker to target, default 'any'
            ├── timeout:    Job timeout
            ├── filters:    List of device filters dictionaries as a JSON string, examples: [{"q": "ceos1"}]
            ├── devices:    Device names to query data for
            ├── dry-run:    Only return query content, do not run it
            └── cache:    How to use cache, default 'True'
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.get_devices