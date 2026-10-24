# NETCONF Cancel Commit

Use `netconf_cancel_commit` to roll back a pending confirmed commit immediately,
instead of waiting for its rollback timer to expire.

## Use Cases

Cancel a configuration rollout when connectivity or service checks fail after
a confirmed commit. Supply the commit's persistence token to cancel it from
another NETCONF session.

## How It Works

The task sends a NETCONF cancel-commit request. The device restores the running
configuration to its state before the pending confirmed commit. It must support
cancel-commit; normal commits and commits already confirmed cannot be undone
with this task.

For a persistent commit, supply its original token as `persist_id`. Without a
token, target the same worker and backend that started the nonpersistent commit,
while its NETCONF connection remains open.

## Output

Each host's XML reply appears under `cancel_commit` for ncclient or `rpc` for
Scrapli, normally containing `<ok/>` on success. Unsupported operations, missing
pending commits, incorrect tokens, and connection errors mark hosts as failed.
`add_details=True` includes execution metadata; `to_dict=False` returns serialized
records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

Cancel a pending persistent confirmed commit started with `persist="change-123"`:

=== "CLI"

    ```text
    nf# nornir netconf cancel-commit persist-id change-123 FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_cancel_commit",
            kwargs={"persist_id": "change-123", "FL": ["router-1"]},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.cancel_commit

cancel-commit: Cancel a pending confirmed commit
├── plugin: NETCONF backend, default ncclient
└── persist-id: Token identifying the persistent confirmed commit to cancel
```

Common host filters, job options, XML processors, and serialization options
are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_cancel_commit
