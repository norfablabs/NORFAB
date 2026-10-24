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
nf# man tree nornir.netconf.rpc

rpc
  ├── plugin: NETCONF backend, default ncclient
  ├── rpc (R): RPC operation XML or template URL
  └── job-data: Template data or YAML file URL
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_rpc
