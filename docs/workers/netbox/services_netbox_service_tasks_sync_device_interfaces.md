---
tags:
  - netbox
---

# Netbox Sync Device Interfaces Task

> task api name: `sync_device_interfaces`

The Netbox Sync Device Interfaces Task is a feature of the NorFab Netbox Service that allows you to synchronize and update the interface data of your network devices in Netbox. This task ensures that the interface configurations in Netbox are accurate and up-to-date, reflecting the current state of your network infrastructure.

Keeping interface data accurate and up-to-date is crucial for effective network management. The Netbox Update Device Interfaces Task automates the process of updating interface information, such as interface names, statuses, mac addresses, and other relevant details.

## Branching Support

Update device interfaces task is branch aware and can push updates to the branch. [Netbox Branching Plugin](https://github.com/netboxlabs/netbox-branching) need to be installed on Netbox instance.

**How it works** - Netbox worker on a call to update interfaces task fetches live data from network devices using nominated datasource, by default it is Nornir service [parse](../nornir/services_nornir_service_tasks_parse.md) task using NAPALM `get_interfaces` getter. Once data retrieved from network, Netbox worker updates records in Netbox database for device interfaces.

![Netbox Update Device Interfaces](../../images/Netbox_Service_Sync_Interfaces.jpg)

1. Client submits and on-demand request to NorFab Netbox worker to update device interfaces

2. Netbox worker sends job request to nominated datasource service to fetch live data from network devices

3. Datasource service fetches data from the network

4. Datasource returns devices interfaces data back to Netbox Service worker

5. Netbox worker processes device interfaces data and updates records in Netbox for requested devices

## Limitations

Datasource `nornir` uses NAPALM `get_interfaces` getter and as such only supports these device platforms:

- Arista EOS
- Cisco IOS
- Cisco IOSXR
- Cisco NXOS
- Juniper JUNOS

## Update Device Interfaces Sample Usage

## NORFAB Netbox Update Device Interfaces Command Shell Reference

NorFab shell supports these command options for Netbox `sync_device_interfaces` task:

```
nf# man tree netbox.update.device.interfaces
root
└── netbox:    Netbox service
    └── sync:    Update Netbox data
        └── device:    Update device data
            └── interfaces:    Update device interfaces
                ├── timeout:    Job timeout
                ├── workers:    Filter worker to target, default 'any'
                ├── verbose-result:    Control output details, default 'False'
                ├── progress:    Display progress events, default 'True'
                ├── instance:    Netbox instance name to target
                ├── dry-run:    Return information that would be pushed to Netbox but do not push it
                ├── devices:    List of Netbox devices to update
                ├── datasource:    Service to use to retrieve device data, default 'nornir'
                │   └── nornir:    Use Nornir service to retrieve data from devices
                │       ├── FO:    Filter hosts using Filter Object
                │       ├── FB:    Filter hosts by name using Glob Patterns
                │       ├── FH:    Filter hosts by hostname
                │       ├── FC:    Filter hosts containment of pattern in name
                │       ├── FR:    Filter hosts by name using Regular Expressions
                │       ├── FG:    Filter hosts by group
                │       ├── FP:    Filter hosts by hostname using IP Prefix
                │       ├── FL:    Filter hosts by names list
                │       ├── FM:    Filter hosts by platform
                │       ├── FN:    Negate the match
                │       ├── add-details:    Add task details to results, default 'False'
                │       ├── num-workers:    RetryRunner number of threads for tasks execution
                │       ├── num-connectors:    RetryRunner number of threads for device connections
                │       ├── connect-retry:    RetryRunner number of connection attempts
                │       ├── task-retry:    RetryRunner number of attempts to run task
                │       ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
                │       ├── connect-check:    RetryRunner test TCP connection before opening actual connection
                │       ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
                │       ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
                │       ├── tf:    File group name to save task results to on worker file system
                │       ├── tf-skip-failed:    Save results to file for failed tasks
                │       ├── diff:    File group name to run the diff for
                │       ├── diff-last:    File version number to diff, default is 1 (last)
                │       └── progress:    Display progress events, default 'True'
                ├── batch-size:    Number of devices to process at a time, default '10'
                └── branch:    Branching plugin branch name to use
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.sync_device_interfaces