# Public HTTP Task Contracts

Canonical requirements: docs/development/specs/001-nornir-http/spec.md.
This is a design contract, not an already available API.

## Operations

| Public task | Backend verb | NFCLI command | Payload |
| --- | --- | --- | --- |
| restconf_get | get | nornir restconf get | none |
| restconf_post | post | nornir restconf post | json or data |
| restconf_put | put | nornir restconf put | json or data |
| restconf_patch | patch | nornir restconf patch | json or data |
| restconf_delete | delete | nornir restconf delete | none |

Public task names fix the operation; callers do not supply method or plugin. _run_http is internal.
Each task accepts the relevant fields in ../data-model.md and returns HttpResult.

## Python Client

```python
result = nfclient.run_job(
    "nornir",
    "restconf_get",
    workers="nornir-worker-1",
    kwargs={
        "FL": ["ceos-spine-1", "ceos-spine-2"],
        "url": "openconfig-system:system/state/hostname",
        "request_timeout": [5, 10],
        "add_details": True,
    },
)
```

Resource path is an Arista-documented candidate that must be checked against the deployed image.
Relative paths join the effective base URL through backend rules. An absolute URL is used as-is
for each selected host; no hostname substitution or Jinja rendering occurs. Selecting two hosts
with the same absolute URL sends two independent operations to that URL.

```python
result = nfclient.run_job(
    "nornir",
    "restconf_patch",
    workers="nornir-worker-1",
    kwargs={
        "FL": ["ceos-spine-1"],
        "url": owned_resource_path,
        "json": "nf://http/owned-resource-patch.json.j2",
        "job_data": {"description": "norfab-http-test"},
    },
)
```

PATCH document shape/media type must match the endpoint. No automatic YANG Patch conversion.
Templates support existing host, job_data, norfab and netbox context conventions. Using those
context helpers can contact other services; tests must use only their declared owned data.

## Shell

```text
nf# nornir restconf get FL ceos-spine-1 url openconfig-system:system/state/hostname request-timeout 10
nf# nornir restconf patch FL ceos-spine-1 url <owned-resource> json nf://http/owned-resource-patch.json.j2
```

Shell request-timeout maps to request_timeout. Existing timeout remains job waiting, workers
selects workers, and nowait/verbose-result keep existing shell semantics. Shell classes inherit
operation inputs and only override fields that need JSON/list parsing. Register one NornirRestconfShell
subshell with five operation commands and existing output/piping behavior.

## Results and Failures

With to_dict=True and add_details=False, a successful GET has the conceptual shape:

```json
{
  "nornir-worker-1": {
    "failed": false,
    "result": {
      "ceos-spine-1": {
        "get": {"openconfig-system:hostname": "ceos-spine-1"}
      }
    }
  }
}
```

Other existing worker Result fields remain present. List and detailed modes follow existing
ResultSerializer contracts. HEAD and successful empty responses can return an empty string.
Errors follow existing Nornir result conventions and identify failed hosts; no new error taxonomy.
One host failure does not erase another host result. No-match performs no request or template fetch.

NorFab adds no retry loop and uses the configured Nornir runner exactly as NETCONF does.
RetryRunner and existing run_* controls determine retries. request_timeout is HTTP connect/read
waiting, distinct from job timeout.

## Inventory and Request Precedence

Backend built-ins < effective inventory extras < non-null explicit request options.
Do not send omitted defaults as None. Explicit headers replace the complete header mapping.
Default YANG JSON media types apply only when no effective headers mapping exists. TLS verification
remains enabled unless an explicit inventory or task value changes it. An absolute URL does not
prevent inventory auth from applying; callers must select trusted targets deliberately.

## Service Exposure

Use @Task input/output models. Generated FastAPI routes use POST for job argument bodies, including
read device operations; this transport choice does not change the device verb. MCP titles and
readOnlyHint/destructiveHint/idempotentHint distinguish reads from mutations conservatively.
No new standalone HTTP server, alternate worker, public dispatcher, or endpoint registry is added.

Initial tests cover core NorFab behavior only; no null-body support or Requests override suite.
Reuse existing methods and keep inputs/payloads inline in simple tests.
