# ADR - FastMCP Task Result Guardrails

## Status

Proposed

Date: 2026-07-19

## Overview

FastMCP exposes NorFab service tasks as MCP tools. The existing
[FastMCP task call guardrails](adr_fastmcp_task_call_guardrails.md) protect the
path from an MCP client to a NorFab task. They inspect tool arguments and can
reject an unsafe call before a job is dispatched.

This ADR protects the opposite boundary: the result returned by a NorFab task
before FastMCP hands it to the MCP client and, ultimately, a language model.
The result may be valid NorFab data while still being unsafe or unsuitable as
model context. Examples include:

- Passwords, private keys, bearer tokens, API keys, SNMP communities, and
  credentials embedded in URLs.
- A result large enough to exhaust or crowd out the model's context window.
- Instructions embedded in device output, documents, logs, or third-party API
  data that attempt indirect prompt injection.
- Unexpected control content, malicious URLs, or deployment-specific text that
  should not be given to a model.

In this ADR, **task result** means data returned by `NFPClient.run_job(...)` and
about to become an MCP `CallToolResult`. It does not mean the language model's
own generated response. The term avoids the ambiguity of "output guardrail,"
which is often used for checks applied after model inference.

## Context

FastMCP currently returns a NorFab job result directly:

```python
return self.client.run_job(
    service=service,
    task=task_name,
    kwargs=arguments,
    workers="all",
)
```

The FastMCP worker's `NFPClient` already stores the complete job and its result
in its client-side SQLite database. `ClientJobDatabase.get_job(uuid)` can read
the record and its `result_data`. This gives FastMCP a durable out-of-band
fallback: if a result cannot safely be placed in model context, FastMCP can
return a small receipt containing the job UUID without discarding the original
result.

The UUID must be selected before dispatch and passed to `run_job(uuid=...)` so
it is available even when the returned result is withheld.

## Decision

NorFab will add a separate FastMCP **task result guardrail pipeline**. It will
run after a NorFab job completes and after the original result is persisted in
the FastMCP worker's client database, but before any result content is returned
through MCP.

The first implementation will provide three deterministic controls:

1. A hard limit on the canonical serialized result size.
2. Recursive detection and redaction or blocking of common credentials and
   secrets.
3. Serializable regex rules that can redact or block deployment-specific
   result content.

The pipeline will construct `types.CallToolResult` explicitly. Successful
results retain structured content. Withheld results use `isError=true` and
contain only a bounded, non-sensitive receipt. This makes the policy outcome
visible to the model without presenting the unsafe content.

The existing input key `mcp["guardrails"]` and inventory
`tools.guardrails` remain unchanged. Result controls use the distinct key
`result_guardrails`; they will not add `direction: in | out` to existing rules.

Sanitization is an action performed by a result guardrail, not the name or the
full scope of the feature. Some conditions can be safely redacted, while other
conditions require the complete result to be withheld.

## Why Result Guardrails Are Separate

Input and result controls share validation concepts, but their enforcement
semantics differ materially:

| Concern | Task call guardrail | Task result guardrail |
| --- | --- | --- |
| Enforcement time | Before job dispatch | After job completion and persistence |
| Protected boundary | MCP client to NorFab task | NorFab task to MCP client/model |
| Primary subject | Tool arguments | Aggregated worker results and errors |
| Safe actions | Reject the call | Allow, redact, or withhold the result |
| Side effects | Rejection prevents them | Task side effects may already have occurred |
| Recovery | Correct arguments and retry | Retrieve the original result out of band by UUID |
| Size handling | Usually small inputs | Potentially very large task results |
| Failure response | Invalid-parameters error | Tool-result error receipt |

Adding `direction` to the existing guardrail model would create fields and
actions that are valid only in one direction. For example, `max_inline_bytes`,
secret redaction, and a job-result receipt have no useful input equivalent.
Separate models keep validation explicit and preserve the accepted task call
guardrail contract.

## Goals

- Treat all NorFab task results as untrusted model context at the FastMCP
  boundary.
- Prevent common credentials and secrets from being passed to a language
  model.
- Prevent oversized tool results from consuming model context.
- Preserve the original result in the FastMCP worker's client SQLite database.
- Give trusted operators a job UUID with which to retrieve a withheld result.
- Let task authors add safe task-specific defaults and operators make a
  deployment stricter without changing task source.
- Apply controls to successful results, failed worker results, and error text.
- Keep the first implementation deterministic, serializable, testable, and
  independent of a particular model vendor.
- Avoid logging sensitive values or full rejected results.

## Non-Goals

- Guaranteeing detection of every secret. Unlabelled passwords and previously
  unknown token formats cannot be detected reliably by generic rules.
- Treating a job UUID as an authorization credential.
- Giving the model unrestricted retrieval of raw results by UUID.
- Silently truncating, sampling, or summarizing oversized results.
- Automatically retrying a task with narrower arguments.
- Replacing service-side data minimization, authorization, or output
  validation.
- Revalidating task output or changing published MCP output schemas. Task
  output models remain authoritative.
- Inspecting results returned through non-MCP NorFab clients.
- Adding a model-based prompt-injection classifier or an external DLP service
  as a mandatory dependency in the first implementation.
- Guarding the language model's final response to a user.
- Scanning binary images, audio, archives, or files referenced by a result.
- Introducing arbitrary Python callbacks in task or inventory metadata.

## Threat Model

### Sensitive Information Disclosure

Network automation output commonly contains secrets in both keys and values:

```json
{
  "username": "automation",
  "password": "correct-horse-battery-staple",
  "authorization": "Bearer eyJ...",
  "private_key": "-----BEGIN PRIVATE KEY-----..."
}
```

Detection must inspect the deserialized structure, not only the final JSON
text. A generic value regex will not identify an arbitrary password, while a
sensitive dictionary key can identify that the complete value must be
redacted.

The baseline detectors will cover:

- Sensitive field names such as `password`, `passwd`, `secret`, `token`,
  `api_key`, `private_key`, `client_secret`, and `community`.
- PEM private key blocks.
- HTTP `Authorization` values using Basic or Bearer authentication.
- Credentials embedded in common URL forms.
- Well-known credential prefixes and formats maintained in a small,
  test-covered detector registry.

The detector will not use generic entropy scoring in the first release. High
entropy is common in hashes, certificates, checksums, and network identifiers,
and would create difficult false positives.

### Context Exhaustion

An MCP server does not reliably know which model will consume a result, its
tokenizer, the size of the existing conversation, or the client's reserved
context budget. The server therefore cannot truthfully decide that a result
"fits the model's context window."

FastMCP will enforce a serialized UTF-8 byte ceiling instead. The default will
be `262144` bytes (256 KiB) per tool call. Operators can lower or raise it
globally or select a different limit for an exact service/task pair. Task
authors can declare only a lower task-specific ceiling; task metadata can never
raise the limit selected by the operator.

The byte limit is an operational safety boundary, not a token estimate. MCP
clients remain responsible for their own conversation-level token budgeting.

### Indirect Prompt Injection

Tool results can contain hostile instructions even when the user supplied safe
arguments. Examples include a device banner, log entry, NetBox custom field,
web page, or document containing text such as "ignore previous instructions"
or instructions to call another tool.

Regex checks can catch narrow deployment-specific patterns but cannot provide
a complete indirect-prompt-injection defense. The first implementation will:

- Treat all task result text as untrusted.
- Allow task and inventory regex rules to block known patterns.
- Preserve a rule type namespace that can later add a classifier-backed
  `prompt_injection` detector without changing the boundary or result actions.
- Encourage least-privilege tool policy and task-specific data minimization as
  independent controls.

Future classifier integration must be optional, versioned, observable, and
explicit about fail-open or fail-closed behavior. It must not send results to
an external service unless the operator configures and authorizes that data
flow.

### Existing Task Output Validation

Task output models already validate task results. FastMCP result guardrails
will not repeat that validation or construct a new aggregate output schema.
They assume the result accepted by the task execution path is structurally
valid and address only whether that result is safe and appropriately sized for
model context.

A worker result with `failed=true` is not automatically a guardrail violation.
Failure information is useful to a model and will be returned if it is bounded
and sanitized. Operators can add task-specific blocking rules when even
sanitized failure detail is inappropriate.

## Task Metadata Contract

Task authors can declare stricter result limits and task-specific rules under
the existing `mcp` dictionary:

```python
@Task(
    input=SomeInput,
    output=SomeOutput,
    mcp={
        "annotations": {...},
        "guardrails": [
            # Existing task call guardrails.
        ],
        "result_guardrails": {
            "max_inline_bytes": 131072,
            "rules": [
                {
                    "description": "Remove a device-local enable secret.",
                    "type": "regex",
                    "match": "(?im)^enable secret\\s+\\S+.*$",
                    "action": "redact",
                    "replacement": "enable secret [REDACTED:CREDENTIAL]",
                },
                {
                    "description": "Do not pass known instruction banners to a model.",
                    "type": "regex",
                    "match": [
                        "(?i)ignore (all |the )?previous instructions",
                        "(?i)system message begins",
                    ],
                    "action": "block",
                    "message": "Task result contained an unsafe instruction pattern.",
                },
            ],
        },
        "prompts": [...],
    },
)
def some_task(...):
    ...
```

`mcp["result_guardrails"]` is NorFab metadata and is not a field accepted by
the MCP SDK `Tool` model. Discovery must pop it from a copied metadata
dictionary before constructing `types.Tool(...)`:

```python
tool_metadata = dict(task["mcp"])
prompts_metadata = tool_metadata.pop("prompts", [])
call_guardrails_metadata = tool_metadata.pop("guardrails", [])
result_guardrails_metadata = tool_metadata.pop("result_guardrails", {})
```

The copy must preserve the original task schema for inspection and later
discovery cycles.

Task metadata has this contract:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `max_inline_bytes` | positive integer | no | Optional task ceiling. It may lower but never raise the operator ceiling. |
| `rules` | list | no | Ordered task-owned result rules. |

Omitted, `None`, or an empty dictionary means the task adds no result-specific
configuration. The FastMCP-wide baseline still applies.

## Inventory Contract

FastMCP-wide result controls live under `tools.result_guardrails`:

```yaml
service: fastmcp
host: "127.0.0.1"
port: 8001

tools:
  result_guardrails:
    enabled: true
    max_inline_bytes: 262144
    disable_builtin_rules: false

    secrets:
      enabled: true
      action: redact
      replacement: "[REDACTED:{detector}]"
      detectors:
        - sensitive_key
        - private_key
        - authorization_header
        - credential_url
        - known_token

    limits:
      - service: nornir
        task: cli
        max_inline_bytes: 131072

    rules:
      - service: nornir
        task: cli
        description: Block a deployment-specific instruction banner.
        type: regex
        match: "(?i)instructions from network administrator:"
        action: block
        message: "Task result contained an unsafe instruction banner."
```

Inventory settings:

| Key | Type | Required | Default | Purpose |
| --- | --- | --- | --- | --- |
| `enabled` | boolean | no | `true` | Master switch. Disabling it requires an explicit operator choice. |
| `max_inline_bytes` | positive integer | no | `262144` | Global serialized result ceiling. |
| `disable_builtin_rules` | boolean | no | `false` | Skip task-owned rules while keeping inventory and FastMCP-wide controls active. |
| `secrets` | dictionary | no | enabled with redaction | Built-in secret detector configuration. |
| `limits` | list | no | `[]` | Exact service/task limit overrides. |
| `rules` | list | no | `[]` | Deployment-specific result rules. |

`enabled: false` disables result processing and should produce a startup
warning. It is provided for compatibility and incident diagnosis, not as the
recommended operating mode.

At most one inventory limit entry may match an exact service/task pair.
Duplicate entries are a configuration error. A matching inventory entry
replaces the global inventory default for that tool, so an operator can make a
specific tool's limit either larger or smaller. The effective ceiling is then
the smaller of that operator-selected limit and any task-owned
`max_inline_bytes` ceiling. This keeps the operator's choice authoritative
while allowing task authors to publish a safer lower bound.

## Rule Contract

Task-owned and inventory-owned rules share the same core model. Inventory
rules add exact `service` and `task` selectors.

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `service` | string | inventory only | Exact NorFab service name. |
| `task` | string | inventory only | Exact NorFab task name. |
| `description` | string | no | Operator-facing explanation. |
| `type` | `regex` | yes | Initial deterministic rule type. |
| `match` | string or list of strings | yes | Python regex checks evaluated with `re.search`. |
| `action` | `redact` or `block` | yes | Transform matching text or withhold the complete result. |
| `replacement` | string | for `redact` | Replacement inserted by `re.sub`. |
| `message` | string | no | Safe client/model-facing message for `block`. |

Rules recursively inspect every string leaf in dictionaries and lists,
including strings in worker failure details. They do not inspect dictionary
key names; the `sensitive_key` secret detector handles structural keys.

When `match` contains multiple expressions, they use OR semantics. Rules run
in author-defined order within each source. Task rules run before inventory
rules unless `disable_builtin_rules` is `true`.

All regex values are compiled during discovery. Invalid rules fail discovery
for that tool and must not be deferred until a tool call.

The first release intentionally omits JSONPath-like selectors. Recursive
inspection gives safe default coverage without introducing another query
language. If later use cases demonstrate excessive false positives, a separate
ADR can define typed result paths.

## Secret Detector Behavior

Secret detection is a FastMCP-wide baseline rather than a rule each task must
remember to declare.

The detector recursively walks dictionaries and lists without mutating the
stored result. It creates a sanitized copy for MCP delivery.

For `sensitive_key`:

- Key matching is case-insensitive and normalizes hyphens and spaces to
  underscores.
- Exact names and deliberately reviewed suffixes are used. Broad substring
  matching is avoided; for example, `token_count` must not be mistaken for an
  API token.
- String scalar values are replaced.
- String leaves inside a list or dictionary stored under a sensitive key are
  replaced while preserving the container shape.
- A non-string scalar under a sensitive key causes the result to be withheld
  because the sanitizer cannot replace it without changing its type.

For value detectors, matching substrings are replaced without returning or
logging the match. The replacement identifies only the detector category, for
example:

```text
[REDACTED:PRIVATE_KEY]
[REDACTED:AUTHORIZATION_HEADER]
[REDACTED:CREDENTIAL_URL]
```

After transformation, FastMCP reserializes the result and rechecks the size.
Redaction preserves the existing container shape and replaces only strings
with strings.

## Enforcement Flow

MCP `tools/call` will follow this sequence:

1. Resolve the MCP tool name and enforce `tools.policy`.
2. Evaluate existing task call guardrails against raw arguments.
3. Generate a job UUID in FastMCP.
4. Call `self.client.run_job(..., uuid=job_uuid)`.
5. Confirm that the client database contains the terminal job record.
6. Keep the original `result_data` unchanged in the client database.
7. Canonically serialize the result with `orjson` and enforce the byte limit.
8. Copy the result and apply built-in secret handling.
9. Apply task-owned and inventory-owned result rules.
10. Reserialize and recheck the transformed result size.
11. Return an explicit MCP `CallToolResult` containing the safe result or a
    bounded error receipt.

The size check runs before content detectors so FastMCP does not perform
potentially expensive recursive and regex scans over content that will not be
sent to the model. An oversized result is safe to leave unscanned because no
part of that result is included in the MCP response.

Guardrail processing must have its own internal exception boundary. An
unexpected serialization, detector, or transformation error fails closed:
FastMCP returns a receipt and does not return the original content.

## Successful Result Behavior

FastMCP will return successful results as `types.CallToolResult` with:

- `structuredContent` containing the sanitized aggregate result.
- `content` containing the JSON serialization required for MCP client
  compatibility.
- `isError=false`.
- `_meta.norfab.job_uuid` containing the job UUID.
- `_meta.norfab.result_guardrails` containing only safe facts such as whether
  redaction occurred and counts by detector category.

No matched values, surrounding excerpts, or raw result fragments may appear in
`_meta` or logs.

Example safe metadata:

```json
{
  "norfab": {
    "job_uuid": "5d2c7c8625bd4ad6aa456c06f8abfa52",
    "result_guardrails": {
      "redacted": true,
      "findings": {
        "sensitive_key": 2,
        "private_key": 1
      }
    }
  }
}
```

Models may not receive MCP `_meta` from every client. Redaction placeholders in
the content must therefore remain self-explanatory.

## Withheld Result Behavior

When the result is too large, blocked by a rule, or cannot be safely processed,
FastMCP returns a bounded `CallToolResult` with `isError=true`. The response
must not include any excerpt from the original result.

Example receipt:

```json
{
  "status": "result_withheld",
  "reason": "result_too_large",
  "message": "The NorFab job completed, but its result is too large for inline model context.",
  "job_uuid": "5d2c7c8625bd4ad6aa456c06f8abfa52",
  "service": "nornir",
  "task": "cli",
  "result_bytes": 917504,
  "max_inline_bytes": 262144,
  "retrieval": "A trusted operator can retrieve the raw result from the FastMCP worker client database using the job UUID. The stored result has not been sanitized."
}
```

Allowed `reason` values in the first release are:

- `result_too_large`
- `result_secret_blocked`
- `result_rule_blocked`
- `result_processing_failed`
- `job_failed_without_result`

The receipt itself has a small fixed maximum size independent of
`max_inline_bytes`. Configured messages will be length-limited and treated as
operator-authored text.

An oversized result is not silently shortened. Truncation could remove the
line that changes the meaning of device state, produce invalid JSON, or omit a
warning while appearing successful. Automatic summarization would introduce a
model dependency and could still expose secrets or follow injected
instructions.

## Retrieving A Withheld Result

The receipt identifies the original job in the FastMCP worker's `NFPClient`
database. Trusted local code can use the existing database abstraction:

```python
job = fastmcp_worker.client.job_db.get_job(job_uuid)
raw_result = job["result_data"] if job else None
```

The stored value is the original raw result. It may be large or sensitive and
must be handled accordingly.

Direct database access is an operator/client workflow, not an MCP model
capability. NorFab will not add a raw `get_result(job_uuid)` MCP tool as part of
this ADR because it would let a model bypass the same size and secret controls.
If NorFab later exposes results as MCP resources or paginated tools, every read
must enforce authorization, byte budgets, and result guardrails again.

A UUID is a locator, not proof of authorization. Database file permissions and
any future result API must enforce access independently.

## Inspection And Observability

`fastmcp.get_tools` with `brief=False` will include the effective task result
configuration after inventory overlays. Secret detector implementation
patterns that would weaken security if disclosed do not need to be published;
detector names and actions are sufficient.

FastMCP will record counters for:

- Results allowed without transformation.
- Results returned after redaction.
- Results withheld by reason.
- Findings by detector or rule identifier.
- Serialized result size and configured ceiling.
- Result-processing failures.

Logs will include job UUID, service, task, tool name, outcome, rule identifier,
detector category, and counts. Logs will not include:

- Full task results.
- Secret matches.
- Surrounding match context.
- Redacted original values.

Inventory may later add `mode: inspect` for staged rollout, but the initial
implementation should not claim protection while forwarding known secrets.
Testing and tuning should happen in a non-production environment or through
metrics that never store matched content.

## Industry Design Signals

This design follows patterns used by current agent and AI safety systems while
keeping NorFab's first implementation local and deterministic:

- The OpenAI Agents SDK distinguishes tool input and tool output guardrails.
  A tool output guardrail can replace rejected content with a safe message to
  the model or raise an exception. See
  [OpenAI Agents SDK tool guardrails](https://openai.github.io/openai-agents-python/guardrails/#tool-guardrails).
- LangChain middleware can apply PII controls specifically to tool results and
  supports redact, mask, hash, and block actions. See
  [LangChain guardrails](https://docs.langchain.com/oss/python/langchain/guardrails).
- Microsoft Prompt Shields treats third-party documents as a separate indirect
  prompt injection surface. Tool and retrieval results have the same trust
  problem. See
  [Azure AI Content Safety Prompt Shields](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/concepts/jailbreak-detection).
- Google Model Armor recommends separate configurations for input and output
  because they have different risks and tuning requirements, and separates
  inspect-only from blocking enforcement. See
  [Model Armor overview](https://docs.cloud.google.com/model-armor/overview).
- Amazon Bedrock Guardrails supports sensitive-information blocking or masking
  and exposes guardrails independently of model invocation. See
  [Amazon Bedrock Guardrails](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html).
- MCP supports structured tool results, error results, and resource links. This
  ADR uses structured content and errors now while leaving guarded resource
  retrieval as a future option. See
  [MCP tools specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

These systems also illustrate a broader lesson: no single detector solves the
problem. Deterministic limits, secret handling, least-privilege tool exposure,
indirect-injection defenses, and application authorization remain separate
layers.

## Candidate Future Controls

The result boundary can support additional controls without changing the
chosen separation from task call guardrails. These are intentionally outside
the first release and should be prioritized from observed NorFab use cases:

| Control | Possible action | Main trade-off |
| --- | --- | --- |
| Prompt-injection classifier | Block or quarantine suspected instructions in retrieved text | Probabilistic results, latency, model/provider dependency, and false positives on legitimate configuration text |
| Malicious URL detector | Redact or block unsafe URLs | Requires reputation data or an external service and clear behavior for private URLs |
| Schema-aware projection | Return only operator-approved result fields | Strong data minimization, but projections must stay synchronized with task schemas |
| Collection and string limits | Reject or explicitly mark overlong lists and individual strings | More precise than whole-result size, but partial data can be mistaken for complete data |
| Data classification labels | Block fields classified as secret, restricted, or regulated | Stronger than inference, but requires task/source systems to publish trustworthy labels |
| Provenance and trust labels | Mark worker, source, collection time, and trust level in MCP metadata | Useful to clients, but metadata alone does not stop a model following hostile content |
| Content-safety filters | Block harmful or policy-restricted text | Often unrelated to network operations and may over-filter logs or command output |
| Hosted DLP integration | Detect organization-specific secrets and regulated data | Better coverage at the cost of external data transfer, availability, latency, and licensing |
| Canary-secret detection | Alert when seeded credentials appear in a result | Good for leakage testing, but not a general secret detector |

Projection and pagination are preferable to generic summarization when a task
regularly produces large results: they can remain deterministic and
schema-aware. They must still expose completeness metadata and pass through the
same secret and injection checks.

## Alternatives Considered

### Add `direction: in | out` To Existing Guardrails

Rejected. It appears uniform in YAML but produces a union model with
direction-specific fields and incompatible actions. It also makes the existing
term `field` ambiguous for deeply nested, worker-keyed results and complicates
the accepted input contract.

### Call The Feature Sanitization

Rejected as the top-level name. Sanitization accurately describes redaction,
but not size rejection, prompt-injection blocking, or a fail-closed processing
error. Sanitization remains one result-guardrail action.

### Return The First N Bytes Or Items

Rejected as the default. Silent partial network results are easy for a model to
misinterpret as complete. Truncation can also break structured output and does
not solve secret or prompt-injection risk in the retained prefix.

### Summarize Large Results Automatically

Rejected for the first release. Summarization consumes model context, adds
latency and vendor coupling, can hallucinate, and must itself be protected from
secrets and indirect prompt injection. A future task-specific summarization
feature could run only after deterministic sanitization and with explicit
operator consent.

### Return An MCP Resource Link For Every Withheld Result

Deferred. MCP resource links are a natural future representation, but NorFab
does not yet have an authorized, guardrail-aware resource reader for client job
records. A link that retrieves raw content would turn the receipt into a policy
bypass. The first release returns a UUID for trusted out-of-band retrieval.

### Count Model Tokens Instead Of Bytes

Rejected at the server boundary. FastMCP does not know the consuming model,
tokenizer, current conversation size, or client context policy. A deterministic
byte ceiling is portable and testable. Clients can enforce an additional token
budget.

### Use Only A Hosted DLP Or Model Armor Service

Rejected as a mandatory dependency. External services introduce availability,
latency, cost, data residency, and credential requirements. The rule model can
gain optional provider-backed detectors later, but the baseline must work
locally.

### Store Only The Sanitized Result

Rejected. The client database is the system of record used for job diagnostics
and operator retrieval. Mutating it would change non-MCP behavior, destroy
forensic detail, and make redaction irreversible. Only the MCP delivery copy is
transformed.

## Implementation Notes

Core worker changes:

1. Keep `mcp["result_guardrails"]` as plain serializable task metadata.
2. Document `result_guardrails` as a NorFab-reserved MCP metadata key alongside
   `prompts` and `guardrails`.
3. Do not add FastMCP-specific detector models to core worker code.

FastMCP worker changes:

1. Add FastMCP-local Pydantic models for inventory, task result metadata, and
   rules.
2. Validate configuration and compile regex values during discovery.
3. Pop result metadata from a copy before constructing the MCP `Tool`.
4. Store the effective result configuration with each registered tool.
5. Generate a UUID before calling `run_job` and pass it through explicitly.
6. Add a pure, independently testable recursive result walker.
7. Add deterministic size, secret, regex, and receipt helpers.
8. Return `types.CallToolResult` explicitly and preserve sanitized
   `structuredContent`.
9. Keep original client database records unchanged.
10. Keep all logging value-free.

The implementation should use one immutable or deep-copied delivery value.
Redaction must never modify the object retained by the client job database.

## Testing

Unit tests should cover:

- Task and inventory result metadata validation.
- Invalid sizes, actions, detector names, and regex expressions fail during
  discovery.
- `result_guardrails` is removed before MCP `Tool` construction without
  mutating task metadata.
- An exact inventory limit replaces the global default, while a lower
  task-owned limit still wins.
- Duplicate exact inventory limit entries fail discovery.
- The default 256 KiB ceiling applies to every discovered tool.
- Exact byte-boundary behavior uses canonical UTF-8 serialized bytes.
- An oversized result returns no result excerpt and includes the correct UUID,
  actual size, and limit.
- The UUID in the receipt retrieves the unchanged original database record.
- Sensitive dictionary key matching is normalized but does not redact benign
  keys such as `token_count`.
- Private keys, authorization headers, credential URLs, and known token formats
  are redacted.
- Secret values split across dictionary/list nesting are handled.
- Multiple findings produce only category counts, never matched values.
- Task regex rules run before inventory regex rules.
- Redact rules replace all intended matches on a copy.
- Block rules return no matched text or surrounding excerpt.
- Worker `failed=true` results are sanitized and returned rather than
  automatically withheld.
- Serialization, detector, and transformation exceptions fail closed.
- Guardrail logs do not contain seeded test credentials.
- The receipt remains below its fixed size cap even with a long configured
  message.
- `enabled: false` preserves compatibility and emits a warning.

Service tests should cover:

- A normal small MCP task result is returned as structured content.
- The MCP result metadata contains the preassigned NorFab job UUID.
- A seeded task result containing a password and private key reaches the client
  database unchanged but reaches MCP only with redaction placeholders.
- A result larger than the configured test ceiling produces
  `isError=true` and `reason=result_too_large`.
- A trusted test client can retrieve that result from the FastMCP worker client
  database using the receipt UUID.
- An inventory regex can block deployment-specific result content without
  modifying task source.
- Existing task call guardrails still reject unsafe arguments before any UUID
  is dispatched.
- Existing `tools.policy` still rejects a disallowed task before result
  guardrails are relevant.

Security regression fixtures must use unmistakably fake credentials. Tests
must assert that raw seeded values are absent from MCP responses, exception
messages, captured logs, and test reports.

## Rollout

1. Add models, discovery validation, and the result-processing helper behind
   configuration.
2. Add unit and service fixtures for size and secret behavior.
3. Enable size limits by default.
4. Enable baseline secret redaction by default after evaluating false
   positives against representative NorFab results.
5. Document how operators tune limits and retrieve raw results by UUID.
6. Consider optional prompt-injection, malicious-URL, and hosted DLP detectors
   only after the deterministic baseline is stable.

## Consequences

- FastMCP gains a defense-in-depth boundary for untrusted tool results.
- Common credentials are kept out of model context while the original job
  record remains available to trusted operators.
- Large results fail visibly and can be retrieved by UUID instead of silently
  consuming model context.
- FastMCP performs extra serialization, traversal, and regex work for each
  result.
- Secret detection will have false positives and false negatives and requires
  maintained fixtures and detector review.
- Returning `CallToolResult` explicitly keeps result-policy behavior in
  testable FastMCP code.
- Operators must protect client database access because it contains raw,
  unsanitized results.
- Indirect prompt injection risk is reduced only for configured patterns in the
  first release; it is not eliminated.

## Follow-Up Questions

The following items require separate decisions after the first implementation
has production evidence:

- Should guarded job results be exposed as authenticated, paginated MCP
  resources with per-read limits?
- Should selected tasks support an explicit, schema-aware projection rather
  than returning their full result?
- Which optional prompt-injection or DLP providers meet NorFab's deployment,
  privacy, and offline requirements?
- Should a future classifier failure default to block globally or be
  configurable per task?
- Should MCP clients be able to advertise a smaller per-call byte or token
  budget that FastMCP can honor without exceeding the operator ceiling?
