# NETCONF Copy Configuration

Use `netconf_copy_config` to replace one datastore with configuration from another.

## Use Cases

Save running configuration to startup, stage running configuration in candidate, or restore running configuration from startup when supported.

## How It Works

Specify different source and target datastores: running, candidate, or startup. The target is replaced, not merged. A running replacement takes effect immediately; candidate changes need a separate commit. The task does not lock or back up configuration. This interface accepts datastores rather than inline XML or URLs.

## Output

Each host's XML reply appears under `copy_config`. Successful datastore operations
normally return `<ok/>`; RPC replies depend on the operation. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf copy-config source running target startup FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_copy_config",
            kwargs={'source': 'running', 'target': 'startup', 'FL': ['router-1']},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.copy_config

copy-config
  ├── plugin: NETCONF backend, default ncclient
  ├── source (R): Datastore to copy from
  └── target (R): Datastore to replace
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_copy_config
