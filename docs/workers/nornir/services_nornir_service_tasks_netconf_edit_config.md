# NETCONF Edit Configuration

Apply XML configuration with `netconf_edit_config` using ncclient (default) or
Scrapli NETCONF. Available through Python, NFCLI, FastAPI, and MCP.

## Output

Use [XML processors](services_nornir_service_tasks_netconf_processors.md) to convert replies to
dictionaries (`xmltodict`), select XML elements (`xpath`), or extract flat
values (`xml-flake`).

Results contain XML replies under each host's `edit_config` key. Successful
operations normally return an `<ok/>` reply. `add_details=True` includes task
metadata; `to_dict=False` returns serialized records. Failed RPCs and connection
errors mark host results as failed.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf edit-config config nf://netconf/interface.xml target running plugin scrapli FL ceos-leaf-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_edit_config",
            kwargs={
                "FL": ["ceos-leaf-1"],
                "target": "running",
                "config": (
                    '<config><interfaces xmlns="http://openconfig.net/yang/interfaces">'
                    '<interface><name>Ethernet1</name><config>'
                    '<name>Ethernet1</name><description>Lab uplink</description>'
                    '</config></interface></interfaces></config>'
                ),
            },
        )
        print(result)
    ```

### Use a configuration template

Store XML including the `<config>` wrapper at `nf://netconf/interface.xml`.
The template can reference `host` and `job_data`.

=== "CLI"

    ```text
    nf# nornir netconf edit-config config nf://netconf/interface.xml target running plugin scrapli FL ceos-leaf-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_edit_config",
        kwargs={
            "config": "nf://netconf/interface.xml",
            "target": "running",
            "plugin": "scrapli",
            "FL": ["ceos-leaf-1"],
        },
    )
    ```

## Notes

- Configure the selected backend using the [NETCONF connection inventory](services_nornir_service_inventory.md#netconf-connection-inventory).
- Include the NETCONF `<config>` wrapper. XML content must match the device's YANG models.
- `config` accepts inline XML or a NorFab template URL. Templates render per host
  with `host`, `job_data`, `norfab`, and `netbox` context. `job_data` accepts data
  or a YAML file URL.
- `target` accepts running or candidate, subject to device capabilities. Running
  changes take effect immediately. Candidate changes require a subsequent commit.
- This task does not lock datastores, validate, commit, or roll back changes.
  A failed edit can leave partial changes. Standard retries can repeat an edit.
- NETCONF subtree and XPath read filters do not apply to edits. The operation
  uses backend default edit behavior; backend-specific edit options are not a
  common interface across both plugins.

## Troubleshooting

Check XML namespaces, datastore capabilities, and write permissions for RPC
errors. Read the configuration back with `netconf_get_config` to verify changes.

## Task Command Shell Reference

```text
nf#man tree nornir.netconf.edit_config

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── edit-config:    Edit NETCONF configuration
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── FO:    Filter hosts using a Nornir-Salt Filter Object
            ├── FB:    Filter hosts by name using glob patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts by name containment pattern
            ├── FR:    Filter hosts by name using regular expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Exclude hosts by name
            ├── FN:    Negate the host filter match
            ├── on-failed:    Run task on hosts currently marked as failed by Nornir, default 'False'
            ├── to-dict:    Return task results as a dictionary keyed by host, default 'True'
            ├── add-details:    Add Nornir task execution details to results, default 'False'
            ├── progress:    Emit progress events during task execution, default 'True'
            ├── num-workers:    RetryRunner number of threads for task execution
            ├── num-connectors:    RetryRunner number of threads for device connections
            ├── connect-retry:    RetryRunner number of connection attempts
            ├── task-retry:    RetryRunner number of attempts to run each task
            ├── reconnect-on-fail:    RetryRunner reconnects to a host after task failure
            ├── connect-check:    RetryRunner tests TCP connectivity before opening connection
            ├── connect-timeout:    RetryRunner TCP connection check timeout in seconds
            ├── creds-retry:    RetryRunner connection credentials and parameters to retry
            ├── tf:    File group name to save task results on the worker
            ├── tf-skip-failed:    Skip failed task results when saving to file
            ├── diff:    File group name to diff task results against
            ├── diff-last:    Previous saved file version to diff against
            ├── xmltodict:    Convert XML replies to dictionaries with DataProcessor, default 'False'
            ├── xpath:    XPath expression to run with DataProcessor
            ├── xml-flake:    XML flake pattern for DataProcessor
            ├── plugin:    NETCONF backend, default 'NetconfPlugin.ncclient'
            ├── config (R):    XML config wrapper or NorFab template URL
            ├── target:    Datastore to edit, default 'NetconfConfigTarget.running'
            └── job-data:    Template data or YAML file URL
nf#
```

Common host filters and job options are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_edit_config
