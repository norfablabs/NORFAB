# FastMCP Server Guardrails

**Date**: 2026-11-14. **Acceptance**: Proposed, awaiting maintainer review. **Implementation**: Not started.

## Purpose And Scope

Apply built-in result protection to every FastMCP tool call, including tools with no task-authored guardrails. Extend input guardrails with client-mediated approval using MCP form elicitation. Approval support is available by default, but no built-in rule requires approval for nornir.cfg or any other task. Limit MCP delivery size, redact common labelled credentials, and leave stored original job results unchanged. This feature changes MCP dispatch gating and result delivery only. It does not change service task arguments or stored results.

## Clarifications

### Session 2026-11-14

- Q: Should this feature add or change job retrieval? -> A: No. Omit job retrieval, recovery instructions, and job_details changes from this feature.

- Q: Should operators be able to disable built-in result redaction and size limiting independently? -> A: Yes. Keep result_guardrail_size_limit for size control and add result_guardrail_secrets_reduction, a boolean enabled by default, to switch built-in secret redaction on or off.

- Q: Which value should disable result_guardrail_size_limit? -> A: 0 disables size limiting independently of secret redaction.

- Q: Should enabled size limits retain the proposed minimum of 4096 characters? -> A: Yes. Accept 0 to disable or integers of at least 4096. Reject smaller positive values.

- Review A1: Measure the combined task result structure across all workers once using len(str(delivery_result)). This measures the Python dictionary string representation, not JSON or MCP transport encoding.
- Review U1: When the limit is exceeded, omit the task result entirely. Return a standard Result with result=None, failed=false, and errors containing exactly one meaningful message explaining the size limit and its configuration. No preview.

- Review U2: Set failed=False for a size-limit omission response. The task did not fail merely because its result exceeded the delivery limit. Keep the single size/configuration error message.

## User Scenarios And Acceptance

1. An operator sets `tools.result_guardrail_size_limit`. Measure the combined structure across all workers. If it exceeds the limit, return result=None and one errors entry explaining the measured size, configured limit, and how to change or disable it. A structure at the limit is retained.
2. Results containing `password 12345`, `password=12345`, or `"secret": "abc"` deliver `REDUCTED` in place of the credential value. Labels, separators, and surrounding useful text remain readable.
3. Nested results, diffs, messages, errors, resources, and sensitive dictionary keys cannot bypass server redaction. Numeric and other non-string values under credential keys are replaced too. Raw stored results remain unchanged.
4. Guardrails leave stored original job results unchanged. This feature adds no job retrieval behavior.
5. Existing result guardrails retain their authored ordering, selector behavior, byte-limit semantics, and disable-switch behavior. Existing input rules without action continue to reject. Server result protections use independent inventory settings and are unaffected by disabling task defaults.

6. An operator adds `action: request_approval` for a chosen service/task, optionally with an argument predicate. Matching calls pause before job dispatch. Only an accepted form with explicit `approved: true` permits that exact call.
7. A matching reject rule prevents dispatch even when an approval rule also matches. Decline, cancel, unsupported clients, invalid responses, and timeout never dispatch a job.
8. With no approval rules configured or authored by a task, no approval prompt is generated. There is no built-in nornir.cfg approval rule.

## Requirements

- FR-001: Add `tools.result_guardrail_size_limit`, a strict integer counting Unicode characters, default 32768. A value of 0 disables only the built-in server size limit. Enabled limits have a minimum of 4096 characters as the accepted configuration floor. Reject booleans, strings, null, negative values, and positive values below 4096 at inventory loading. Existing task/inventory limit rules remain active when the server limit is disabled.
- FR-002: Add tools.result_guardrail_secrets_reduction as a StrictBool with default true. False skips built-in result secret redaction only, leaving size limits and existing task/inventory result rules unchanged. When enabled, apply built-in server redaction after existing task/inventory transformations and before the final size check. Use `REDUCTED` consistently, including with repeated application. Cover case-insensitive password, passwd, pwd, secret, token, api_key, api-key, and authorization labels. Handle whitespace, equals, colon, quoted values, bearer/basic authorization values, and multiline PEM private keys. Match complete credential labels rather than substrings in ordinary words.
- FR-003: When built-in server secret redaction is enabled, redact the entire delivery copy, including dictionary keys and metadata. Replace values under sensitive keys as a unit, without traversing their original value. For keys containing inline credentials, sanitize the key. If sanitized keys collide, withhold that containing mapping with a fixed safe marker rather than silently overwrite data.
- FR-004: When enabled, measure the complete delivery structure combined across all workers once using len(str(delivery_result)), after authored rules and enabled built-in redaction. Include worker keys, results, diffs, and metadata. Do not apply the threshold per worker. Count Python string characters, not compact JSON, SDK text, UTF-8 bytes, or transport framing. Existing task limit rules retain their byte-based measurement.
- FR-005: Retain the delivery structure when its measured size is at or below the limit. When exceeded, replace the aggregate with a standard Result whose result is None, failed is false, and errors contains exactly one message. The message states the measured character count, configured limit, that the result was omitted, and how to change tools.result_guardrail_size_limit or set it to 0 to disable. Preserve the original job UUID when available. Do not include a preview, original result/diff, or recovery instructions. This is an omission threshold, not a guarantee about the final diagnostic response's encoded size. Ensure MCP output handling accepts this failure envelope rather than returning an SDK schema-validation error.
- FR-006: Capture the original UUID before task rules can reshape the aggregate. When unavailable, omit the job UUID. Never invent a UUID, database path, job, or successful completion. Preserve `None` for absent raw results.
- FR-007: Job retrieval is out of scope. Do not add a retrieval task, change job_details, or include Python recovery instructions in size-limit errors. Leave existing job APIs and stored results unchanged.
- FR-008: Compile fixed patterns once, validate new inventory settings once, and use existing result models and deep-copy behavior. If redaction/serialization fails, return a fixed safe error without original content or exception text. Retain safe UUID context where available. Never fall back to raw results.
- FR-009: Logs contain tool identity, counts, and size-limit outcomes only. Remove raw argument logging in the touched tool-call path. New logs and events start lowercase and events use `severity`.

- FR-010: Extend TaskMCPGuardrail with `action`, accepting only `reject` and `request_approval`, default `reject`. Existing rules and service/task exact selectors retain their meaning. No client-visible approval argument is added to service task schemas.
- FR-011: For request_approval only, allow `field`, `type`, and `match` to be omitted together for an unconditional selected-task rule. If any is supplied, all three are required and existing predicate behavior applies. Reject rules retain the required predicate triple. Missing selected argument does not match a conditional rule. Explicit null values are invalid.
- FR-012: Evaluate every applicable input guardrail before dispatch. A matching reject wins regardless of rule order. With no rejects, combine matching approval rules into one elicitation request. A positive response cannot bypass policy or rejection. With no matching approval rules, retain current dispatch behavior.
- FR-013: Approval support is enabled without a feature flag. Do not add built-in approval rules for any task. Task authors may declare approval rules in task MCP metadata. Operators may declare them under tools.guardrails. Existing tools.disable_builtin_guardrails disables task-authored rules, including approval rules. Inventory-defined approval rules remain enabled. No changes to this switch's scope.
- FR-014: Use request-scoped MCP form elicitation with a required `approved: StrictBool` response field and no positive default. Continue only when action is accept and validated approved is exactly true. Do not ask for credentials. The confirmation message includes service/task, matched reasons, actual all-workers dispatch scope, and a bounded sanitized argument summary. Approval summaries remain sanitized even when result_guardrail_secrets_reduction is false. State when that summary is incomplete or contains unresolved references.
- FR-015: Explicitly check form capability before elicitation. Accept legacy empty elicitation capability as form support, accept explicit form support, and reject missing or URL-only support. Decline, cancel, false, invalid/missing content, timeout, disconnect, and SDK errors fail closed. Return a safe MCP tool error and create no NorFab job. Do not mislabel refusal as a worker execution failure.
- FR-016: Bound elicitation waiting to 120 seconds using a cancellation-aware asynchronous timeout compatible with supported Python versions. Bind consent to the originating request and a deep snapshot of the submitted arguments. Dispatch that snapshot once. Do not cache approval, change arguments during the wait, accept approval through tool kwargs, or reuse consent for retries. Cancellation before dispatch creates no job. Cancellation after dispatch does not promise worker rollback.
- FR-017: Use the existing authenticated session and transport. Audit request/tool identity and approval outcome without argument values or form content. Document that elicitation is client-mediated confirmation, not independently authenticated proof of a human or a replacement for access control. Clients can auto-answer. Human operation requires a trusted client configured to display the form.

## Additional Guardrails Considered

| Candidate | Decision | Reason |
|---|---|---|
| Avoid raw argument logging | Include | Current call logging can disclose passwords before result redaction. |
| Redact error and diagnostic metadata | Include | Credentials can appear outside `result` and `diff`. |
| Prompt-injection phrase blocking | Keep optional existing regex rules | Text matching cannot reliably establish whether content is an instruction. |
| Input size, nesting, and list-count limits | Defer | Require separate limits and workload evidence. A delivery limit does not bound worker execution or memory. |
| Rule-driven approval | Include | request_approval action uses form elicitation before dispatch. No built-in task approval rules. |
| Rate limits and concurrency quotas | Defer | Separate resource-management design. |
| URL/file content inspection | Defer | Requires service-side resolution and authorization. Inline guards cannot inspect fetched content. |

## Limitations And Non-Goals

Pattern redaction is best effort, not a guarantee that every secret is detected. Unlabelled, encoded, and novel credential formats can escape detection. The stored database remains sensitive. This work does not change database permissions, retention, authentication, transport framing, prompts, or events. Job retrieval is out of scope. Non-MCP task dispatch and delivery remain unchanged. Approval applies only to matching MCP tool calls. Inline predicates do not inspect resolved nf:// content. A confirmation is not authorization for future calls or proof that referenced content remains unchanged. No arbitrary operator-supplied regex engine or new dependency is added. Large results still arrive and are copied before delivery protection.

## Success Criteria

When size limiting is enabled, combined structures above the threshold are omitted with result=None, failed=false, and exactly one actionable errors entry. Structures at the threshold are retained. The threshold uses len(str(delivery_result)) across all workers. When built-in secret redaction is enabled, selected credential examples are absent from every MCP result surface. Original database records are byte-for-byte unchanged by guardrails. Matching approval calls dispatch only after explicit valid confirmation. All denial paths create no NorFab job. Calls with no approval rules remain prompt-free. Existing guardrail integration tests continue to pass. See [Plan](plan.md), [Research](research.md), [Data Model](data-model.md), [Interface Reference](contracts/server-guardrails.md), and [Validation Guide](quickstart.md).
