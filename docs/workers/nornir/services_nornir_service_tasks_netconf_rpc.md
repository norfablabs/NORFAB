# NETCONF RPC

Use `netconf_rpc` to send NETCONF operation XML, including vendor-specific operations.

## Use Cases

Retrieve a vendor-specific operational subtree or invoke an operation not covered by the dedicated NETCONF tasks.

## How It Works

Supply the operation element and its namespace, without an outer `<rpc>` envelope. XML can be inline or a template URL, rendered per host with `host`, `job_data`, `norfab`, and `netbox`. The backend adds the envelope. Effects and required capabilities depend on the operation; retries can repeat state-changing RPCs.

## Output

Each host's XML reply appears under `rpc`. Reply content depends on the operation. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf rpc rpc nf://netconf/get_system_rpc.xml FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_rpc",
            kwargs={'rpc': 'nf://netconf/get_system_rpc.xml', 'FL': ['router-1']},
        )
        print(result)
    ```

Store this read-only template at `nf://netconf/get_system_rpc.xml`:

```xml
<get xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <filter type="subtree">
    <system xmlns="http://openconfig.net/yang/system">
      <config><hostname/></config>
    </system>
  </filter>
</get>
```

## Task Command Shell Reference

```text
nf#man tree nornir.netconf.rpc

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── netconf:    Manage devices using NETCONF
        └── rpc:    Send a NETCONF operation XML or template
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
            ├── rpc (R):    RPC operation XML or NorFab template URL
            └── job-data:    Template data or YAML file URL
nf#
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_rpc
