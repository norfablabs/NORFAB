# NORFAB Python API

The NORFAB Python API provides a programmatic interface to interact with the NORFAB automation fabric. It is designed for developers who want to integrate NORFAB capabilities into their Python applications for advanced network automation and management tasks.

NorFab Python API can be used to interact with automations fabric. To start working with Python API need to import `NorFab` object and instantiate it.

```
from norfab.core.nfapi import NorFab

nf = NorFab(inventory="./inventory.yaml")
nf.start()
nf.destroy()
```

Refer to [Getting Started](norfab_getting_started.md) section on 
how to construct  `inventory.yaml` file.

All interaction with NorFab happens via client, to create a client need to call `make_client` method:

!!! example

    === "Direct Invocation"

        This example demonstrates steps to create NorFab instance, create client,
        run job and destroy NorFab instance.

        ```
        import pprint
        from norfab.core.nfapi import NorFab

        nf = NorFab(inventory="./inventory.yaml")
        nf.start()

        client = nf.make_client()

        result = nf.client.run_job(
            service="nornir",
            task="cli",
            kwargs={"commands": ["show version", "show clock"]}
        )

        pprint.pprint(result)

        nf.destroy()
        ```

    === "With Context Manager"

        Context manager simplifies code and handles client creation and NorFab cleanup.

        ```
        import pprint
        from norfab.core.nfapi import NorFab

        with NorFab(inventory="./inventory.yaml") as nf:
            result = nf.client.run_job(
                service="nornir",
                task="cli",
                kwargs={"commands": ["show version", "show clock"]}
            )

        pprint.pprint(result)
        ```

Calling `destroy` method will kill all the clients as well.

## Client Names

Each NorFab client has a name. The name is used as the client identity when
communicating with the broker and is also used for the client's local job
database and files under `__norfab__/files/client/`.

By default, `make_client()` derives the name from the Python entry script and
adds a short hash of the current folder path:

```
client = nf.make_client()
```

For example, running `python lab.py` creates a client name similar to
`lab_a1b2c3_NFPClient`. The folder hash keeps default names deterministic
while avoiding collisions between projects that run scripts with the same file
name. If Python cannot determine the entry script name, the default uses
`<folder-hash>_NFPClient`.

You can also provide an explicit name:

```
client = nf.make_client(name="lab_client_1")
```

Use explicit names when running multiple clients from the same script, shell,
notebook, test runner, or application directory:

```
client_1 = nf.make_client(name="lab_client_1")
client_2 = nf.make_client(name="lab_client_2")
```

Unique client names prevent clients from sharing the same broker identity and
local job database. This helps avoid cases where replies or events for one
client are delivered to another client, or where multiple clients read and
write the same local job state while fetching results.

!!! note:

    Think of the client name as a network address, not just a display label. The
    broker uses this name to route replies and events back to the client. Two active
    clients with the same name are competing for the same broker route, so a later
    connection can disrupt an earlier one. If two clients need to be active at the
    same time, give them different names.

## Running Jobs

NorFab client supports two ways to run worker tasks:

1. `run_job()` - submits a job and blocks until the result is available. This is the simplest API and is best for scripts that only need final results.
2. `submit_job()` - submits a job and returns a future object. Use this API when the caller needs to read job events while the job is running, respond to worker input requests, or wait for the result later.

### Synchronous Jobs

Use `run_job()` for normal blocking execution:

```
result = nf.client.run_job(
    service="nornir",
    task="cli",
    workers="all",
    kwargs={"commands": ["show version"]},
    timeout=600,
)
```

### Future Based Jobs

Use `submit_job()` to get a job future object:

```
future = nf.client.submit_job(
    service="nornir",
    task="cli",
    workers="all",
    kwargs={"commands": ["show version"]},
    timeout=600,
)

for event in future.events():
    print(event["event_type"], event["message"])

result = future.result(timeout=600)
```

The future object provides these methods:

1. `events(timeout=None)` - blocking iterator that yields job events until the job completes or until no event is received within `timeout`.
2. `result(timeout=None, markdown=False)` - blocks until the job completes and returns worker results.
3. `send_response(input_id, value, worker=None, cancel=False, metadata=None)` - sends a response to a worker input request.

Events always include `event_type`. Current event types are:

1. `progress` - regular worker task progress event.
2. `input_request` - worker is paused and waiting for client input.
3. `input_response` - worker received, cancelled, or timed out waiting for input.

### Event Shape

Events yielded by `future.events()` are dictionaries. Common event fields are:

```
{
    "event_type": "progress",
    "message": "starting",
    "service": "nornir",
    "worker": "nornir-worker-1",
    "task": "cli",
    "uuid": "job-uuid",
    "timestamp": "07-Jun-2026 10:30:00.123",
    "severity": "INFO",
    "status": "running",
    "resource": [],
    "extras": {},
}
```

`event_type` is always present. Other fields depend on the worker task and event type.

Input request details are stored under `event["extras"]["input_request"]`:

```
{
    "event_type": "input_request",
    "message": "approve dummy task?",
    "service": "DummyService",
    "worker": "dummy-worker-1",
    "task": "input_request_task",
    "uuid": "job-uuid",
    "severity": "INFO",
    "status": "waiting_client_input",
    "timeout": 120,
    "extras": {
        "input_request": {
            "id": "input-request-id",
            "question": "approve dummy task?",
            "default": "no",
            "metadata": {"task": "input_request_task"},
        }
    },
}
```

The response sent by `future.send_response()` has this shape:

```
{
    "input_id": "input-request-id",
    "value": "yes",
    "cancel": False,
    "metadata": {},
}
```

After the worker receives, cancels or times out waiting for input, it emits an `input_response` event. Response details are stored under `event["extras"]["input_response"]`:

```
{
    "event_type": "input_response",
    "message": "approve dummy task?",
    "status": "received",
    "extras": {
        "input_response": {
            "input_id": "input-request-id",
            "metadata": {},
        }
    },
}
```

For cancelled input, `status` is `cancelled`. For unanswered input, `status` is `timeout`.

### Interactive Jobs

Worker tasks can pause and ask the client for input. Client code should listen for `input_request` events and reply using `send_response()`:

```
future = nf.client.submit_job(
    service="DummyService",
    task="input_request_task",
    workers="dummy-worker-1",
    timeout=600,
)

for event in future.events():
    if event["event_type"] != "input_request":
        print(event["message"])
        continue

    input_request = event["extras"]["input_request"]
    answer = input(input_request["question"] + " ")
    future.send_response(
        input_id=input_request["id"],
        value=answer,
        worker=event["worker"],
    )

result = future.result(timeout=600)
```

To cancel a pending input request:

```
future.send_response(
    input_id=input_request["id"],
    value=None,
    worker=event["worker"],
    cancel=True,
)
```
