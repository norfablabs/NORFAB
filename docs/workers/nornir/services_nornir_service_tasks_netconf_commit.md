# NETCONF Commit Configuration

Use `netconf_commit` to activate candidate configuration or confirm a pending
confirmed commit on selected devices.

## Use Cases

- Activate staged configuration after reviewing and validating candidate changes.
- Apply changes with a rollback timer, then confirm them after checking the network.
- Confirm a persistent commit from another NETCONF session using its token.

## How It Works

A normal commit copies candidate configuration into running configuration.
With `confirmed=True`, the device rolls back unless a subsequent commit confirms
the change before `confirm_delay` expires. Omit the delay to use the device default.
Unlike `netconf_transaction`, this task does not send the final confirmation
automatically.

The device must support candidate configuration and, for confirmed commits,
the confirmed-commit capability. All pending candidate changes are committed;
this task does not edit, lock, or validate configuration.

## Output

Each host's `commit` key contains its XML reply, normally `<ok/>` on success.
RPC, capability, and connection errors mark hosts as failed.
`add_details=True` includes execution metadata; `to_dict=False` returns serialized
records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

### Commit candidate configuration

=== "CLI"

    ```text
    nf# nornir netconf commit FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_commit", kwargs={"FL": ["router-1"]}
        )
        print(result)
    ```

### Commit with a rollback timer

Use a persistent token to confirm independently of the original connection.
After checking connectivity and services, send the final confirmation before
the timer expires. If the checks fail, leave the commit unconfirmed to let the
device roll back.

=== "CLI"

    ```text
    nf# nornir netconf commit confirmed True confirm-delay 120 persist change-123 FL router-1
    nf# nornir netconf commit persist-id change-123 FL router-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_commit",
        kwargs={
            "FL": ["router-1"],
            "confirmed": True,
            "confirm_delay": 120,
            "persist": "change-123",
        },
    )
    # Check the result, connectivity, and services before confirming.
    result = client.run_job(
        "nornir", "netconf_commit",
        kwargs={"FL": ["router-1"], "persist_id": "change-123"},
    )
    ```

Without a persistent token, confirmation must use the original NETCONF session;
target the same worker and backend, and keep its connection open. The
`confirm-delay` controls the device rollback timer; the common `timeout` option
controls how long the client waits for the job. Retries may repeat a commit.

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.commit

commit: Commit NETCONF candidate configuration
├── plugin: NETCONF backend, default ncclient
├── confirmed: Start a confirmed commit, default False
├── confirm-delay: Rollback timeout in seconds
├── persist: Token to keep a confirmed commit across sessions
└── persist-id: Token identifying the persistent confirmed commit to confirm
```

Common host filters, job options, XML processors, and serialization options
are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_commit
