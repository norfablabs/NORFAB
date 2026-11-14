# Implementation Plan: FastMCP Server Guardrails

**Working Branch**: `master`. **Feature Identifier**: `003-fastmcp-server-guardrails` (reported by setup-plan, not an existing Git branch). **Date**: 2026-11-14.

**Specification**: [FastMCP Server Guardrails](spec.md). **Acceptance**: Proposed. **Implementation**: Not started.

## Summary

Add rule-driven request_approval input actions using the installed SDK form elicitation API. Support is available by default with no built-in approval rule for any task. Preserve reject as the default action.

Extend FastMCP models with a small validated server-guardrail settings model. Apply fixed server redaction and a final aggregate character threshold at the MCP delivery boundary. Retain existing task guardrails and untouched database results. Oversized aggregates become a standard Result with result=None, failed=false, and one actionable errors entry. No result preview is returned.

## Technical Context

- Language: existing Python support `>=3.10,<3.15`. Develop and validate with Python 3.12.
- Dependencies: existing Pydantic, orjson, Python re, MCP SDK 1.30.0, and diskcache 5.6.3. No new dependency.
- Storage: existing SQLite `ClientJobDatabase`, owned by the FastMCP internal NFPClient. No schema migration.
- Testing: pytest, existing FastMCP public MCP/client integration fixtures and Docker/Invoke framework.
- Platforms: existing Windows/Linux worker deployments.
- Type: service-worker enhancement. Scope is the central tool result boundary and settings model.
- Performance: fixed compiled regex patterns and direct recursive traversal. No extra network calls for result protection. Approval adds one client form exchange with a 120-second bound. No LLM classification, new caches, or dynamic regex configuration. No unsupported latency target. The size threshold is not a memory cap.
- Constraints: preserve public task inputs and existing byte-limit behavior. Server result protections have independent controls. Task-default disable does not affect them.

## Constitution Check

Pre-research: PASS. Scope is the requested guardrail enhancement and its necessary delivery integration. Existing client/database boundaries remain intact. No production application edits occur during planning.

Post-design: PASS. Use existing models, serializer, database reader, and test fixtures. One focused settings model, one primitive approval form model, the existing input rule model, and direct call/delivery stages are sufficient. No middleware hierarchy, plugin registry, new service, or schema migration. Validate once at inventory load. Favor a few public integration scenarios plus focused model/serialization checks where the public path cannot isolate the boundary. Documentation and changelog changes describing shipped behavior belong to implementation. No exceptions are required.

## Project Structure

All feature artifacts live under `docs/development/specs/003-fastmcp-server-guardrails/`: spec.md, plan.md, research.md, data-model.md, quickstart.md, contracts/server-guardrails.md, and checklists/requirements.md. `tasks.md` is generated separately by speckit-tasks.

Affected implementation locations:


- `norfab/workers/fastmcp_worker/fastmcp_models.py`: strict settings model, action and predicate validation, primitive approval response model, and field documentation. Leave TaskMCPResultGuardrail semantics intact.
- `norfab/workers/fastmcp_worker/fastmcp_worker.py`: inventory validation in initialization, fixed patterns, delivery-copy redaction, UUID capture, final aggregate size check, and safe call logging. Extend the existing matcher to determine reject versus approval outcomes. Await approval in call_tool before run_job.
- `tests/services/fastmcp/test_guardrails.py` and existing MCP helpers: action matching, elicitation callbacks, no-rule behavior, and no-dispatch denial coverage.
- `tests/services/fastmcp/test_result_guardrails.py`: extend related integration coverage using existing fixtures.
- `tests/nf_tests_inventory/`: isolated FastMCP settings or fixtures only as needed.
- `docs/workers/fastmcp/services_fastmcp_service_inventory.md`: settings, ordering, size units, and limitations.
- `docs/workers/fastmcp/services_fastmcp_service.md` and `docs/norfab_changelog.md`: concise delivered-behavior updates during implementation.

## Phase 0: Research

Complete. [Research](research.md) resolves unchanged job storage, serialization, ordering, disable behavior, redaction coverage, and additional guardrails. No unresolved design questions block task generation. Defaults are proposed decisions for maintainer review.

Approval research also resolves installed SDK context access, form capability checks, one-call consent, fail-closed outcomes, and client trust. Follow SDK 1.30.0 APIs rather than newer main-branch examples.

## Phase 1: Design

Complete. [Data Model](data-model.md), [Interface Reference](contracts/server-guardrails.md), and [Validation Guide](quickstart.md) define configuration and observable behavior.

Processing sequence: allowed-task policy -> snapshot arguments -> evaluate input guards -> reject if any reject matches -> await one form if approval rules match -> dispatch and persist raw result -> existing ordered result rules on a delivery copy -> server redaction -> len(str(combined delivery structure)) -> omit result with one error if exceeded -> MCP SDK encoding. Capture the original UUID before transformations. Size omission sets failed=False and does not classify task execution as failed. Apply the final server stage even when existing limit rules return a standalone Result rather than an aggregate.

Result redaction uses tools.result_guardrail_secrets_reduction (StrictBool, default true). Size limiting is independently controlled by result_guardrail_size_limit. A value of 0 disables only the built-in server size limit. Disabling server redaction does not disable task-authored or inventory replacements.

Measure once across all workers with len(str(delivery_result)). Preserve the structure when its count is at or below the configured limit. Above it, replace the aggregate with Result(result=None, failed=False, errors=[message], juuid=original_uuid). The single message explains the measured size, limit, and tools.result_guardrail_size_limit setting, including 0 to disable. No original result, diff, preview, or recovery instructions remain in that envelope. Do not try to fit the diagnostic response within the same threshold or budget SDK encoding.

Ensure the MCP-facing output declaration supports the standard guardrail failure envelope as well as normal tool results. Keep non-MCP task models unchanged. Verify a typed tool through a real MCP client so a schema-validation error cannot replace the useful size-limit message. Redaction of typed values/keys still needs compatible MCP output handling and is not resolved merely by omitting oversized results.

## Approval Integration

Use `ctx = self.app.get_context()` inside the existing low-level asynchronous call_tool handler, then `await ctx.elicit(message, schema=TaskMCPApprovalResponse)`. The SDK carries the originating request ID. No migration to the high-level tool decorator or new middleware is needed. Check `ctx.session.client_params.capabilities.elicitation` explicitly. SDK check_client_capability only checks capability presence, not form mode.

Keep matching synchronous and approval I/O asynchronous. Reject rules retain their current error behavior. For approval denials, use the existing McpError mechanism with INVALID_PARAMS and a fixed safe reason such as approval declined, cancelled, unavailable, invalid, or timed out. No raw exception text. Bound the await with asyncio.wait_for (Python 3.10-compatible). Propagate request cancellation without dispatch. Do not swallow cancellation into an accepted result.

Snapshot arguments before matching. Reuse the planned server sanitization routine for a copy used in the prompt. Cap the complete prompt at 4096 characters and clearly label truncated summaries. Include tool identity and workers=all before the argument summary. Do not expose raw configuration in logs or the form. Reasons come from configured message/description and are sanitized too. Never derive the approval decision from prompt text.

The existing synchronous run_job can block the server loop after approval. Record this limitation and retain the current dispatch implementation. Do not bundle concurrency refactoring or durable approval state into this feature. A disconnected client cannot resume consent on a new request.

No default nornir.cfg rule and no new approval-enable flag are planned. Existing task-default disable behavior applies to task-authored approvals. Deployment-defined approvals stay active.

## Implementation Slices

1. Add strict settings validation and fixed credential rules. Cover invalid inventory and representative labelled/structured secrets.
2. Integrate server redaction after existing rules, including metadata and standalone limit-result shapes. Remove raw call-argument logs in this path. Verify unchanged stored results and safe failure.
3. Add final combined-structure size enforcement and omission errors. Verify multi-worker aggregation, Python string counting, equality, UUID context, typed-tool output handling, and existing-rule interactions.
4. Extend input models with action and conditional validation. Add synchronous match outcome collection, reject precedence, and one bounded request-scoped elicitation step before dispatch. Verify no-rule behavior and fail-closed outcomes through MCP callbacks.
5. Update user documentation and draft changelog. Run focused integration, quality checks, and docs build. Inspect Docker reports for actual results.

These are planning slices, not generated executable tasks. No implementation or test completion is claimed.

Job retrieval is out of scope. Do not change job_details or add recovery tasks or instructions.

## Complexity Tracking

No constitution violations or additional infrastructure.
