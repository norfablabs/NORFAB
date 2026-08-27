---
tags:
  - nornir
---

# Nornir Errdisabled Hosts Tasks

> task API names: `errdisabled_hosts_list`, `errdisabled_hosts_clear`

When a Nornir task fails for a host, Nornir adds that host to its shared
failed-host state. Later tasks skip the host by default. NorFab calls these
hosts **errdisabled hosts** and tracks when they failed, their remaining
recovery time, and the failure reason when Nornir exposes one.

This behavior is active when the worker uses persistent errdisabled mode:

```yaml
service: nornir
failed_hosts_recovery_timeout: 60
reset_failed_hosts_before_task: false
```

`failed_hosts_recovery_timeout` is the number of seconds before the watchdog
recovers a failed host automatically. The default is `60` seconds.

!!! warning "Compatibility mode disables errdisabled behavior"

    `reset_failed_hosts_before_task: true` resets failed hosts before every
    Nornir task. In that mode, persistent errdisabled-host behavior is disabled
    and `failed_hosts_recovery_timeout` is effectively ignored.

## List Errdisabled Hosts

> task API name: `errdisabled_hosts_list`

The task returns a list of currently errdisabled hosts. Each item contains:

| Field | Description |
|---|---|
| `host` | Nornir host name. |
| `errdisabled_at` | Time when NorFab first recorded the failed-host state. |
| `recovery_time_left` | Whole seconds remaining before watchdog recovery. |
| `reason` | Failure reason, when it is available from the originating Nornir result. |

NFCLI example:

```bash
nf# show nornir errdisabled-hosts workers nornir-worker-1
```

Python API example:

```python
result = client.run_job(
    service="nornir",
    task="errdisabled_hosts_list",
    workers=["nornir-worker-1"],
)
```

## Clear Errdisabled Hosts

> task API name: `errdisabled_hosts_clear`

The task immediately recovers all currently errdisabled hosts on each selected
worker. Its result is a list of recovered host names. It is safe to call when
there are no failed hosts; the returned list is empty.

NFCLI example:

```bash
nf# nornir clear errdisabled-hosts workers nornir-worker-1
```

Python API example:

```python
result = client.run_job(
    service="nornir",
    task="errdisabled_hosts_clear",
    workers=["nornir-worker-1"],
)
```

## Run a Task on Errdisabled Hosts

All Nornir service tasks that execute against hosts accept `on_failed`. It is
`false` by default, so errdisabled hosts are skipped. Set it to `true` to
include failed hosts in one specific run:

!!! example

    === "NFCLI"

        ```bash
        nf# nornir cli FL spine-1 commands "show version" on-failed
        ```

    === "Python"

        ```python
        result = client.run_job(
            service="nornir",
            task="cli",
            workers=["nornir-worker-1"],
            kwargs={
                "FL": ["spine-1"],
                "commands": ["show version"],
                "on_failed": True,
            },
        )
        ```

`on_failed=True` does not recover or clear the host. If the run succeeds or
fails, the host remains in Nornir's failed-host state until watchdog recovery
or `errdisabled_hosts_clear` is called.

## Choosing a Recovery Mode

| Requirement | Configuration |
|---|---|
| Temporarily suppress repeated work against failed devices | `reset_failed_hosts_before_task: false` and set `failed_hosts_recovery_timeout` to the desired hold-down period. |
| Retry an errdisabled host for one particular job | Keep persistent mode enabled and set `on_failed=True` for that job. |
| Recover all failed hosts immediately | Run `errdisabled_hosts_clear`. |
| Always retry every matched host on every task, matching earlier behavior | Set `reset_failed_hosts_before_task: true`; the watchdog timeout and per-run override are unnecessary. |

Task results report hosts that executed in `resources` and hosts that failed
during the current execution in `resources_failed`.

## Python API Reference

::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.errdisabled_hosts_list

::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.errdisabled_hosts_clear
