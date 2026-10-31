# gNMI Set

Merge, replace, or delete device configuration with `gnmi_set`. Combine operations
in one Set request per host. Use only configuration paths you own in these examples.

## Output

Results are keyed by host, then `set`. Replies list the operations performed and the device timestamp. Use [Get](services_nornir_service_tasks_gnmi_get.md) to
verify resulting values. `add_details=True` includes error and execution details.
`to_dict=False` returns a list of results. Unmatched filters return `no_match`.
Connection and device errors mark hosts failed.

## Examples

### Update configuration

Update adds or changes the supplied settings at each path. NFCLI takes a JSON
list of path/object pairs. Python takes a list of pairs.

=== "CLI"

    ```bash
    nf# nornir gnmi set FL ceos-spine-1 update [["openconfig:/interfaces/interface[name=Loopback100]/config", {"name": "Loopback100", "type": "iana-if-type:softwareLoopback", "description": "managed by NorFab"}]]
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "gnmi_set",
        kwargs={
            "FL": ["ceos-spine-1"],
            "update": [[
                "openconfig:/interfaces/interface[name=Loopback100]/config",
                {"name": "Loopback100", "type": "iana-if-type:softwareLoopback",
                 "description": "managed by NorFab"},
            ]],
        },
    )
    ```

### Apply a prefix and target

`prefix` supplies a common path before every operation's relative path. Set the
origin in the prefix and use relative paths without their own origin.

`target` sets the gNMI request's target name. It does not select Nornir hosts or
workers: use `FL` and `workers` for those. Target names and support depend on the
device or gNMI proxy. Omit target when the server does not require it. The example
uses a server that recognizes `ceos-spine-1` as its target.

=== "CLI"

    ```bash
    nf# nornir gnmi set FL ceos-spine-1 prefix openconfig:/interfaces target ceos-spine-1 update [["interface[name=Loopback100]/config", {"description": "updated using a prefix"}]]
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "gnmi_set",
        kwargs={
            "FL": ["ceos-spine-1"],
            "prefix": "openconfig:/interfaces",
            "target": "ceos-spine-1",
            "update": [["interface[name=Loopback100]/config",
                        {"description": "updated using a prefix"}]],
        },
    )
    ```

### Delete an inline list of paths

=== "CLI"

    ```bash
    nf# nornir gnmi set FL ceos-spine-1 prefix openconfig:/interfaces delete ["interface[name=Loopback102]", "interface[name=Loopback103]"]
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "gnmi_set",
        kwargs={
            "FL": ["ceos-spine-1"],
            "prefix": "openconfig:/interfaces",
            "delete": ["interface[name=Loopback102]", "interface[name=Loopback103]"],
        },
    )
    ```


### Combine update, replace, and delete in one call

Each operation accepts an `nf://` JSON or YAML file containing its usual list.
Files must be published by the FileSharing service. Pass all three file references
in one call to send update, replace, and delete together in a single Set request
per device. The files below use relative paths, so the call supplies
`prefix openconfig:/interfaces`.

Use these files on configuration you own: update changes Loopback100, replace
replaces Loopback101's configuration, and delete removes Loopback102 and
Loopback103. Inline lists and file references can be mixed in the same request.

=== "CLI"

    Save under the FileSharing inventory root (for example, `lab/`) as `gnmi/update.yaml`:

    ```yaml
    - - interface[name=Loopback100]/config
      - description: updated from YAML
    ```

    Save under the FileSharing inventory root (for example, `lab/`) as `gnmi/replace.json`:

    ```json
    [
      ["interface[name=Loopback101]/config", {
        "name": "Loopback101",
        "type": "iana-if-type:softwareLoopback",
        "description": "replacement from JSON"
      }]
    ]
    ```

    Save under the FileSharing inventory root (for example, `lab/`) as `gnmi/delete.yaml` (a list of paths):

    ```yaml
    - interface[name=Loopback102]
    - interface[name=Loopback103]
    ```

    ```bash
    nf# nornir gnmi set FL ceos-spine-1 prefix openconfig:/interfaces update nf://gnmi/update.yaml replace nf://gnmi/replace.json delete nf://gnmi/delete.yaml
    ```

=== "Python"

    Save under the FileSharing inventory root as `gnmi/update.yaml`:

    ```yaml
    - - interface[name=Loopback100]/config
      - description: updated from YAML
    ```

    Save under the FileSharing inventory root as `gnmi/replace.json`:

    ```json
    [
      ["interface[name=Loopback101]/config", {
        "name": "Loopback101",
        "type": "iana-if-type:softwareLoopback",
        "description": "replacement from JSON"
      }]
    ]
    ```

    Save under the FileSharing inventory root as `gnmi/delete.yaml` (a list of paths):

    ```yaml
    - interface[name=Loopback102]
    - interface[name=Loopback103]
    ```

    ```python
    result = client.run_job(
        "nornir", "gnmi_set",
        kwargs={
            "FL": ["ceos-spine-1"],
            "prefix": "openconfig:/interfaces",
            "update": "nf://gnmi/update.yaml",
            "replace": "nf://gnmi/replace.json",
            "delete": "nf://gnmi/delete.yaml",
        },
    )
    ```
    
## Notes

- Configure [gNMI connection inventory](services_nornir_service_inventory.md#gnmi-connection-inventory).
- Update adds or changes settings. Replace replaces all settings at the selected
  path. Delete removes the selected configuration.
  At least one nonempty operation list is required.
- Each file must contain a list in the format shown above. The same contents
  apply to every selected device. Templates and links to other files are not supported.
- Update and replace files can use YAML or JSON. Each path must be paired with a
  mapping of setting names to values, as shown in the examples.
- Encoding is chosen automatically. Set `encoding` when your device needs a
  specific format.
- Changes are applied separately to each device. No backup or rollback is provided.
  After a timeout, check the device before retrying. The first request may already
  have changed the configuration. Whether changes survive a restart depends on
  the device.
- Common host filters, retries, and structured processors such as `jmespath` apply.
  For deletion alone, use [Delete](services_nornir_service_tasks_gnmi_delete.md).

## Troubleshooting

For file errors, check the FileSharing URL, JSON/YAML syntax, and list structure.
For connection errors, check the gRPC service, port, TLS, and credentials. For device
errors, check permissions, model paths, object contents, and encoding support.
Supported paths and write operations depend on the device and software version.

## Task Command Shell Reference

```bash
nf#man tree nornir.gnmi.set

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── gnmi:    Retrieve device data using gNMI
        └── set:    Merge, replace, or delete configuration
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
            ├── update:    JSON array of path/object pairs to merge, default ''
            ├── replace:    JSON array of path/object pairs to replace, default ''
            ├── delete:    Configuration path or paths to delete, default '[]'
            ├── prefix:    Common YANG path prefix, default ''
            ├── target:    gNMI target name
            └── encoding:    Payload encoding; default negotiates with the device
nf#
```

## Python API Reference

::: norfab.workers.nornir_worker.gnmi_tasks.GnmiTasks.gnmi_set
