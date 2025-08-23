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

```
nf# man tree netbox.update.device.facts
root
└── netbox:    Netbox service
    └── update:    Update Netbox data
        └── device:    Update device data
            └── facts:    Update device serial, OS version
                ├── timeout:    Job timeout
                ├── workers:    Filter worker to target, default 'any'
                ├── verbose-result:    Control output details, default 'False'
                ├── progress:    Display progress events, default 'True'
                ├── instance:    Netbox instance name to target
                ├── dry-run:    Return information that would be pushed to Netbox but do not push it
                ├── devices:    List of Netbox devices to update
                ├── batch-size:    Number of devices to process at a time, default '10'
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
                │       ├── FX:    Filter hosts excluding them by name
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
                └── branch:    Branching plugin branch name to use
nf#
```

## Python API Reference

::: norfab.workers.netbox_worker.NetboxWorker.update_device_facts