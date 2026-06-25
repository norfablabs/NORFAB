# ADR - NorFab Library Logging and Per-Process Log Files

## Status

Proposed.

## Date

2026-06-24.

## Decision

Normalize NorFab logging around the standard Python boundary:

- `norfab.core.nfapi.NorFab` behaves as a library API.
- Applications that use NFAPI own logging setup.
- `nfcli` is the NorFab application and sets up NorFab default logging before
  constructing `NorFab`.
- Parent scripts that import NFAPI keep ownership of their own logging.

`NorFab.__init__()` should no longer call `logging.config.dictConfig()` or
construct application log handlers as an implicit side effect. NFAPI should emit
records through normal module loggers such as `norfab.core.nfapi`,
`norfab.core.client`, `norfab.core.broker`, and worker module loggers.

Abandon `__norfab__/logs/norfab.log` as the primary shared runtime log file.
Each NorFab process writes to its own log file under `__norfab__/logs`.

Default application logging should use a small NorFab logging helper called by
`nfcli` and by NorFab-owned broker/worker process entrypoints. The helper should
use only the Python standard library and a custom JSON formatter for the default
file sink.

The inventory `logging` section remains based on Python's
`logging.config.dictConfig` schema. Per-process JSONL files are the default
NorFab file destination, not the only supported logging destination. Inventory
logging can still configure additional or replacement handlers such as
`SysLogHandler`, journald handlers supplied by optional packages, Windows Event
Log handlers, SMTP handlers, socket handlers, stream handlers, filters, and
formatters.

## Context

Current NFAPI construction configures process logging:

```python
nf = NorFab(inventory="inventory.yaml")
client = nf.make_client()
```

Even if the caller only wants a client, `NorFab.__init__()` calls
`setup_logging()`, which applies inventory logging with:

```python
logging.config.dictConfig(self.inventory["logging"])
```

The default logging config contains a `root` section and handlers for terminal
and `__norfab__/logs/norfab.log`. This replaces the parent application's root
handlers. `disable_existing_loggers: False` keeps named loggers alive, but it
does not preserve the root handlers once `dictConfig()` configures `root`.

The current queue logging model is useful inside one NorFab-owned process tree:

- parent NFAPI process owns terminal/file handlers;
- broker and workers send records to the parent with `QueueHandler`;
- one parent `QueueListener` writes the shared log file.

That model stops being safe when two independent NFAPI parent processes run
from the same folder. Each process owns a different queue listener and both can
open the same `__norfab__/logs/norfab.log`, causing file access and rotation
collisions, especially on Windows.

The cleaner split is:

- NFAPI does not decide application logging.
- `nfcli` configures logs because it is an application.
- every process writes its own log file, avoiding shared file ownership.

## Goals

- Keep code changes surgical and close to current logging paths.
- Preserve simple `nfcli` behavior: users still get NorFab logs without extra
  CLI flags or logging concepts.
- Stop NFAPI from overriding parent application logging.
- Avoid multi-process writes to the same rotating log file.
- Keep broker, worker, and client logs discoverable under `__norfab__/logs`.
- Use JSON lines so logs can later be queried and merged in a uniform order.
- Avoid adding a logging dependency.
- Preserve the existing inventory-driven logging flexibility based on Python
  `dictConfig`.

## Non-Goals

- Do not add user-facing `logging_mode`, `log_file_strategy`, or similar knobs.
- Do not add a socket log receiver in this change.
- Do not introduce a multi-process-safe third-party file handler.
- Do not redesign task event handling or job event storage.
- Do not implement the full log query CLI in the first minimal change.

## Proposed Minimal Implementation

### Add A Small Logging Helper

Add a focused helper module, for example:

```text
norfab/core/logging.py
```

The helper should expose simple functions such as:

```python
setup_process_logging(
    base_dir,
    role,
    name=None,
    log_level=None,
    inventory_logging=None,
)
```

The helper creates `__norfab__/logs` if needed and configures logging for the
current process only.

The helper should treat inventory logging as a per-process template:

- copy the inventory `logging` dictionary before modifying it;
- inject process metadata such as role, process name, worker name, client name,
  and PID;
- provide a safe per-process file handler when the inventory does not replace
  the default file sink;
- preserve custom inventory handlers where practical;
- apply the resulting config in the current process only.

No broad rewrite is required. Existing `setup_logging()` methods in NFAPI,
broker, and worker can be reduced to thin calls into this helper, or NFAPI
logging setup can be removed while broker/worker process entrypoints call the
helper directly.

### Move Default Log Construction To NFCLI

`nfcli` should call the helper before creating `NorFab`.

Example shape:

```python
setup_process_logging(
    base_dir=resolved_base_dir,
    role="nfcli",
    name="nfcli",
    log_level=LOGLEVEL,
    inventory_logging=inventory_logging,
)

nf = NorFab(
    inventory=INVENTORY,
    log_level=LOGLEVEL,
    run_broker=...,
    run_workers=...,
)
```

`nfcli -c`, `nfcli -b`, `nfcli -w`, and default interactive shell usage should
still produce logs automatically. The difference is ownership: `nfcli` chooses
to configure logs because it is the application.

Parent Python scripts that use NFAPI directly do not get NorFab application
logging unless they configure logging themselves.

### Per-Process Log Files

Each process gets a safe default file named from its role and process identity.

Suggested names:

```text
__norfab__/logs/nfcli-nfcli-<pid>.jsonl
__norfab__/logs/broker-NFPBroker-<pid>.jsonl
__norfab__/logs/worker-nornir-worker-1-<pid>.jsonl
__norfab__/logs/client-<client-name>-<pid>.jsonl
```

Include the worker name for workers and the client name for clients. Include
the PID to avoid collisions when the same worker or client name is started more
than once. A process start timestamp may also be included if needed for stale
file clarity:

```text
worker-nornir-worker-1-12345-20260624T101530.jsonl
```

The old shared file:

```text
__norfab__/logs/norfab.log
```

is no longer the primary runtime log destination.

This does not remove other handler types. For example, an inventory can still
send the same process records to syslog or another configured sink while the
default NorFab file handler writes JSONL locally.

### Rotation

Use standard `logging.handlers.RotatingFileHandler` per process.

Default rotation policy:

```text
backupCount: 30
```

Keep the existing `maxBytes` default unless there is a separate reason to
change it. The important change is that rotation is per process, not shared
across independent processes.

### Custom JSON Formatter

Use a small custom formatter instead of adding `python-json-logger` for the
default NorFab JSONL file handler.

Each line should be one JSON object. Required fields:

```json
{
  "ts": "2026-06-24T10:15:30.123456+10:00",
  "level": "INFO",
  "logger": "norfab.core.worker",
  "message": "worker started",
  "pid": 12345,
  "processName": "Process-2",
  "threadName": "MainThread",
  "role": "worker",
  "name": "nornir-worker-1",
  "module": "worker",
  "line": 123
}
```

Optional fields should be emitted when present on the log record:

```text
service
worker
client
task
job_uuid
event_type
exception
```

The formatter should preserve normal logging behavior by using
`record.getMessage()` and `formatException()` for exceptions.

Inventory may still define and use non-JSON formatters for terminal, syslog,
Event Log, SMTP, or custom handlers. JSON formatting is required only for the
default per-process file sink intended for future NorFab log querying.

### Log Ordering Metadata

To support future NFCLI interactive shell `show logging ...` commands or
equivalent log query code, JSON records should include enough metadata for
stable ordering:

- timestamp with timezone;
- PID;
- process role;
- process name;
- optional per-process sequence number.

Uniform ordering across processes will be timestamp-based. Exact sub-millisecond
global ordering cannot be guaranteed, but timestamp plus PID plus sequence is
stable and good enough for operational log review.

## Behavior

### NFCLI

`nfcli` configures NorFab application logging.

Examples:

```bash
nfcli -c
nfcli -b
nfcli -w
nfcli
```

Expected behavior:

- Logs are written under `__norfab__/logs`.
- `nfcli -c` writes a client/nfcli process log.
- broker and workers write their own process logs.
- no process competes for `norfab.log`.

### NFAPI As A Library

Parent application:

```python
import logging
from norfab.core.nfapi import NorFab

logging.basicConfig(filename="parent.log", level=logging.INFO)

nf = NorFab(inventory="inventory.yaml", run_broker=True, run_workers=True)
nf.start()
client = nf.make_client()
```

Expected behavior:

- NFAPI does not replace parent root handlers.
- NorFab log records propagate according to the parent's logging config unless
  the parent config chooses otherwise.
- If the parent wants NorFab-style JSON process files, it can call the same
  helper that `nfcli` uses.

### Broker And Workers

Broker and worker process entrypoints should configure their own process log
file with the helper and apply the inventory logging template in that process.

This removes the need for broker/worker child processes to share a log file
through the parent NFAPI process. Existing queue logging can be removed or kept
temporarily as compatibility during migration, but the target design is direct
per-process logging setup.

If the inventory configures external handlers, each broker or worker process
uses those handlers independently. For example, a `SysLogHandler` configured in
inventory sends records from every process to syslog, while the default file
handler still writes a process-specific JSONL file.

## Log Query Architecture

Per-process log files make writes safe, but users still need a single view from
the interactive shell. Log retrieval should follow NorFab ownership boundaries.

### Worker Logs

Workers should expose a task that reads their local process log files and
returns matching JSON records to the client.

Suggested task shape:

```text
service: workers
task: logging_read
```

or a service-specific built-in worker task exposed consistently across worker
types.

The task should support filters such as:

```text
since
until
level
logger
task
job_uuid
limit
tail
follow
```

The first implementation can support bounded reads only. Follow/streaming can
be added later through the interactive shell or task streaming path.

### Broker Logs

The broker should expose an MMI command to read broker-local logs:

```text
mmi.service.broker logging_read
```

The broker MMI should use the same filter names and return the same JSON record
shape as worker log tasks.

### Client-Side Merge

`norfab.core.client.NFPClient` should gain a small log merge helper that accepts
record iterables from broker MMI and worker tasks, normalizes records, and
returns a single ordered stream.

Ordering should use:

```text
ts, pid, sequence
```

where `sequence` is optional. If a record is malformed, the client should keep
the error local to the log query result instead of failing the entire query.

NFCLI interactive shell `show logging ...` commands should use this client-side
merge capability rather than duplicating merge logic in the shell models.

## Inventory Compatibility

Keep inventory logging support compatible with current behavior:

- Continue accepting existing inventory `logging.handlers.terminal.level` and
  `logging.handlers.file.level` values where practical.
- Treat inventory logging as Python `dictConfig` and preserve user-defined
  handlers, formatters, filters, loggers, and root settings where practical.
- Map the old/default `file` handler settings to the per-process JSON file
  handler.
- Change default `backupCount` to 30 for the per-process file handler.
- Treat `filename` from the default `file` handler carefully. The NorFab default
  file sink should use a process-specific filename to avoid collisions.
- Preserve clearly custom non-file handlers such as syslog, journald handlers,
  Windows Event Log handlers, SMTP handlers, socket handlers, and stream
  handlers.
- Preserve custom file handlers where practical, but document that a custom
  file handler pointing multiple processes at one normal rotating file is the
  user's responsibility and can reintroduce file contention.

The first implementation should avoid a large schema redesign. Existing logging
inventory can be partially honored by the helper while the new default behavior
stops using a shared `norfab.log`.

Example inventory remains valid:

```yaml
logging:
  handlers:
    file:
      level: DEBUG
      maxBytes: 1024000
      backupCount: 30
    syslog:
      class: logging.handlers.SysLogHandler
      address: /dev/log
      level: INFO
  root:
    handlers: [file, syslog]
    level: INFO
```

In the new model, each process receives its own resolved `file.filename`, while
the `syslog` handler is preserved.

## Migration Plan

Keep code changes small:

1. Add the custom JSON formatter and process logging helper.
2. Make `nfcli` call the helper before constructing `NorFab`.
3. Stop `NorFab.__init__()` from applying global logging configuration.
4. Update broker and worker process startup to call the helper with their role
   and name.
5. Update client creation paths used by `nfcli` to configure a client/nfcli log
   file through the helper.
6. Leave unrelated logging calls unchanged. Existing `log =
   logging.getLogger(__name__)` usage remains correct.

Do not refactor worker task logging, job events, CLI command behavior, or
inventory loading as part of this change.

## Consequences

- NFAPI behaves like a normal Python library.
- Parent scripts keep their logging configuration.
- `nfcli` still gives users NorFab logs by default.
- Independent processes no longer compete for one rotating file.
- Opening one static `norfab.log` is replaced by reading per-process JSONL log
  files.
- Inventory logging remains extensible through Python `dictConfig`; JSONL is
  the default NorFab file sink, not a restriction on all logging destinations.
- Future log query tooling can merge JSON records across files.
- The first implementation is intentionally surgical: add helper, call helper
  from app/process entrypoints, remove NFAPI global logging setup.

## Follow-Up Work

- Write a NorFab logging tutorial that explains the new logging model from a
  user's point of view:
  - NFAPI behaves as a library and does not configure parent application
    logging.
  - `nfcli` configures NorFab logging as the NorFab application.
  - The inventory `logging` section remains Python `dictConfig` compatible.
  - Default file logs are per-process JSONL files under `__norfab__/logs`.
  - Worker and broker names are used in log filenames.
  - Rotation defaults to `backupCount: 30`.
  - Examples show changing terminal/file levels, disabling terminal output,
    adding syslog or journald/Event Log handlers, and using environment
    variables with Jinja2.
  - Troubleshooting explains why a shared `norfab.log` is no longer the default
    and how to inspect or merge logs through the interactive shell.
- Add NFCLI interactive shell `show logging ...` commands to read all
  `__norfab__/logs/*.jsonl`, sort by timestamp, and filter by role, name,
  level, logger, task, or job UUID.
- Add worker log-reading task support so workers can return their local
  per-process JSONL records to clients.
- Add broker MMI log-reading support so broker-local JSONL records can be
  queried through the same client flow.
- Add client-side log merge utilities in `client.py` so NFCLI and other clients
  can combine broker and worker log records in uniform timestamp order.
- Add interactive shell support to follow multiple process logs.
- Add interactive shell support to export logs to a combined human-readable
  file when needed.
- Document the new per-process log file naming convention.
- Consider whether to keep a human-readable formatter for terminal output while
  retaining JSONL for files.
