# RESTCONF PATCH

Use `restconf_patch` to update selected values in a RESTCONF resource. The device must support
PATCH and the payload format you send.

## Output

Each host's reply appears under `patch`. JSON responses become structured data; other responses
remain text. Successful operations may return an empty string. Connection and device errors mark
hosts failed. `add_details=True` includes execution details; `to_dict=False` returns list records.

## Examples

The example changes the Loopback100 description.
Paths and payload fields must match the device's supported YANG models.

=== "CLI"

    ```bash
    nf# nornir restconf patch FL ceos-spine-1 url openconfig-interfaces:interfaces/interface=Loopback100/config data '{"openconfig-interfaces:description":"configured using NorFab"}'
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir",
        "restconf_patch",
        workers="nornir-worker-1",
        kwargs={
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
            "data": '{"openconfig-interfaces:description":"configured using NorFab"}',
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
        "http://localhost:8000/api/nornir/restconf_patch/",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "workers": "nornir-worker-1",
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
            "data": '{"openconfig-interfaces:description":"configured using NorFab"}',
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json())
    ```

    **curl**

    ```bash
    curl -X POST 'http://localhost:8000/api/nornir/restconf_patch/' \
      -H 'Authorization: Bearer YOUR_TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{
      "workers": "nornir-worker-1",
      "FL": [
        "ceos-spine-1"
      ],
      "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
      "data": "{\"openconfig-interfaces:description\":\"configured using NorFab\"}"
    }'
    ```

=== "MCP"

    ```text
    Use the NorFab Nornir RESTCONF patch tool to update the description of Loopback100
    on ceos-spine-1 to "configured using NorFab". Leave other settings unchanged
    and report the result.
    ```

### Use a payload file

Publish a JSON payload as `restconf/interface.json.j2` under the FileSharing inventory root.
For example, this template sets the interface description to the selected host's name:

```json
{"openconfig-interfaces:description": "configured on {{ host.name }}"}
```

Supply `nf://restconf/interface.json.j2` as `data` through any interface. Inline `data` also supports
Jinja2. Use `job_data` to provide additional template values. The payload is sent as text; configure
its Content-Type in HTTP inventory. Resource paths are not rendered.

## Notes

Configure the device endpoint, credentials, TLS verification, HTTP timeout and default headers in
[HTTP inventory](services_nornir_service_inventory.md#restconf-connections). Relative resource
paths use its RESTCONF base URL. Use `params` for query parameters and `headers` when a request
needs different headers; supplied headers replace the inventory mapping.

The CLI `timeout` controls waiting for the NorFab job. Device requests use the configured Nornir
runner, including its retry settings. Review those settings before configuration changes.

PATCH payloads and media types vary by device. Set the required Content-Type in inventory or
the request headers; NorFab does not convert between patch formats.

## Task Command Shell Reference

```bash
nf# man tree nornir.restconf.patch
```

## Python API Reference

::: norfab.workers.nornir_worker.restconf_task.RestconfTask.restconf_patch
