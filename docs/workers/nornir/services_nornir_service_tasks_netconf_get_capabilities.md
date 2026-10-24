# NETCONF Get Capabilities

List capabilities advertised by device NETCONF sessions using ncclient or Scrapli.
Use `netconf_get_capabilities` to check protocol features and advertised YANG modules.

## Output

Each host has a `server_capabilities` list of capability URIs. A capability filter
with no matches returns an empty list. `add_details=True` includes metadata and
`to_dict=False` returns serialized records. Connection errors mark hosts as failed.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf get-capabilities plugin ncclient FC spine
    nf# nornir netconf get-capabilities plugin scrapli capab-filter *candidate* FC leaf
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get_capabilities",
            kwargs={"plugin": "scrapli", "capab_filter": "*candidate*", "FC": "leaf"},
        )
        print(result)
    ```

## Notes

- `capab_filter` is a case-sensitive glob. Omit it to retrieve all capability URIs.
- Host filters select devices. The capability filter selects URIs within each reply.
- Capabilities describe the session. Use YANG Library or NETCONF monitoring for
  a fuller module inventory. Retrieve module source with [get-schema](services_nornir_service_tasks_netconf_get_schema.md).
- Configure the backend using the [NETCONF inventory](services_nornir_service_inventory.md#netconf-connection-inventory).

## Troubleshooting

Check NETCONF connectivity and credentials for connection errors. An empty
filtered list means no advertised URI matched. It does not indicate a failed RPC.

## Task Command Shell Reference

```text
nf#man tree nornir.netconf.get_capabilities

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── get-capabilities:    List NETCONF capabilities
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
            ├── plugin:    NETCONF backend, default 'NetconfPlugin.ncclient'
            └── capab-filter:    Capability glob filter
nf#
```

Common host filters and job options apply.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_get_capabilities
