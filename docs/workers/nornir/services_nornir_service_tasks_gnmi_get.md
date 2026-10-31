# gNMI Get

Retrieve configuration or operational data using `gnmi_get`. Device YANG models
and Get support determine which paths are available.

## Output

Results are keyed by host, then `get`. Replies contain `notification`
data with paths, timestamps, and values. The value structure depends on the
requested YANG tree. Serialization and failure options are described below.

## Examples

=== "CLI"

    Read an OpenConfig path:

    ```bash
    nf# nornir gnmi get FL ceos-spine-1 path /system/config/hostname datatype config
    nf# nornir gnmi get FL ceos-spine-1 openconfig-interfaces
    ```

=== "Python"

    Read an OpenConfig path:

    ```python
    result = client.run_job(
        "nornir", "gnmi_get",
        kwargs={"FL": ["ceos-spine-1"], "path": ["/system/config/hostname"], "datatype": "config"},
    )
    ```

=== "Junos"

    For native Junos configuration, use the `juniper` origin, `datatype config`,
    and `encoding json_ietf`. Put the origin in either the path or the prefix.

    CLI examples - read configuration sections:

    ```bash
    nf# nornir gnmi get FL vmx-1 path juniper:/interfaces datatype config encoding json_ietf
    nf# nornir gnmi get FL vmx-1 path juniper:/protocols/bgp datatype config encoding json_ietf
    nf# nornir gnmi get FL vmx-1 path juniper:/system/services datatype config encoding json_ietf
    ```

    Read one Junos interface using a prefix:

    ```bash
    nf# nornir gnmi get FL vmx-1 prefix juniper:/interfaces path interface[name=ge-0/0/0] datatype config encoding json_ietf
    ```

    Python examples - read configuration sections:

    ```python
    result = client.run_job(
        "nornir", "gnmi_get",
        kwargs={
            "FL": ["vmx-1"],
            "path": ["juniper:/interfaces", "juniper:/protocols/bgp",
                     "juniper:/system/services"],
            "datatype": "config",
            "encoding": "json_ietf",
        },
    )
    ```

    Read one Junos interface using a prefix:

    ```python
    result = client.run_job(
        "nornir", "gnmi_get",
        kwargs={
            "FL": ["vmx-1"],
            "prefix": "juniper:/interfaces",
            "path": ["interface[name=ge-0/0/0]"],
            "datatype": "config",
            "encoding": "json_ietf",
        },
    )
    ```

    The prefix example selects the same configuration as
    `juniper:/interfaces/interface[name=ge-0/0/0]`. Use `path /` with
    `datatype config` and `encoding json_ietf` for the complete native Junos
    configuration. OpenConfig shortcuts select a different model.

## Named getters

Select one or more shortcuts instead of, or alongside, explicit paths.
Python uses the corresponding underscore name with `True`.

| CLI shortcut | Python argument | Path |
| --- | --- | --- |
| `openconfig-system` | `openconfig_system` | `openconfig:/system` |
| `openconfig-interfaces` | `openconfig_interfaces` | `openconfig:/interfaces` |
| `openconfig-lldp` | `openconfig_lldp` | `openconfig:/lldp` |
| `openconfig-platform` | `openconfig_platform` | `openconfig:/components` |

The shortcut names identify YANG modules. `openconfig` is the gNMI origin.
At least one path or getter is required.

!!! note

    OpenConfig Get requests have been validated with Arista EOS and Cisco IOS XR.
    The same approach should work with any device that supports the requested
    `openconfig:/` path and Get operation. Available paths and encodings depend on
    the device.

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
    nf# nornir gnmi get FL ceos-spine-1 path nf://gnmi/paths.yaml
    ```

=== "Python"

    `gnmi/paths.yaml`:

    ```yaml
    - openconfig:/interfaces/interface[name=Loopback100]
    - openconfig:/interfaces/interface[name=Loopback101]
    ```

    ```python
    result = client.run_job(
        "nornir", "gnmi_get",
        kwargs={"FL": ["ceos-spine-1"], "path": "nf://gnmi/paths.yaml"},
    )
    ```

## Notes

Configure credentials, port, and TLS in the [gNMI connection inventory](services_nornir_service_inventory.md#gnmi-connection-inventory).
Common host filters, retries, and structured processors such as `jmespath` apply.
Use `add_details=True` for error and execution details. Use `to_dict=False`
for a list of results. Unmatched filters return `no_match`. Connection and
device errors mark hosts failed.

Use `prefix` for a shared path prefix and `target` for a gNMI target name.
Encoding is chosen automatically. If you set `encoding`, choose a format your
device supports for Get. Subscriptions are not exposed by this task.

## Troubleshooting

For connection errors, check the gRPC service, port, TLS, and credentials.
For device errors, check the path, datatype, and encoding. Advertised capabilities
do not guarantee every combination works. See [Get Capabilities](services_nornir_service_tasks_gnmi_get_capabilities.md).

## Task Command Shell Reference

```bash
nf#man tree nornir.gnmi.get

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── gnmi:    Retrieve device data using gNMI
        └── get:    Retrieve configuration or state
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
            ├── path:    YANG path or list of paths to retrieve, default '[]'
            ├── openconfig-system:    Get the OpenConfig system tree, default 'False'
            ├── openconfig-interfaces:    Get the OpenConfig interfaces tree, default 'False'
            ├── openconfig-lldp:    Get the OpenConfig LLDP tree, default 'False'
            ├── openconfig-platform:    Get the OpenConfig components tree, default 'False'
            ├── prefix:    Common YANG path prefix, default ''
            ├── target:    gNMI target name
            ├── datatype:    Data type to retrieve, default 'GnmiDataType.all_'
            └── encoding:    Response encoding. Default negotiates with the device
nf#
```

## Python API Reference

::: norfab.workers.nornir_worker.gnmi_tasks.GnmiTasks.gnmi_get
