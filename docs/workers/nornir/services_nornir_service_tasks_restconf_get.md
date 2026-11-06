# RESTCONF GET

Read device configuration or operational data with `restconf_get`. Use a RESTCONF resource
path to retrieve only the information you need, or select a predefined getter to read
a supported OpenConfig subtree without specifying a path.

## Output

Each host's reply appears under `get`. JSON responses become structured data. Other responses
remain text. Successful operations may return an empty string. Connection and device errors mark
hosts failed. `add_details=True` includes execution details. `to_dict=False` returns list records.

```json
{
  "ceos-spine-1": {
    "get": {
      "openconfig-system:hostname": "ceos-spine-1"
    }
  }
}
```

## Supported Getters

Getters are predefined RESTCONF resource shortcuts. The selected device must support
the corresponding YANG data model. A shortcut does not translate between vendor
models.

| Getter | Description |
| --- | --- |
| `openconfig-interfaces` | Interface configuration, state and counters under `openconfig-interfaces:interfaces`. |
| `openconfig-lldp` | LLDP configuration and neighbor state under `openconfig-lldp:lldp`. |
| `openconfig-system` | System configuration and operational state under `openconfig-system:system`. |

Select only one getter or explicit `url` per request. False flags do not count.
Unsupported models produce the device's response or a failed host result. No automatic
vendor fallback is performed. Replies retain the device model structure under `get`.

CLI flags use hyphens. Python and FastAPI arguments use underscores, for example
`openconfig_lldp`. Subtrees follow the
[OpenConfig models](https://github.com/openconfig/public/tree/master/release/models).

## Examples

### Read a resource path

=== "CLI"

    ```bash
    nf# nornir restconf get FL ceos-spine-1 url openconfig-system:system/state/hostname
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir",
        "restconf_get",
        workers="nornir-worker-1",
        kwargs={
            "FL": ["ceos-spine-1"],
            "url": "openconfig-system:system/state/hostname",
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
        "http://localhost:8000/api/nornir/restconf_get/",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "workers": "nornir-worker-1",
            "FL": ["ceos-spine-1"],
            "url": "openconfig-system:system/state/hostname",
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json())
    ```

    **curl**

    ```bash
    curl -X POST 'http://localhost:8000/api/nornir/restconf_get/' \
      -H 'Authorization: Bearer YOUR_TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{
      "workers": "nornir-worker-1",
      "FL": [
        "ceos-spine-1"
      ],
      "url": "openconfig-system:system/state/hostname"
    }'
    ```

=== "MCP"

    ```text
    Use the NorFab Nornir RESTCONF get tool to read the hostname of ceos-spine-1.
    Show the returned hostname.
    ```

### Use a predefined getter

This example retrieves OpenConfig interfaces. Use `openconfig-lldp` or
`openconfig-system` in CLI, or `openconfig_lldp=True` or `openconfig_system=True`
in Python, to select another getter. FastAPI JSON uses lowercase `true`.

=== "CLI"

    ```bash
    nf# nornir restconf get FL ceos-spine-1 openconfig-interfaces
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir",
        "restconf_get",
        workers="nornir-worker-1",
        kwargs={
            "FL": ["ceos-spine-1"],
            "openconfig_interfaces": True,
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
        "http://localhost:8000/api/nornir/restconf_get/",
        headers={"Authorization": "Bearer YOUR_TOKEN"},
        json={
            "workers": "nornir-worker-1",
            "FL": ["ceos-spine-1"],
            "openconfig_interfaces": True,
        },
        timeout=60,
    )
    response.raise_for_status()
    print(response.json())
    ```

    **curl**

    ```bash
    curl -X POST 'http://localhost:8000/api/nornir/restconf_get/' \
      -H 'Authorization: Bearer YOUR_TOKEN' \
      -H 'Content-Type: application/json' \
      --data '{
      "workers": "nornir-worker-1",
      "FL": [
        "ceos-spine-1"
      ],
      "openconfig_interfaces": true
    }'
    ```

=== "MCP"

    ```text
    Use the NorFab Nornir RESTCONF get tool with the OpenConfig interfaces getter
    to read interface configuration and state from ceos-spine-1.
    ```

## Notes

Configure the device endpoint, credentials, TLS verification, HTTP timeout and default headers in
[HTTP inventory](services_nornir_service_inventory.md#restconf-connection-inventory). Relative resource
paths use its RESTCONF base URL. Use `params` for query parameters and `headers` when a request
needs different headers. Supplied headers replace the inventory mapping.

The CLI `timeout` controls waiting for the NorFab job. Device requests use the configured Nornir
runner, including its retry settings. Review those settings before configuration changes.

## Task Command Shell Reference

```bash
nf# man tree nornir.restconf.get
```

## Python API Reference

::: norfab.workers.nornir_worker.restconf_task.RestconfTask.restconf_get
