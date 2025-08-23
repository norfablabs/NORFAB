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

## Branching Support

Update device facts task is branch aware and can push updates to the branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) need to be installed on Netbox instance.

## Update Device Facts Sample Usage

## NORFAB Netbox Update Device Facts Command Shell Reference

NorFab shell supports these command options for Netbox `update_device_facts` task:

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.update_device_facts