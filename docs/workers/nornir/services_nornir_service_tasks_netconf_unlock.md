# NETCONF Unlock Datastore

Use `netconf_unlock` to release a datastore lock after completing a configuration change.

## Use Cases

Release a lock acquired with `netconf_lock` so other sessions can edit the datastore.

## How It Works

Target the same worker and backend that acquired the lock. Another session cannot release it. Unlocking does not commit or discard configuration; complete those operations first.

## Output

Each host's XML reply appears under `unlock`. Successful operations normally return `<ok/>`. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf unlock target candidate workers nornir-worker-1 FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_unlock", workers="nornir-worker-1",
            kwargs={'target': 'candidate', 'FL': ['router-1']},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.unlock

unlock
  ├── plugin: NETCONF backend, default ncclient
  └── target: Datastore to unlock, default candidate
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_unlock
