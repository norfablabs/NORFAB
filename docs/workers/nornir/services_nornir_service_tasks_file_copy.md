---
tags:
  - nornir
---

# Nornir Service File Copy Task

> task api name: `file_copy`

The Nornir Service File Copy Task is a component of NorFab's Nornir service, designed to facilitate the transfer of files to and from network devices. This task provides network engineers with a reliable and efficient method for managing device configurations, firmware updates, and other critical files. By leveraging the capabilities of the Nornir service, users can automate file transfers.

## Nornir File Copy Sample Usage

## NORFAB Nornir File Copy Shell Reference

NorFab shell supports these command options for Nornir `file-copy` task:

```
nf#man tree nornir.file_copy
root
└── nornir:    Nornir service
    └── file-copy:    Copy files to/from devices
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── add-details:    Add task details to results, default 'False'
        ├── num-workers:    RetryRunner number of threads for tasks execution
        ├── num-connectors:    RetryRunner number of threads for device connections
        ├── connect-retry:    RetryRunner number of connection attempts
        ├── task-retry:    RetryRunner number of attempts to run task
        ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
        ├── connect-check:    RetryRunner test TCP connection before opening actual connection
        ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
        ├── tf:    File group name to save task results to on worker file system
        ├── tf-skip-failed:    Save results to file for failed tasks
        ├── diff:    File group name to run the diff for
        ├── diff-last:    File version number to diff, default is 1 (last)
        ├── progress:    Display progress events, default 'True'
        ├── table:    Table format (brief, terse, extend) or parameters or True
        ├── headers:    Table headers
        ├── headers-exclude:    Table headers to exclude
        ├── sortby:    Table header column to sort by
        ├── FO:    Filter hosts using Filter Object
        ├── FB:    Filter hosts by name using Glob Patterns
        ├── FH:    Filter hosts by hostname
        ├── FC:    Filter hosts containment of pattern in name
        ├── FR:    Filter hosts by name using Regular Expressions
        ├── FG:    Filter hosts by group
        ├── FP:    Filter hosts by hostname using IP Prefix
        ├── FL:    Filter hosts by names list
        ├── FM:    Filter hosts by platform
        ├── FX:    Filter hosts excluding them by name
        ├── FN:    Negate the match
        ├── hosts:    Filter hosts to target
        ├── *source-file:    Source file to copy
        ├── plugin:    Connection plugin parameters
        │   └── netmiko:    Use Netmiko plugin to copy files
        │       ├── destination-file:    Destination file to copy
        │       ├── file-system:    Destination file system
        │       ├── direction:    Direction of file copy, default 'put'
        │       ├── inline-transfer:    Use inline transfer, supported by Cisco IOS, default 'False'
        │       ├── overwrite-file:    Overwrite destination file if it exists, default 'False'
        │       ├── socket-timeout:    Socket timeout in seconds, default '10.0'
        │       └── verify-file:    Verify destination file hash after copy, default 'True'
        └── dry-run:    Do not copy files, just show what would be done, default 'False'
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.file_copy