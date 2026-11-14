# FastMCP Guardrail Data Model

## Server Settings

Proposed model: `FastMCPServerGuardrails`, located in fastmcp_models.py. Extract only its declared setting from the existing tools inventory so unrelated tools keys retain their current behavior.

| Field | Type | Default | Validation |
|---|---|---|---|
| `result_guardrail_size_limit` | StrictInt | 32768 | 0 disables the built-in server size limit. Otherwise at least 4096 characters. Reject 1 through 4095. |
| `result_guardrail_secrets_reduction` | StrictBool | true | False disables built-in result redaction only. |

Validate at worker initialization before serving requests. No per-call argument controls or per-task overrides. Fixed server credential rules are code-defined, enabled by default via result_guardrail_secrets_reduction, and not disabled by `tools.disable_builtin_guardrails`.

## Delivery Data

Input is the existing raw worker aggregate or None. Existing task rules may turn it into a standalone Result. Capture the UUID before those transformations. Size omission uses failed=False because limiting delivery does not constitute a task failure. The server stage supports both shapes without assuming every top-level value is a worker result.

- Full delivery: same structure, sanitized across string values, sensitive keys, and metadata when built-in redaction is enabled.
- Oversized delivery: existing Result model with result=None, failed=false, exactly one errors item explaining the measured size, limit, and tools.result_guardrail_size_limit configuration, plus original UUID when available. No preview or original diff.
- Processing failure: fixed safe error Result with failed=true. No exception text or original content.
- Missing raw result: unchanged None.

The threshold measures len(str(delivery_result)) on the complete combined structure, including worker keys and metadata. It does not constrain SDK encoding or the diagnostic response. MCP output handling must support the standard omission envelope without changing non-MCP task output models. No new database entities, persistence fields, task input models, or state transitions. The source ClientJobDatabase record remains unchanged.

## Input Rule Extension

Extend existing TaskMCPGuardrail. Keep extra=forbid and current strict string, match-list, and regex validation.

| Field | Proposed Behavior |
|---|---|
| action | Literal reject or request_approval. Default reject. |
| field, type, match | Required for reject. For request_approval omit all three or supply all three. Omission matches every call to the selected service/task. Explicit null is invalid. |
| description, message | Existing optional strings. Supply a sanitized reason in the approval prompt. |

Inventory service and task selectors remain required exact strings. Task-authored metadata gets its service/task from discovery. Result guardrail models do not gain action. Existing input match case rules and list traversal remain unchanged.

## Approval Response And Lifecycle

Add TaskMCPApprovalResponse in fastmcp_models.py: required approved: StrictBool with a descriptive Field, no default, extra=forbid. It is an internal elicitation schema, not a tool parameter or persisted database model.

Transient state: matched -> rejected, or awaiting confirmation -> accepted/denied/cancelled/timed out/unavailable. Only accepted plus approved=true transitions to dispatch. No job is created while awaiting confirmation. Consent expires when its request ends and is not stored for reuse. No approval queue, database table, public endpoint, token, or new task model is introduced.

Approval availability has no enable flag and no built-in task rules. The existing disable_builtin_guardrails setting suppresses task-authored approval rules only.

## Job Retrieval Scope

No job retrieval models, arguments, tasks, or database changes. Existing job_details behavior stays unchanged.
