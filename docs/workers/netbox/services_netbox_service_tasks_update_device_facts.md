---
tags:
  - netbox
---

# Netbox Update Device Facts Task

> task api name: `update_device_facts`

## Limitations

Datasource `nornir` uses NAPALM `get_facts` getter and as such only supports these device platforms:

- Arista EOS
- Cisco IOS
- Cisco IOSXR
- Cisco NXOS
- Juniper JUNOS

Update device facts task is branch aware and can push updates to the branch, branching plugin need to be installed on Netbox instance.

## Update Device Facts Sample Usage

## NORFAB Netbox Update Device Facts Command Shell Reference

NorFab shell supports these command options for Netbox `update_device_facts` task:

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.update_device_facts