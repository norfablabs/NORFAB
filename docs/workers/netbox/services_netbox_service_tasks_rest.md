---
tags:
  - netbox
---

# Netbox REST Task

> task api name: `rest`

Sends a direct HTTP request to the configured NetBox REST API. Use this task when a dedicated NetBox worker task does not exist for the endpoint you need.

## Inputs

| Parameter | Required | Description |
|---|---:|---|
| `api` | Yes | NetBox API path under `/api`, for example `dcim/devices` |
| `method` | No | HTTP method to use, default `get` |
| `instance` | No | NetBox instance name to target |
| `**kwargs` | No | Additional request arguments passed to `requests`, such as `params`, `json`, or `data` |

## Output

Returns the decoded JSON response from NetBox when possible. If the response is not JSON, the task returns response text or the HTTP status code.

## Notes / Gotchas

- `api` is joined under the configured NetBox URL as `/api/<api>/`.
- Request headers, token, SSL verification, and default timeout are set by the worker.
- On HTTP errors, the task returns the response status code in `result`.
- The current NFCLI command model does not expose `rest`, so use the Python API or other task surfaces.

## Examples

=== "Python"

    Context manager:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "api": "dcim/devices",
                "method": "get",
                "params": {"q": "ceos-leaf"},
            },
        )
    ```

    Direct lifecycle:

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()

        result = client.run_job(
            "netbox",
            "rest",
            workers="any",
            kwargs={
                "api": "extras/tags",
                "method": "post",
                "json": {
                    "name": "automation-managed",
                    "slug": "automation-managed",
                },
            },
        )
    finally:
        nf.destroy()
    ```

## Python API Reference

::: norfab.workers.netbox_worker.netbox_worker.NetboxWorker.rest
