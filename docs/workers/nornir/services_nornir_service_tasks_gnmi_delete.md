# gNMI Delete

Remove configuration paths using `gnmi_delete`. For deletion combined with
updates or replacements, use [Set](services_nornir_service_tasks_gnmi_set.md).
Delete only configuration you own.

## Output

Results are grouped by host under the `set` key. Replies list the deleted paths
and the device timestamp.

## Examples

=== "CLI"

    ```bash
    nf# nornir gnmi delete FL ceos-spine-1 path openconfig:/interfaces/interface[name=Loopback100]
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "gnmi_delete",
        kwargs={
            "FL": ["ceos-spine-1"],
            "path": ["openconfig:/interfaces/interface[name=Loopback100]"],
        },
    )
    ```

## Read paths from a file

The path argument also accepts an `nf://` JSON/YAML file containing a list of
paths. Use the same file for all selected devices. Write the paths directly
in the file. Templates and links to other files are not supported.

=== "CLI"

    `gnmi/paths.yaml`:

    ```yaml
    - openconfig:/interfaces/interface[name=Loopback100]
    - openconfig:/interfaces/interface[name=Loopback101]
    ```

    ```bash
    nf# nornir gnmi delete FL ceos-spine-1 path nf://gnmi/paths.yaml
    ```

=== "Python"

    `gnmi/paths.yaml`:

    ```yaml
    - openconfig:/interfaces/interface[name=Loopback100]
    - openconfig:/interfaces/interface[name=Loopback101]
    ```

    ```python
    result = client.run_job(
        "nornir", "gnmi_delete",
        kwargs={"FL": ["ceos-spine-1"], "path": "nf://gnmi/paths.yaml"},
    )
    ```

## Notes

Configure credentials, port, and TLS in the [gNMI connection inventory](services_nornir_service_inventory.md#gnmi-connection-inventory).
Common host filters, retries, and structured processors such as `jmespath` apply.
Use `add_details=True` for error and execution details. Use `to_dict=False`
for a list of results. Unmatched filters return `no_match`. Connection and
device errors mark hosts failed.

Supply a nonempty path list. Optional `prefix` and `target` apply to the request.
Update and replace arguments are rejected.

No backup or rollback is performed. A timeout can leave the outcome uncertain.
Retries may repeat an applied deletion. Deleting an already removed path may succeed or fail, depending on the device. Verify the resulting configuration with [Get](services_nornir_service_tasks_gnmi_get.md).

## Troubleshooting

Check port, TLS, and credentials for connection errors. Check permissions and
model paths for device errors. A previously removed path may produce a different
result when deleted again.

## Task Command Shell Reference

```bash
nf#man tree nornir.gnmi.delete

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── gnmi:    Retrieve device data using gNMI
        └── delete:    Delete configuration paths
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
            ├── jmespath:    JMESPath expression to run with DataProcessor
            ├── path (R):    Configuration path or paths to delete
            ├── prefix:    Common YANG path prefix, default ''
            └── target:    gNMI target name
nf#
```

## Python API Reference

::: norfab.workers.nornir_worker.gnmi_tasks.GnmiTasks.gnmi_delete
