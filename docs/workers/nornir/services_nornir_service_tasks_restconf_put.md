# RESTCONF PUT

Use `restconf_put` to replace configuration at a RESTCONF resource. Choose PUT when you
intend to supply the configuration for the addressed resource, rather than merge selected values.

## Output

Each host's reply appears under `put`. JSON responses become structured data; other responses
remain text. Successful operations may return an empty string. Connection and device errors mark
hosts failed. `add_details=True` includes execution details; `to_dict=False` returns list records.

## Examples

The example sets the Loopback100 configuration.
Paths and payload fields must match the device's supported YANG models.

=== "CLI"

    ```bash
    nf# nornir restconf put FL ceos-spine-1 url openconfig-interfaces:interfaces/interface=Loopback100/config data '{"openconfig-interfaces:name":"Loopback100","openconfig-interfaces:type":"iana-if-type:softwareLoopback","openconfig-interfaces:description":"configured using NorFab"}'
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir",
        "restconf_put",
        workers="nornir-worker-1",
        kwargs={
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
            "data": '{"openconfig-interfaces:name":"Loopback100","openconfig-interfaces:type":"iana-if-type:softwareLoopback","openconfig-interfaces:description":"configured using NorFab"}',
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
        "http://localhost:8000/api/nornir/restconf_put/",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "workers": "nornir-worker-1",
            "FL": ["ceos-spine-1"],
            "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
            "data": '{"openconfig-interfaces:name":"Loopback100","openconfig-interfaces:type":"iana-if-type:softwareLoopback","openconfig-interfaces:description":"configured using NorFab"}',
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json())
    ```

    **curl**

    ```bash
    curl -X POST 'http://localhost:8000/api/nornir/restconf_put/' \
      -H 'Authorization: Bearer YOUR_TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{
      "workers": "nornir-worker-1",
      "FL": [
        "ceos-spine-1"
      ],
      "url": "openconfig-interfaces:interfaces/interface=Loopback100/config",
      "data": "{\"openconfig-interfaces:name\":\"Loopback100\",\"openconfig-interfaces:type\":\"iana-if-type:softwareLoopback\",\"openconfig-interfaces:description\":\"configured using NorFab\"}"
    }'
    ```

=== "MCP"

    ```text
    Use the NorFab Nornir RESTCONF put tool to replace the configuration of Loopback100
    on ceos-spine-1. Set its type to software loopback and its description to
    "configured using NorFab". Report the result.
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

PUT replaces configuration at the addressed resource; use [PATCH](services_nornir_service_tasks_restconf_patch.md)
when the device supports merging selected values.

## Task Command Shell Reference

```bash
nf# man tree nornir.restconf.put
```

## Python API Reference

::: norfab.workers.nornir_worker.restconf_task.RestconfTask.restconf_put
