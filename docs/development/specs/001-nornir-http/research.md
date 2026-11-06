# Research: Nornir HTTP Tasks

## Decisions

- Reuse installed nornir-salt http_call and HTTPPlugin. The connection is inventory bookkeeping,
  not a persistent session; do not create a new backend or session abstraction.
- Reuse the configured Nornir runner; RetryRunner owns retries and NorFab adds none.
- Follow existing NETCONF rendering/temporary-host-data conventions inside the connection lock,
  cleaning in finally. Sequential preparation avoids a rendering adapter and cache-lock machinery.
- Reuse existing utilities and task/model conventions; ask before altering existing application code.
- No special JSON null-body support. No Requests defaults/override test suite.
- Initial tests prove new core NorFab behavior only. Inline input values/payloads; repetition is
  preferable to shared test data, builders or helper functions. Keep one behavior per test.
- Existing backend DEBUG diagnostics can include request parameters. Document the dependency
  limitation and keep new wrapper messages free of secrets; no new logging/redaction framework.

## Initial Lab Gate (Resolved Below)

Declared topology uses ceosimage:4.35.2F. Existing spine port mappings do not publish RESTCONF's
usual 6020, HTTP inventory profiles are absent, and saved spine configs are not explicitly attached
as startup-config. Previous probes to mapped eAPI HTTPS ports were unreachable. This does not
prove RESTCONF is unsupported. Verify live image, HTTPS/SSL/control-plane setup and distinct ports,
then read a supported resource from both named spines. eAPI does not replace this requirement.

## References

- [Arista configuration](https://aristanetworks.github.io/openmgmt/configuration/restconf/)
- [Arista examples](https://aristanetworks.github.io/openmgmt/examples/restconf/curl/)
- [Backend source](https://github.com/dmulyalin/nornir-salt/blob/master/nornir_salt/plugins/tasks/http_call.py)

No application code, tests, dependency settings or devices changed during design simplification.

## Implementation Readiness Check ? 2026-11-07

Branch: feature/nornir-restconf; working tree clean at start. Specification-quality checklist:
16 checked, zero unchecked. No implementation hooks are configured.

Read-only HTTPS probes to https://containerlab.lab:6020/restconf/data/ and
https://containerlab.lab:6021/restconf/data/ both failed to establish a connection (HTTP 000).
The checked-in topology still has no published RESTCONF 6020 ports for either spine.
The new cfg/enable_restconf.txt contains RESTCONF enablement commands, but its presence does
not establish that they were applied to the devices. Running image versions and a supported
hostname resource could not be verified. No device configuration was changed.

T001 remains incomplete: the mandatory live readiness gate failed. Per tasks.md, stop before
service implementation rather than substitute eAPI or mocks. Restore lab reachability and
confirm RESTCONF listening addresses/published ports, then rerun T001-T003.

## Corrected-Port Recheck ? 2026-11-07

HTTP inventory and Containerlab now agree on host ports 6030/6031 for the two spines.
From this agent environment, containerlab.lab resolves to 192.168.1.220. Direct TCP probes
with a three-second timeout failed for both ports, and authenticated HTTPS hostname reads
also timed out. No proxy environment variables were present. This is a network reachability
failure before TLS/authentication, not a failed RESTCONF resource assertion.

T001 remains incomplete. No service implementation, test substitution, or device modification
was performed. Confirm that this environment can route to 192.168.1.220 and that deployed
container port publication (not only the YAML declaration) exposes TCP 6030 and 6031.

Implementation clarification (2026-11-07): use the existing configured Nornir runner exactly
as NETCONF. No with_runner override or task-owned retry handling; inventory runner settings apply.

## Resolved Readiness and Implementation ? 2026-11-07

Both containerlab.lab:6030 and :6031 returned HTTP 200 for the system/state/hostname resource,
with distinct ceos-spine-1 and ceos-spine-2 identities. RESTCONF remains in the default VRF;
the lab control-plane permit-all ACL enabled access. Earlier blocked probe results are historical.

The user explicitly requires normal configured Nornir invocation matching NETCONF: no runner
override, and no NorFab-owned retry handling. RetryRunner performs its configured retries.
This supersedes the earlier ThreadedRunner proposal. RestconfGetInput reuses NornirCommonArgs.

cEOS PUT interface config accepts module-qualified leaf fields directly, not a nested config
container. Owned Loopback987/988/989 resources were created, read back and deleted by the core
public-client tests; none of these tests use Netbox data.
