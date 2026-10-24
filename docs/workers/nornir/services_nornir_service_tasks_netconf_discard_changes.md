# NETCONF Discard Changes

Use `netconf_discard_changes` to abandon uncommitted candidate edits and restore candidate configuration from running.

## Use Cases

Abandon a staged rollout after review or validation fails, without changing running configuration.

## How It Works

The task discards all pending candidate changes, including changes made by other sessions. It requires candidate support. It does not undo running changes or cancel a pending confirmed commit.

## Output

Each host's XML reply appears under `discard_changes` for ncclient or
`discard` for Scrapli, normally containing `<ok/>` on success. RPC and connection
errors mark hosts as failed. `add_details=True` includes execution metadata;
`to_dict=False` returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf discard-changes FL router-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_discard_changes",
            kwargs={'FL': ['router-1']},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.discard_changes

discard-changes
  └── plugin: NETCONF backend, default ncclient
```

Common host filters, job options, XML processors, and serialization options
are also available. ncclient is the default backend; select `plugin scrapli`
to use Scrapli NETCONF.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_discard_changes
