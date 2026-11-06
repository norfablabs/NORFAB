# Implementation Plan: Nornir HTTP and RESTCONF Tasks

**Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

## Summary

Add http_get, http_post, http_put, http_patch, http_delete, http_head and http_options as thin
public methods around one direct shared runner following NETCONF. Use existing nornir-salt
http_call, HTTP inventory settings, filtering, processors, serialization, templates and watchdog.
No new HTTP backend, session manager, rendering adapter, cache-lock layer or test server.

## Technical Context

Python and dependencies follow pyproject.toml; full-service validation uses Python 3.12.
Existing Nornir, nornir-salt, Pydantic, PICLE and Jinja2 suffice. No new dependency/storage.
Primary use is RESTCONF device management. Literal paths; inline/nf:// Jinja payload rendering.
JSON null bodies are not required. Do not retest Requests behavior or expose retry machinery.

## Constitution Check

Surgical changes and reuse are mandatory. Ask confirmation before specifically unapproved changes
to existing application code. New task/model/shell files follow existing service patterns.
Initial tests are short public-client core checks with inline values, one behavior per test;
no shared test-data helpers or edge-case matrices. Preserve ownership and cleanup.
Real RESTCONF readiness on both spines remains BLOCKED until verified; do not substitute eAPI.

## Project Structure

Feature artifacts live together in docs/development/specs/001-nornir-http/.
Worker implementation: norfab/workers/nornir_worker/http_task.py.
Models: norfab/workers/nornir_worker/nornir_models.py.
Registration: norfab/workers/nornir_worker/nornir_worker.py.
Shell: norfab/clients/nfcli_shell/nornir/nornir_picle_shell_http.py and nornir_picle_shell.py.
Tests: tests/services/nornir/test_http.py, using existing nfclient and inventory.

## Execution Design

Use one linear flow: validate -> filter -> render -> execute once -> serialize -> cleanup.
Return no_match before rendering/fetching. Reuse existing methods rather than wrapping them.
Prepare payloads sequentially with existing Jinja utilities and job_data context; use the existing
connection lock and temporary per-host payload convention, keeping preparation, execution and
cleanup together under the lock. Remove temporary state in finally, including after failure.
Do not add a per-host execution adapter or concurrent renderer/cache synchronization.

For HTTP only use a filtered Nornir clone with core ThreadedRunner so configured RetryRunner
cannot repeat requests. Do not change the shared runner, add retry loops or retry policy options.
Reuse existing model/filter/processor mixins; narrowly omit/reject unsupported retry controls.
Avoid a broad common-model refactor or copying fields without checking reuse opportunities.

Public methods fix the backend verb. POST/PUT/PATCH accept JSON or raw text, including inline
Jinja or nf:// templates; reject simultaneous bodies at the model boundary. Parse rendered JSON
before execution. URLs never render. Map request_timeout to backend timeout; CLI timeout retains
its client-wait meaning. Forward request options using existing conventions; omit None while
preserving explicit false values. No special JSON null/scalar serialization path.

Use normal Nornir per-host errors and existing events/results. New messages must not include
credentials or payloads. Backend DEBUG logging is an existing dependency limitation to document;
do not add a global filter, redaction framework or custom error taxonomy to this feature.
If an existing utility must change, present the exact change for confirmation first.

## Delivery Slices and Validation

1. Verify lab, configure RESTCONF safely and add distinct HTTP inventory ports.
2. Deliver GET plus one public-client test proving actual identities on both spines.
3. Add remaining verbs and payload rendering; use a few separate core mutation/rendering tests.
4. Add CLI routing, task metadata and concise documentation; run focused tests and existing checks.

Task generation is permitted while lab readiness is blocked; service implementation and real
acceptance remain gated by lab verification and required existing-code confirmations.

## Complexity Tracking

One shared runner is required; further helper functions/layers are not planned. No general HTTP
fixture server, exhaustive failure matrix, Requests-default testing or diagnostic subsystem.

## Risks and Readiness

Both spine RESTCONF endpoints must be verified; existing probes did not establish reachability.
Protect only owned mutation resources. Unsupported device verbs remain documented limitations.
No simplification authorizes changes to existing shared code or a waiver of the no-retry rule.
