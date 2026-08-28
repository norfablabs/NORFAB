# ADR - Delayed and Periodic NorFab Jobs

## Status

Proposed.

## Date

2026-08-28.

## Decision

Extend the existing client-side job architecture with two distinct concepts:

1. A **delayed job** is one concrete job with a future `scheduled_for` time.
2. A **periodic schedule** is a durable definition that creates a new concrete
   job for each due occurrence.

Delayed jobs remain in the existing `jobs` table. Periodic definitions use a
new `job_schedules` table. Every execution has its own unique job UUID and
follows the current NorFab lifecycle through the broker and workers.

The client dispatcher processes due times before dispatching `NEW` jobs. No
change is required in the broker, NFP framing, or worker execution model.

## Why Separate Schedules from Jobs

A job is an execution record. It has one UUID, one set of arguments, one
result, and one terminal outcome. A periodic schedule is not an execution. It
is a rule that can produce many jobs over time.

Storing both concepts in one row creates ambiguity:

- updating a recurring rule could rewrite job history;
- one UUID would refer to multiple executions;
- results from different runs would collide;
- cancellation could mean either one occurrence or the entire series; and
- missed-run and overlap policies would have nowhere clear to live.

The established industry pattern is to keep the recurring definition separate
and let it materialize execution jobs:

| System | Recurring definition | Execution |
| --- | --- | --- |
| APScheduler | Schedule plus trigger | Job |
| Quartz | Job detail plus trigger | Fired job instance |
| Celery Beat | Periodic schedule entry | Enqueued task |
| Kubernetes | CronJob | Job |
| NorFab | `job_schedules` row | `jobs` row |

This ADR adopts that pattern without introducing another task queue or
execution framework.

## Goals

- Run a normal NorFab job once at or after a requested future time.
- Run a normal NorFab job repeatedly from a persistent interval definition.
- Preserve a unique UUID, result, events, and lifecycle for every execution.
- Recover delayed jobs and periodic definitions after client restart.
- Define explicit missed-run and overlap behavior.
- Keep immediate `run_job()` behavior backward compatible.
- Reuse the current SQLite database, dispatcher, futures, broker routing, and
  worker execution path.
- Leave room for cron triggers without requiring them initially.

## Non-Goals

- A cluster-wide scheduler shared by unrelated clients.
- Leader election between processes using different client databases.
- Workflow dependencies or directed acyclic graphs.
- Distributed locks across multiple NorFab installations.
- Calendar exclusions, holidays, or solar schedules in the first iteration.
- Cancelling a job after it has been dispatched to a worker.
- Exactly-once execution across process, operating-system, or network failure.

## Existing Architecture

`NFPClient` already provides most of the required machinery:

- `ClientJobDatabase` persists jobs and events in SQLite;
- `submit_job()` creates a job and an `NFPJobFuture`;
- the dispatcher sends `NEW` jobs and polls active jobs;
- job deadlines and terminal states are persisted; and
- `recover_job_futures()` restores active jobs after client restart.

Scheduling should extend these components instead of adding a second queue.

## Job and Schedule Model

### Immediate and delayed jobs

Add `SCHEDULED`, `CANCELLED`, and `MISSED` to `JobStatus`.
`CANCELLED` and `MISSED` are terminal.

```text
Immediate:
  NEW -> SUBMITTING -> DISPATCHED -> STARTED -> COMPLETED/FAILED/STALE

Delayed:
  SCHEDULED -> NEW -> SUBMITTING -> DISPATCHED -> STARTED
            -> COMPLETED/FAILED/STALE

Not executed:
  SCHEDULED -> CANCELLED
  SCHEDULED -> MISSED
```

Add these nullable columns to the existing `jobs` table:

| Column | Purpose |
| --- | --- |
| `scheduled_for` | UTC epoch time assigned to the occurrence |
| `start_deadline` | Latest time at which execution may start |
| `schedule_id` | Parent periodic schedule UUID; null for direct jobs |

The job UUID remains the only identity of an execution. `schedule_id` is a
foreign-key relationship and provenance field, not an alternative job key.
Deleting a schedule must not delete its historical jobs; use `ON DELETE SET
NULL` or retain the schedule as disabled.

Add indexes for:

- `(status, scheduled_for)` to release delayed jobs efficiently;
- `(schedule_id, status)` for overlap checks and schedule history; and
- a unique `(schedule_id, scheduled_for)` constraint when `schedule_id` is not
  null, preventing the same occurrence from being materialized twice.

Do not start the existing completion `deadline` while a job is waiting in
`SCHEDULED`. When the dispatcher releases it to `NEW`, set `deadline` to the
release time plus `timeout`. `start_deadline` independently decides whether a
late job may be released at all. This separation follows the common distinction
between a missed start and an execution timeout.

### Periodic schedule definitions

Add a `job_schedules` table. One row describes a recurring rule and the NorFab
job template used for every occurrence.

| Column | Purpose |
| --- | --- |
| `uuid` | Unique schedule UUID |
| `name` | Optional human-readable name, unique within one client |
| `service` | Target NorFab service |
| `task` | Target task name |
| `args`, `kwargs` | Compressed job-template arguments |
| `workers` | Requested worker selector |
| `timeout` | Timeout copied to each generated job |
| `trigger_type` | Initially `interval`; later `cron` |
| `trigger_config` | Validated trigger-specific JSON |
| `timezone` | IANA timezone, default `UTC` |
| `start_at`, `end_at` | Optional schedule bounds |
| `next_run_at` | Next UTC occurrence maintained by the dispatcher |
| `last_run_at` | Last occurrence materialized |
| `state` | `ACTIVE`, `PAUSED`, `COMPLETED`, or `DISABLED` |
| `coalesce` | Missed-occurrence policy: `latest`, `earliest`, or `all` |
| `misfire_grace_seconds` | Maximum permitted start delay |
| `overlap_policy` | `ALLOW` or `FORBID` |
| `max_instances` | Maximum active jobs generated by this schedule |
| `jitter_seconds` | Maximum random delay added per occurrence |
| `created_at`, `updated_at` | Audit timestamps |

`trigger_config` keeps the first schema small while permitting new trigger
types. The dispatcher queries only indexed `next_run_at`; it does not need to
query inside the trigger JSON.

For an interval trigger, validate a structure such as:

```json
{
  "seconds": 300,
  "mode": "fixed_rate"
}
```

The first implementation supports positive whole-second intervals. Cron can
be added later with an explicit parser dependency and documented daylight
saving behavior.

### Schedule UUID versus job UUID

A schedule and a job are different records and therefore have different UUIDs.
For example:

```text
schedule UUID:  7ad2...       # "run backup every hour"
job UUID:       a103...       # 09:00 occurrence
job UUID:       b49f...       # 10:00 occurrence
job UUID:       f9c1...       # 11:00 occurrence
```

The schedule UUID groups and controls the series. Each job UUID independently
identifies one dispatch, result, and event stream.

## Public Client API

### Delayed execution

Keep `run_job()` immediate. Add an explicit non-blocking method:

```python
future = client.schedule_job(
    service="nornir",
    task="cli",
    workers=["nornir-worker-1"],
    kwargs={"commands": ["show clock"]},
    scheduled_for=run_at,
    misfire_grace_seconds=300,
    timeout=600,
)
```

`scheduled_for` accepts a timezone-aware `datetime` or a UTC epoch value.
Reject naive datetimes. The method persists the job and returns its
`NFPJobFuture` immediately. A null `misfire_grace_seconds` permits release
after any delay; otherwise it sets `start_deadline`.

Add:

- `cancel_scheduled_job(uuid)`;
- `reschedule_job(uuid, scheduled_for)`; and
- scheduled fields to existing job inspection filters and results.

Cancellation and rescheduling succeed only while status is `SCHEDULED`.

### Periodic execution

Add a separate schedule API:

```python
schedule = client.create_job_schedule(
    name="collect-clock",
    service="nornir",
    task="cli",
    workers=["nornir-worker-1"],
    kwargs={"commands": ["show clock"]},
    trigger={"type": "interval", "seconds": 300},
    coalesce="latest",
    overlap_policy="FORBID",
    max_instances=1,
    misfire_grace_seconds=60,
    timeout=600,
)
```

Add management methods:

- `list_job_schedules()` and `get_job_schedule(uuid)`;
- `pause_job_schedule(uuid)` and `resume_job_schedule(uuid)`;
- `update_job_schedule(uuid, ...)`;
- `delete_job_schedule(uuid)`; and
- `run_job_schedule_now(uuid)`.

Updating a schedule affects future occurrences only. Pausing or deleting it
does not cancel a job that has already become `NEW` or been dispatched.
Historical execution jobs remain queryable.

## Dispatcher Behavior

### Release delayed one-shot jobs

At the start of each dispatcher cycle:

1. Select `SCHEDULED` jobs where `scheduled_for <= now`.
2. Mark a job `MISSED` when `start_deadline` has passed.
3. Otherwise set `deadline = now + timeout` and change it to `NEW`.
4. Let the existing `dispatch_new_jobs()` code submit it normally.

Selection and status update occur in one SQLite write transaction.

### Materialize periodic occurrences

In the same dispatcher cycle, process active schedule rows where
`next_run_at <= now`:

1. Acquire the due schedule inside the SQLite write transaction.
2. Calculate due occurrence times from `next_run_at` through the current time.
3. Apply the schedule's coalescing policy.
4. Apply `misfire_grace_seconds` and count discarded occurrences as missed.
5. Check active jobs for the schedule and apply `overlap_policy` and
   `max_instances`.
6. Create a new `jobs` row with a fresh UUID for each accepted occurrence.
7. Copy the schedule UUID into `jobs.schedule_id` and the occurrence time into
   `jobs.scheduled_for`.
8. Advance `last_run_at` and `next_run_at` in the same transaction.
9. Commit, then dispatch the generated `NEW` jobs normally.

The unique `(schedule_id, scheduled_for)` index makes materialization
idempotent if the dispatcher retries after an interrupted transaction.

### Coalescing and missed starts

When several occurrences became due while the client was offline:

| Policy | Behavior |
| --- | --- |
| `latest` | Create one job for the most recent due occurrence |
| `earliest` | Create one job for the oldest due occurrence |
| `all` | Create one job per due occurrence, subject to a safety limit |

Default to `latest`. Limit `all` catch-up to 100 jobs per dispatcher pass and
make the limit configurable. This avoids an unbounded backlog after a long
outage.

`misfire_grace_seconds` produces a `start_deadline` for every generated job.
An occurrence that is already beyond that deadline is recorded as missed and
is not sent to the broker.

### Overlap policy

Before creating an occurrence, count non-terminal jobs with the same
`schedule_id`.

- `ALLOW` permits creation up to `max_instances`.
- `FORBID` skips the occurrence when any earlier job from the schedule is
  active.

Default to `FORBID` and `max_instances=1`. A skipped overlap updates schedule
status/counters and does not cancel the running job.

NorFab cannot promise exactly-once external effects. A worker can complete an
external action and fail before its result is recorded. Scheduled tasks must
therefore be idempotent where practical.

## Recovery and Ownership

`recover_job_futures()` includes `SCHEDULED` jobs. Periodic definitions need no
future until they materialize an execution job.

The dispatcher recalculates due schedules from persisted `next_run_at` after
restart. The coalescing and misfire policies determine what happens to elapsed
occurrences.

Schedules belong to the client database that created them. They run only while
that client, or another process using the same inventory base and client name,
is active. The first implementation assumes one active process owns a client
database. Multi-process schedule acquisition leases are deferred.

Use UTC internally. Convert an input timezone only when calculating trigger
occurrences and return both UTC timestamps and the configured timezone in
inspection output.

## Database Migration

Client database initialization must perform additive, versioned migrations:

1. Add missing job columns.
2. Create `job_schedules` and its indexes.
3. Record the schema version only after the migration transaction succeeds.

Existing jobs have null scheduling fields and retain their current behavior.
No migration may delete job or event history.

## Observability

Job inspection includes `scheduled_for`, `start_deadline`, and `schedule_id`.
Schedule inspection includes:

- current state and next run;
- last materialized occurrence;
- active job count;
- total runs, failures, missed starts, and overlap skips; and
- sanitized last error.

Use the existing events table for events tied to an execution job. Store
schedule-level counters and the last schedule-processing outcome on the
`job_schedules` row. A separate schedule-events table is unnecessary in the
first implementation.

Logging calls start with uppercase letters. Job event messages continue to
start with lowercase letters, following repository conventions.

## Security and Validation

- Apply the same service, task, kwargs, worker, and timeout validation used for
  immediate jobs.
- Reject schedules targeting unknown or forbidden tasks when that information
  is available.
- Enforce positive intervals, bounded jitter, bounded catch-up, and reasonable
  future dates.
- Do not persist credentials outside the existing protected job arguments.
- Treat schedule create, update, pause, resume, delete, and run-now operations
  as mutating APIs.
- A caller who can create a schedule must already be authorized to submit the
  underlying job.

## Implementation Sequence

### Phase 1 - Delayed jobs

- Add schema versioning and additive migration helpers.
- Add scheduling fields and statuses to jobs.
- Implement `schedule_job()`, cancellation, and rescheduling.
- Atomically release due jobs from the existing dispatcher.
- Extend recovery, inspection, and tests.

### Phase 2 - Interval schedules

- Add `job_schedules` and interval trigger validation.
- Implement schedule CRUD, pause/resume, and run-now.
- Materialize occurrences with unique job UUIDs.
- Add coalescing, misfire, overlap, and catch-up limits.
- Add schedule status and counters.

### Phase 3 - Additional triggers

- Add cron only after selecting a maintained parser and defining timezone and
  daylight-saving behavior.
- Consider one-time date triggers only if they offer value beyond
  `schedule_job()`.
- Consider database acquisition leases only if multiple processes must share
  one schedule store.

## Testing Strategy

### Delayed jobs

- A job produces no NFP traffic before `scheduled_for`.
- A due job is released once and follows the normal lifecycle.
- Completion deadline calculation starts when the due job is released, while
  `start_deadline` independently controls lateness.
- Cancellation and rescheduling are transaction-safe.
- Naive datetimes and invalid times are rejected.
- Restart recovery releases one overdue job without duplication.

### Periodic schedules

- Every occurrence receives a unique job UUID and parent `schedule_id`.
- The `(schedule_id, scheduled_for)` constraint prevents duplicate occurrence
  materialization.
- Pause, resume, update, delete, and run-now have documented history behavior.
- `latest`, `earliest`, and bounded `all` coalescing behave deterministically.
- Misfire grace marks late occurrences without dispatch.
- `ALLOW`, `FORBID`, and `max_instances` control overlap.
- Interval calculations remain correct across restart and clock changes.
- Disabled and completed schedules create no jobs.

### Compatibility

- Existing databases migrate without data loss.
- Immediate `run_job()` and `submit_job()` behavior remains unchanged.
- Broker, NFP, worker, and existing service tests pass unchanged.
- Python 3.10-3.14 and Windows, Linux, and macOS timestamp behavior is covered.

## Alternatives Considered

### Store repeating jobs only in `jobs`

Rejected. One row cannot cleanly represent both a mutable recurrence rule and
multiple immutable execution histories.

### Make each periodic task schedule its successor

Rejected as the generic periodic mechanism. The chain breaks when a task is
never dispatched or the process stops before creating its successor. It also
makes recurrence behavior inconsistent across services.

### Add APScheduler

Viable, but not selected initially. APScheduler uses the same sound separation
between schedules and jobs and provides mature trigger calculations. NorFab
already owns persistent jobs and dispatch, so adopting the data model is
smaller than adding a second scheduler runtime. APScheduler or one of its
trigger implementations can be reconsidered for cron and complex calendars.

### Use Tornado `PeriodicCallback`

Rejected for persistent scheduling. It is an in-memory timer, not a durable
schedule definition or execution history.

### Use Celery Beat

Rejected because it introduces another broker, producer, and task lifecycle
beside NorFab.

## Consequences

Benefits:

- Delayed and periodic work use the existing NorFab job lifecycle.
- Schedule definitions remain small while every execution keeps independent
  results and events.
- Restart, missed-run, and overlap behavior is explicit.
- No broker, NFP, or worker execution change is required.
- The schema can support cron later without redesigning job history.

Costs and constraints:

- The client database and dispatcher gain migration and schedule-processing
  responsibilities.
- Schedule ownership remains local to one named client database.
- Exactly-once external effects are not guaranteed.
- Cron and distributed ownership require further design.
- Periodic history increases the jobs table and relies on existing retention
  or cleanup policy.

## Acceptance Criteria

- One delayed job uses one unique UUID and cannot dispatch before its due time.
- One periodic definition uses one schedule UUID and creates a new unique job
  UUID for every accepted occurrence.
- Periodic definitions are stored separately from execution jobs.
- Due processing, occurrence insertion, and `next_run_at` advancement are
  transaction-safe.
- Immediate jobs remain backward compatible.
- Restart recovery applies explicit coalescing and misfire policies.
- Overlap behavior is deterministic and defaults to one active instance.
- Job history survives schedule update, pause, disable, or deletion.
- No broker, NFP, or worker change is required.

## References

- [APScheduler concepts and schedule processing](https://apscheduler.readthedocs.io/en/master/userguide.html)
- [APScheduler schedule data structure](https://apscheduler.readthedocs.io/en/master/api.html#apscheduler.Schedule)
- [Quartz jobs and triggers](https://www.quartz-scheduler.net/documentation/quartz-4.x/tutorial/jobs-and-triggers.html)
- [Quartz database schema](https://www.quartz-scheduler.net/documentation/quartz-4.x/db/)
- [Celery periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html)
- [Kubernetes CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)

## Approval Boundary

This ADR defines architecture only. It does not implement database migrations,
scheduled jobs, periodic schedules, client APIs, or external job execution.
