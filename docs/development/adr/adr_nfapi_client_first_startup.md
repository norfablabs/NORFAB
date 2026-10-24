# ADR - NFAPI Client-First Startup and Client Connection Overrides

## Status

Proposed.

## Date

2026-06-20.

## Decision

Improve NorFab startup so default NFCLI interactive mode can return the prompt
as soon as the client is constructed, without waiting for all local worker
processes to finish initialization.

`NorFab.start()` must no longer expose or use a public `wait` argument. Startup
uses one simple path:

```python
nf = NorFab(inventory="inventory.yaml", log_level=log_level)
nf.start()
client = nf.make_client()
```

`NorFab.start()` schedules requested broker and worker startup through a
short-lived background startup thread and returns using the existing return
behavior. Broker and workers continue starting in the background.

`NorFab.__enter__()` must support the same behavior as direct lifecycle usage.
Context manager usage should remain valid and should not require a separate
NFCLI flow:

```python
with NorFab(inventory="inventory.yaml", log_level=log_level) as nf:
    client = nf.client
```

NFCLI default shell mode should keep using `with NorFab(...) as nf`, with all
CLI overrides passed through `NorFab.__init__()`.

When broker authentication is enabled, client certificate setup should wait for
the local broker-generated key only when all of these conditions are true:

- broker authentication is enabled;
- no broker token/shared key is available from API arguments, CLI arguments,
  environment variables, or inventory;
- a local broker is requested in the same NorFab instance.

If a token is available from `broker_token`, `--broker-token`,
`NORFAB_BROKER_TOKEN`, or inventory, the client should use it immediately and
must not wait for local broker startup or local `__norfab__` state.

Jobs submitted before broker or target workers are ready should be accepted
into the local client job database. If the broker reports no matching workers
with the existing `400` / `workers=None` response, the client should mark the
job as `WAITING_WORKERS` and retry every 5 seconds until the job deadline.
Management requests that are not stored in the job database keep their current
synchronous timeout behavior.

Add client connection overrides:

- `nfcli --broker-url tcp://host:port`
- `nfcli --broker-token <broker-public-key>`

Add `.env` loading in NFAPI before inventory rendering. Existing process
environment variables must win over `.env` values.

Restart support should be designed in this ADR but implemented as a follow-up
change after client-first startup.

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

Existing useful properties:

- `NFPClient` connects with ZeroMQ DEALER sockets, so connecting to an endpoint
  is non-blocking at the socket layer.
- The client already has receiver and dispatcher threads and future-based job
  handling.
- `submit_job()` already writes jobs to the local SQLite job database before
  the dispatcher sends anything to the broker.
- Worker readiness is already represented by per-process `init_done_event`.
- Workers and clients already read broker endpoint and shared key from
  `inventory.broker`.

The current client job path needs a small adjustment for client-first startup.
`dispatch_new_jobs()` sends `NEW` jobs to the broker and marks them
`SUBMITTING`. The common early-startup failure is
broker-ready-but-workers-not-ready: `NFPBroker.dispatch()` returns a `400`
response with `workers=None` when the service has no matching active workers,
and `handle_response()` currently treats all `4xx` and `5xx` responses as
terminal failures.

The authentication constraint is local key bootstrap. `NFPClient` calls
`generate_certificates()` during construction. That helper creates the client
keypair and then either copies the broker public key from
`__norfab__/files/broker/public_keys/broker.key` or writes
`inventory.broker["shared_key"]` into the client's local `broker.key`. After
that, `reconnect_to_broker()` loads the client's local
`public_keys/broker.key`.

If broker authentication is enabled and no shared key is provided, client
construction fails when the local broker key has not been generated yet.
Certificate setup should support a bounded wait for the local broker key when
a local broker is being started in the same NorFab instance.

## Goals

- Return the NFCLI prompt quickly in default shell mode.
- Keep startup behavior simple: no public wait flags and no separate
  broker-wait or worker-wait modes.
- Keep context manager usage and direct lifecycle usage equivalent.
- Keep immediate job submissions durable during background startup by retrying
  worker-unavailable startup conditions until the job deadline.
- Allow client-only NFCLI connections to remote brokers without editing
  `inventory.yaml`.
- Load `.env` before inventory Jinja2 rendering so inventory can use
  `{{ env.VAR_NAME }}` values.
- Keep startup hooks and worker dependency ordering intact unless the new
  background startup model requires a narrow adjustment.
- Keep code changes minimal and close to existing NFAPI/client patterns.

## Non-Goals

- Do not rewrite broker, client, or worker protocol flows.
- Do not make job execution complete before the broker or target workers are
  actually reachable.
- Do not make broker state persistent.
- Do not change worker task semantics.
- Do not add public wait flags.
- Do not implement restart support in the first client-first startup change.
- Do not implement broker watchdog support in the first restart change.
- Do not add a `show startup` shell command in the first startup change.

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
- If `broker_url` is not supplied, `NORFAB_BROKER_URL` from the environment is
  used when present.
- If `broker_token` is not supplied, `NORFAB_BROKER_TOKEN` from the environment
  is used when present.
- If neither explicit arguments nor environment variables are present, keep the
  broker endpoint and shared key values provided by the inventory.
- Precedence is API/CLI argument first, environment variable second, inventory
  value last.
- Broker overrides mutate only the in-memory inventory and are not persisted to
  disk.
- `load_env=True` loads the local `.env` before `NorFabInventory` reads and
  renders inventory.
- For path-based inventory, `load_env=True` only checks the directory that
  contains `inventory.yaml`.
- `load_env=<filepath>` loads the explicit env file. Relative paths are
  resolved from the inventory file directory.
- Missing explicit `load_env=<filepath>` raises an error.
- `load_env=False` or `load_env=None` skips env loading.
- `.env` loading should be supported for both `inventory` and `inventory_data`
  modes.
- For `inventory_data` mode, the resolved `NorFabInventory.base_dir` anchors
  `load_env=True` and relative `load_env=<filepath>` values. After the
  inventory base directory fix, omitted `base_dir` defaults to the current
  working directory.

### NorFab Startup

Keep `start()` close to the existing public shape, but remove any public wait
argument:

```python
nf.start(
    run_broker=None,
    run_workers=None,
)
```

Behavior:

- `start()` schedules requested broker/workers using a short-lived startup
  thread.
- `start()` does not wait for all workers to initialize.
- If both `run_broker=False` and `run_workers=False`, `start()` returns
  immediately without creating a startup thread, as long as this keeps the code
  smaller and clearer.
- `start()` keeps the existing return behavior unless the new threading logic
  makes a narrow return change unavoidable.
- The startup thread handles broker startup, worker dependency ordering, worker
  readiness tracking, startup hooks, and minimal startup status recording.
- Use explicit `is None` checks instead of `run_broker = run_broker or
  self.run_broker` and `run_workers = run_workers or self.run_workers`, so
  explicit `False` values remain meaningful.
- If another `start()` call happens while startup is already running, keep the
  closest existing behavior and avoid adding new public state unless required.

Minimal startup status should be limited to what is needed now:

- `starting`
- `running`
- `error`

Do not add future-oriented status fields such as `completed_at`,
`per-worker states`, or a public startup status object unless implementation
requires them.

Startup hooks should keep existing behavior unless the new background startup
flow would break current semantics.

### Context Manager

`NorFab.__enter__()` should use the same lifecycle as direct startup:

1. call `self.start()` using constructor-resolved `run_broker` and
   `run_workers`;
2. call `self.make_client()`;
3. return `self`.

This allows NFCLI to keep:

```python
with NorFab(
    inventory=inventory,
    run_broker=run_broker,
    run_workers=run_workers,
    broker_url=broker_url,
    broker_token=broker_token,
) as nf:
    builtins.NFCLIENT = nf.client
    shell.start()
```

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
  file, client certificate setup waits up to the broker startup timeout for
  that file before raising a clear `RuntimeError`.
- The key wait only happens when auth is enabled, no broker token exists, and
  a local broker is requested.
- Client-only remote mode with broker authentication enabled and no token
  should fail quickly with a clear error instead of waiting for a local key
  that will never be generated.

### NFCLI Arguments

Add arguments in `norfab/utils/nfcli.py`:

```text
--broker-url      Broker ZMQ endpoint for the client.
--broker-token    Broker public key/shared key for client authentication.
```

Rules:

- Use only `--broker-url`; do not add `--broker-endpoint`.
- `--broker-token` accepts the raw public key/shared key value, same as
  inventory, not a file path.
- If `--broker-url` is omitted and `NORFAB_BROKER_URL` exists, use
  `NORFAB_BROKER_URL`.
- If `--broker-token` is omitted and `NORFAB_BROKER_TOKEN` exists, use
  `NORFAB_BROKER_TOKEN`.
- NFCLI help text should mention the environment-variable fallbacks.
- Apply these arguments to all modes that create a NorFab client:
  `--client`, default shell mode, `--tui`, and `--web-ui` if supported by that
  path.

When `--broker` is also used, `--broker-url` is the local broker bind endpoint.
When `--workers` is used, both overrides are passed through the in-memory
inventory so workers connect to the same broker.

## Implementation Plan

Keep the first implementation intentionally small. The first client-first
startup change should include:

- NFAPI constructor argument handling for `.env`, broker URL, and broker token.
- NFAPI startup orchestration through one startup thread.
- Context manager behavior matching direct startup behavior.
- Client certificate setup wait for locally generated broker keys.
- Client job dispatch retry for broker no-workers responses.
- NFCLI argument parsing and passing broker overrides into `NorFab`.
- Moving mutable `NorFab` class attributes such as `workers_processes` and
  `worker_plugins` to instance attributes if needed for correct background
  startup ownership.
- Documentation updates for changed startup semantics, environment loading,
  broker overrides, and job retry behavior.

The restart capability is a follow-up change and should not be included in the
first client-first startup implementation.

Avoid new broker protocol commands, remote administrative APIs, database schema
changes, and broad worker refactors in the client-first startup change.

### Code and Style Guidelines

Follow the style used by the other ADRs in this folder:

- Keep the common path first and keep sections scannable.
- Keep examples short and use fenced code blocks with a language tag.
- Use the same terms consistently: broker, worker, client, startup thread,
  lifecycle supervisor, lifecycle signal.
- Put compatibility, risks, and open questions in their own sections.
- Prefer staged implementation notes over broad refactors.

Keep code changes small and close to the current code shape:

- Reuse existing `start_broker_process()`, `start_worker_process()`,
  `multiprocessing.Process`, `multiprocessing.Event`, and `threading.Thread`
  patterns.
- Do not introduce asyncio, a new process manager, a new broker protocol
  command, or a remote admin service.
- Put new NFAPI state on the `NorFab` instance, not class attributes.
- Use explicit `is None` checks for optional booleans so `False` remains a
  meaningful caller value.
- Do not log `broker_token` or broker shared keys.
- Give the startup thread a clear name such as `norfab-startup`.
- Prefer small helper methods over new classes unless the helper starts
  carrying independent state.
- Keep NFCLI changes in argument parsing and shell startup wiring.

### 1. Load `.env` Before Inventory Rendering

Use `python-dotenv` for env file parsing:

```python
from dotenv import load_dotenv

load_dotenv(dotenv_path=path, override=False)
```

Add `python-dotenv` as a core dependency because `.env` loading is part of
NFAPI startup behavior.

Call `load_dotenv()` at the top of `NorFab.__init__()` before constructing
`NorFabInventory`, because `render_jinja2_template()` reads `os.environ` during
inventory load.

For path-based inventory:

- `load_env=True` loads only `<inventory-directory>/.env`.
- `load_env=<relative path>` resolves from `<inventory-directory>`.
- `load_env=<absolute path>` uses that exact path.
- Missing explicit env file paths raise an error.

For `inventory_data` mode:

- `load_env=True` loads `<resolved-base-dir>/.env`.
- `load_env=<relative path>` resolves from the resolved base directory.
- If `base_dir` is omitted, the resolved base directory is the current working
  directory because `NorFabInventory` now uses
  `os.path.abspath(base_dir or os.getcwd())` for dictionary inventory.
- Compute this resolved base directory before constructing `NorFabInventory` so
  `.env` values are loaded before any inventory or worker file template
  rendering reads `os.environ`.

### 2. Apply Broker Overrides Centrally

After inventory is loaded, apply:

```python
broker_url = broker_url or os.environ.get("NORFAB_BROKER_URL")
broker_token = broker_token or os.environ.get("NORFAB_BROKER_TOKEN")

if broker_url:
    self.inventory.broker["endpoint"] = broker_url
if broker_token:
    self.inventory.broker["shared_key"] = broker_token
```

If neither explicit arguments nor environment variables are present, do not
modify these inventory fields. Then set `self.broker_endpoint` from the final
inventory value.

### 3. Handle Local Broker Key Wait In Client Setup

Do not add NFAPI key-readiness checks or startup branches. `NFPClient` already
knows the exact certificate paths during construction, so the bounded wait
belongs close to `generate_certificates()` and `reconnect_to_broker()`.

The common flow stays the same for all local shell startups:

1. `nf.start()` schedules broker and worker startup in the background.
2. `nf.make_client()` constructs the client.
3. Client certificate setup uses the configured broker token immediately, or
   waits for the broker-generated local `broker.key` file if auth is enabled,
   no token is configured, and a local broker is requested.
4. NFCLI starts the shell once the client exists.

If certificate setup cannot obtain a required broker key before the broker
startup timeout, raise `RuntimeError` and exit NFCLI startup.

If `__norfab__` is missing but a broker token is available from CLI/API,
environment, or inventory, the client should proceed using the provided token.

Do not pre-generate or rotate broker keys outside broker startup. The broker
remains responsible for creating its own key files.

### 4. Make Job Dispatch Retry No-Worker Startup Responses

Keep `submit_job()` as the durable local enqueue point. A submitted job should
be written to the client database and represented by an `NFPJobFuture` before
any broker or worker availability is required.

Update dispatcher/response handling:

- Add `JobStatus.WAITING_WORKERS = "WAITING_WORKERS"`.
- When `handle_response()` receives `status == "400"` with
  `payload["workers"] is None`, update the job to `WAITING_WORKERS`, store a
  useful warning, set `last_poll_timestamp`, and do not call
  `future.mark_done()`.
- Apply this retry behavior to all `workers=None` responses, including
  requests that target a specific worker name that does not currently exist.
  Most calls use `workers="all"` or `workers="any"`, and the first
  implementation should keep the behavior simple by retrying until the job
  deadline.
- Have `dispatch_new_jobs()` pick up `NEW` and `WAITING_WORKERS` jobs.
- Retry `WAITING_WORKERS` jobs every 5 seconds.
- Keep other client errors and server errors terminal.
- Keep the job deadline timer starting when the job is stored locally.
- Keep existing `future.result(timeout=...)` behavior; it should not mutate job
  state on caller timeout.
- Keep MMI behavior unchanged.
- Log a `log.info` message when a job enters `WAITING_WORKERS`.

If the job deadline is reached, the job should be marked `STALE` according to
the existing stale-job behavior. Avoid broad deadline refactors unless tests
show the current behavior does not handle the new `WAITING_WORKERS` status.

### 5. Use a Startup Thread For Local Components

Move the existing body of `NorFab.start()` into an internal method such as
`_start_components(run_broker, run_workers)`.

Make `add_built_in_workers_inventory()` idempotent before background startup or
future restart paths can call it more than once. It should not insert duplicate
`filesharing-worker-1` entries into `inventory.topology["workers"]`.

`start()` creates a startup thread for requested local broker/workers:

```python
self.startup_thread = threading.Thread(
    target=self._start_components,
    args=(run_broker, run_workers),
    name="norfab-startup",
    daemon=True,
)
self.startup_thread.start()
```

The startup thread is not a supervisor loop. It should start broker/workers,
track minimal startup status, run startup hooks when their existing
prerequisites are met, and exit. Broker and workers continue running in their
existing `multiprocessing.Process` instances.

If no local broker or workers are requested, `start()` should return
immediately without creating a startup thread when that keeps the code smaller.

Broker startup failure is fatal for local all-in-one startup. NFAPI/NFCLI
should call `destroy()` for cleanup and terminate with `SystemExit` carrying a
useful error message and traceback details when local broker startup failure is
detected. If the failure is detected inside the background startup thread, that
thread must record the fatal error and propagate it to the NFCLI/main control
path; raising `SystemExit` only inside the background thread is not sufficient
to stop the interactive shell. Worker startup failure should be logged as an
error without preventing the prompt from being returned, unless existing
behavior already treats that specific failure as fatal.

NFCLI should display a small startup line before the prompt so users know local
broker/workers are starting in the background.

### 6. Preserve Worker Dependency Ordering And Hooks

Keep current `depends_on` behavior:

- a worker with dependencies is only started after dependency processes are
  alive and their `init_done_event` values are set;
- workers without dependencies can start immediately.

Startup hooks currently run only after all workers initialize. Keep that
semantic unless broker-only mode or background startup exposes a current bug.

If worker initialization times out, log an error. Do not add new public status
commands for this first change.

### 7. Avoid Worker Readiness CPU Spin

The current final worker readiness loop has no sleep in the polling loop. Add a
small sleep, for example `time.sleep(0.05)`, to avoid CPU spin while waiting for
slow workers.

### 8. Cleanup

`destroy()` must set exit events and join the startup thread briefly if it is
still running before joining processes. This avoids races where startup creates
processes while shutdown is trying to stop them.

## Restart Follow-Up Design

Restart support should be implemented after the client-first startup change.
It should be a normal supported feature, not experimental.

Required public Python API methods:

```python
nf.restart_worker("nornir-worker-1", reason="client-request")
nf.restart_broker(reason="client-request")
```

Do not add `restart_all` in the first restart implementation.

Lifecycle commands should be serialized through one NFAPI-owned
`multiprocessing.Queue` with many producers and one supervisor consumer. This
is the smallest portable option for structured requests from both shell methods
and child processes. The lifecycle supervisor is the only place that mutates
broker/worker process state.

Use plain dictionary lifecycle signals initially:

```python
{
    "action": "restart_worker",
    "target": "nornir-worker-1",
    "reason": "worker-request",
    "source": "nornir-worker-1",
    "timestamp": time.time(),
}
```

### Worker Restart

Worker restart requirements:

- expose public `restart_worker(name, reason=None)`;
- allow worker watchdog code to request its own restart;
- watchdog restart is enabled by default and should not require an inventory
  knob to turn it on;
- if watchdog settings are needed later, place them under individual worker
  inventory;
- do not add restart limits or rate limits in the first restart implementation;
- the worker process must not stop or replace itself directly; NFAPI parent
  process handles the restart.

The supervisor should restart a worker with this sequence:

1. Mark the worker as restarting internally.
2. Set only that worker's stop signal.
3. Join the worker process with a bounded timeout.
4. If the process is still alive, terminate it as a last resort and record the
   forced stop.
5. Remove the old process and init event from `self.workers_processes`.
6. Create a new `init_done_event`.
7. Call `start_worker(worker_name, worker_data)` using existing dependency
   checks.
8. Wait for the new worker `init_done_event` up to `workers_init_timeout`.
9. Mark internal status as running or error.

The current shared `self.workers_exit_event` is sufficient for global shutdown
but not for individual worker restart. Add a per-worker exit event stored in
`self.workers_processes[worker_name]["exit_event"]`. Global shutdown should set
all per-worker exit events.

### Broker Restart

Broker restart requirements:

- expose public `restart_broker(reason=None)`;
- restart only the broker by default;
- keep local workers intact and rely on reconnect behavior;
- do not rotate broker keys during broker restart;
- leave broker watchdog support for a future ADR.

Broker restart flow:

1. Stop the broker process and join it with a bounded timeout.
2. Create a fresh broker exit event.
3. Start a new broker process on the same endpoint.
4. Wait for broker readiness.
5. Keep workers running unless a later explicit feature adds worker restart.

During worker or broker restart, worker-local in-flight jobs that should be
replayed must be returned to `PENDING`. `worker.py` inserts received jobs as
`PENDING`, `get_next_pending_job()` only selects `PENDING` jobs, and the worker
loop atomically marks them `STARTED` before submitting work to the thread pool.
The restart implementation should reset interrupted `STARTED` or
`WAITING_CLIENT_INPUT` worker DB rows to `PENDING` and clear fields such as
`started_timestamp` or `completed_timestamp` where needed so the worker thread
can pick them up normally after restart.

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

## Documentation Updates

Update user and developer documentation as part of the implementation.

Required documentation updates:

- Update NFAPI docs and NFCLI docs for client-first startup behavior.
- NFAPI usage examples should show context manager usage and explicit lifecycle
  usage side by side, ideally in tabbed views.
- NFAPI constructor documentation should describe `load_env`, `broker_url`,
  and `broker_token`, including precedence: explicit API/CLI argument,
  environment variable, then inventory value.
- `.env` documentation should describe `load_env=True`,
  `load_env=<filepath>`, and `load_env=False` / `None`, with accurate workable
  examples.
- Environment variable documentation should include `NORFAB_BROKER_URL` and
  `NORFAB_BROKER_TOKEN`.
- NFCLI documentation and help text should include `--broker-url` and
  `--broker-token`, with examples for client-only remote broker connections and
  local all-in-one startup.
- Startup behavior documentation should state that `NorFab.start()` schedules
  broker and worker startup in the background and returns before all components
  are necessarily ready.
- Job documentation should describe early submission as local queueing before
  broker/worker readiness, and explain `WAITING_WORKERS`.
- MMI and other non-job command documentation should remain clear that these
  calls are synchronous and may time out if broker/workers are not ready.
- Startup hooks documentation should state that hooks run after background
  worker readiness, not before client construction or prompt display.
- Restart documentation should describe public `restart_worker()` and
  `restart_broker()` when the follow-up restart change is implemented.
- Troubleshooting documentation should include local broker key wait timeout
  failures, missing broker token/key cases, `.env` precedence confusion, and
  jobs waiting for workers.

## Compatibility

- This is accepted as a non-backward-compatible startup behavior change.
- Existing inventory files keep working.
- Existing client-only mode keeps working and gains explicit broker endpoint
  and token overrides.
- Existing worker dependency configuration should keep working.
- Existing context manager usage remains supported.
- Restart support is additive and implemented later.

## Testing And Validation

- Run the full test suite and refactor tests for the new startup behavior as
  needed.
- Add focused tests for first-run encrypted local startup and existing-runtime
  client-first startup.
- Create a small test fixture/folder with a minimal environment for these
  startup tests.
- Add tests for `.env` loading, env variable precedence, and explicit broker
  overrides.
- Add tests for `WAITING_WORKERS` retry behavior using a 5 second retry
  interval where practical.
- Test restart follow-up behavior with the existing dummy worker.
- No separate Windows-specific validation is required.

## Risks

### Commands Before Readiness

The shell prompt may appear before the broker or workers are reachable. Jobs
stored in the local client database should retry worker-unavailable responses
until their deadline. MMI and other synchronous non-job requests keep their
existing timeout behavior and should return clear errors.

This changes early job submission semantics from "broker accepted the job" to
"client queued the job locally for dispatch." Documentation and logging should
make this visible.

### Broker Failure In Background

Broker startup failure is fatal for local broker mode, but startup now happens
in a background thread. The implementation must make that failure visible and
exit NFCLI when detected, without reintroducing full worker startup blocking.
On fatal local broker failure, NFAPI should call `destroy()` and make the
NFCLI/main control path raise `SystemExit` with a useful message and traceback
details.

### Local Broker Key Wait

NFCLI cannot show the prompt until client construction completes. When a local
broker is requested, broker authentication is enabled, and no broker token is
available from API/CLI arguments, environment variables, or inventory, client
certificate setup waits up to the broker startup timeout for the
broker-generated local key file.

If the key does not appear, client construction raises `RuntimeError` and NFCLI
exits.

### Shared Inventory Mutation

Broker override values mutate the in-memory inventory. This is intentional for
one NorFab process, but the implementation must not write these overrides back
to `inventory.yaml`.

### Background Thread Cleanup

`destroy()` must set exit events and join the startup thread briefly if it is
still running before joining processes, otherwise startup and shutdown can
race.

### Broker Restart Disruption

Broker restart drops the broker's in-memory worker registry and can interrupt
in-flight jobs. The follow-up restart implementation must verify worker
reconnect and job requeue behavior carefully.

## Open Questions

No open questions remain for the first client-first startup implementation.
