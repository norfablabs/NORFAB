# ADR - NFAPI Client-First Startup and Client Connection Overrides

## Status

Proposed.

## Date

2026-06-20.

## Decision

Improve NorFab startup so the NFCLI interactive prompt can be returned before
all local broker and worker processes have finished initialization.

The implementation should use one simple startup path: start requested broker
and worker processes through a short-lived background startup thread, then
create and return the client without waiting for all local components to
finish initialization.

```python
nf = NorFab(inventory="inventory.yaml", log_level=log_level)
nf.start()
client = nf.make_client()
```

NFCLI shell mode should use this path and show the `nf#` prompt as soon as the
client is constructed. Broker and workers continue starting in the background
while the user uses the shell.

When broker authentication is enabled and the client has no broker token from
CLI/API arguments, environment variables, or inventory, the client certificate
setup should wait briefly for the local broker key file to appear, copy it, and
then continue. This keeps key bootstrap inside the client, where the exact key
paths are already known, and avoids NFAPI startup branches for first-run local
authentication.

Jobs submitted before the broker or target workers are ready should be accepted
into the local client job database and retried until their deadline. Transient
startup conditions, such as broker not yet connected or broker reporting no
matching workers yet, should not immediately mark those jobs as failed.
Management requests that are not stored in the client job database can continue
to use their existing synchronous timeout behavior.

Add client connection overrides:

- `nfcli --broker-url tcp://host:port`
- `nfcli --broker-token <broker-public-key>`

The overrides should update the client-side broker endpoint and shared key
before the client is created. For local all-in-one startup, they should also be
available to broker and worker processes through the in-memory inventory.

Add automatic `.env` loading in NFAPI before inventory rendering, using the
same local folder as the inventory file by default. Existing process
environment variables must win over `.env` values.

## Context

Current `nfcli` default shell mode calls
`start_picle_shell(..., run_workers=True, run_broker=True)` from
`norfab/utils/nfcli.py`. `start_picle_shell()` in
`norfab/clients/nfcli_shell/nfcli_shell_client.py` enters `with NorFab(...) as
nf`, and `NorFab.__enter__()` calls `self.start()` followed by
`self.make_client()`.

`NorFab.start()` in `norfab/core/nfapi.py` currently blocks in three places:

- `start_broker()` starts the broker process and waits up to 30 seconds for
  broker `init_done_event`.
- Worker processes are started according to topology and dependency rules.
- The final worker readiness loop waits until every worker `init_done_event` is
  set, or until `workers_init_timeout` expires.

As a result, the interactive client is created only after broker and all
selected workers have initialized. Slow workers, plugin imports, remote API
checks, large inventories, or worker dependency chains delay the NFCLI prompt.

The implementation also has useful existing properties:

- `NFPClient` connects with ZeroMQ DEALER sockets, so connecting to an endpoint
  is non-blocking at the socket layer.
- The client already has receiver and dispatcher threads and future-based job
  handling.
- `submit_job()` already writes jobs to the local SQLite job database before
  the dispatcher sends anything to the broker.
- Worker readiness is already represented by per-process `init_done_event`.
- Workers and clients already read broker endpoint and shared key from
  `inventory.broker`.

The current client job path needs one adjustment for client-first startup.
`dispatch_new_jobs()` sends `NEW` jobs to the broker and marks them
`SUBMITTING`. If `send_to_broker()` raises, the job is currently marked
`FAILED`, but ZeroMQ normally queues sends while the broker endpoint is not
connected, so broker-not-ready does not usually fail at this point. The more
likely early-startup failure is broker-ready-but-workers-not-ready:
`NFPBroker.dispatch()` returns a `400` response with `workers=None` when the
service has no matching active workers, and `handle_response()` currently
treats all `4xx` and `5xx` responses as terminal failures.

Also, if a job reaches `SUBMITTING` and no broker response ever arrives, the
waiting caller can time out, but the live dispatcher does not currently mark
that database row stale. `recover_job_futures()` handles stale active jobs on
client restart, but client-first startup needs the running dispatcher to apply
the same deadline discipline.

The main constraint is local authentication bootstrap. `NFPClient` currently
calls `generate_certificates()` during construction. That helper creates the
client keypair and then either copies the broker public key from
`__norfab__/files/broker/public_keys/broker.key` or writes
`inventory.broker["shared_key"]` into the client's local `broker.key`. After
that, `reconnect_to_broker()` calls `zmq.auth.load_certificate()` on the
client's local `public_keys/broker.key`.

If broker authentication is enabled and no shared key is provided, client
construction fails when the local broker key has not been generated yet. Rather
than making NFAPI inspect broker key paths before constructing a client,
certificate setup should support a bounded wait for the local broker key when a
local broker is being started in the same NorFab instance.

## Goals

- Return the NFCLI prompt quickly in default shell mode.
- Keep startup behavior simple: callers should not need to choose between
  broker wait, worker wait, and client wait modes.
- Keep immediate job submissions durable during background startup by retrying
  transient broker/worker-unavailable conditions until the job deadline.
- Allow client-only NFCLI connections to remote brokers without editing
  `inventory.yaml`.
- Load `.env` before inventory Jinja2 rendering so inventory can use
  `{{ env.VAR_NAME }}` values.
- Keep startup hooks and worker dependency ordering intact.
- Improve startup observability and avoid avoidable CPU spin during readiness
  waits.

## Non-Goals

- Do not rewrite broker, client, or worker protocol flows.
- Do not make job execution complete before the broker or target workers are
  actually reachable. Local job submission may succeed by storing the job in
  the client database and retrying dispatch until timeout.
- Do not make broker state persistent.
- Do not change worker task semantics.
- Do not add multiple wait flags or separate broker/worker wait modes.
- Do not implement remote broker-routed restart authorization in the first
  change.
- Do not implement automatic restart-on-crash policy in the first change.

## Proposed API

### NorFab Constructor

Add optional arguments:

```python
NorFab(
    inventory="./inventory.yaml",
    inventory_data=None,
    base_dir=None,
    log_level=None,
    run_broker=True,
    run_workers=True,
    broker_url=None,
    broker_token=None,
    load_env=True,
)
```

Behavior:

- `broker_url` overrides `inventory.broker["endpoint"]`.
- `broker_token` overrides `inventory.broker["shared_key"]`.
- If `broker_url` is not supplied, `NORFAB_BROKER_URL` from the environment
  is used when present.
- If `broker_token` is not supplied, `NORFAB_BROEKR_TOKEN` from the
  environment is used when present. Keep the variable name exactly as written
  for this ADR.
- `load_env=True` loads the local `.env` before `NorFabInventory` reads and
  renders the inventory.
- `load_env=<filepath>` loads the explicit env file path.
- `load_env=False` or `load_env=None` skips env loading.
- For `load_env=True`, NFAPI checks `<inventory-directory>/.env` for path-based
  inventory, `<base_dir>/.env` for dictionary inventory with `base_dir`, then
  `./.env` as fallback.

### NorFab Startup

Keep `start()` close to the existing public shape:

```python
nf.start(
    run_broker=None,
    run_workers=None,
)
```

Behavior:

- `start()` always starts requested broker/workers using a short-lived startup
  thread.
- `start()` returns after scheduling the startup thread.
- The startup thread handles broker startup, worker dependency ordering,
  worker readiness tracking, startup hooks, and startup status recording.
- Callers do not choose separate wait modes for broker and workers.
- Client construction does not depend on broker/worker readiness except for
  the client's own bounded broker-key wait when authentication requires it.

Use explicit `is None` checks instead of `run_broker = run_broker or
self.run_broker` and `run_workers = run_workers or self.run_workers`. This
preserves explicit `False` values passed to `start()`.

### Client Creation

Extend `make_client()`:

```python
nf.make_client(
    broker_endpoint=None,
    broker_token=None,
    name="NFPClient",
)
```

Behavior:

- `broker_endpoint` overrides the endpoint for that client.
- `broker_token` updates the broker shared key before certificate generation.
- `name` allows future clients to avoid sharing the same local client database
  and certificate directory.
- When the client must read the broker token from a local broker-generated key
  file, client certificate setup waits up to a small bounded timeout for that
  file before raising a clear error. This wait is an internal client behavior,
  not an NFAPI startup mode.

### NFCLI Arguments

Add arguments in `norfab/utils/nfcli.py`:

```text
--broker-url      Broker ZMQ endpoint for the client.
--broker-token    Broker public key/shared key for client authentication.
```

If `--broker-url` is omitted and `NORFAB_BROKER_URL` exists in the environment,
use `NORFAB_BROKER_URL` as the broker URL. If `--broker-token` is omitted and
`NORFAB_BROEKR_TOKEN` exists in the environment, use `NORFAB_BROEKR_TOKEN` as
the broker token.

Apply these arguments to all modes that create a NorFab client:

- `--client`
- default shell mode
- `--tui`
- `--web-ui` if the web client construction supports passing them through

When `--broker` is also used, `--broker-url` is the local broker bind endpoint.
When `--workers` is used, both overrides are passed through inventory so workers
connect to the same broker.

## Implementation Plan

Keep the first implementation intentionally small. The required code changes
should be limited to:

- NFAPI constructor argument handling for `.env`, broker URL, and broker token.
- NFAPI startup orchestration through one startup thread.
- Client certificate setup wait for locally generated broker keys.
- Client job dispatch retry and deadline cleanup for broker/worker-not-ready
  startup windows.
- NFCLI argument parsing and passing broker overrides into NorFab.
- A local lifecycle queue/supervisor for restart commands.
- Per-worker exit events to support individual worker restart.
- Moving mutable `NorFab` class attributes such as `workers_processes` and
  `worker_plugins` to instance attributes.

Avoid new broker protocol commands, remote administrative APIs, database
schema changes, and broad worker refactors in this ADR.

### Code and Style Guidelines

Follow the style used by the other ADRs in this folder:

- Keep the common path first and keep sections scannable.
- Keep examples short and use fenced code blocks with a language tag.
- Use the same terms consistently: broker, worker, client, startup thread,
  supervisor thread, lifecycle signal.
- Put compatibility, risks, and open questions in their own sections.
- Prefer staged implementation notes over broad refactors.

Keep code changes small and close to the current code shape:

- Reuse existing `start_broker_process()`, `start_worker_process()`,
  `multiprocessing.Process`, `multiprocessing.Event`,
  `multiprocessing.Queue`, and `threading.Thread` patterns.
- Do not introduce asyncio, a new process manager, a new broker protocol
  command, or a remote admin service for this change.
- Put new NFAPI state on the `NorFab` instance, not class attributes.
- Use explicit `is None` checks for optional booleans so `False` remains a
  meaningful caller value.
- Keep lifecycle signals as plain dictionaries for the first implementation.
  Add a model only when validation or documentation generation needs it.
- Do not log `broker_token`, broker shared keys, or full lifecycle payloads
  that may contain secrets.
- Give background threads clear names such as `norfab-startup` and
  `norfab-lifecycle-supervisor`.
- Protect `workers_processes`, broker process state, and startup status with a
  single NFAPI lock instead of scattering locks across helpers.
- Prefer small helper methods over new classes unless the helper starts
  carrying independent state.
- Keep NFCLI changes in argument parsing and shell startup wiring. Avoid
  changing shell command models except for explicit lifecycle commands.
- Add focused tests or manual validation for first-run encrypted local startup,
  existing environment client-first startup, explicit `run_broker=False`,
  explicit `run_workers=False`, and one worker restart path.

### 1. Load `.env` Before Inventory Rendering

Use `python-dotenv` for env file parsing:

```python
from dotenv import load_dotenv

load_dotenv(dotenv_path=path, override=False)
```

Add `python-dotenv` as a core dependency because `.env` loading is now part of
NFAPI startup behavior, not only an optional service feature.

Use `override=False` so existing process environment variables win over `.env`
values.

Call `load_dotenv()` at the top of `NorFab.__init__()` before constructing
`NorFabInventory`, because `render_jinja2_template()` reads `os.environ` during
inventory load.

### 2. Apply Broker Overrides Centrally

After inventory is loaded, apply:

```python
broker_url = broker_url or os.environ.get("NORFAB_BROKER_URL")
broker_token = broker_token or os.environ.get("NORFAB_BROEKR_TOKEN")

if broker_url:
    self.inventory.broker["endpoint"] = broker_url
if broker_token:
    self.inventory.broker["shared_key"] = broker_token
```

Then set `self.broker_endpoint` from the final inventory value.

This keeps broker, client, and worker configuration aligned without adding
separate protocol fields.

Also move mutable state currently declared at class level on `NorFab` into
`__init__()`:

```python
self.client = None
self.broker = None
self.workers_processes = {}
self.worker_plugins = {}
```

This avoids cross-instance leakage and makes threaded startup/restart state
ownership explicit.

### 3. Handle Local Broker Key Wait In Client Setup

Do not add NFAPI key-readiness checks or startup branches. `NFPClient` already
knows the exact certificate paths during construction, so the bounded wait
belongs close to `generate_certificates()` and `reconnect_to_broker()`.

The common flow stays the same for all local shell startups:

1. `nf.start()` schedules broker and worker startup in the background.
2. `nf.make_client()` constructs the client.
3. Client certificate setup uses the configured broker token immediately, or
   waits briefly for the broker-generated local `broker.key` file if no token
   is configured.
4. NFCLI starts the shell once the client exists.

If `__norfab__` is missing but a broker token is available from CLI/API,
environment, or inventory, the client should not wait for local broker startup
just to create the directory. The client can proceed using the provided token
and create its own local client runtime state as it does today.

Do not pre-generate or rotate broker keys outside broker startup. The broker
remains responsible for creating its own key files.

Add a bounded wait to client certificate setup. The smallest code change is to
enhance `generate_certificates()` with optional arguments such as:

```python
generate_certificates(
    ...,
    broker_key_wait_timeout=30,
    broker_key_wait_interval=0.05,
)
```

When `broker_keys_dir` is provided, `inventory.broker["shared_key"]` is not
set, and `broker.key` is not present yet, wait up to
`broker_key_wait_timeout` for `broker.key` before raising a clear exception.
When a shared key is provided, keep the current behavior and write it directly
to the client's local `broker.key` file without waiting.

Use a small default timeout so first local encrypted startup works without any
NFAPI or NFCLI branching. The default should be short enough to fail quickly
for invalid client-only remote configurations that do not provide a token.

### 4. Make Job Dispatch Retry Startup Unavailability

Keep `submit_job()` as the durable local enqueue point. A submitted job should
be written to the client database and represented by an `NFPJobFuture` before
any broker or worker availability is required.

Update the dispatcher and response handling so transient startup availability
does not become terminal failure:

- Add a retryable job state, for example
  `JobStatus.WAITING_WORKERS = "WAITING_WORKERS"`, or reuse `NEW` if the first
  implementation must be even smaller.
- When `handle_response()` receives the broker's current no-workers response
  (`status == "400"` with `payload["workers"] is None`), update the job to the
  retryable state, store a warning event or appended warning, set
  `last_poll_timestamp`, and do not call `future.mark_done()`.
- Have `dispatch_new_jobs()` pick up `NEW` and retryable worker-waiting jobs.
  Respect `last_poll_timestamp` with a small retry interval so the client does
  not hammer the broker while workers are registering.
- Keep other client errors and server errors terminal. For example malformed
  requests, authorization failures, and worker task failures should still mark
  the job `FAILED`.
- Add live deadline handling for `NEW`, retryable worker-waiting, and
  `SUBMITTING` jobs. Once `time.time() >= deadline`, mark the job `STALE`,
  set `completed_timestamp`, append a clear timeout error, and mark the future
  done.

This makes the default shell safe for scripts that submit a job immediately
after the client is returned:

```python
client.run_job("nornir", "cli", kwargs={"commands": ["show clock"]}, timeout=60)
```

If the broker is still booting, ZeroMQ can queue the POST until the endpoint is
available. If the broker is ready but workers are not registered yet, the
client retries dispatch until the job deadline. If the workers never appear,
the job becomes `STALE` instead of failing immediately with a startup race.

Do not make MMI requests durable in this change. `client.mmi()` has no local
job database row and should keep its current synchronous timeout behavior.
Shell commands backed by MMI may still timeout if used before the broker is
ready.

### 5. Always Use a Startup Thread

Move the existing body of `NorFab.start()` into an internal method such as
`_start_components(run_broker, run_workers)`.

Make `add_built_in_workers_inventory()` idempotent before background startup or
broker restart can call it more than once. It should not insert duplicate
`filesharing-worker-1` entries into `inventory.topology["workers"]`.

`start()` always creates a thread:

```python
self.startup_thread = threading.Thread(
    target=self._start_components,
    daemon=True,
    args=(...),
)
self.startup_thread.start()
```

`start()` returns immediately after the startup thread has been scheduled.

The startup thread is not a supervisor loop. It should start broker/workers,
track initialization, run startup hooks when their existing prerequisites are
met, record startup status, and exit. Broker and workers continue running in
their existing `multiprocessing.Process` instances.

Protect `self.workers_processes` and startup state with a lock because callers
can observe process state while the startup thread is running.

Guard against concurrent startup calls. If `self.startup_thread` exists and is
alive, a second `start()` should either return the existing thread status or
raise a clear `RuntimeError`; it must not start another orchestration thread
against the same process state.

### 6. Preserve Hooks

Startup hooks currently run only after all workers initialize. Keep that
semantic.

Run startup hooks inside the startup thread after worker readiness is reached.
If worker initialization times out, log the error and set a startup status
field for inspection. Do not kill the already-running interactive shell.

### 7. Update NFCLI Shell Startup

Change `start_picle_shell()` to avoid `with NorFab(...) as nf` for default
interactive mode. Use explicit lifecycle management:

```python
nf = NorFab(...)
try:
    nf.start(run_broker=run_broker, run_workers=run_workers)
    NFCLIENT = nf.make_client(...)
    shell.start()
finally:
    nf.destroy()
```

Client-only mode should not start broker/workers. It can still use
`broker_url` and `broker_token` to connect to a remote broker.

TUI can follow the same pattern if it benefits from immediate startup. If the
TUI requires initial broker data at launch, keep it blocking until a separate
TUI readiness view is implemented.

### 8. Improve Worker Readiness Waits

The current final worker readiness loop has no sleep in the polling loop. Add a
small sleep, for example `time.sleep(0.05)`, to avoid CPU spin while waiting for
slow workers.

Track startup status per worker:

- `process_started`
- `init_done`
- `failed`
- `depends_on_wait`
- `error`

Use this status for logs and future `show startup` shell output.

### 9. Keep Dependency Ordering

Keep current `depends_on` behavior:

- a worker with dependencies is only started after dependency processes are
  alive and their `init_done_event` values are set;
- workers without dependencies can start immediately.

This dependency logic remains in the startup thread. The shell can be
available while dependent workers wait.

### 10. Add NFAPI Lifecycle Supervisor

Add a long-lived NFAPI lifecycle supervisor thread for explicit restart
requests. This is separate from the short-lived startup thread:

- startup thread: starts broker/workers, waits for initialization if requested,
  runs startup hooks, then exits;
- supervisor thread: remains alive while NFAPI is alive and handles lifecycle
  commands such as worker restart and broker restart.

NorFab currently runs broker and workers as `multiprocessing.Process`
instances, not threads. Public API names should use `restart_broker()` and
`restart_worker()` to describe the real operation clearly.

Recommended NFAPI methods:

```python
nf.restart_worker("nornir-worker-1", reason="client-request")
nf.restart_broker(reason="client-request", restart_workers=False)
nf.restart_all(reason="client-request")
```

Recommended internal queue item:

```python
{
    "action": "restart_worker",
    "target": "nornir-worker-1",
    "reason": "worker-request",
    "source": "nornir-worker-1",
    "timestamp": time.time(),
}
```

Lifecycle commands should be serialized through one `multiprocessing.Queue`
owned by NFAPI. Client-facing shell methods and child processes both submit
restart requests to that queue. The supervisor thread is the only place that
mutates broker/worker process state.

#### Lifecycle Signal Object

Use a small structured lifecycle signal rather than a bare event flag. An event
is useful for waking a loop, but restart needs payload data: action, target,
source, reason, timestamp, and optional metadata.

For the minimal implementation, use a plain dictionary payload. A dataclass or
Pydantic model can be added later if more lifecycle actions appear.

```python
{
    "action": "restart_worker",
    "target": "nornir-worker-1",
    "source": "nornir-worker-1",
    "reason": "watchdog-memory-threshold",
    "metadata": {},
    "timestamp": time.time(),
}
```

Example actions:

- `restart_worker`
- `restart_broker`
- `restart_all`
- `worker_unhealthy`
- `broker_unhealthy`

Use `multiprocessing.Queue` because signals can be emitted by child processes.
NFAPI can wrap it with a supervisor thread that blocks on
`queue.get(timeout=...)` and dispatches signals serially.

#### Watchdog-Signaled Restart

Workers can have watchdog threads. Broker can also grow a watchdog or health
monitor. These watchdogs should not restart their own process directly. They
should emit a lifecycle signal to NFAPI and let NFAPI perform the restart.

Worker watchdog flow:

1. Worker watchdog detects an unrecoverable condition.
2. Watchdog calls `self.worker.request_restart(reason=..., metadata=...)`.
3. Base worker puts a lifecycle signal with `action="restart_worker"`,
   `target=self.name`, and `source=self.name` on the lifecycle queue.
4. NFAPI supervisor receives the signal and runs the worker restart flow.

Broker watchdog flow:

1. Broker watchdog or broker health monitor detects an unrecoverable broker
   condition.
2. It emits a lifecycle signal with `action="restart_broker"`,
   `target="broker"`, and `source="broker"` to NFAPI.
3. NFAPI supervisor runs the broker restart flow.

For broker restart signaling, prefer a lifecycle queue passed from NFAPI into
the broker process, the same way it is passed into worker processes. Avoid OS
signals for normal lifecycle control because they are harder to test, less
portable on Windows, and carry little structured context.

#### Worker-Signaled Restart

Add a dedicated lifecycle queue from NFAPI to worker processes:

1. `NorFab.__init__()` creates `self.lifecycle_queue`.
2. `start_worker_process()` receives `lifecycle_queue`.
3. Base `NFPWorker` stores it as `self.lifecycle_queue`.
4. Base worker exposes:

```python
self.request_restart(reason="configuration changed")
```

5. `request_restart()` places a restart command on the lifecycle queue and then
   returns. The worker can either keep running until NFAPI stops it, or call a
   graceful local shutdown helper after publishing the request.

Watchdog implementations should use this same API. Service-specific watchdogs
should not need direct access to NFAPI internals.

Do not reuse the logging queue for lifecycle commands. Restart is control
plane data and should not be coupled to logging delivery.

#### Client-Triggered Restart

For the local interactive shell, add NFCLI commands that call the local NFAPI
object directly:

```text
workers restart nornir-worker-1
broker restart
norfab restart
```

This requires `start_picle_shell()` to keep both `NFCLIENT` and the owning
`NorFab` object available, for example `builtins.NORFAB = nf`.

Remote client-triggered restarts should be treated as a later extension unless
there is an immediate need. A remote restart API would require an explicit
broker-routed administrative service, authorization rules, and audit logging.

#### Worker Restart Flow

The supervisor should restart a worker with this sequence:

1. Mark worker startup status as `restarting`.
2. Set only that worker's stop signal or otherwise ask the process to exit
   gracefully.
3. Join the worker process with a bounded timeout.
4. If the process is still alive, terminate it as a last resort and record the
   forced stop.
5. Remove the old process and init event from `self.workers_processes`.
6. Create a new `init_done_event`.
7. Call `start_worker(worker_name, worker_data)` using the existing dependency
   checks.
8. Wait for the new worker `init_done_event` up to `workers_init_timeout`.
9. Mark status as `ready` or `failed`.

To make this reliable, NFAPI should preserve the normalized worker topology
data used at startup, for example `self.workers_topology`, so a later restart
does not need to reconstruct worker dependency metadata from a partially
mutated local variable.

The current shared `self.workers_exit_event` is sufficient for global shutdown
but not for individual worker restart. Add a per-worker exit event stored in
`self.workers_processes[worker_name]["exit_event"]`. Global shutdown should set
all per-worker exit events. Individual restart should set only the target
worker's event. The existing shared event can remain during transition, but new
worker process creation should pass the per-worker event to
`start_worker_process()`.

#### Broker Restart Flow

Broker restart is more disruptive than worker restart because worker and client
sockets depend on it. Keep the first implementation conservative:

1. Add `restart_broker(reason, restart_workers=False)`.
2. Stop the broker process and join it with a bounded timeout.
3. Start a new broker process on the same endpoint.
4. Wait for broker readiness.
5. If `restart_workers=True`, restart all local workers after the broker is
   ready.

Broker restart also needs a fresh broker exit event. Once
`self.broker_exit_event` is set for the old process, create a new event before
starting the replacement broker.

If broker restart is requested from inside the broker process itself, the
broker must only emit the lifecycle signal. The NFAPI supervisor remains
responsible for stopping and replacing the broker process.

With `restart_workers=False`, rely on existing worker keepalive/reconnect logic
to reconnect to the new broker. This should be tested carefully because the
broker loses its in-memory worker registry during restart.

Do not rotate broker keys during broker restart.

#### Automatic Restart Policy

Add optional topology settings later, not in the first minimal change:

```yaml
topology:
  restart_policy:
    workers: on-request
    broker: manual
    max_restarts: 3
    restart_window: 300
```

Initial implementation should support manual/client-triggered restart and
worker-signaled self restart. Automatic restart on unexpected process exit can
be added once restart accounting and backoff are in place.

## Startup Speed Review

The largest user-visible delay is not process creation itself. It is waiting
for all worker initialization before constructing the client and starting the
shell.

Other improvement opportunities:

- Avoid the busy wait in `NorFab.start()` worker readiness loop.
- Keep plugin entry point registration cheap by storing entry points and only
  loading worker classes in child processes or immediately before starting the
  relevant worker.
- Consider lazy importing service-specific NFCLI shell modules so client-only
  startup does not import every service command tree up front.
- Avoid repeatedly rendering and merging worker inventory where a worker can be
  given already-resolved data safely, but treat this as a later optimization
  because it changes process payload and inventory semantics.
- Add timestamped startup logs for each phase: inventory loaded, logging ready,
  broker process started, broker ready, worker process started, worker ready,
  startup hooks complete.

## Compatibility

- `NorFab.start()` changes from a blocking startup call to a background startup
  scheduling call. This is the main compatibility tradeoff of keeping the API
  simple and avoiding wait-mode flags.
- Existing inventory files keep working.
- Existing local all-in-one authentication keeps working because broker startup
  remains responsible for generating broker keys in the same directory and
  format as today.
- Existing client-only mode keeps working and gains explicit broker endpoint
  and token overrides.
- Existing worker dependency configuration keeps working.
- Restart support is additive. Existing callers do not use it unless they call
  the new NFAPI/NFCLI lifecycle commands or a worker explicitly requests a
  restart.

## Risks

### Commands Before Readiness

The shell prompt may appear before the broker or workers are reachable. Jobs
stored in the local client database should retry transient startup
unavailability until their deadline. MMI and other synchronous non-job
requests should keep their existing timeout behavior and return clear errors.
NFCLI should not hide these failures.

This changes the meaning of early job submission from "broker accepted the job"
to "client durably queued the job for dispatch." Documentation and shell output
should be clear when a job is still waiting for workers.

### Startup Hooks In Background

Hooks that previously completed before shell entry may now run after the prompt
appears. Document that startup hooks are tied to background component startup,
not to client construction.

### Local Broker Key Wait

NFCLI cannot show the prompt until client construction completes. When a local
broker is requested, broker authentication is enabled, and no broker token is
available from CLI/API arguments, environment variables, or inventory, client
certificate setup may need to wait briefly for the broker-generated local key
file. Missing `__norfab__` state alone should not trigger a broker wait when a
token is available.

This wait should be bounded and produce a clear error if the broker key does
not appear. It should not wait for all broker initialization phases or any
workers.

### Shared Inventory Mutation

Broker override values mutate the in-memory inventory. This is intentional for
one NorFab process, but the implementation should not write these overrides
back to `inventory.yaml`.

### Background Thread Cleanup

`destroy()` must set exit events and join the startup thread briefly if it is
still running before joining processes, otherwise startup and shutdown can
race.

### Restart Loops

Worker-signaled restart can create a tight loop if a worker requests restart
immediately after startup. Add restart accounting before enabling automatic
restart-on-exit policies, and always record restart reason/source in logs.
Watchdog-triggered restart should include rate limits, for example maximum
restart count within a time window, before being enabled by default.

### Broker Restart Disruption

Broker restart drops the broker's in-memory worker registry and can interrupt
in-flight jobs. The first broker restart implementation should be manual and
should document that in-flight jobs may fail or need to be resubmitted.

## Questionnaire Before Finalizing

Use this flat checklist to finalize the ADR decisions before implementation.

1. Should `NorFab.start()` always schedule broker and worker startup in the
   background and return without a public `wait` argument?
2. Should `NorFab.__enter__()` use the same simple order:
   `start()` then `make_client()`?
3. Should default `nfcli` shell mode use the same simple order:
   create `NorFab`, call `start()`, call `make_client()`, then show the shell?
4. Is client-side broker-key wait the right place to handle first local
   encrypted startup, instead of NFAPI checking key file existence?
5. Should client certificate setup wait only when broker authentication is
   enabled and no broker token exists from CLI/API, environment, or inventory?
6. If `__norfab__` is missing but a broker token is provided through
   `--broker-token`, `NORFAB_BROEKR_TOKEN`, API, or inventory, should NFCLI
   create the client immediately without waiting for broker startup?
7. What timeout should client certificate setup use while waiting for a local
   broker-generated `broker.key` file: 5, 10, 30 seconds, or reuse the existing
   broker startup timeout?
8. If the local broker key file does not appear before timeout, should client
   creation raise an exception or should NFCLI continue without a client and
   show a degraded prompt?
9. If background startup fails, should NFCLI only log the
   error, or should it show a visible shell notification?
10. Should NFCLI display a small startup status line before the prompt, or keep
   the prompt completely immediate and rely on `show broker` / `show workers`?
11. Should startup status become a first-class shell command, for example
   `show startup`, after the background startup state is added?
12. Should `NorFab.start()` return the startup thread/status object,
   or keep returning `None`?
13. If a second `start()` call happens while startup is running, should NFAPI
   return the existing startup status or raise `RuntimeError`?
14. What startup status fields are required for the first implementation:
   `running`, `completed`, `failed`, `errors`, `started_at`, `completed_at`,
   per-worker states?
15. Should startup hooks run after workers are ready only, or also after broker
    is ready in broker-only mode?
16. If worker initialization times out during background startup, should NFAPI call
    `destroy()` or leave already-started components running?
17. Should `load_env=True` search only the inventory directory, or keep the
    proposed fallback order of inventory directory, `base_dir`, then current
    directory?
18. Should `load_env=<filepath>` accept relative paths anchored to current
    working directory or inventory directory?
19. Should missing explicit `load_env=<filepath>` raise an error or only log a
    warning?
20. Should `.env` loading happen for both `inventory` and `inventory_data`
    modes?
21. Should `NORFAB_BROKER_URL` always be treated as the default for
    `--broker-url` and `broker_url` when CLI/API values are omitted?
22. Should `NORFAB_BROEKR_TOKEN` keep this exact spelling, or should the
    implementation also support the corrected alias `NORFAB_BROKER_TOKEN`?
23. Should the CLI option be named `--broker-url`, `--broker-endpoint`, or both
    with one alias?
24. Should `--broker-token` accept only the raw public key value, or also a path
    to a `broker.key` file?
25. Should `broker_url` and `broker_token` mutate only in-memory inventory, or
    should there be any option to persist them to disk?
26. If inventory, environment, and CLI/API all provide broker settings, should
    precedence be CLI/API first, environment second, inventory last?
27. Should restart support be implemented in the same change as client-first
    startup, or as a separate follow-up change?
28. Which restart commands are required first: `restart_worker`,
    `restart_broker`, `restart_all`, or only `restart_worker`?
29. Should lifecycle restart commands be exposed only in local NFCLI, or should
    Python API methods be public from day one?
30. Should broker restart restart local workers by default, or rely on worker
    reconnect logic by default?
31. Should in-flight jobs be cancelled, marked stale, or left to existing
    timeout behavior during worker/broker restart?
32. Should worker-requested restart stop the worker immediately after queueing
    the request, or should NFAPI always be responsible for stopping it?
33. Should worker watchdog restart be enabled by default, or only when
    inventory explicitly enables it?
34. Should watchdog restart policy live under each worker inventory, topology,
    or both?
35. What default restart limit should be used, if any, for watchdog-triggered
    restarts?
36. Should broker watchdog support be included now, or left as a future design
    until broker health checks are clearer?
37. What manual startup scenarios must pass before merge?
38. Are automated tests required for first-run encrypted startup and existing-runtime
    client-first startup?
39. Should restart behavior be tested with a fake worker only, or with a real
    built-in worker such as filesharing?
40. Should Windows-specific validation be mandatory because NFAPI uses
    multiprocessing, events, and local key files?
41. Should a broker `400` response with `workers=None` always be treated as
    retryable until the job deadline, including explicit target-worker typos?
42. Should retryable no-worker jobs use a new visible status such as
    `WAITING_WORKERS`, or should the client keep resetting them to `NEW` for
    the smallest code change?
43. What retry interval should the dispatcher use while waiting for workers:
    0.5, 1, 2, or 5 seconds?
44. Should the job deadline timer start when the client stores the job locally,
    or only after the broker first accepts and dispatches it?
45. If the broker is not reachable and a job remains `SUBMITTING` with no
    response, should the running dispatcher mark it `STALE` at deadline?
46. Should `future.result(timeout=...)` also mark the job `STALE` when the
    caller timeout expires, or should only the dispatcher mutate job status?
47. Should MMI calls remain synchronous timeout-only, or should selected MMI
    calls also get a retry wrapper for startup readiness?
48. Should NFCLI show a friendly "job queued, waiting for workers" message
    when a job enters the retryable worker-waiting state?
