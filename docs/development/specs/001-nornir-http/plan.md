# Implementation Plan: Nornir HTTP and RESTCONF Tasks

**Date**: 2026-11-06 | **Spec**: [spec.md](spec.md)

## Summary

Add restconf_get, restconf_post, restconf_put, restconf_patch and restconf_delete as thin
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
Real RESTCONF readiness on both spines verified on 2026-11-07; core integration reads pass.

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

Use the configured Nornir runner exactly as NETCONF does: filter, add processors, then nr.run.
Do not replace the runner or introduce retry handling. Reuse NornirCommonArgs and existing
processor mixins; runner behavior remains controlled by inventory and existing run_* arguments.

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

Both spine RESTCONF endpoints returned HTTP 200 with their distinct hostnames.
Protect only owned mutation resources. Unsupported device verbs remain documented limitations.
No simplification authorizes changes to existing shared code or task-owned retry logic.

Implementation clarification (2026-11-07): use the existing configured Nornir runner exactly
as NETCONF. No with_runner override or task-owned retry handling; inventory runner settings apply.


## RESTCONF OpenConfig Getters - Review and Plan

Date: 2026-11-07. Status: proposed. Not implemented or device-validated.

## Review findings

- `netconf_get` exposes explicit boolean getters and resolves them before calling
  `_run_netconf`. `NetconfGetInput` validates mutually exclusive selections.
- `restconf_get` already delegates to `_run_restconf`. Add selection directly in
  this method and retain its configured Nornir runner, processors, serialization,
  HTTP inventory connection, and normal error handling.
- `RestconfGetShell` inherits `RestconfGetInput`. New fields and CLI aliases should
  flow through without additional commands or registration.
- `RestconfPutInput` currently inherits `RestconfGetInput`. It must declare its
  existing arguments explicitly so GET-only getters do not appear on PUT.
- OpenConfig BGP is nested under network instances and protocol list entries.
  A guessed default VRF or protocol name would restrict results incorrectly.

## Proposed public contract

Extend `restconf_get` with these explicit `StrictBool` model fields, default false,
and matching method arguments. Use the same hyphen aliases and presence metadata
as NETCONF getters.

| Argument | Resource relative to inventory base_url |
| --- | --- |
| `openconfig_interfaces` | `openconfig-interfaces:interfaces` |
| `openconfig_lldp` | `openconfig-lldp:lldp` |
| `openconfig_system` | `openconfig-system:system` |
| `openconfig_bgp` | `openconfig-network-instance:network-instances` with the projection below |

For BGP, propose `params['fields'] = 'network-instance/protocols/protocol/bgp'`.
This is a server-side projection across network instances, not a wildcard URL.
Confirm the projection and returned namespace structure on both cEOS spines
before committing to it. BGP output retains the network-instance/protocol
envelope and may include large RIB data.

Allow at most one getter or explicit `url`. With no getter, preserve current GET
behavior, including omitted URL. Continue accepting explicit `params` and `headers`.
For BGP, reserve `fields` for its projection and reject a caller-supplied `fields`
entry at the input boundary rather than silently overwriting it. Other query
parameters retain their existing behavior. Do not mutate caller dictionaries.

Return existing raw per-host `get` payloads. Do not normalize vendor data or hide
HTTP failures. Model availability and optional RESTCONF `fields` support depend
on the device. If a device does not support the BGP projection, expose the error.
Do not add discovery requests, broad-query fallback, or local data pruning.

## Small implementation changes

1. Verify the four raw resource requests through `nfclient.run_job` against
   `ceos-spine-1` and `ceos-spine-2`. Verify the BGP projection first, with BGP
   already configured. Record actual response keys and errors. Do not configure
   devices as part of this review. If unsupported, revisit BGP scope explicitly.
2. Update `nornir_models.py`: make PUT's existing arguments explicit, add four
   GET fields, and one NETCONF-style selection validator. Validate the BGP
   `fields` conflict there. Keep validation out of the runner.
3. Update `restconf_task.py`: add explicit getter arguments and docstrings,
   select the resource in a short direct block, add BGP projection when selected,
   and call `_run_restconf` once. No new helper, task, dependency, or runner change.
4. Extend `TestRestconfGet` in `tests/services/nornir/test_restconf.py` with four
   small public-client tests, one per getter. Inline all input and expectations.
   Each checks both spines, success, and a meaningful model-specific value or
   structure. Use existing `nornir` and `nornir_restconf` marks. Keep the existing
   explicit URL test as the regression check. No edge-case matrix or HTTP library
   tests. Check PUT's exposed schema and CLI help during focused validation.
5. Update the existing RESTCONF GET guide with a short getter description and
   consistent CLI, Python, FastAPI, and MCP examples. Document model support,
   mutual exclusion, and BGP scope. Update the feature's Spec Kit artifacts to
   reflect agreed requirements before implementation. Fold the capability into
   the existing draft RESTCONF FEATURES note if RESTCONF remains unreleased.

Acceptance: each selector requests its documented subtree, explicit URLs still
work, GET-only fields do not leak into PUT, and failures remain visible.
Run focused RESTCONF tests, focused formatting/lint checks, and the docs build.
Before implementation, obtain confirmation for the specific existing application
code edits required by constitution principle I. This review changes no code.

## Sources

- Existing `netconf_get`, `NetconfGetInput`, `restconf_get`, `RestconfGetInput`,
  `RestconfPutInput`, and `RestconfGetShell` in this checkout.
- [RESTCONF resource identifiers](https://www.rfc-editor.org/rfc/rfc8040.html#section-3.5.3).
- [RESTCONF fields projection and capability](https://www.rfc-editor.org/rfc/rfc8040.html#section-4.8.3).
- [OpenConfig network-instance model, including BGP grouping](https://github.com/openconfig/public/blob/master/release/models/network-instance/openconfig-network-instance.yang).

## Interfaces-only delivery - 2026-11-07

The authorized first increment implements only openconfig_interfaces. Select its
resource through the module-level RESTCONF_GETTERS dictionary and NETCONF-style
selection loop in restconf_get, with boundary validation in RestconfGetInput
and the existing runner unchanged. PUT declares its existing fields explicitly
to keep the GET selector out of write schemas. LLDP, system and BGP remain deferred.
One public-client test verifies Management0 in both spine replies.

LLDP and system follow the same dictionary/selection loop with their top-level
OpenConfig resources. One getter or URL is allowed. BGP remains deferred.
