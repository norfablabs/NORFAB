# NETCONF Get Schema

Retrieve a YANG module with `netconf_get_schema` using ncclient or Scrapli.
The device must implement NETCONF monitoring `get-schema`.

## Output

Per-host XML replies contain the schema text. The operation key is `get_schema`
for ncclient and `rpc` for Scrapli, which sends the standard RPC directly.
Missing modules and unsupported operations mark hosts as failed.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf get-schema identifier openconfig-system plugin ncclient FL ceos-spine-1
    nf# nornir netconf get-schema identifier openconfig-system plugin scrapli FL ceos-spine-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get_schema",
            kwargs={"identifier": "openconfig-system", "plugin": "scrapli",
                    "FL": ["ceos-spine-1"]},
        )
        print(result)
    ```

## Notes

- Select an `identifier` from module names advertised in capabilities, YANG
  Library, or the NETCONF monitoring schema list. Capabilities may be incomplete
  and do not guarantee that schema retrieval is available.
- `version` selects a revision, usually YYYY-MM-DD. Omit it for server selection.
- `format` accepts `yang` (default) or `yin`. Imports are not fetched automatically.
- Configure the backend in the [NETCONF inventory](services_nornir_service_inventory.md#netconf-connection-inventory).

## Troubleshooting

For missing-schema errors, verify the identifier and revision against the device
schema list. An unsupported-operation error means the device cannot serve the
schema through this RPC.

## Task Command Shell Reference

```text
nf#man tree nornir.netconf.get_schema

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── get-schema:    Retrieve a YANG module
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
            ├── identifier (R):    YANG module name
            ├── version:    Module revision
            ├── format:    Schema format, default 'NetconfSchemaFormat.yang'
            └── plugin:    NETCONF backend, default 'NetconfPlugin.ncclient'
nf#
```

Common host filters and job options apply.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_get_schema
