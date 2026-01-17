---
tags:
  - netbox
---

# Netbox Get Circuits Task

> task api name: `get_circuits`

## How It Works

Sample devices' circuits data retrieved from Netbox:

```
{
    "netbox-worker-1.1": {
        "fceos4": {
            "CID1": {
                "comments": "",
                "commit_rate": null,
                "custom_fields": {},
                "description": "",
                "interface": "eth101",
                "is_active": true,
                "last_updated": "2026-01-02T22:50:14.739796+00:00",
                "provider": "Provider1",
                "provider_account": "",
                "remote_device": "fceos5",
                "remote_interface": "eth101",
                "status": "active",
                "tags": [],
                "tenant": null,
                "termination_a": {
                    "id": "36",
                    "last_updated": "2026-01-02T22:50:12.085037+00:00"
                },
                "termination_z": {
                    "id": "37",
                    "last_updated": "2026-01-02T22:50:14.498313+00:00"
                },
                "type": "DarkFibre"
            },
            "CID2": {
              ... etc ...
```

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