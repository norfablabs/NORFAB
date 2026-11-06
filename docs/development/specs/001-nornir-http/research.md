# Research: Nornir HTTP Tasks

## Decisions

- Reuse installed nornir-salt http_call and HTTPPlugin. The connection is inventory bookkeeping,
  not a persistent session; do not create a new backend or session abstraction.
- Core ThreadedRunner on a filtered clone prevents inherited RetryRunner repetition without
  retry code or changing other tasks. Preserve the no-retry contract.
- Follow existing NETCONF rendering/temporary-host-data conventions inside the connection lock,
  cleaning in finally. Sequential preparation avoids a rendering adapter and cache-lock machinery.
- Reuse existing utilities and task/model conventions; ask before altering existing application code.
- No special JSON null-body support. No Requests defaults/override test suite.
- Initial tests prove new core NorFab behavior only. Inline input values/payloads; repetition is
  preferable to shared test data, builders or helper functions. Keep one behavior per test.
- Existing backend DEBUG diagnostics can include request parameters. Document the dependency
  limitation and keep new wrapper messages free of secrets; no new logging/redaction framework.

## Lab Gate: BLOCKED

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
