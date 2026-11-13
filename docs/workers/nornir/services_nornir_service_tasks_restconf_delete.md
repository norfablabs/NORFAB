# RESTCONF DELETE

Use `restconf_delete` to delete configuration from selected network devices through RESTCONF.
It sends an HTTP DELETE request to the specified resource path, allowing you to remove
configuration such as interfaces or individual settings supported by the device's YANG models.

## Output

Each host's reply appears under `delete`. JSON responses become structured data; other responses
remain text. Successful operations may return an empty string. Connection and device errors mark
hosts failed. `add_details=True` includes execution details; `to_dict=False` returns list records.

## Examples

The example deletes Loopback100.
Paths and payload fields must match the device's supported YANG models.

=== "CLI"

    ```bash
    nf# nornir restconf delete FL ceos-spine-1 url openconfig-interfaces:interfaces/interface=Loopback100
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir",
        "restconf_delete",
        workers="nornir-worker-1",
        kwargs={
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100",
        },
    )
    ```

=== "FastAPI"

    Replace the address and token with those of your
    [FastAPI service](../fastapi/services_fastapi_service.md).

    **Python requests**

    ```python
    import requests

    response = requests.post(
        "http://localhost:8000/api/nornir/restconf_delete/",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "workers": "nornir-worker-1",
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100",
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json())
    ```

    **curl**

    ```bash
    curl -X POST 'http://localhost:8000/api/nornir/restconf_delete/' \
      -H 'Authorization: Bearer YOUR_TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{
      "workers": "nornir-worker-1",
      "FL": [
        "ceos-spine-1"
      ],
      "url": "openconfig-interfaces:interfaces/interface=Loopback100"
    }'
    ```

=== "MCP"

    ```text
    Use the NorFab Nornir RESTCONF delete tool to remove Loopback100 from ceos-spine-1.
    Report whether the operation succeeded.
    ```

## Notes

Configure the device endpoint, credentials, TLS verification, HTTP timeout and default headers in
[HTTP inventory](services_nornir_service_inventory.md#restconf-connection-inventory). Relative resource
paths use its RESTCONF base URL. Use `params` for query parameters and `headers` when a request
needs different headers; supplied headers replace the inventory mapping.

The CLI `timeout` controls waiting for the NorFab job. Device requests use the configured Nornir
runner, including its retry settings. Review those settings before configuration changes.

## Task Command Shell Reference

```bash
nf# man tree nornir.restconf.delete
```

## Python API Reference

::: norfab.workers.nornir_worker.restconf_task.RestconfTask.restconf_delete
