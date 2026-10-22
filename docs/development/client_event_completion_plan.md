# Client completion events and socket wake-up plan

Status: Part 1 implemented on 22 October 2026; core and FileSharing validation passed.
Part 2 implemented on 22 October 2026; Windows socket wake-up validation passed.

## Objective

Use a worker completion event to trigger retrieval of that worker's saved result.
Remove frequent GET requests from normal job execution. Separately replace the
client's 100 ms socket polling timeout with an explicit wake-up channel.

Keep public client methods, worker task interfaces, result formats, SQLite job
storage, and the existing broker protocol commands unchanged. Keep the dispatcher
and ZeroMQ owner threads; do not introduce asyncio or another worker thread.

## Original behavior and findings

- `submit_job()` writes the job, creates its future, and wakes the dispatcher.
- `dispatch_new_jobs()` queues POST. Only `zmq_send_recv()` sends and receives
  messages on the broker socket.
- `poll_active_jobs()` queues GET every 0.5 seconds for active jobs. Its comments
  incorrectly describe a five-second interval.
- `run_next_job()` saves results before emitting its final completion event,
  including when task execution raises an exception.
- `handle_event()` stores and exposes events but does not request results.
- Worker `_get()` already returns saved results for completed and failed jobs.
- `handle_response()` merges results by worker and completes the future after
  every originally dispatched worker has returned a result.
- The broker acknowledges both POST and GET with status 202. The client currently
  replaces `workers_dispatched` on every 202. A targeted GET would therefore
  incorrectly shrink a multi-worker job's expected worker set.
- Local queue insertion does not wake the ZeroMQ poller. The socket thread drains
  outgoing messages before polling, with a limit of 100 messages per iteration.
- Timeout checks currently share the throttled GET scan. They must be separated
  before increasing the recovery interval.
- Outbound messages can be dropped when queues are full. Events alone do not
  guarantee result delivery; retain occasional recovery GET requests.

## Part 1: event-triggered result retrieval

1. **Mark the worker's final event.** In `run_next_job()`, add
   `event_type="result_ready"` to the existing final completion event, after
   database persistence. Keep its existing completed status. Ordinary task
   progress events must not trigger retrieval merely because they say completed.
   The event sender already includes the worker name, service, and job UUID.

2. **Preserve the original dispatch list.** In the 202 response branch, set
   `workers_dispatched` only when the job has not yet received its original
   dispatch acknowledgement. Subsequent GET acknowledgements must not change it,
   reset its start time, or regress its status. Likewise, late 201 replies must
   not undo partial result collection or an active input request. The broker
   queues its POST acknowledgement before forwarding POST to workers.

3. **Queue a targeted GET from `handle_event()`.** Preserve normal event storage
   and delivery to the future. For a marked event, load the job and verify that
   it is active, the worker belongs to the original dispatch list, and its result
   has not already been collected. Queue GET for the existing UUID and that one
   worker using `send_to_broker()`. Never call blocking `run_job()` here. Use the
   existing task, args, and kwargs request shape.

4. **Reuse result merging.** Keep the 200 response path and `future.mark_done()`.
   A completion event indicates that a result can be fetched; it does not itself
   finish the future. Returned task failures still count as returned worker
   results. Late responses must not reopen terminal jobs. Duplicate notifications
   before a GET returns may cause an extra GET; do not add an in-flight registry
   unless testing demonstrates a need.

5. **Separate deadlines from recovery GET timing.** Continue inspecting active
   jobs on dispatcher cycles, expiring overdue jobs through `expire_job()`.
   Apply the GET throttle only after checking deadlines. Do not first filter
   overdue jobs out through `min_poll_age`. Keep the existing batch limit and
   verify that batches do not starve later jobs.

6. **Make GET polling a recovery path.** Increase the existing `poll_interval`
   from 0.5 to 10 seconds. Query only dispatched workers without saved results;
   never send an empty target list. Completion events bypass this interval.
   Review timestamp handling so repeated events from one worker do not postpone
   recovery indefinitely for another. No new public configuration is required.

7. **Recover interrupted clients without repeating execution.** For restored
   dispatched/started jobs, make the first recovery GET immediately eligible.
   Use the original dispatched worker list. For already expired restored jobs,
   use `expire_job()` to preserve partial results and create missing-worker timeout
   results. Existing ambiguous SUBMITTING recovery can resubmit POST; do not
   claim exactly-once execution or expand this change into submission deduplication.

8. **Keep interactive jobs working.** Input requests already arrive as events.
   Update the client job status from actual input-request/response events when
   appropriate, without reopening terminal jobs. Keep GET's 102 handling for
   recovery, including input-ID deduplication. Test this with multiple workers.

### Implementation scope and separate review

Part 1 keeps the existing dispatcher, socket thread, event delivery, response
merging, and database schema. Deadline selection is an inline bounded query;
no helper functions were added. Futures keep outstanding input IDs by worker so
one worker's response cannot clear another worker's input-waiting status.

Part 2 adds a nonblocking native socket pair to the existing poller. Queue
insertion and shutdown signal it; outgoing batches remain bounded. The dispatcher
also signals it on external exit. Both threads stop before sockets are closed.
No helper functions or additional threads were added.

## Part 2: remove the client socket's 100 ms wait

Implement separately, after Part 1 passes its integration checks.

1. Create a Python `socket.socketpair()` notification channel during client
   initialization, before starting either thread. Make both ends nonblocking and
   register the receiving end with the existing ZeroMQ poller. Verify native
   socket polling on Windows and Linux before adopting this mechanism.
2. After successfully placing an outgoing message in `outbound_queue`, write a
   notification byte. A full notification buffer already represents a pending
   wake-up; do not block producers or drop the queued message for this reason.
   Multiple callers can signal the native socket; do not share a ZeroMQ sending
   socket between threads.
3. In `zmq_send_recv()`, distinguish notification readiness from broker readiness.
   Drain notification bytes, then service the outgoing queue. Handle broker data
   only when the broker socket is readable.
4. Preserve bounded outgoing batches so incoming messages are not starved. If
   queued messages remain after a batch, poll with timeout zero and continue
   draining; never enter an indefinite wait with outgoing work already queued.
   Otherwise block until broker traffic or a notification arrives.
5. A completion event already wakes this thread. Its targeted GET enters the
   existing queue and is sent on the next iteration without a timed wait.
6. Wake both the dispatcher and socket loop during `destroy()`, then join threads
   before closing notification sockets or destroying the ZeroMQ context. Account
   for a shared external exit event: the dispatcher must notify the socket loop
   when it exits, even if nobody calls `client.destroy()` immediately.
7. Leave the shared 100 ms NFP constant in place for the worker's socket loop.
   This change removes its use in the client only. Worker wake-up is separate work.

## Validation

Follow `docs/testing/norfab_testing_framework.md`. Extend existing tests in
`tests/core/test_client.py` and existing dummy-service task fixtures only where
needed. Use real broker and worker processes, without mocking network handling.

- With recovery GET disabled by a long interval, a normal task and a task that
  raises both finish through the completion-event path. Set the existing recovery
  timestamp so this check cannot pass through an initial recovery GET.
- A multi-worker job retrieves each result from its notifying worker, retains
  its full original dispatch list, and completes only after the last result.
- An ordinary task progress event marked completed does not trigger retrieval.
- Duplicate completion events and late acknowledgements leave results intact.
- A real stored result without its final notification is recovered by GET. Use
  a narrowly scoped test task/worker fixture to suppress only that notification;
  do not mock the client transport.
- A client disconnected during completion recovers the saved result on restart,
  using its existing routing identity and database. Verify those prerequisites
  explicitly in the test.
- Overdue asynchronous jobs become stale independently of the recovery interval;
  existing partial results survive. Include more jobs than the dispatch batch size.
- Interactive input, cancellation, and input timeouts still work through events
  and recovery responses.
- Existing FileSharing tests pass, including empty files, streamed files,
  interrupted streams, and alternating workers.
- For Part 2, test an idle send, simultaneous producers, bursts larger than the
  drain limit, incoming broker traffic, external exit, and repeated shutdown.
  Use structural assertions and generous bounded waits rather than sub-100 ms
  timing assertions in CI. Measure latency separately for comparison.

Run focused integration suites first, then the core and FileSharing suites.
Run formatting and lint checks for touched files. Validate socket wake-up on
both Windows and Linux; report any platform not exercised.

### Validation results: 22 October 2026

Local Windows / Python 3.13, following the testing framework:

- `poetry run pytest core -q -k 'not load_inventory_from_dictionary'`:
  152 passed, 1 skipped, 1 deselected.
- `poetry run pytest services/filesharing -q`: 71 passed, using both FileSharing workers.
- Black checks and `git diff --check` passed. Ruff reported no new findings
  compared with HEAD; existing annotation findings remain.

The full core attempt stalled in the dictionary-inventory fixture, whose workers
repeatedly reported broker keepalive expiry at port 7777. That test was excluded
from the completed core run. Linux was not exercised in this initial Part 1 run.

### Part 2 validation results: 22 October 2026

Local Windows / Python 3.13:

- Native `socket.socketpair()` readiness was verified with the ZeroMQ poller.
- `poetry run pytest core services/filesharing -q -k 'not load_inventory_from_dictionary'`:
  226 passed, 1 skipped, 1 deselected, using both FileSharing workers.
- Checks cover idle sends, multiple producers, more than two outgoing batches,
  incoming broker replies, a full notification buffer, external exit, and repeated shutdown.
- Black, targeted Ruff checks (E/F/I with the repository's E501 exclusion), and
  `git diff --check` passed. Existing annotation findings were not changed.

The previously stalled dictionary-inventory test remains excluded. Linux was
not exercised because the Docker Linux engine was unavailable. The worker's
100 ms socket polling constant is unchanged. Periodic job polling remains 10 seconds.

## Documentation and scope

Update the interactive-client ADR, file-streaming developer guide, feature
catalogue, and latest changelog to describe event-triggered GET with recovery.
Keep documentation explicit that 10-second periodic polling remains. Update
comments and docstrings when changing their behavior.

Expected runtime files: `norfab/core/client.py` and `norfab/core/worker.py`.
No broker changes, database migration, new protocol command, public option,
additional thread, asyncio conversion, or delivery-acknowledgement subsystem.

Part 1 removes repeated status GETs from normal execution. Part 2 removes the
socket thread's periodic 100 ms wake-ups. The dispatcher's existing local database
scan and deadline checks remain; this is not a claim of a completely timer-free
client.
