# FastMCP Server Guardrail Interface

**Status**: Proposed. This behavior is not implemented yet.

## Inventory

```yaml
service: fastmcp
tools:
  result_guardrail_size_limit: 32768
  result_guardrail_secrets_reduction: true
```

This tools-level setting counts len(str(delivery_result)) for the complete combined structure across all workers, after authored rules and enabled redaction. It does not count JSON, SDK formatting, or transport bytes. Accepted values are 0 or integers at least 4096. Existing task `type: limit` continues to count bytes. The existing disable_builtin_guardrails flag disables task-authored guards only. Inventory rules remain active. Server redaction and size limiting have independent controls. result_guardrail_secrets_reduction=false disables only built-in server redaction. A size limit of 0 disables only the built-in server size limit.

## Result Behavior

Server redaction runs after task and inventory rules and before final size measurement. Credential values become the literal text `REDUCTED`. For example, `password 12345` becomes `password REDUCTED`. Quoted and structured credentials are covered. Detailed matching requirements appear in [Specification](../spec.md).

Results at or below the threshold retain their existing structure. Oversized combined results are replaced with a standard Result having result=None, failed=false, and exactly one errors entry. Preserve the original UUID when available. Do not return any preview or original diff. For example, the errors list contains:

```json
["result omitted because the combined task structure is 50000 characters, exceeding tools.result_guardrail_size_limit=32768. Increase this inventory setting or set it to 0 to disable the server size limit."]
```

The error reports actual measured/configured values. This threshold does not promise a bound on final SDK-encoded text or the diagnostic envelope. MCP output handling must accept the standard omission response for typed tools too.

## Job Retrieval Scope

Job retrieval and Python recovery instructions are excluded. Existing job_details and other job APIs stay unchanged.

## Input Guardrail Actions

Proposed inventory example. No task approval rule is installed automatically.

```yaml
tools:
  guardrails:
    - service: nornir
      task: cfg
      action: request_approval
      description: Confirm configuration changes before dispatch.
      message: Approve this configuration operation?

    - service: nornir
      task: cli
      action: request_approval
      field: commands
      type: contains
      match: commit confirmed
      message: Approve this CLI operation?
```

The first rule matches every nornir.cfg call only when the operator configures it. The second matches the existing commands predicate. Omit action to keep reject behavior. A matching task-owned reject still blocks the CLI example. Approval does not override it.

Reject requires field/type/match. Approval may omit all three. Partial predicates and explicit null values are invalid. Service/task selectors remain exact, not globs. An absent argument does not satisfy a conditional rule. Existing list and case matching behavior stays unchanged.

Evaluate all rejects before prompting. If no reject matches, combine approval reasons into a single form. No matched approval means no form. Inventory rules remain active when tools.disable_builtin_guardrails disables task-authored rules. There is no built-in nornir.cfg approval rule or approval feature flag.

## Confirmation Exchange

Use MCP form elicitation through the originating session. The form asks for one required boolean approved, without a default. The prompt identifies service/task, rule reasons, workers=all, and a sanitized argument summary capped within a 4096-character message. Mark incomplete summaries and unresolved file references explicitly. It never requests secrets.

| Response Or Condition | Outcome |
|---|---|
| accept and validated approved=true | Dispatch the same argument snapshot once. |
| accept and approved=false | Reject without dispatch. |
| decline or cancel | Reject without dispatch. |
| Invalid or missing response fields | Reject without dispatch. |
| Missing form capability or URL-only client | Reject without dispatch. |
| Timeout after 120 seconds or SDK/transport failure | Reject without dispatch. |
| Originating request cancelled before dispatch | Cancel without dispatch. |

Denials use safe MCP tool errors through the existing McpError path. Clients must not retry as an automatic approval bypass. Every new call repeats rule evaluation and confirmation. No approved kwarg or cached confirmation is accepted. Existing non-MCP Python task calls are unaffected.

## Client Compatibility And Trust

The installed mcp 1.30.0 SDK supports Context.elicit and attaches the originating request ID. Its generic capability check does not distinguish form mode, so inspect negotiated elicitation modes directly. Legacy empty elicitation capability means form support. URL-only does not.

The host controls how confirmation is presented and can answer automatically. This feature cannot verify that a human clicked. Use a trusted host configured for interactive confirmation. MCP authentication and deployment authorization remain necessary. Clients/transports that cannot complete form elicitation fail closed. No URL approval web application or out-of-band identity system is included.
