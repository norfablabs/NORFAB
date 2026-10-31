# gNMI Get Capabilities

Discover models, encodings, and protocol version advertised by a device using
`gnmi_get_capabilities`.

## Output

Results are keyed by host, then `capabilities`. Backend replies advertise:

- `supported_models`: model names, organizations, and versions.
- `supported_encodings`: encoding names.
- `gnmi_version`: protocol version.

Fields depend on what the device advertises.

## Examples

=== "CLI"

    ```bash
    nf# nornir gnmi get-capabilities FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "gnmi_get_capabilities",
        kwargs={"FL": ["ceos-spine-1"]},
    )
    ```

## Notes

Configure credentials, port, and TLS in the [gNMI connection inventory](services_nornir_service_inventory.md#gnmi-connection-inventory).
Common host filters, retries, and structured processors such as `jmespath` apply.
Use `add_details=True` for error and execution details. Use `to_dict=False`
for a list of results. Unmatched filters return `no_match`. Connection and
device errors mark hosts failed.

The device may not support every listed path or encoding for every operation.
This task lists models and versions. It does not download YANG schema files. For schema downloads,
use [NETCONF Get Schema](services_nornir_service_tasks_netconf_get_schema.md)
when supported. The model sets advertised over NETCONF and gNMI can differ.

## Troubleshooting

For connection errors, check the gRPC service, port, TLS, and credentials. The device may omit some capability details. To confirm a particular path works, issue
an actual [Get](services_nornir_service_tasks_gnmi_get.md) request.

## Task Command Shell Reference

```bash
nf#man tree nornir.gnmi.get_capabilities

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── gnmi:    Retrieve device data using gNMI
        └── get-capabilities:    Discover gNMI models, encodings, and version
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
            └── jmespath:    JMESPath expression to run with DataProcessor
nf#
```

## Python API Reference

::: norfab.workers.nornir_worker.gnmi_tasks.GnmiTasks.gnmi_get_capabilities
