# ADR - NorFab Logging Isolation and Multi-Process Log Files

## Status

Proposed.

## Date

2026-06-22.

## Context

NorFab currently treats `NorFab(...)` construction as application startup for
logging. `NorFab.__init__()` loads inventory, creates the log queue, creates the
`__norfab__/logs` directory, and calls `setup_logging()`.

`NorFab.make_client()` does not directly configure logging, but normal
client-only usage still constructs a `NorFab` object first:

```python
nf = NorFab(inventory="inventory.yaml")
client = nf.make_client()
```

That means a script that only wants a client still receives the side effects of
`NorFab.setup_logging()`. The current setup calls:

```python
logging.config.dictConfig(self.inventory["logging"])
```

The default listener config defines `root.handlers = ["terminal", "file"]`, so
the parent application's root handlers are replaced by NorFab's handlers. The
inventory uses `disable_existing_loggers: False`, but that only preserves named
loggers. It does not preserve root handlers when the `root` section is supplied
in the `dictConfig`.

NorFab also uses the same default file for all NFAPI processes started from the
same base directory:

```text
__norfab__/logs/norfab.log
```

The listener uses Python's standard `logging.handlers.RotatingFileHandler`.
That handler is safe enough for one process that owns the file, including child
broker and worker processes that send records through that one process' queue.
It is not safe when two independent NFAPI parent processes both open and rotate
the same log file. On Windows this is especially visible because one process can
hold the file while the other tries to write, rename, or rotate it.

These are two separate problems:

- Embedded/client-only NFAPI should not take ownership of the parent script's
  logging configuration.
- Multiple independent NFAPI processes should not write to the same rotating
  log file unless there is a single writer or a multi-process-safe handler.

## Goals

- Let parent applications keep their own logging configuration when they use
  NorFab as a client library.
- Keep NorFab broker and worker logs working when NorFab is used as the owning
  application process.
- Avoid collisions when several NFAPI processes run from the same folder.
- Preserve a simple default for `nfcli` and standalone NorFab runs.
- Keep the implementation compatible with the current queue-based broker and
  worker logging model.

## Non-Goals

- Do not redesign the event bus or job event logging.
- Do not require every user script to define a logging config.
- Do not rely on operating-system-specific log file behavior.
- Do not make independent Python processes share a `multiprocessing.Queue`.
  That queue only works for processes created by the same parent.

## Current Behavior

The current logging topology has two modes inside one NorFab-owned process tree:

- The parent NFAPI process is the log listener. It applies inventory logging
  configuration and owns terminal/file handlers.
- Broker and worker child processes are log producers. They apply a producer
  config with a `QueueHandler` on the root logger and send records to the
  parent's queue.

That model is good for `nf.start(run_broker=True, run_workers=True)` because
there is one file owner.

It is awkward for embedded usage because the parent application's root logger is
reconfigured even when the script only wants a client.

It is unsafe for two independent NFAPI parent processes because both become log
listeners and both open `__norfab__/logs/norfab.log`.

## Options

### Option 1 - Add a `configure_logging` Flag

Add a constructor flag:

```python
NorFab(..., configure_logging=True)
```

When `False`, NorFab does not call `setup_logging()` and does not start a
`QueueListener`.

This is the smallest change. It gives embedded applications a direct escape
hatch:

```python
nf = NorFab(inventory="inventory.yaml", run_broker=False, run_workers=False, configure_logging=False)
client = nf.make_client()
```

Drawbacks:

- Users must know to pass the flag.
- If they later call `start(run_broker=True)` with logging disabled, broker and
  worker logs need either a delayed setup step or a clear warning.
- It does not by itself solve shared `norfab.log` collisions for standalone
  processes.

### Option 2 - Add Logging Ownership Modes

Add an explicit logging ownership argument:

```python
NorFab(..., logging_mode="auto")
```

Suggested values:

- `auto`: choose based on requested role.
- `standalone`: NorFab owns its logging pipeline.
- `embedded`: NorFab does not configure global logging and leaves the parent
  application in charge.
- `disabled`: suppress NorFab logging except critical fallback output.

Suggested `auto` behavior:

- If `run_broker=True` or `run_workers=True`, use `standalone`.
- If `run_broker=False` and `run_workers=False`, use `embedded`.

This matches how the object is normally used:

- `nfcli`, broker, and worker orchestration remain standalone.
- Client-only scripts become embedded and stop overriding parent logging.

An explicit mode still lets advanced users override the default:

```python
nf = NorFab(..., run_broker=False, run_workers=False, logging_mode="standalone")
```

### Option 3 - Configure the `norfab` Logger Instead of Root

Move NorFab's application logging from the root logger to a named logger:

```text
norfab
```

The listener configuration would attach terminal/file handlers to
`logging.getLogger("norfab")` and set `propagate=False` for that logger.
NorFab modules already use names like `norfab.core.nfapi`, so they naturally
sit below the `norfab` logger.

Benefits:

- Parent root handlers are not replaced.
- Parent application logs and NorFab logs can be configured independently.
- NorFab can still have its own terminal/file output in standalone mode.

Important detail:

Broker and worker subprocesses currently attach `QueueHandler` to root. To keep
isolation, their producer config should also target the `norfab` logger when
NorFab-owned logging is enabled. If NorFab intentionally wants to capture
third-party logs from worker code, this should be a separate explicit option,
for example `capture_root_logs=True`.

Drawbacks:

- Third-party library logs emitted from workers will not automatically go into
  NorFab logs unless they propagate through `norfab` or root capture is enabled.
- Inventory examples that configure `root` need a migration path or
  compatibility adapter.

### Option 4 - Snapshot and Restore Parent Root Handlers

Before calling `dictConfig`, store the existing root handlers and restore them
after NorFab client construction.

This is not recommended as the main design. It is brittle because `dictConfig`
can also change levels, filters, formatter objects, propagation, named loggers,
and handler lifetimes. It may also close handlers that the parent application
expects to keep.

This can be useful only as a temporary compatibility measure.

### Option 5 - Unique Log File Per NFAPI Process

Keep the current handler type but stop independent processes from sharing the
same file. For example:

```text
__norfab__/logs/norfab.log
__norfab__/logs/norfab-client-<client-name>-<pid>.log
__norfab__/logs/norfab-<role>-<pid>.log
```

Suggested policy:

- A standalone process that starts the broker/workers owns
  `__norfab__/logs/norfab.log`.
- Client-only standalone logging uses a client-specific or pid-specific file.
- Embedded client-only mode does not create a NorFab file handler unless
  explicitly requested.

Benefits:

- Simple and uses only the standard library.
- No cross-process rotation conflict.
- Keeps each independent process' logs available.

Drawbacks:

- Logs are split across files.
- Operators need a clear naming convention.

### Option 6 - Single External Log Writer

Keep one logical `norfab.log`, but route all independent processes to one log
writer. Possible transports:

- `logging.handlers.SocketHandler` to a local TCP log receiver.
- A small NorFab log collector process.
- OS logging such as journald, syslog, Windows Event Log, or container stdout.

Benefits:

- One consolidated log file.
- Correct single-writer semantics.

Drawbacks:

- More moving parts.
- Needs lifecycle management.
- More complex than necessary for local client-only scripts.

### Option 7 - Use a Multi-Process-Safe Rotating Handler

Replace standard `RotatingFileHandler` with a handler that uses inter-process
file locking, such as `concurrent-log-handler`'s
`ConcurrentRotatingFileHandler`.

Benefits:

- Keeps the single-file behavior.
- Minimal conceptual change for users.

Drawbacks:

- Adds a dependency.
- Locking and rotation behavior must be tested on Windows, Linux, and network
  or synced folders.
- It still couples independent processes to one file, which can be noisy for
  client-only use.

## Recommended Direction

Use a combination of Options 2, 3, and 5.

1. Add an explicit logging ownership mode, with `auto` as the default.
2. In embedded mode, do not call `logging.config.dictConfig()` and do not start
   a `QueueListener`.
3. In standalone mode, configure NorFab's named `norfab` logger instead of
   replacing root handlers.
4. Keep broker and worker child processes using queue logging, but attach the
   producer `QueueHandler` to the `norfab` logger by default.
5. Use one shared `norfab.log` only for the process tree that owns broker and
   worker subprocesses.
6. Use per-process log files, or no NorFab file logging, for independent
   client-only processes.

This separates the two concerns:

- Logging ownership is controlled by `logging_mode`.
- Log file collision avoidance is controlled by the file naming strategy for
  independent NFAPI processes.

## Proposed API

```python
NorFab(
    inventory="./inventory.yaml",
    inventory_data=None,
    base_dir=None,
    log_level=None,
    run_broker=True,
    run_workers=True,
    logging_mode="auto",
    log_file_strategy="auto",
    capture_root_logs=False,
)
```

`logging_mode`:

- `auto`: use `standalone` when broker/workers are requested, otherwise
  `embedded`.
- `standalone`: NorFab configures its own named logger and starts the log queue
  listener.
- `embedded`: NorFab leaves existing application logging alone.
- `disabled`: NorFab suppresses its own logging setup.

`log_file_strategy`:

- `auto`: use `shared` for broker/worker owner processes and `none` or
  `per_process` for client-only processes.
- `shared`: write to `__norfab__/logs/norfab.log`.
- `per_process`: write to a pid/client-specific file.
- `none`: do not add a NorFab file handler.

`capture_root_logs`:

- `False`: only NorFab's named logger is sent to the NorFab queue.
- `True`: broker/worker producer processes also attach a queue handler to root
  to capture third-party logs from worker code.

## Behavioral Examples

Embedded parent application:

```python
import logging
from norfab.core.nfapi import NorFab

logging.basicConfig(filename="my_app.log", level=logging.INFO)

nf = NorFab(
    inventory="inventory.yaml",
    run_broker=False,
    run_workers=False,
    logging_mode="embedded",
)
client = nf.make_client()
```

Expected behavior:

- Parent script keeps `my_app.log`.
- NorFab does not replace root handlers.
- NorFab messages follow normal Python logging propagation and can be captured
  by the parent if the parent wants them.

Standalone NorFab process:

```python
nf = NorFab(inventory="inventory.yaml", logging_mode="standalone")
nf.start(run_broker=True, run_workers=True)
```

Expected behavior:

- NorFab owns `__norfab__/logs/norfab.log`.
- Broker and worker children send records to the parent listener queue.
- Parent application logging is not relevant because NorFab is the application.

Second client-only process from the same folder:

```python
nf = NorFab(
    inventory="inventory.yaml",
    run_broker=False,
    run_workers=False,
    logging_mode="standalone",
    log_file_strategy="per_process",
)
client = nf.make_client()
```

Expected behavior:

- The process does not open the broker owner's `norfab.log`.
- Its file is unique, for example
  `__norfab__/logs/norfab-client-myclient-12345.log`.
- No standard-library rotating handler is shared between independent processes.

## Migration Notes

The least surprising migration path is:

1. Add `logging_mode` and keep the old behavior behind `standalone`.
2. Make `auto` the default.
3. Treat `run_broker=False` and `run_workers=False` as embedded client-only
   usage.
4. Keep inventory `logging.root` support for compatibility, but internally map
   it to the `norfab` logger when NorFab owns logging.
5. Document that independent NFAPI processes must not share the standard
   `RotatingFileHandler` file. Use `per_process`, `none`, a central log
   collector, or a multi-process-safe handler.

## Consequences

- Parent scripts can call `NorFab(...).make_client()` without losing their
  logging handlers.
- Standalone NorFab still has a complete logging pipeline for broker and worker
  subprocesses.
- Independent client processes stop competing for `norfab.log`.
- Users who want one combined log from many independent NFAPI processes need a
  central writer or a multi-process-safe handler.
- A small compatibility layer is needed for existing inventory files that only
  configure `root`.

## Open Questions

- Should `auto` embedded mode be selected only when both `run_broker=False` and
  `run_workers=False`, or should there also be a `client_only=True` shortcut?
- Should client-only `auto` use `log_file_strategy="none"` or
  `log_file_strategy="per_process"` by default?
- Should NorFab keep capturing third-party worker logs by default, or should
  that require `capture_root_logs=True`?
- Is adding `concurrent-log-handler` acceptable as an optional extra for users
  who require one shared file across independent processes?
