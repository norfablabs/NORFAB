---
tags:
  - nornir
---

# Nornir Service File Copy Task

> task api name: `file_copy`

The Nornir service `file_copy` task transfers files to or from network devices. It is commonly used for configuration backups, file staging, image transfers, and other operational file movement workflows. The task currently exposes file transfer through the Netmiko plugin.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `source_file` | Yes | Local source file path on the worker. |
| `plugin` | No | File transfer plugin parameters. Use `{"netmiko": {...}}` for Netmiko options. |
| `dry_run` | No | Return the planned operation without copying files. |
| `workers` | No | Nornir workers to target. Defaults to all workers. |
| `add_details` | No | Include detailed Nornir task metadata in the result. |
| `FC`, `FB`, `FH`, `FL`, `FM`, `FG`, `FR`, `FO`, `FP`, `FX`, `FN`, `hosts` | No | Host filters. |

## Output

The task returns per-host file transfer results. With `dry_run=True`, the result shows what would be copied without performing the transfer.

## Examples

!!! example

    === "CLI"

        Copy a file to devices whose hostnames contain `spine`:

        ```bash
        nf# nornir file-copy source-file ./files/startup.cfg FC spine plugin netmiko destination-file startup.cfg file-system flash:
        ```

        Preview the copy operation without transferring the file:

        ```bash
        nf# nornir file-copy source-file ./files/startup.cfg FC spine dry-run
        ```

    === "Python"

        Context manager - copy a file with Netmiko:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        with NorFab(inventory="inventory.yaml") as nf:
            client = nf.make_client()

            result = client.run_job(
                service="nornir",
                task="file_copy",
                kwargs={
                    "source_file": "./files/startup.cfg",
                    "FC": "spine",
                    "plugin": {
                        "netmiko": {
                            "destination_file": "startup.cfg",
                            "file_system": "flash:",
                            "direction": "put",
                            "overwrite_file": True,
                            "verify_file": True,
                        }
                    },
                },
            )

            pprint.pprint(result)
        ```

        Direct lifecycle - dry run before copying:

        ```python
        import pprint

        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="inventory.yaml")
        try:
            nf.start()
            client = nf.make_client()

            result = client.run_job(
                service="nornir",
                task="file_copy",
                kwargs={
                    "source_file": "./files/startup.cfg",
                    "FC": "spine",
                    "dry_run": True,
                },
            )

            pprint.pprint(result)
        finally:
            nf.destroy()
        ```

## NORFAB Nornir File Copy Shell Reference

NorFab shell supports these command options for Nornir `file-copy` task:

```bash
nf# man tree nornir.file_copy
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

::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.file_copy
