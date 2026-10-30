# ADR - Nornir gNMI Tasks

## Status

Get MVP implemented; set/delete remain proposed. Date: 2026-10-31.

The first slice exposes only `gnmi_get`, using the linear `run_gnmi` method.
Rendering and additional abstraction are deferred. The MVP follows existing
models with `extra="allow"` because runtime validation includes the injected
job argument; stricter argument handling below remains a proposed follow-up.
Live reads remain unverified: integration attempts timed out establishing gRPC
connections to the configured lab ports.

## Context

The Nornir worker needs dedicated gNMI get, set, and delete tasks, following
`snmp_task.py` for operation-specific APIs and `netconf_task.py` for execution
lifecycle and events.

Reviewed compatibility target: installed `nornir-salt==0.23.6` and
`pygnmi==0.8.15`; `pyproject.toml` already includes both in the Nornir extras.
No new dependency is required.

Source review found:

- `pygnmi_call` dispatches methods through the `pygnmi` connection and names
  each Nornir result after its backend call.
- Get accepts `path`, `prefix`, `target`, `datatype`, and `encoding`.
- Set accepts `update`, `replace`, `delete`, `prefix`, `target`, `encoding`,
  and `extension`. Update/replace entries are path/value pairs; the plugin
  converts JSON lists into tuples.
- The plugin's delete helper accepts `path` but calls `connection.set(delete=path)`
  without forwarding other options. Using it would silently lose prefix/target.
- The plugin logs backend kwargs at debug level; configuration payloads can
  therefore appear in dependency logs.

## Decision

Add `norfab/workers/nornir_worker/gnmi_tasks.py` containing a `GnmiTasks` mixin
and one `run_gnmi` runner. Register the mixin on `NornirWorker`.

| Public task | Arguments | Backend call |
| --- | --- | --- |
| `gnmi_get` | Required `path: list[str]`; optional `prefix=""`, `target=None`, `datatype="all"`, `encoding=None` | `get` |
| `gnmi_set` | Optional `update`, `replace`, `delete`, `prefix=""`, `target=None`, `encoding=None`, `extension=None`; at least one nonempty operation required | `set` |
| `gnmi_delete` | Required `path: list[str]`; optional `prefix=""`, `target=None` | `set`, with `delete=path` |

All tasks accept the existing common Nornir filters, processors, retry and
serialization options. Expose no arbitrary `call` or backend selector.
Keep the public operation separate from the backend call in the runner:
`gnmi_delete` has a NorFab task label ending in `gnmi_delete`, while its serialized
backend result is keyed by `set`. Document this explicitly.

### Validation and results

Define `GnmiGetInput`, `GnmiSetInput`, `GnmiDeleteInput`, and `GnmiResult` in
`nornir_models.py`. Reuse common and structured processor models and
`NornirSerializedResult`.

Require nonempty path lists with nonblank strings; allow explicit `/` paths.
Validate update/replace entries as two-item path/value pairs before the plugin
can silently discard malformed entries. Accept JSON-compatible values without
requiring dictionaries. Validate datatype against `all`, `config`, `state`,
`operational`; validate explicit encodings against pygnmi's supported values.
Leave encoding unset by default to retain backend negotiation.
Reject backend-dispatch overrides and arguments belonging to other operations
at the input boundary; do not inherit unrestricted plugin passthrough blindly.

Preserve backend response dictionaries, host failures, `no_match`,
`to_dict=False`, and `add_details=True` through existing serializer behavior.
Do not invent a fixed schema for vendor-specific notification values.

### Execution and safety

Follow NETCONF's filtering, processor attachment, connection locking,
`update_nornir_result`, serialization, and watchdog lifecycle. Track connection
name `pygnmi`; run cleanup in `finally`. Emit lowercase-starting execution and
completion events, with `severity` on failures. Do not log payloads in NorFab.

Use inventory `connection_options.pygnmi` for credentials, gRPC port, TLS,
and `gnmi_timeout`; set the port explicitly to avoid inheriting an SSH port.
Preserve backend TLS defaults. Insecure connections must be explicitly configured.

Declare all three tasks as FastAPI POST operations. MCP get is read-only;
set/delete are destructive writes. Use conservative `idempotentHint=False`
for writes because device behavior and retry outcomes vary. A timeout can leave
the write outcome uncertain; retries can repeat an applied operation.

Set sends one request per host, including combined delete/replace/update when
supplied. No cross-host transaction, automatic backup, rollback, or NETCONF-style
commit is provided. Subscription, capabilities, rendering, and dedicated
update/replace tasks are outside this initial scope.

## Alternatives and consequences

- Direct pygnmi calls duplicate Nornir connection and retry integration; reuse
  nornir-salt instead.
- The delete helper is shorter but loses options; use backend Set consistently.
- A generic gNMI dispatcher is flexible but weakens schemas and read/write MCP
  metadata; expose explicit tasks.

Integration tests require a reachable gNMI server and owned configuration paths.
Existing cEOS lab configurations enable gNMI, but reachability, TLS settings,
and writable paths still need verification. FakeNOS CLI recordings do not prove
gRPC support.

## References

- [SNMP design](adr_nornir_snmp_tasks.md)
- [Task model guide](../tasks_pydantic_models_guide.md)
- [Testing guide](../testing/norfab_testing_framework.md)
- [Nornir-Salt source](https://github.com/dmulyalin/nornir-salt/blob/0.23.0/nornir_salt/plugins/tasks/pygnmi_call.py)
  (published reference; implementation details above checked against installed 0.23.6).
- [pygnmi source](https://github.com/akarneliuk/pygnmi/blob/0.8.15/pygnmi/client.py)
