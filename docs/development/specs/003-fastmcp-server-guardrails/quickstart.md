# Validate FastMCP Server Guardrails

**Status**: Future implementation validation. These scenarios do not imply the feature exists today.

## Prerequisites

Use Python 3.12 and the existing FastMCP test environment. Read the [testing framework](../../norfab_developing_and_testing_framework.md) and repository guide `docker/norfab-docker-tests/README.md`. Run commands from the repository root.

```bash
uv sync --locked --python 3.12 --extra full --extra docs
uv run inv --list
uv run inv docker-tests-build
uv run inv docker-tests-fastmcp
```

Inspect the current Docker test report and JUnit results. Confirm the FastMCP task name in `inv --list` before executing if automation changes.

## Focused Validation Scenarios

Extend `tests/services/fastmcp/test_result_guardrails.py` and existing MCP fixtures. Prefer a few simple public-client tests. Use an isolated deterministic task/result fixture rather than real credentials or mutable Netbox data.

1. Call a tool without authored rules. Return nested password/secret values, numeric credentials, a diagnostic string, and a non-sensitive field. Assert the MCP output contains REDUCTED and useful content but no fixture secrets. Confirm stored original values remain unchanged using existing test access.
2. Configure a 4096-character limit and deliver a combined multi-worker structure where each worker is individually below 4096 but len(str(combined_structure)) exceeds it. Assert result is None, failed is false, errors has exactly one meaningful size/configuration message, and no preview or original diff is returned. Verify the original UUID when available. Exercise a typed tool through the MCP SDK and ensure the response contains the intended error rather than an output-validation error.
3. Disable task defaults and configure existing inventory replacements/limits. Verify inventory behavior remains ordered and the final server protections still apply, including to a standalone Result returned by an old byte-limit rule.

Add narrowly scoped boundary checks for invalid settings, equality at the limit, Python string representation counting, missing UUID, redaction failure, and sanitized key collisions when these cannot be cleanly proven through public fixtures. Do not add a large permutation matrix.

## Quality And Documentation Checks

```bash
uv run inv checks
uv run inv docs-build
```

Check startup errors for invalid inventory and inspect test logs for absence of fixture secrets. Document unavailable infrastructure honestly. No Netbox manifest changes are needed for tests without Netbox records. Verify existing task/client arguments, stored results, and existing guardrail tests remain unchanged.


## Validate Rule-Driven Approval

Extend tests/services/fastmcp/test_guardrails.py and the existing public MCP test client. Add elicitation callbacks rather than mocking dispatch as the only proof. Keep fixture data inline and use safe temporary task behavior. Do not execute real configuration changes to test acceptance.

1. With no approval rule, call an existing safe tool. Assert no elicitation callback occurs. Confirm there is no built-in nornir.cfg approval rule through detailed get_tools metadata.
2. Configure a request_approval rule for an existing safe test tool. Accept the form with approved=true. Assert the operation executes once after the callback, the form names workers=all, and arguments shown to the client are sanitized. Also validate the optional argument predicate through a matching and a non-matching safe call.
3. Decline a matching approval request. Assert a tool error and no dispatched job or fixture side effect. Extend narrowly for cancel, approved=false, missing/invalid data, timeout, disconnect, URL-only capability, and no capability using the existing SDK client fixtures where possible.
4. Configure a matching reject and approval together. Assert rejection and zero forms, independent of their ordering. Verify old rules without action still reject.

Use focused model checks for all-or-none predicates and required strict boolean. Exercise task-default disable versus inventory rules, multiple matched approval reasons producing one form, and request cancellation without a queued job. Test that retrying a call asks again. No credentials or full argument dumps should appear in logs or approval prompts.

Complete one manual test in an actual supported host: confirm that its UI presents the form, a human can decline, and declining causes no task. Record the host/version and transport used. An automated callback acceptance proves protocol integration, not human interaction. No implementation checks are claimed by this planning guide.

## Validate Independent Controls

Verify result_guardrail_secrets_reduction=false skips only built-in server result masking. Existing task/inventory replacement rules and the size limit still apply. Approval summaries stay sanitized independently of this setting. Check invalid boolean values fail inventory validation.

Job retrieval and job_details changes are excluded from this feature. Verify a size limit of 0 disables the server cap while preserving task/inventory limits and enabled redaction.
