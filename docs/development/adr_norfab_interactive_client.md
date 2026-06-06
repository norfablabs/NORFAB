# ADR - NorFab Future-Based Interactive Client

## Status

Proposed.

## Date

2026-06-06.

## Decision

Implement a future-based client job API with blocking synchronous methods only.

The canonical non-blocking submission API will be:

```python
future = client.submit_job(...)
```

Callers can then block for job events or final results:

```python
for event in future.events():
    ...

result = future.result()
```

`NFPClient.run_job()` remains the stable synchronous API. Existing Python API
callers, worker built-in clients, service internals, tests, and NFCLI commands
that do not consume events can continue using `run_job()` for blocking job
execution.

Do not introduce new NFP protocol commands for this refactor. Use the existing
command set:

- `NFP.POST` to submit jobs.
- `NFP.GET` to poll job status and retrieve results.
- `NFP.RESPONSE` to report accepted, pending, waiting, failed, and completed
  job states.
- `NFP.EVENT` to push progress, lifecycle messages, and input requests from
  worker to client.
- `NFP.PUT` to send job-scoped client input back to the worker.
- `NFP.STREAM` to continue serving file-transfer bytes.

Add a required `event_type` field to all event payloads. Keep the event type
set minimal:

- `progress`
- `input_request`
- `input_response`

Use `progress` for normal progress messages and job lifecycle updates such as
started, completed, failed, or stale. Use `status` for the exact lifecycle
state.

## Context

The current implementation already has most pieces required for this design.

### Current Client Behavior

`norfab/core/client.py` has:

- Client-side SQLite job storage.
- A receiver thread that is the only socket reader.
- A dispatcher thread that submits `NEW` jobs with `POST` and polls active jobs
  with `GET`.
- `run_job()` that creates a job record and blocks by polling the client job
  database until the result is ready.
- `event_queue`, currently used by NFCLI shell progress rendering.

This refactor removes `event_queue` from the client-side event path. Job events
should be delivered to futures instead.

### Current Worker Behavior

`norfab/core/worker.py` has:

- Worker-side SQLite job storage.
- A running-job registry.
- A per-job `client_input_queue`.
- `Job.wait_client_input()`.
- `_put(...)`, which receives `NFP.PUT` payloads and places decoded JSON into
  the running job input queue.
- `_event(...)`, which sends `NFP.EVENT` payloads to the original client.
- `_get(...)`, which can return status `102` for `WAITING_CLIENT_INPUT`,
  although current code does not appear to set that status yet.

### Current Broker and Protocol Behavior

`norfab/core/broker.py` is a thin `ROUTER` mediator:

- It routes client commands to selected workers.
- It routes worker `RESPONSE`, `EVENT`, and `STREAM` messages back to clients.
- It does not persist job state, event state, or prompt ownership.

`norfab/core/NFP.py` already defines `PUT`, `EVENT`, `STREAM`, `POST`, `GET`,
and `RESPONSE`. The file streaming design in
`docs/development/file_streaming_fetch_file.md` already treats `PUT` as a
job-scoped client-to-worker control channel. The changelog for `0.15.0` also
notes that `PUT` can be extended for user input during job execution.

## Goals

- Add a first-class job future object.
- Keep the public API blocking and synchronous.
- Keep `run_job()` working exactly as the stable synchronous API.
- Remove client-side `event_queue`.
- Update NFCLI shells so event/progress rendering uses future event streams.
- Add a required, minimal `event_type` field to event payloads.
- Use existing NFP commands only.
- Keep file streaming behavior unchanged.
- Keep broker changes minimal.
- Avoid adding a new `ClientJobCoordinator` class unless implementation proves
  the existing client internals become too hard to maintain.

## Non-Goals

- No asyncio API in this refactor.
- No full asyncio rewrite of client, broker, or worker loops.
- No new NFP command constants.
- No broker-managed prompt persistence.
- No `Job.confirm()` convenience method.
- No `input_request.kind` field.
- No worker suspension/resume engine. A worker job waiting for user input can
  occupy its job thread until timeout or reply.

## Proposed API

### Future Object

Add an `NFPJobFuture` object created by `NFPClient.submit_job()`.

Recommended shape:

```python
class NFPJobFuture:
    uuid: str
    service: str
    task: str
    workers_requested: str | list[str]

    def result(self, timeout: int | float | None = None, markdown: bool = False) -> Any: ...

    def events(self, timeout: int | float | None = None): ...

    def send_response(
        self,
        input_id: str,
        value: Any = None,
        *,
        worker: str | None = None,
        cancel: bool = False,
        metadata: dict | None = None,
    ) -> None: ...
```

The future is not a local executor job. It is a handle to a remote NorFab job
tracked by UUID, client job database state, and in-memory event queues.

`future.events()` is a blocking iterator. It should yield events for the job
until the job is terminal and all queued events have been consumed. Callers can
then call `future.result()` to retrieve final job results.

### Client Methods

Add:

```python
future = client.submit_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version"]},
    workers="all",
    timeout=600,
)
```

Keep:

```python
result = client.run_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version"]},
    workers="all",
    timeout=600,
)
```

`run_job()` can be internally implemented through `submit_job()` as part of
this refactor, but its external behavior should not change.

## Protocol Usage

No new NFP command should be added for this refactor.

### Job Submission

Client submits jobs exactly as today:

```text
Client -> Broker: NFP.POST
Broker -> Worker: NFP.POST
```

The client-side future is created before or during job DB insertion. It is then
updated by the same receiver and dispatcher paths that update the SQLite job
database.

### Job Result Polling

Client polling remains:

```text
Client -> Broker: NFP.GET
Broker -> Worker: NFP.GET
Worker -> Broker: NFP.RESPONSE
Broker -> Client: NFP.RESPONSE
```

Worker status values remain status-code based:

- `201`: worker accepted/created job.
- `202`: broker dispatched job.
- `300`: worker still processing.
- `102`: worker is waiting for client input.
- `200`: worker returned result.
- `4xx` or `5xx`: failure.

The client should handle `102` as a non-terminal state.

When a worker returns `102`, the response payload should include the current
pending input request if one exists. This is required for client restart
recovery because `NFP.EVENT` messages emitted while a client is offline may not
be delivered to the restarted client.

Example `102` response payload:

```json
{
  "worker": "netbox-worker-1",
  "uuid": "job-uuid",
  "service": "netbox",
  "status": "WAITING_CLIENT_INPUT",
  "input_request": {
    "id": "input-uuid",
    "question": "Apply 12 interface updates?",
    "default": false,
    "required": true,
    "choices": null,
    "metadata": {
      "summary": {
        "create": 4,
        "update": 8,
        "delete": 0
      }
    }
  }
}
```

When the client receives a `102` payload with `input_request`, it should expose
that request to the matching future as an `event_type="input_request"` event
and store it in the client events table.

### Events

Workers continue sending progress and messages with `NFP.EVENT`.

Every event must include `event_type`. Worker-side event creation should set
`event_type="progress"` automatically when the caller does not provide an event
type.

Event types:

- `progress`: normal progress, lifecycle update, status update, or
  user-facing message.
- `input_request`: worker is asking the client for input.
- `input_response`: worker is reporting that input was received, cancelled, or
  timed out.

Existing event fields remain part of the contract:

- `event_type`
- `message`
- `severity`
- `status`
- `resource`
- `timestamp`
- `task`
- `extras`
- `timeout`

Clients should treat an event without `event_type` as malformed. Worker-side
event creation is responsible for setting it automatically.

### Input Request Event

An input request is an ordinary `NFP.EVENT` with `event_type="input_request"`
and structured data under `extras.input_request`.

Example event payload:

```json
{
  "event_type": "input_request",
  "uuid": "job-uuid",
  "worker": "netbox-worker-1",
  "service": "netbox",
  "task": "sync_device_interfaces",
  "message": "Apply 12 interface updates?",
  "severity": "INFO",
  "status": "waiting_client_input",
  "resource": [],
  "timeout": 120,
  "extras": {
    "input_request": {
      "id": "input-uuid",
      "question": "Apply 12 interface updates?",
      "default": false,
      "required": true,
      "choices": null,
      "metadata": {
        "summary": {
          "create": 4,
          "update": 8,
          "delete": 0
        }
      }
    }
  }
}
```

The client detects an input request by checking:

```python
event.get("event_type") == "input_request"
```

and then reading:

```python
input_request = event.get("extras", {}).get("input_request")
```

### Input Reply

The client replies using `NFP.PUT`, as file streaming already does for chunk
offset requests.

Input reply payload:

```json
{
  "input_id": "input-uuid",
  "value": true,
  "cancel": false,
  "metadata": {}
}
```

File streaming remains unchanged and continues using payloads such as:

```json
{
  "offset": 256000
}
```

Worker `_put(...)` can continue placing decoded `PUT` payloads into the running
job's `client_input_queue`. `Job.request_input()` validates the `input_id` and
ignores unrelated messages.

## Worker API

Add `Job.request_input(...)`.

```python
answer = job.request_input(
    question="Apply changes?",
    default=False,
    timeout=120,
    metadata={"summary": summary},
)
```

Expected flow:

1. Generate `input_id`.
2. Set worker DB job status to `WAITING_CLIENT_INPUT`.
3. Persist the pending input request in worker-side job state or events.
4. Emit `NFP.EVENT` with `event_type="input_request"`.
5. Wait on `Job.wait_client_input(timeout=...)`.
6. Validate matching `input_id`.
7. Clear the pending input request and restore worker DB job status to
   `STARTED`.
8. Emit `NFP.EVENT` with `event_type="input_response"` and `status` set to
   `received`, `cancelled`, or `timeout`.
9. Return the reply value, return default, or raise timeout/cancel according to
   helper policy.

Recommended timeout behavior:

- Default behavior should raise a clear timeout exception.
- Default-on-timeout behavior should only be added if it is explicitly needed
  by the first interactive tasks.

## Client Internals

Avoid adding a separate `ClientJobCoordinator` in this refactor. The existing
client internals can handle the new behavior with focused additions.

Required client changes:

- Add `self.job_futures: dict[str, NFPJobFuture]` to `NFPClient`.
- Add `submit_job(...)` to create the job DB record and register a future.
- Remove `self.event_queue` and stop exposing raw event queue consumption as
  the NFCLI progress mechanism.
- Extend `handle_event(...)`:
  - Store the event in SQLite as today.
  - Notify the matching future.
- Extend `handle_response(...)`:
  - Update the job DB as today.
  - Notify the matching future of status/result changes.
  - Treat status `102` as a non-terminal waiting-for-input state.
  - If a `102` response contains `input_request`, synthesize and store an
    `event_type="input_request"` event for the matching future.
- Extend stale-job handling in `poll_active_jobs(...)` to notify the matching
  future.
- Implement `NFPJobFuture.send_response(...)` by calling the owning client
  `send_to_broker(NFP.PUT, ...)`.

This keeps the refactor close to the current code shape and avoids introducing
an abstraction before it is clearly needed.

### Client Restart Recovery

Client restart recovery should use the existing client job database and worker
job persistence.

Assumptions:

- Client job records survive process restart in `ClientJobDatabase`.
- Worker job records survive while the job is still pending, running, waiting
  for input, or completed within the worker retention window.
- Broker remains stateless. It does not persist offline client events.

Recovery behavior:

- On client startup, scan the client job database for non-terminal jobs
  (`NEW`, `SUBMITTING`, `DISPATCHED`, `STARTED`) that have not exceeded their
  deadline.
- Recreate in-memory futures for those jobs in `self.job_futures`.
- Let the existing dispatcher continue polling those jobs with `NFP.GET`.
- If a worker is waiting for input, its `GET` response returns `102` with the
  pending `input_request`.
- Client `handle_response(...)` turns that `102.input_request` payload into an
  `event_type="input_request"` event for the recovered future.
- NFCLI event rendering, now based on `future.events()`, prompts the user and
  sends the answer with `future.send_response(...)`.

Worker-side routing note:

- A restarted client reconnects with the same ZeroMQ identity, so the original
  `Job.client_address` remains valid for routing follow-up `input_response`,
  `progress`, and completion events.
- No worker-side client address refresh is required for the normal restart
  recovery path.

Lost event behavior:

- Progress events emitted while the client was offline may be unavailable to
  the restarted client unless they are retrieved from worker/client databases.
- Pending input requests must not rely only on event delivery. They must be
  recoverable through `GET` status `102`.

## Broker Changes

Broker changes should be minimal.

Required:

- None for the happy path if `NFP.PUT` already routes correctly.

Recommended hardening:

- Improve logging for `PUT` dispatch failures.
- Return a clear client error when a `PUT` target cannot be routed, if this can
  be done without changing the protocol.
- Document that `PUT` is a job-scoped control command used by both file
  streaming and interactive input.

Do not add broker prompt persistence in this refactor.

## NFCLI Usage

Simple NFCLI commands that do not consume job events can keep using `run_job()`:

```python
result = NFCLIENT.run_job(
    service="nornir",
    task="cli",
    kwargs={"commands": commands, "progress": progress},
    workers=workers,
    timeout=timeout,
)
```

All NFCLI command paths that display progress/events should move to
`submit_job()` and consume the future event stream. The shared client
`event_queue` and requeue behavior should be removed.

Synchronous shell style:

```python
future = NFCLIENT.submit_job(
    service="netbox",
    task="sync_device_interfaces",
    kwargs={"dry_run": False, "progress": progress},
    workers=workers,
    timeout=timeout,
)

for event in future.events():
    if event.get("event_type") == "input_request":
        input_request = event.get("extras", {}).get("input_request", {})
        answer = ask_user_in_shell(input_request)
        future.send_response(
            input_request["id"],
            answer,
            worker=event.get("worker"),
        )
    else:
        print_progress_event(event)

result = future.result()
```

The existing `listen_events_thread()` should be removed or rewritten as a
future-based helper. It should accept an `NFPJobFuture` and consume
`future.events()` instead of reading `NFCLIENT.event_queue`.

The `@listen_events` decorator and all NFCLI shell modules that rely on it
should be updated to use `submit_job()` and future event consumption for job
event rendering.

## Worker Built-In Client Usage

Workers that internally call other services should keep using the synchronous
client API.

Example:

```python
result = self.client.run_job(
    service="filesharing",
    task="file_details",
    kwargs={"url": url},
    workers="all",
    timeout=timeout,
)
```

This keeps current task implementations stable and avoids changing worker
built-in client behavior.

## Python API Usage

### Existing Blocking API

```python
result = client.run_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version"]},
    workers="all",
    timeout=600,
)
```

### Future API

```python
future = client.submit_job(
    service="nornir",
    task="cli",
    kwargs={"commands": ["show version"]},
    workers="all",
    timeout=600,
)

for event in future.events():
    print(event["message"])
result = future.result()
```

### Interactive Future API

```python
future = client.submit_job(
    service="netbox",
    task="sync_device_interfaces",
    kwargs={"dry_run": False},
    workers="all",
    timeout=600,
)

for event in future.events():
    if event.get("event_type") == "input_request":
        input_request = event.get("extras", {}).get("input_request", {})
        answer = ask_user(input_request)
        future.send_response(
            input_request["id"],
            answer,
            worker=event.get("worker"),
        )

result = future.result()
```

## Implementation Refactoring Plan

### Client Future Core

- Add `NFPJobFuture`.
- Add `NFPClient.submit_job()`.
- Add future registry by UUID.
- Remove client `event_queue`.
- Fan out `EVENT` and `RESPONSE` updates to futures from existing client
  handler functions.
- Keep `run_job()` behavior unchanged.

### Interactive Input

- Add `Job.request_input()`.
- Emit input requests as normal `NFP.EVENT` payloads with
  `event_type="input_request"` and `extras.input_request`.
- Send replies as `NFP.PUT` payloads with `input_id`.
- Handle worker `102 WAITING_CLIENT_INPUT` responses as non-terminal.

### NFCLI Integration

- Keep simple commands without event/progress rendering on `run_job()`.
- Move all NFCLI commands that display job events/progress to `submit_job()`.
- Remove shared-queue requeue behavior in `listen_events_thread()` and replace
  it with future event consumption.
- Update all NFCLI shell modules using `@listen_events` or raw
  `NFCLIENT.event_queue` access.

### Tests and Documentation

- Test existing `run_job()` callers.
- Test future result waiting.
- Test sync event consumption.
- Test required `event_type` handling.
- Test input request, input reply, cancel, timeout, and multi-worker prompts.
- Test file streaming to ensure existing `PUT` offset behavior is unchanged.

## Compatibility

- Existing `run_job()` callers continue working.
- Existing worker tasks continue working.
- Existing worker built-in clients continue using `run_job()`.
- Existing event payload fields remain valid, with `event_type` added as a
  required field.
- Existing file streaming remains unchanged.
- No new NFP commands are introduced.

## Risks

### Prompt Reply Routing

For `workers="all"`, more than one worker can ask for input. The client should
reply to the worker that emitted the request. `future.send_response(...)` should
require `worker` when more than one active input request exists.

### Worker Thread Occupancy

Waiting for client input occupies a worker job thread. Use timeouts and keep
interactive prompts short.

### NFCLI Event Migration

Removing `event_queue` means all NFCLI progress/event rendering must be routed
through futures. The migration should update every NFCLI shell path using
`listen_events_thread()`, `@listen_events`, or raw `NFCLIENT.event_queue`
access.

### Future Registry Cleanup

Completed futures should be removed from `client.job_futures` after final
event consumption is complete. A small retention window can help debugging,
but unbounded retention should be avoided.

## Open Questions

- Should `submit_job()` be the only new public method, or should
  `run_job(future=True)` also be added as convenience?
- Should `Job.request_input()` return the default on timeout only when
  explicitly configured, or always raise on timeout?
- Should broker return an explicit error response for failed `PUT` dispatch, or
  is logging enough for this refactor?
