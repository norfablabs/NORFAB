# NETCONF Delete Configuration

Use `netconf_delete_config` to delete configuration from a non-running datastore.

## Use Cases

Remove saved startup configuration when preparing a device for reprovisioning, if the device supports NETCONF deletion.

## How It Works

The target is required and accepts startup or candidate, subject to device support. Running is forbidden. This deletes configuration rather than restoring candidate from running; use `netconf_discard_changes` to abandon candidate edits. Deleting startup configuration affects the next boot. The task does not make a backup.

## Output

Each host's XML reply appears under `delete_config`. Successful datastore operations
normally return `<ok/>`; RPC replies depend on the operation. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf delete-config target startup FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_delete_config",
            kwargs={'target': 'startup', 'FL': ['router-1']},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.delete_config

delete-config
  ├── plugin: NETCONF backend, default ncclient
  └── target (R): Datastore to delete; running is forbidden
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_delete_config
