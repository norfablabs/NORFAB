# NETCONF Validate Configuration

Use `netconf_validate` to check a device configuration datastore for errors
without changing the configuration.

## Use Cases

Check staged candidate changes before committing them, or check running or
startup configuration for errors reported by the device.

## How It Works

The task sends a NETCONF validate request for the selected datastore, defaulting
to candidate. The device must support the validate capability and the selected
datastore. Validation does not commit, discard, or lock configuration, and does
not check connectivity or service health.

## Output

Each host's `validate` key contains the XML reply, normally `<ok/>` on success.
Validation errors, unsupported capabilities, and connection errors mark the host
as failed. `add_details=True` includes execution metadata; `to_dict=False`
returns serialized records. [XML processors](services_nornir_service_tasks_netconf_processors.md)
can convert or filter replies.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf validate source candidate FL ceos-leaf-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_validate",
            kwargs={"source": "candidate", "FL": ["ceos-leaf-1"]},
        )
        print(result)
    ```

## Task Command Shell Reference

```text
nf# man tree nornir.netconf.validate

validate: Validate NETCONF configuration
├── plugin: NETCONF backend, default ncclient
└── source: Datastore to validate, default candidate
```

Common host filters, job options, XML processors, and serialization options
are also available.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_validate
