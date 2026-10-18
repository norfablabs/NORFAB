# NETCONF Get Configuration

Retrieve configuration with `netconf_get_config` using `ncclient` (default) or
`scrapli`. The task is available through Python, NFCLI, generated FastAPI endpoints,
and MCP tools.

## Output

Default results contain an XML reply under each host's `get_config` key.
`add_details=True` includes execution metadata; `to_dict=False` returns serialized
records. Connection and RPC failures appear in per-host results.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf get-config source running plugin ncclient FC spine
    nf# nornir netconf get-config source running plugin scrapli FC leaf
    nf# nornir netconf get-config plugin scrapli filter-xpath "/*[local-name()='system']" FC leaf
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get_config",
            kwargs={
                "plugin": "scrapli",
                "source": "running",
                "FC": "leaf",
                "filter_subtree": '<system xmlns="http://openconfig.net/yang/system"/>',
            },
        )
        print(result)
    ```

### Filter by subtree

Retrieve the OpenConfig system hostname. Both backends accept either filter type.

=== "CLI"

    ```text
    nf# nornir netconf get-config plugin ncclient filter-subtree '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>' FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get_config",
        kwargs={
            "plugin": "ncclient",
            "FL": ["ceos-spine-1"],
            "filter_subtree": (
                '<system xmlns="http://openconfig.net/yang/system">'
                '<config><hostname/></config></system>'
            ),
        },
    )
    ```

### Filter by XPath

Requires device XPath support. This expression matches local element names
regardless of namespace; adapt it to the device's YANG models.

=== "CLI"

    ```text
    nf# nornir netconf get-config plugin scrapli filter-xpath "/*[local-name()='system']/*[local-name()='config']/*[local-name()='hostname']" FC leaf
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get_config",
        kwargs={
            "plugin": "scrapli",
            "FC": "leaf",
            "filter_xpath": (
                "/*[local-name()='system']"
                "/*[local-name()='config']"
                "/*[local-name()='hostname']"
            ),
        },
    )
    ```

### Use a filter template

Either filter accepts a NorFab file URL. File content can use per-host Jinja2
context, for example `{{ host.name }}`.

=== "CLI"

    ```text
    nf# nornir netconf get-config filter-subtree nf://netconf/get_system.xml FC spine
    nf# nornir netconf get-config filter-xpath nf://netconf/get_hostname.xpath FC leaf
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get_config",
        kwargs={"FC": "spine", "filter_subtree": "nf://netconf/get_system.xml"},
    )
    ```

Configure the selected backend using the [NETCONF connection inventory](services_nornir_service_inventory.md#netconf-connection-inventory).

## Notes

- `source` accepts running, candidate, or startup; device support is required.
- `filter_subtree` accepts inline XML or a NorFab template URL such as
  `nf://netconf/system.xml`. Templates render per host with `host`, `job_data`,
  `norfab`, and `netbox` context. `job_data` accepts data or a YAML file URL.
- Filters use device-specific YANG namespaces. Use `filter_xpath` for server-side XPath filtering; the device must advertise the XPath capability.
- `filter_subtree` and `filter_xpath` are mutually exclusive. Both support per-host templates and NorFab file URLs. Explicit XPath namespace mappings are not exposed; use namespace-independent expressions where appropriate.
- The common `xpath` processor filters replies locally after retrieval.
- Common Nornir filters, processors, retry settings, and serialization options apply.

## Troubleshooting

Verify the NETCONF SSH port and credentials for connection errors. For RPC errors,
check datastore capabilities and XML namespaces. XPath filters require the server
capability `urn:ietf:params:netconf:capability:xpath:1.0`; the current cEOS integration
image does not advertise it and rejects XPath requests. Empty filtered data can indicate
that the selected YANG model is absent on the device.

## Task Command Shell Reference

```text
nf#man tree nornir.netconf.get_config

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── get-config:    Get configuration
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
            ├── xpath:    XPath expression to run with DataProcessor
            ├── xml-flake:    XML flake pattern for DataProcessor
            ├── plugin:    NETCONF backend, default 'NetconfPlugin.ncclient'
            ├── source:    Datastore to retrieve, default 'NetconfConfigSource.running'
            ├── filter-subtree:    XML subtree filter or template URL, examples: <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>
            ├── filter-xpath:    XPath filter or template URL, examples: /*
            └── job-data:    Template data or YAML file URL
nf#
```

Common host filters and job options are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_get_config
