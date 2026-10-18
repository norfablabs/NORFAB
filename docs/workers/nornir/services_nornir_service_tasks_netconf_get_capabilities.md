# NETCONF Get Capabilities

List capabilities advertised by device NETCONF sessions using ncclient or Scrapli.
Use `netconf_get_capabilities` to check protocol features and advertised YANG modules.

## Output

Each host has a `server_capabilities` list of capability URIs. A capability filter
with no matches returns an empty list. `add_details=True` includes metadata and
`to_dict=False` returns serialized records. Connection errors mark hosts as failed.

## Examples

=== "CLI"

    ```text
    nf# nornir netconf get-capabilities plugin ncclient FC spine
    nf# nornir netconf get-capabilities plugin scrapli capab-filter *candidate* FC leaf
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get_capabilities",
            kwargs={"plugin": "scrapli", "capab_filter": "*candidate*", "FC": "leaf"},
        )
        print(result)
    ```

## Notes

- `capab_filter` is a case-sensitive glob. Omit it to retrieve all capability URIs.
- Host filters select devices. The capability filter selects URIs within each reply.
- Capabilities describe the session. Use YANG Library or NETCONF monitoring for
  a fuller module inventory. Retrieve module source with [get-schema](services_nornir_service_tasks_netconf_get_schema.md).
- Configure the backend using the [NETCONF inventory](services_nornir_service_inventory.md#netconf-connection-inventory).

## Troubleshooting

Check NETCONF connectivity and credentials for connection errors. An empty
filtered list means no advertised URI matched. It does not indicate a failed RPC.

## Task Command Shell Reference

```text
nornir netconf get-capabilities
  plugin ncclient|scrapli
  capab-filter <glob pattern>
```

Common host filters and job options apply.

## Python API Reference

::: norfab.workers.nornir_worker.netconf_task.NetconfTask.netconf_get_capabilities
