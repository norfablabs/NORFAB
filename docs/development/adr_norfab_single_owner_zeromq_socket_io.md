# ADR - Single-Owner ZeroMQ Socket I/O

## Status

Accepted.

Date: 2026-08-27.

Implemented in 0.21.2.

## Problem

NorFab currently shares the same ZeroMQ socket between multiple Python threads:

- client `recv()` polls and receives, while `send_to_broker()` sends from API
  and dispatcher threads;
- worker `recv()` polls and receives, while job, result, event, stream, and
  keepalive threads send;
- broker `mediate()` polls and receives, while broker-side keepalive threads
  also send.

This is protected with `socket_lock`, but DEALER and ROUTER sockets are not
thread-safe socket types. PyZMQ also recommends one socket per thread instead
of sharing a socket with `threading.Lock`.

The 0.21.1 keepalive change made this more visible because receive loops now
hold the socket lock while polling for up to 100 ms. Senders can be delayed and
messages can arrive in bursts.

## Decision

Keep the current ZeroMQ topology and NFP protocol, but make each existing
socket owned by exactly one existing loop:

| Component | Socket | Owner |
| --- | --- | --- |
| Client | DEALER | existing `recv()` thread, renamed to `zmq_send_recv` |
| Worker | DEALER | existing `recv()` thread, renamed to `zmq_send_recv` |
| Broker | ROUTER | existing `mediate()` loop |

No extra ZeroMQ sockets are introduced.

`socket_lock` is removed from normal socket access after all send, receive,
poll, reconnect, and close operations are owned by those loops.

## How Sending Works

Public send methods stay in place:

- `NFPClient.send_to_broker(...)`
- `NFPWorker.send_to_broker(...)`
- broker `send_to_client(...)` and `send_to_worker(...)`

For client and worker, public `send_to_broker()` no longer calls
`socket.send_multipart()` directly. It only builds the same NFP multipart frame
and puts it into an outbound `queue.Queue`.

The existing `recv()` thread becomes the only code that drains that queue and
uses the ZeroMQ socket.

Simple shape:

```text
producer thread:
  send_to_broker() builds NFP frame
  send_to_broker() puts frame into outbound queue

zmq_send_recv thread:
  send queued frames
  poll and receive broker messages
  process due keepalives where applicable
```

The outbound queue must be bounded. If the broker is offline for a long time,
clients and workers must not keep accepting outbound messages until memory is
exhausted. `send_to_broker()` returns after the frame is accepted into the
local queue. When the queue is full, it waits up to a small internal timeout
and then reports an error to the caller. Existing caller logic can then retry,
fail the job, or continue polling as it does for send failures today.

When the `zmq_send_recv` thread itself needs to send, it sends directly through
the owned socket instead of calling public `send_to_broker()` and queueing to
itself.
Examples:

- client file-stream PUT credit requests from `handle_stream()`;
- worker READY and DISCONNECT during reconnect;
- broker replies and routed messages.

## Keepalives

`KeepAliver` should stop using a ZeroMQ socket directly.

It becomes passive state:

- when the next keepalive is due;
- when the peer hold time expires;
- sent and received counters;
- `received_heartbeat()`, `is_alive()`, `show_holdtime()`, and
  `show_alive_for()`.

The `zmq_send_recv` thread sends the existing keepalive frames when they are
due.

Keepalive behavior must stay the same:

- same configured interval and multiplier;
- same worker-to-broker and broker-to-worker NFP frames;
- same hold-time calculation;
- same reconnect behavior when keepalives expire;
- READY is still sent before the first worker keepalive after connect or
  reconnect.

## Owner Loop

The `zmq_send_recv` loop should stay small:

```text
while running:
  send a bounded number of queued outbound frames
  send keepalive if due
  poll the socket for inbound messages
  receive and process inbound message if available
  reconnect or stop if required
```

Use a short poll timeout, for example 10 ms. A Python queue cannot wake a
thread blocked in `zmq.Poller.poll()`, and this ADR intentionally does not add
an in-process wake socket.

Do not derive this timeout from the keepalive interval. Jobs, events, stream
chunks, MMI calls, and client input need a much smaller response bound than the
default keepalive interval.

## Component Changes

### Client

- Existing `recv()` is renamed to `zmq_send_recv` and becomes the only owner of
  `broker_socket` and `poller`.
- `send_to_broker()` builds frames and submits them to the outbound queue.
- `dispatcher()` keeps its current job database and polling logic.
- `handle_response()` keeps the current job protocol handling.
- `handle_stream()` must use a direct send path for follow-up PUT chunk
  requests because it runs inside the `zmq_send_recv` thread.
- Shutdown stops new queue submissions before destroying the ZeroMQ context.

### Worker

- Existing `recv()` is renamed to `zmq_send_recv` and becomes the only owner of
  `broker_socket` and `poller`.
- `_post()`, `_get()`, `_event()`, and stream code keep doing their current
  work, but send replies/events through the outbound queue.
- Reconnect runs in the `zmq_send_recv` thread. It sends DISCONNECT when
  possible, replaces the socket, sends READY, and resets keepalive state.
- Existing worker job queues remain unchanged.

### Broker

- Existing `mediate()` remains the only owner of the ROUTER socket and poller.
- `send_to_client()` and `send_to_worker()` become owner-only helpers because
  broker routing already happens inside `mediate()`.
- Broker-side worker records keep routing address and keepalive state, but do
  not send on the ROUTER socket themselves.
- Broker keepalives are sent from `mediate()`, not from one thread per worker.

## What Must Not Change

- No new ZeroMQ sockets.
- No NFP command or frame layout changes.
- No ROUTER/DEALER topology changes.
- No CURVE/authentication changes.
- No client job state machine changes.
- No change to response codes such as 102, 200, 201, 202, 300, 400, 404, or
  500.
- No change to client `poll_interval`.
- No duplicate GET polling changes in this refactor.
- No worker job execution queue redesign.

## Main Risks

- Owner code accidentally calls public `send_to_broker()` and queues to itself.
- The outbound queue is too large or unbounded and consumes memory while the
  broker is offline.
- Shutdown destroys the ZeroMQ context while another thread is trying to enqueue
  a send.
- The 10 ms owner tick increases idle CPU too much on Windows or Linux.

The first implementation should keep this simple:

- keep queued sends during reconnect and drain them after reconnect;
- use a bounded outbound queue and fail sender calls when the queue stays full;
- fail new queue submissions during shutdown;
- keep the 10 ms tick as an internal constant, not inventory;
- add tests for owner-only socket access, keepalive timing, reconnect ordering,
  and normal job result collection.

## Verification

- Code review and focused tests confirm each DEALER/ROUTER socket and poller is
  used by one thread after ownership starts.
- Client and worker producers can submit outbound messages without touching a
  ZeroMQ socket.
- Long-running jobs still complete and return the same result shape.
- FastAPI task calls still receive dictionary results.
- Events, MMI calls, file streaming, and interactive client input still work.
- Keepalive interval, multiplier, counters, expiry, and reconnect behavior stay
  compatible.
- The number and types of ZeroMQ sockets are unchanged.

## References

- [PyZMQ thread safety](https://pyzmq.readthedocs.io/en/v17.1.0/morethanbindings.html#thread-safety)
- [libzmq socket thread safety](https://libzmq.readthedocs.io/en/latest/zmq_socket.html#thread-safety)
- [libzmq poller thread safety](https://zeromq.github.io/libzmq/zmq_poller.html#thread-safety)
- NorFab protocol definitions: `norfab/core/NFP.py`
- NorFab keepalive implementation: `norfab/core/keepalives.py`
