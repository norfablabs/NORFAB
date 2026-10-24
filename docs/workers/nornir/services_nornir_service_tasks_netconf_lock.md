# NETCONF Lock Datastore

Use `netconf_lock` to reserve a datastore for your NETCONF session while applying a configuration change.

## Use Cases

Prevent competing sessions from editing the same datastore during a multi-step change.

## How It Works

The lock belongs to the NETCONF session. Target the same worker and backend for edits and unlocking. The device releases the lock when that session closes, including connection cleanup by the worker. Locks acquired on other devices remain held if one device fails.

## Output

Each host's XML reply appears under `lock`. Successful operations normally return `<ok/>`. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf lock target candidate workers nornir-worker-1 FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_lock", workers="nornir-worker-1",
            kwargs={'target': 'candidate', 'FL': ['router-1']},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.lock

lock
  ├── plugin: NETCONF backend, default ncclient
  └── target: Datastore to lock, default candidate
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_lock
