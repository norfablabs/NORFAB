# NETCONF Get Data

Retrieve configuration and operational state with `netconf_get` using `ncclient` (default) or
`scrapli`. The task is available through Python, NFCLI, generated FastAPI endpoints,
and MCP tools.

## Output

Use [XML processors](services_nornir_service_tasks_netconf_processors.md) to convert replies to
dictionaries (`xmltodict`), select XML elements (`xpath`), or extract flat
values (`xml-flake`).

Default results contain an XML reply under each host's `get` key. Unfiltered
Scrapli requests use `<get/>` through its RPC method and return under `rpc`.
`add_details=True` includes execution metadata; `to_dict=False` returns serialized
records. Connection and RPC failures appear in per-host results.

## Supported Getters

Getters are predefined subtree filter shortcuts. The selected device must support
the corresponding YANG data model; a shortcut does not translate between vendor
models.

| Getter | Description |
| --- | --- |
| `ietf-interfaces` | Retrieve the `/interfaces` subtree in the `urn:ietf:params:xml:ns:yang:ietf-interfaces` namespace, including configuration and state exposed there. |
| `openconfig-interfaces` | Interface configuration, state, and counters under `/interfaces` in the OpenConfig interfaces namespace. |
| `openconfig-lldp` | LLDP configuration and neighbor state under `/lldp`. |
| `openconfig-bgp` | The BGP subtree under `/network-instances/network-instance/protocols/protocol/bgp` across network instances. Includes available configuration and session state; may also include large BGP RIB data. |
| `openconfig-system` | System configuration and operational state under `/system` in the OpenConfig system namespace. |
| `ietf-routing` | Routing configuration and available RIB data under `/routing`. Does not select the legacy `/routing-state` subtree; replies can be large. |
| `ietf-hardware` | Hardware components and available state under `/hardware`. Does not select the legacy `/hardware-state` subtree. |

Select only one getter or explicit filter per request. False flags do not count.
Unsupported models may produce empty data or a device RPC error; no automatic
vendor fallback is performed.

Subtrees follow the [OpenConfig models](https://github.com/openconfig/public/tree/master/release/models),
[IETF routing model](https://www.rfc-editor.org/rfc/rfc8349.html), and
[IETF hardware model](https://www.rfc-editor.org/rfc/rfc8348.html).

## Examples

=== "CLI"

    ```text
    nf# nornir netconf get plugin ncclient FC spine
    nf# nornir netconf get plugin scrapli FC leaf
    nf# nornir netconf get plugin scrapli filter-xpath "/*[local-name()='system']" FC leaf
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get",
            kwargs={
                "plugin": "scrapli",
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
    nf# nornir netconf get plugin ncclient filter-subtree '<system xmlns="http://openconfig.net/yang/system"><config><hostname/></config></system>' FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
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
    nf# nornir netconf get plugin scrapli filter-xpath "/*[local-name()='system']/*[local-name()='config']/*[local-name()='hostname']" FC leaf
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
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
    nf# nornir netconf get filter-subtree nf://netconf/get_system.xml FC spine
    nf# nornir netconf get filter-xpath nf://netconf/get_hostname.xpath FC leaf
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
        kwargs={"FC": "spine", "filter_subtree": "nf://netconf/get_system.xml"},
    )
    ```

Configure the selected backend using the [NETCONF connection inventory](services_nornir_service_inventory.md#netconf-connection-inventory).

### Retrieve IETF interfaces

The `ietf-interfaces` flag selects the standard `/interfaces` subtree, including
configuration and state exposed there by the device. It requires device support;
an empty successful reply remains successful. The legacy `/interfaces-state`
subtree is not selected.

=== "CLI"

    ```text
    nf# nornir netconf get ietf-interfaces FL router1,router2
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
        kwargs={"ietf_interfaces": True, "FL": ["router1", "router2"]},
    )
    ```

Only one getter or explicit filter may be selected. Getter flags set to true
cannot be combined with each other, `filter_subtree`, or `filter_xpath`. False leaves the
existing filter selection unchanged.

### Retrieve LLDP Neighbors or BGP Sessions

=== "CLI"

    ```text
    nf# nornir netconf get openconfig-lldp FL router1
    nf# nornir netconf get openconfig-bgp xmltodict FL router1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
        kwargs={"FL": ["router1"], "openconfig_bgp": True, "xmltodict": True},
    )
    ```

## Notes

- NETCONF `get` reads configuration and operational state. Use
  [Get Configuration](services_nornir_service_tasks_netconf_get_config.md) to
  read a specific configuration datastore. Omit both filters to retrieve all
  available data; large replies can require longer timeouts.

- `filter_subtree` accepts inline XML or a NorFab template URL such as
  `nf://netconf/system.xml`. Templates render per host with `host`, `job_data`,
  `norfab`, and `netbox` context. `job_data` accepts data or a YAML file URL.
- Filters use device-specific YANG namespaces. Use `filter_xpath` for server-side XPath filtering; the device must advertise the XPath capability.
- `filter_subtree` and `filter_xpath` are mutually exclusive. Both support per-host templates and NorFab file URLs. Explicit XPath namespace mappings are not exposed; use namespace-independent expressions where appropriate.
- The common `xpath` processor filters replies locally after retrieval.
- Common Nornir filters, processors, retry settings, and serialization options apply.

## Troubleshooting

Verify the NETCONF SSH port and credentials for connection errors. For RPC errors,
check supported YANG models and XML namespaces. XPath filters require the server
capability `urn:ietf:params:netconf:capability:xpath:1.0`; the current cEOS integration
image does not advertise it and rejects XPath requests. Empty filtered data can indicate
that the selected YANG model is absent on the device.

## Task Command Shell Reference

```bash
nf# man tree nornir.netconf.get

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── get:    Retrieve configuration and operational state
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
            ├── ietf-interfaces:    Retrieve the IETF interfaces subtree, default 'False'
            ├── openconfig-interfaces:    Retrieve the openconfig interfaces subtree, default 'False'
            ├── openconfig-lldp:    Retrieve the openconfig lldp subtree, default 'False'
            ├── openconfig-bgp:    Retrieve the openconfig bgp subtree, default 'False'
            ├── openconfig-system:    Retrieve the openconfig system subtree, default 'False'
            ├── ietf-routing:    Retrieve the ietf routing subtree, default 'False'
            ├── ietf-hardware:    Retrieve the ietf hardware subtree, default 'False'
            ├── filter-subtree:    XML subtree filter or template URL, examples: <interfaces xmlns="urn:ietf:params:xml:ns:yang:ietf-interfaces"/>
            ├── filter-xpath:    XPath filter or template URL, examples: /*
            └── job-data:    Template data or YAML file URL
nf#
```

Common host filters and job options are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_get
