# ADR - FastMCP Task Result Guardrails

## Status

Proposed

Date: 2026-07-19

## Overview

FastMCP exposes NorFab service tasks as MCP tools. The existing
[FastMCP task call guardrails](adr_fastmcp_task_call_guardrails.md) inspect MCP
tool arguments and can reject an unsafe call before a NorFab job is dispatched.

This ADR adds guardrails for the opposite direction: the NorFab task result
before FastMCP hands it to an MCP client and language model.

A valid task result can still be unsafe or unsuitable for model context. It may
contain:

- Passwords, private keys, bearer tokens, API keys, or other credentials.
- Enough data to consume too much of a model's context window.
- Instructions embedded in device output, logs, documents, or third-party data
  that attempt indirect prompt injection.
- Deployment-specific content that should never be passed to a model.

Task output models already validate task results. FastMCP result guardrails do
not repeat task output validation or change MCP output schemas. Their scope is
limited to model-facing size and content controls.

The content-inspection scope is deliberately narrower than the size scope:

- `limit` serializes and measures the complete aggregate dictionary returned by
  `run_job()`.
- `replace` and `regex` recursively inspect string values only below each
  worker's `result` and `diff` fields.
- Dictionary keys and all other `Result` fields are outside regex inspection.

## Decision

NorFab will add FastMCP **task result guardrails** as lists of dictionaries.
They deliberately follow the same general shape as existing task call
guardrails:

- Task-owned defaults live in `mcp["result_guardrails"]`.
- Inventory-owned additions live in `tools.result_guardrails`.
- Inventory entries add `service` and `task` selectors.
- All definitions remain serializable metadata.
- FastMCP validates them during tool discovery.

The first implementation supports only three result guardrail types:

| Type | Purpose | Result action |
| --- | --- | --- |
| `limit` | Enforce a maximum serialized result size. | Discard the delivery copy and reconstruct bounded base `Result` values explaining that raw output is available by `juuid`. |
| `replace` | Use regex substitution to redact sensitive result text. | Return a copied result with matching text replaced. |
| `regex` | Detect result text that must not reach the model. | Clear only the matching worker's affected `result` or `diff` field and append guardrail outcomes. |

The original result remains unchanged in the FastMCP worker's `NFPClient`
SQLite database. FastMCP returns the existing aggregate worker-result shape and
does not add MCP-only fields to it. Every worker value continues to use the
fields defined by `norfab.models.Result`.

All replacement and blocking behavior operates on a deep delivery copy. It
does not mutate the aggregate object returned by `run_job()` or its persisted
database value.

When `limit` is exceeded, FastMCP does not return or mutate the NorFab worker
results. It reconstructs the aggregate using new base `Result` objects with
`failed=False` and a bounded explanatory string in `result`. The text includes
the measured size, limit, and database retrieval guidance using the existing
`juuid`.

When `regex` withholds task content, FastMCP preserves the original worker
result fields and values except for the matching worker's affected `result` or
`diff` field. It appends explanations and database retrieval guidance to the
existing `errors` and `messages` lists without changing `failed` or `status`.
When `replace` changes task content, FastMCP appends a notice to the existing
`messages` list.

The existing input guardrail contract remains unchanged.

## Why Use A Separate Result Guardrail List

Input and result guardrails use similar configuration, but they execute at
different times and have different outcomes:

| Concern | Task call guardrail | Task result guardrail |
| --- | --- | --- |
| Enforcement time | Before job dispatch | After job completion and persistence |
| Inspected data | MCP tool arguments | Aggregated NorFab task result |
| Safe actions | Reject the call | Replace text or clear affected `result`/`diff` content |
| Task side effects | Prevented by rejection | May already have occurred |
| Oversized data | Not in scope | Return reconstructed bounded `Result` values with retrieval guidance using `juuid` |
| Recovery | Correct arguments and retry | Retrieve the raw stored result out of band |

## Goals

- Prevent oversized NorFab results from being inserted into model context.
- Redact known sensitive patterns before results reach a model.
- Block results containing configured unsafe patterns.
- Keep task and inventory metadata small, deterministic, and serializable.
- Preserve raw results for trusted operator retrieval and diagnostics.
- Return clear guardrail outcomes through existing `result`, `errors`,
  `messages`, and `juuid` fields.
- Avoid logging secrets, matching excerpts, or complete rejected results.
- Apply `limit` to the entire aggregate response while restricting `replace`
  and `regex` to each worker's `result` and `diff` fields.

## Non-Goals

- Revalidating task output models.
- Constructing or changing aggregate MCP output schemas.
- Guaranteeing detection of every password, key, token, or prompt injection.
- Adding a model-based classifier or hosted DLP dependency in the first
  implementation.
- Silently truncating or summarizing an oversized result.
- Mutating the result returned by `run_job()` or stored in the client database.
- Giving a model unrestricted access to raw job results by UUID.
- Applying these controls to non-MCP NorFab clients.
- Supporting arbitrary Python callbacks in guardrail definitions.
- Guarding the language model's final answer to a user.
- Changing the existing behavior when `run_job()` returns `None` rather than an
  aggregate result dictionary.

## Task Metadata Contract

Task authors define result guardrails as a list under the existing `mcp`
dictionary:

```python
@Task(
    input=SomeInput,
    output=SomeOutput,
    mcp={
        "guardrails": [
            # Existing input guardrails.
        ],
        "result_guardrails": [
            {
                "description": "Keep this task result below 128 KiB.",
                "type": "limit",
                "limit": 131072,
            },
            {
                "description": "Redact passwords from command output.",
                "type": "replace",
                "match": "(?i)(password\\s*[=:]\\s*)\\S+",
                "replace": "\\1[REDACTED:PASSWORD]",
                "messages": ["Sensitive task result content was redacted."],
            },
            {
                "description": "Block known instruction injection text.",
                "type": "regex",
                "match": [
                    "(?i)ignore (all |the )?previous instructions",
                    "(?i)system message begins",
                ],
                "errors": [
                    "Task result contained an unsafe instruction pattern."
                ],
            },
        ],
        "prompts": [...],
    },
)
def some_task(...):
    ...
```

`mcp["result_guardrails"]` is NorFab metadata, not an MCP SDK `Tool` field.
Discovery must remove it from a copied metadata dictionary before constructing
`types.Tool(...)`:

```python
tool_metadata = dict(task["mcp"])
prompts_metadata = tool_metadata.pop("prompts", [])
call_guardrails_metadata = tool_metadata.pop("guardrails", [])
result_guardrails_metadata = tool_metadata.pop("result_guardrails", [])
```

The split must not mutate the task metadata retained for inspection or later
discovery cycles.

The NorFab-reserved keys inside task `mcp` metadata are therefore:

- `prompts`
- `guardrails`
- `result_guardrails`

When `mcp=False`, the task is not exposed as an MCP tool and no result
guardrails are evaluated through FastMCP.

Task metadata values have these meanings:

| Value | Behavior |
| --- | --- |
| Key omitted, `None`, or `[]` | The task adds no built-in result guardrails. Inventory rules can still apply. |
| Non-empty list | FastMCP validates and evaluates the listed rules for this task. |
| Any non-list value other than `None` | Tool discovery fails for that task. |

FastMCP normalizes `None` to an empty list before validation.

## Inventory Contract

Inventory-defined result guardrails use a list of dictionaries under
`tools.result_guardrails`, matching the shape of existing inventory call
guardrails:

```yaml
service: fastmcp
host: "127.0.0.1"
port: 8001

tools:
  result_guardrails:
    - service: "*"
      task: "*"
      description: Keep all MCP task results below 256 KiB.
      type: limit
      limit: 262144

    - service: "*"
      task: "*"
      description: Redact PEM private keys.
      type: replace
      match: "(?s)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
      replace: "[REDACTED:PRIVATE_KEY]"
      messages:
        - "Private key content was redacted from the task result."

    - service: nornir
      task: cli
      description: Block a deployment-specific instruction banner.
      type: regex
      match: "(?i)instructions from network administrator:"
      errors:
        - "Task result contained an unsafe instruction banner."
```

Each inventory entry requires `service` and `task`. Selectors use `fnmatch`
semantics so operators can define global rules with `"*"` or restrict rules to
one service and task.

Task-owned guardrails are evaluated together with every matching inventory
entry. Inventory guardrails do not replace task-owned guardrails.

If operators need to disable task-owned result guardrails, FastMCP supports the
same explicit pattern used for input guardrails:

```yaml
tools:
  disable_builtin_guardrails: true
  result_guardrails:
    - service: "*"
      task: "*"
      type: limit
      limit: 262144
```

This existing switch skips both task-owned `mcp["guardrails"]` and
`mcp["result_guardrails"]` entries while retaining inventory-defined input and
result guardrails.

Inventory option:

| Key | Type | Required | Default | Purpose |
| --- | --- | --- | --- | --- |
| `disable_builtin_guardrails` | boolean | no | `false` | Skip both input and result task-owned guardrails while retaining inventory entries. |

FastMCP does not add an implicit result rule when the effective list is empty.
Deployments that require a universal context limit should configure the global
`service: "*"`, `task: "*"` limit shown above.

For inventory, an omitted `tools.result_guardrails`, `None`, or `[]` means no
inventory-defined result guardrails. Any other non-list value is invalid.

## Common Rule Fields

All task and inventory entries support these common fields:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `service` | string | inventory only | Service selector using `fnmatch`. |
| `task` | string | inventory only | Task selector using `fnmatch`. |
| `description` | string | no | Human-readable operator explanation. |
| `type` | `limit`, `replace`, or `regex` | yes | Guardrail behavior. |

Unknown fields and unsupported types fail validation during discovery.

## `limit` Guardrails

A `limit` guardrail has one additional field:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `limit` | positive integer | yes | Maximum compact serialized JSON result size in bytes. |

Example:

```yaml
- service: netbox
  task: get_devices
  type: limit
  limit: 262144
```

FastMCP measures the complete delivery aggregate at the `limit` rule's authored
position as `len(orjson.dumps(delivery_result))`. This includes every worker and
every serialized `Result` field. When a limit precedes content rules, its first
measurement is equivalent to the raw aggregate returned by `run_job()`. The
limit is a byte budget, not a token count. FastMCP does not know the consuming
model, tokenizer, current conversation size, or client context policy.

This compact `orjson` size is deterministic for the value but is not
necessarily the exact number of bytes later placed in model context. The
current MCP SDK can render a returned dictionary as indented JSON, and MCP
clients may transform it again. The limit is therefore a server-side size proxy
unless FastMCP also takes ownership of the final MCP serialization.

When several matching `limit` guardrails have been encountered in authored
order, the smallest encountered limit is effective. Operators should place
global limit rules before content rules when they want both a raw pre-check and
post-replacement enforcement.

When a result exceeds the effective limit, FastMCP discards the entire delivery
copy. For each worker key, it constructs a new `norfab.models.Result` with only
the original `juuid` copied as the database locator. The new value uses the
model defaults, explicitly sets `failed=False`, and places a bounded notice in
`result` stating the measured size and limit and explaining that the raw result
can be retrieved from the FastMCP client database using that `juuid`.

No task-produced `result`, `diff`, `errors`, `messages`, `resources`, status,
timestamps, task name, service name, or other worker-result value is reused.
The reconstructed aggregate is the terminal limit response and is not passed
through later result guardrails or rechecked against the same limit. The raw
result stays unchanged in the client database.

## `replace` Guardrails

A `replace` guardrail has these additional fields:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `match` | string or list of strings | yes | Python regex pattern or patterns. |
| `replace` | string | yes | Replacement value passed to `re.sub` for every match. |
| `messages` | list of strings | no | Safe notices appended when this rule replaces content. |

Example:

```yaml
- service: nornir
  task: cli
  type: replace
  match:
    - "(?i)(authorization:\\s*bearer\\s+)\\S+"
    - "(?i)(password\\s*[=:]\\s*)\\S+"
  replace: "\\1[REDACTED]"
  messages:
    - "Sensitive content was redacted from the task result."
```

For each worker, FastMCP walks the values stored in the worker's `result` and
`diff` fields in a copied aggregate result. Either field may contain a string,
dictionary, list, or nested combination of those types. FastMCP recursively
applies `re.sub` to every string leaf. Dictionary keys and non-string scalar
values are not modified. No other `Result` field is inspected or rewritten by
a `replace` rule. After replacement, FastMCP may append its safe notice to
`messages` as the explicit guardrail outcome.

The recursive walker follows these rules:

- For a dictionary, recurse through values and preserve keys unchanged.
- For a list, recurse through items in order.
- For a string, apply the configured regex operation.
- For `None`, numbers, booleans, and other JSON scalars, return the value
  unchanged.

When `match` is a list, patterns run in declared order using the same
`replace` value. Multiple `replace` guardrails also run in their effective order:
task-owned entries first, followed by matching inventory entries.

For every unique path changed by a rule, FastMCP appends every configured
`messages` entry to that worker's existing `messages` list and adds the worker
name and path. Paths use simple dotted/list notation, for example
`result.devices[0].credentials.password` or `diff.interfaces.Ethernet1`.

Replacement changes only the MCP delivery copy. It never changes the object or
serialized result stored in the client database.

Regex replacement is deterministic but cannot discover an arbitrary unlabelled
password. Task authors and operators must define patterns appropriate to the
actual result formats they expose.

## `regex` Guardrails

A `regex` guardrail has one additional field:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `match` | string or list of strings | yes | Python regex pattern or patterns evaluated with `re.search`. |
| `errors` | list of strings | no | Additional safe errors returned when a pattern blocks the result. |

Example:

```yaml
- service: nornir
  task: cli
  type: regex
  match:
    - "(?i)ignore previous instructions"
    - "(?i)call the following tool"
  errors:
    - "Task result contained a blocked instruction pattern."
```

For each worker, FastMCP recursively inspects every string leaf inside the raw
`result` and `diff` fields. A match from any configured expression withholds
only the affected top-level field for the matching worker: a match below
`result` sets that worker's copied `result` to `None`, while a match below
`diff` sets that worker's copied `diff` to `None`. Other workers remain intact.
Other `Result` fields, including `errors`, `messages`, and `resources`, are not
regex inputs. Patterns use OR semantics and no matching value or excerpt is
returned to the client or logs.

FastMCP appends the rule's configured `errors` and a safe generated message to
the matching worker. The generated outcome includes the worker name and matched
key path, plus database retrieval guidance using that worker's existing
`juuid`, but never the matching value. Processing then continues with the next
guardrail in effective authored order.

`regex` is intentionally a blocking rule. Use `replace` when matching content
can be safely redacted and the rest of the result remains useful.

## Validation

FastMCP validates all result guardrail metadata during tool discovery:

- After omitted and `None` values are normalized to `[]`, the guardrail
  collection must be a list.
- Every entry must be a dictionary.
- `type` must be `limit`, `replace`, or `regex`.
- `limit` must be a positive integer for `type: limit`.
- `match` must be a string or non-empty list of strings for `replace` and
  `regex`.
- `replace` must be a string for `type: replace`.
- `errors`, when present on `regex`, must be a list of strings.
- `messages`, when present on `replace`, must be a list of strings.
- Every regex is compiled during discovery.
- Every `replace` template is validated against every compiled pattern in that
  rule so invalid capture-group references fail during discovery.
- Inventory rules require string `service` and `task` selectors.
- Unknown fields are rejected.

Invalid metadata fails discovery for that tool. It is not deferred until an
MCP tool call.

This validation applies only to guardrail configuration. Task output validation
remains the responsibility of each task's output model.

## Enforcement Order

MCP `tools/call` follows this sequence:

1. Resolve the MCP tool name and enforce `tools.policy`.
2. Evaluate existing task call guardrails against raw MCP arguments.
3. Call `self.client.run_job(...)` and receive the aggregate worker results.
4. Leave the raw result stored in the client database unchanged.
5. Build one effective list: task-owned entries in declared order, followed by
   matching inventory entries in inventory order.
6. Deep-copy the aggregate result once for MCP delivery.
7. Iterate through the effective list exactly once in authored order:
   - For `limit`, add the rule to the encountered limits, calculate the
     smallest encountered limit, serialize the complete delivery copy with
     `orjson.dumps`, and immediately reconstruct the aggregate when exceeded.
   - For `regex`, recursively inspect `result` and `diff` for each worker,
     clear only an affected field for an affected worker, and append safe
     `errors` and `messages` with worker/path context.
   - For `replace`, recursively replace string leaves in `result` and `diff`
     and append every configured message with worker/path context.
   - After a `replace`, recheck all previously encountered limits against the
     complete transformed aggregate.
8. Stop content processing and return immediately after a limit is exceeded.
   The return value retains the worker-keyed aggregate shape, but every worker
   value is a newly constructed base `Result` rather than the NorFab result.
9. Otherwise, return the copied aggregate using its existing worker and
   `Result` shape.

If `run_job()` returns `None` instead of an aggregate dictionary, FastMCP keeps
its existing tool-error behavior. Result guardrails do not attempt to create a
synthetic worker result because there is no existing `Result` value or `juuid`
to preserve.

Strict authored order is intentional. A `replace` before a `regex` may remove
text that the later regex would otherwise block; a `regex` before a `replace`
sees the original text. Inventory rules always run after task-owned rules.

An unexpected serialization, regex, copy, or replacement error follows the
existing FastMCP tool-error path and never falls back to the raw content. This
is separate from a normal limit match, which returns reconstructed `Result`
values rather than a tool error.

## Successful Result Behavior

When no blocking rule matches and the result is within the size limit, FastMCP
returns the existing aggregate dictionary keyed by worker name. FastMCP does
not add `_meta`, a second UUID, guardrail counters, or any other field to the
result.

When a `replace` rule changes one or more values, FastMCP records every unique
worker/path affected by that rule. For each affected worker/path it appends
every configured `messages` entry to that worker's copied result, augmented
with the worker name and key path. If the rule does not configure `messages`,
or configures an empty list, FastMCP appends this default text with the same
context:

```text
FastMCP result guardrail replaced sensitive content for worker
'nornir-worker-1' at path 'result.devices[0].password'.
```

Messages are appended only when at least one replacement occurred. Repeated
matches at the same worker/path for the same rule produce one set of notices;
different rules may each append their configured notices. Replacement text
such as `[REDACTED]` should also be self-explanatory.
If the existing `messages` field is `None`, FastMCP normalizes it to an empty
list on the delivery copy before appending notices.

## Withheld Result Behavior

`limit` and `regex` intentionally have different outcomes.

When a `limit` is exceeded, FastMCP keeps the aggregate worker keys but discards
all worker values from the delivery copy. Each worker value is reconstructed as
`Result(result=notice, failed=False, juuid=original_juuid).model_dump()`. The
notice is bounded and states:

- The original compact serialized size and effective byte limit.
- That the oversized result was omitted from the MCP response.
- That the raw result can be retrieved from the FastMCP client's database using
  the job UUID.
- That the stored result has not been sanitized.

Copying `juuid` is the single exception to not reusing the NorFab worker result:
it is required as the existing database locator. All remaining fields come
from a newly constructed base `Result`; task-produced metadata and content are
not copied. In particular, `errors` and `messages` are empty, `status`, `task`,
`service`, timestamps, and `diff` are `null`, resources are empty, and
`dry_run` uses its default. `failed=False` means the task's oversized delivery
is not misrepresented as a task execution failure.

Example worker value after a result exceeds its limit:

```json
{
  "result": "Task result omitted because its serialized size of 917504 bytes exceeded the FastMCP limit of 262144 bytes. Retrieve the raw result from the FastMCP client database using job UUID '5d2c7c8625bd4ad6aa456c06f8abfa52'. The stored result has not been sanitized.",
  "failed": false,
  "errors": [],
  "task": null,
  "messages": [],
  "juuid": "5d2c7c8625bd4ad6aa456c06f8abfa52",
  "resources": [],
  "status": null,
  "task_started": null,
  "task_completed": null,
  "service": null,
  "diff": null,
  "dry_run": false
}
```

The reconstructed limit response is terminal and intentionally is not checked
against the triggering limit. Its fixed-format notices prevent task output
from influencing its size. The response may grow only with the number of
worker keys and UUIDs, not with the omitted task content.

When `regex` withholds content, FastMCP instead preserves the existing worker
result and changes only the affected top-level field. A match below `result`
sets that worker's copied `result` to `null`; a match below `diff` sets that
worker's copied `diff` to `null`. Other workers and all unaffected values are
preserved. FastMCP appends the configured safe errors and a generated message
with the worker name, matched path, and database retrieval guidance using the
existing `juuid`. If an existing `errors` or `messages` value is `None`, it is
normalized to an empty list on the delivery copy before appending.

FastMCP-generated regex outcomes never contain result excerpts, matched text,
regex patterns, or secret values. Configured errors are operator-authored text;
operators must keep them non-sensitive.

An oversized result is not silently truncated. Partial network results can be
misleading, structurally incomplete, or missing the line that changes their
meaning. Automatic summarization is also excluded because it introduces model
dependency and can still disclose secrets or follow injected instructions.

## Retrieving A Withheld Result

The FastMCP worker's `NFPClient` already stores job results in its client-side
SQLite database. Trusted local code can retrieve a result using the existing
worker result `juuid`:

```python
juuid = worker_result["juuid"]
job = fastmcp_worker.client.job_db.get_job(juuid)
raw_result = job["result_data"] if job else None
```

The stored result is raw and has not passed through `replace` guardrails. It may
be large or sensitive and must be handled accordingly.

The job UUID is a locator, not an authorization credential. This ADR does not
add a raw `get_result(juuid)` MCP tool because it would let a model bypass
the same result guardrails. Any future MCP resource or paginated result reader
must enforce authorization, size limits, blocking regex rules, and replacement
rules on every read.

## Inspection And Logging

`fastmcp.get_tools` with `brief=False` returns the effective result guardrail
list after task and inventory rules are combined.

Logs may include:

- Job UUID, service, task, and MCP tool name.
- Guardrail type and non-sensitive rule identifier.
- Result size and effective limit.
- Replacement count.
- Whether the result was allowed, replaced, or withheld.

Logs must not include:

- Full task results.
- Matching values or surrounding excerpts.
- Original values changed by `replace`.
- Full MCP response content.

Because `replace` and `regex` inspect only `result` and `diff`, credentials or
hostile text placed in `errors`, `messages`, `resources`, or other metadata are
not content-filtered by these rules. Those fields still count toward `limit`.
Task implementations remain responsible for keeping their metadata fields safe
for clients and models.

## Industry Design Signals

The simplified design follows common tool-result protection patterns:

- The OpenAI Agents SDK distinguishes tool input and tool output guardrails and
  can replace rejected tool output with a safe message to the model. See
  [OpenAI Agents SDK tool guardrails](https://openai.github.io/openai-agents-python/guardrails/#tool-guardrails).
- LangChain can apply PII handling specifically to tool results and supports
  replacement or blocking behavior. See
  [LangChain guardrails](https://docs.langchain.com/oss/python/langchain/guardrails).
- Microsoft Prompt Shields treats third-party documents as an indirect prompt
  injection surface. Tool results have the same trust problem. See
  [Azure AI Content Safety Prompt Shields](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
- MCP supports structured tool results, error results, and resource links. See
  [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

The first NorFab implementation stays local and deterministic. Optional
classifier-backed prompt-injection or DLP rules can be considered later as new
guardrail types if operational evidence justifies their cost and privacy
impact.

## Alternatives Considered

### Add `direction: in | out` To Existing Guardrails

Rejected. Input and result rules have different enforcement times and actions.
Separate list keys preserve a familiar dictionary shape without creating one
union model full of direction-specific fields.

### Add A Nested Result Policy Structure

Rejected. Structures such as `result_guardrails.limits`,
`result_guardrails.secrets`, and `result_guardrails.rules` are harder to merge,
inspect, validate, and extend. One flat list matches existing guardrails and
keeps inventory concise.

### Call The Feature Sanitization

Rejected as the top-level name. `replace` sanitizes matching text, but `limit`
and blocking `regex` rules clear affected task content. Guardrails describe the
broader behavior.

### Truncate Or Summarize Oversized Results

Rejected for the first release. Both can change the meaning of operational
data. Summarization also adds a model dependency and another injection surface.

### Return An MCP Resource Link Automatically

Deferred. NorFab does not yet expose an authorized, guardrail-aware MCP resource
reader for client job records. Returning a UUID for trusted out-of-band access
does not create a raw model retrieval path.

### Count Model Tokens Instead Of Bytes

Rejected. FastMCP does not know the consuming model, tokenizer, current
conversation size, or client context policy. Serialized bytes provide a stable
server-side limit.

## Confirmed Decisions

The maintainer confirmed these implementation choices:

1. Inventory `service` and `task` selectors use `fnmatch`, including `"*"`.
2. The effective flat list runs in strict authored order: task rules first,
   followed by matching inventory rules.
3. A blocking `regex` clears only the matching worker's affected `result` or
   `diff` field; it does not clear other workers.
4. A blocking `regex` preserves the original `failed` and `status` values.
5. For `regex` and `replace`, all original fields and unaffected values are
   preserved. Guardrail errors and messages are appended rather than replacing
   existing lists.
6. Every configured replacement message is appended for every affected worker
   and unique key path, with worker name and path included.
7. An encountered limit is checked at its authored position and checked again
   after later replacements. Place global limits first for raw and transformed
   checks.
8. An empty effective result-guardrail list means no implicit size limit.
9. Existing `disable_builtin_guardrails` disables both input and result
   task-owned defaults while retaining inventory rules.
10. `run_job() -> None` retains current MCP tool-error behavior.
11. `len(orjson.dumps(delivery_result))` is accepted as the deterministic size
    proxy even though clients may render different JSON text.
12. Exceeding a `limit` discards the complete NorFab delivery result and
    reconstructs each worker value with `norfab.models.Result`. Only the
    existing `juuid` is copied for database retrieval; `failed=False`, and the
    `result` field contains a bounded oversized-result notice.

## Implementation Notes

### Keep The Change Surgical

Implementation must preserve the existing FastMCP worker logic and call flow.
The intended change to `call_tool` is small: assign the existing
`self.client.run_job(...)` return value to a local result, apply the effective
guardrail list to one deep delivery copy, and return that same aggregate shape.
If a limit is exceeded, replace the delivery copy with newly constructed base
`Result` values and return it immediately.

Keep the code linear and explicit:

- Do not introduce a generic guardrail engine, result pipeline class, policy
  framework, callback registry, or changes to broker/client job flow.
- Do not refactor unrelated FastMCP discovery or call logic.
- Do not change service task results, `norfab.models.Result`, `NFPClient`, the
  broker, or the client database schema.
- Prefer one straightforward loop over the effective rule list.
- Add a helper only when logic is reused in more than one place and the helper
  represents one clear operation. A small recursive string-leaf walker is
  justified because both `regex` and `replace` use it. Keep size checks and
  simple field/list updates inline unless they become genuinely duplicated.
  Keep limit-result reconstruction inline unless the exact operation is reused.
- Reuse existing FastMCP logging, policy checks, discovery storage, and error
  handling.

The implementation should touch only the FastMCP-local models, worker,
focused tests, task metadata documentation, and task definitions that opt into
built-in result guardrails.

Core worker changes:

1. Keep `mcp["result_guardrails"]` as plain serializable task metadata.
2. Document `result_guardrails` as a NorFab-reserved MCP metadata key alongside
   `prompts` and `guardrails`.
3. Keep FastMCP-specific rule models out of core worker code.

FastMCP worker changes:

1. Add the smallest practical FastMCP-local Pydantic validation model for
   `limit`, `replace`, and `regex` rules.
2. Add `service` and `task` selectors for the inventory form of the same rules.
3. Validate rules and compile regex patterns during discovery.
4. Remove result metadata from a copy before MCP `Tool` construction.
5. Store the effective flat guardrail list with each registered tool.
6. Add one small recursive helper shared by result/diff inspection and
   replacement.
7. Apply rules in one linear loop inside the existing call flow.
8. For `replace` and `regex`, append to existing `messages` or `errors` and
   update only affected `result`/`diff` values on the delivery copy.
9. For `limit`, discard the delivery copy and create a base `Result` for each
   worker key with only `juuid`, `failed=False`, and the bounded `result` notice
   explicitly supplied.
10. Return the existing aggregate worker-result dictionary shape.
11. Keep original client database results unchanged.

## Testing

Unit tests should cover:

- Task and inventory result guardrails must be lists of dictionaries.
- Only `limit`, `replace`, and `regex` types are accepted.
- Unknown fields, invalid limits, missing `replace` values, empty matches, and
  invalid regex patterns fail during discovery.
- Invalid regex `errors` or replacement `messages` values and invalid
  replacement capture-group references fail during discovery.
- `result_guardrails` is removed before MCP `Tool` construction without
  mutating task metadata.
- Task rules combine with matching inventory rules.
- `disable_builtin_guardrails` skips both input and result task rules but
  retains inventory rules.
- `service` and `task` selectors use `fnmatch` semantics.
- The smallest encountered limit wins at each point in authored order.
- Results exactly at the byte limit pass and results one byte over are
  withheld.
- A limit is checked when encountered and rechecked after every later
  replacement; a limit authored after a replacement sees only the transformed
  value.
- An empty effective list applies no implicit limit.
- `replace` handles every string leaf nested under each worker's `result` and
  `diff` fields without modifying dictionary keys, numbers, booleans, other
  `Result` fields, or the stored result.
- Multiple replacement patterns and rules run in deterministic order.
- `regex` blocks when any pattern matches a string leaf under a worker's
  `result` or `diff` field.
- `replace` and `regex` do not inspect `errors`, `messages`, `resources`,
  identity fields, or timestamps.
- Strict authored order is honored for interleaved `regex` and `replace` rules.
- Blocked results use only existing `Result` fields.
- Limit outcomes discard every NorFab worker value and reconstruct base
  `Result` values with `failed=False`, a bounded notice in `result`, and only
  the original `juuid` copied for database retrieval.
- Reconstructed limit results contain none of the original `result`, `diff`,
  errors, messages, resources, task/service metadata, status, or timestamps.
- Regex outcomes preserve all fields, clear only the matching worker's
  affected `result` or `diff`, and return no match or source excerpt.
- Regex and replacement outcomes preserve existing `failed`, `status`,
  `errors`, `messages`, and `resources` values; guardrail outcomes are appended.
- Replacement notices include worker name and unique key path and are added to
  `messages` only for affected workers.
- A reconstructed limit response is terminal and is not rechecked against its
  triggering limit.
- Processing errors fail closed.
- `run_job() -> None` retains existing MCP error behavior.
- Captured logs contain no seeded test secrets.

Service tests should cover:

- A normal small result passes unchanged.
- A seeded credential is replaced in the MCP result but remains unchanged in
  the FastMCP client database.
- An oversized result returns newly constructed base `Result` values with no
  original task content or metadata, a bounded notice in `result`,
  `failed=False`, and usable `juuid` values.
- A blocking regex clears only the matching worker's affected field, preserves
  other workers and metadata, and does not return the match.
- A trusted test client can retrieve omitted or regex-cleared raw content using
  the existing `juuid`.
- Existing task call guardrails still reject unsafe arguments before job
  dispatch.
- Existing `tools.policy` still rejects disallowed tasks before result
  guardrails are relevant.

Security fixtures must use unmistakably fake credentials. Tests must assert
that seeded raw values are absent from MCP responses, exceptions, captured
logs, and test reports.

## Consequences

- Result inventory follows the same flat list style as existing guardrails.
- Only three rule types need implementation and documentation.
- Operators can apply global or task-specific context limits with wildcard
  selectors.
- Regex replacement provides deterministic redaction without an external
  service.
- Blocking regex rules provide a basic indirect-prompt-injection and content
  denylist mechanism, but do not guarantee detection.
- Authored order is behaviorally significant; operators must place rules in the
  intended sequence.
- Regex blocking is isolated to the matching worker and affected top-level
  `result` or `diff` field.
- Regex and replacement outcomes retain the task execution status. Limit
  outcomes intentionally return base `Result` values with `failed=False` and
  no copied status because they describe model-facing delivery rather than the
  omitted task result.
- Raw results remain available to trusted operators by job UUID.
- FastMCP performs additional serialization, recursive traversal, and regex
  processing for guarded results.
- The implementation remains a surgical FastMCP boundary change and does not
  alter core job transport, storage, or service task behavior.
- Operators and task authors must maintain patterns appropriate to their actual
  data formats.
