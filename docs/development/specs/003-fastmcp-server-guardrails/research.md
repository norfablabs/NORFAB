# FastMCP Guardrail Research

**Status**: Design research complete. Implementation not started.

## Existing Behavior And Ordering

Decision: Keep `TaskMCPResultGuardrail` and authored rules unchanged. Add server protection after them.

Rationale: `make_task_result_guardrails` builds task rules followed by matching inventory rules. `apply_task_result_guardrails` deep-copies raw results and supports ordered byte limits, replacement, and withholding. A limit rule may return early with a standalone Result. A separate final stage covers that shape and prevents later authored replacements from undoing server redaction.

Alternatives considered: Inject server rules into every task's metadata. Rejected because current rules inspect only `result` and `diff`, and an early limit return could bypass final protection.

Source: `norfab/workers/fastmcp_worker/fastmcp_worker.py`, make_task_result_guardrails, apply_task_result_guardrails, and fastmcp_start.call_tool.

## Configuration And Character Counting

Decision: Keep tools.result_guardrail_size_limit default 32768, accept 0 to disable or integers at least 4096. Measure len(str(delivery_result)) once for the complete combined worker structure after authored rules and enabled server redaction. Do not use per-worker limits for this server threshold.

Rationale: User resolved analysis finding A1 by selecting the combined dictionary string representation. SDK indentation, JSON escaping, UTF-8 encoding, and transport framing do not enter this measurement. It is a result omission threshold rather than a final encoded-response budget.

Alternatives considered: Compact orjson size and final MCP text size. Superseded by the user's explicit counting choice. Existing task byte-limit semantics remain unchanged.

## Oversized Result Omission

Decision: Replace oversized aggregate data with the existing Result envelope, result=None, failed=false, errors=[one meaningful size/configuration message], and original UUID when available. Do not return a preview or diff.

Rationale: User resolved analysis finding U1 for size failures by removing the task result altogether. The error explains actual count/limit and tools.result_guardrail_size_limit, including 0 to disable. Stored results remain unchanged.

Alternatives considered: Truncated JSON previews and text notices inside result. Both are superseded. SDK output validation must accept the standard omission envelope for typed tools. Separate schema compatibility for redaction remains an implementation design concern.

## Job Retrieval Scope

Decision: Omit job retrieval and recovery instructions. Do not change job_details or add a retrieval task.

Rationale: User explicitly removed retrieval from this feature. Truncation includes a short notice and existing UUID when available. Raw stored results remain unchanged.

Alternatives considered: Local database access, a new FastMCP retrieval task, and extending inherited job_details. All are excluded from this scope.

## Credential Coverage And Failure

Decision: Fixed precompiled Python regex substitutions for labelled free text and PEM blocks, plus whole-value replacement under credential dictionary keys. Traverse the whole delivery copy. Sanitize inline credentials in keys and safely withhold mappings with resulting collisions. Return a fixed safe error if processing fails.

Rationale: Existing task replace rules ignore keys and diagnostic metadata. Text-only replacement misses structured numeric credentials. Redaction must precede preview slicing so partial secrets cannot survive through boundary cuts. Logging argument dictionaries before guards is another direct disclosure path.

Alternatives considered: Universal secret detection, arbitrary configurable regex, external DLP, and LLM classification. These introduce false assurance, dependency cost, or unbounded pattern behavior. Fixed patterns remain best effort. Existing detailed Nornir CLI patterns remain valuable.

Sources: `norfab/workers/fastmcp_worker/fastmcp_models.py`, TaskMCPResultGuardrail. `norfab/workers/nornir_worker/cli_task.py`, MCP_RESULT_GUARDRAILS. `tests/services/fastmcp/test_result_guardrails.py`.

## Additional Protections

Decision: Include diagnostic redaction and safe call logging. Retain policy, existing call guards, and optional injection regex. Include configured client-mediated approval. Defer new input budgets, independent human identity verification, rate controls, and resolved-file inspection.

Rationale: Included items close direct leaks in the touched delivery path. Deferred items require independent requirements and enforcement boundaries. Result truncation does not constrain source-job computation, database retention, or memory use.

Alternatives considered: Bundle all guardrails into one configurable framework. Rejected under the simplicity and surgical-scope principles.

## Request Approval Through Elicitation

Decision: Extend input guardrails with action=reject (default) or request_approval. Enable the capability without installing any built-in approval rule. Inventory or task metadata explicitly selects affected calls. In particular, nornir.cfg has no automatic approval rule.

Rationale: User review explicitly excludes a built-in nornir.cfg rule. Existing selector and predicate mechanisms already identify the relevant calls. Approval-only rules can omit all predicate fields to match the selected task unconditionally. Existing reject rules stay strict and keep their behavior.

Alternatives considered: Prompt for all configuration calls by default. Rejected by user instruction. Add a new approval-policy section or enable flag. Rejected because the requested action fits the existing guardrail list.

## SDK And Protocol Findings

Decision: Use installed mcp 1.30.0 Context.elicit through self.app.get_context() inside low-level call_tool. Await a primitive required StrictBool approved field using a bounded timeout, then inspect action and validated data.

Rationale: Local SDK Context.elicit delegates to elicit_with_validation with the active session and originating request ID. The helper supports accept, decline, and cancel. Its own docstring notes a client agent may generate the answer automatically. This is client-mediated confirmation, not independent proof of a human.

Local sources: mcp/server/fastmcp/server.py (get_context and Context.elicit), mcp/server/elicitation.py (elicit_with_validation), mcp/server/session.py (elicit_form and check_client_capability), mcp/types.py (ElicitationCapability), all inspected in the installed 1.30.0 package.

Protocol reference: [MCP 2025-11-25 elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation) describes form and URL modes, client capability advertisement, primitive schemas, and accept/decline/cancel. Empty elicitation capability retains legacy form support. Forms must not request credentials. This versioned reference matches the installed session-style API. Newer upstream main examples are not assumed compatible.

Alternatives considered: Sampling asks an LLM rather than a user. Tool annotations do not enforce confirmation. URL mode requires a separate trusted approval application and authenticated decision store. A pause/resume task or persisted queue adds unnecessary state. These are excluded.

## Rule Precedence And Safe Dispatch

Decision: Evaluate rejects before approval, collect matching reasons, and send one form for one immutable argument snapshot. Reject every non-positive outcome and do not create a NorFab job while waiting. Timeout is 120 seconds, using asyncio.wait_for for Python 3.10 compatibility.

Rationale: Authored rule order must not allow consent to bypass a prohibition. Existing all-reject lists retain their outcomes. The argument snapshot and request context avoid approval reuse. No durable approval entity is needed.

Sources: existing make_task_guardrails, check_tool_call_guardrails, and fastmcp_start.call_tool. The current handler uses low-level registration, so high-level tool parameter injection is unnecessary. SDK check_client_capability checks only elicitation presence. Explicit mode inspection is required to reject URL-only hosts.

Alternatives considered: First matching approval wins, one prompt per rule, client-supplied approved kwargs, or cached consent. Rejected because they weaken reject precedence, cause duplicate prompts, or make consent reusable.

## Compatibility And Limitations

Decision: Retain existing tools.disable_builtin_guardrails semantics for task-authored input rules, including new approvals. Inventory approval rules stay active. Reuse result sanitization for a bounded prompt summary. Do not upgrade the SDK or refactor synchronous job dispatch as part of approval.

Rationale: Preserve existing operator controls and minimize changes. Approval only inspects inline arguments. File references may resolve later. Synchronous run_job still blocks the event loop after consent, which may delay other calls. Supported interactive client behavior must be tested, not inferred from capability presence alone.

Alternatives considered: Claim verified human authorization, resolved-content approval, or universal host support. These promises are unsupported by the inspected protocol and existing architecture.

## Clarified Result Controls And Worker Review

Decision: Add tools.result_guardrail_secrets_reduction as a strict boolean defaulting to true. Keep size control independent through result_guardrail_size_limit. A value of 0 disables only the built-in server size limit.

Rationale: User explicitly requested this field name and independent control. Disabling built-in redaction does not remove existing task or inventory replacement rules. Approval prompts must still sanitize their summaries, even if result redaction is disabled.

Worker review confirmed job_details uses the worker database while MCP-dispatched jobs belong to the internal client. No changes to either retrieval interface are planned. The user explicitly excluded retrieval after that review.
