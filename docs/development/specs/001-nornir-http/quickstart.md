# HTTP Task Validation

After implementation, verify RESTCONF support and reachability on both spines and configure
HTTP inventory profiles as described in research.md. Preserve existing connections and scope TLS
exceptions to the lab. Obtain confirmation before specifically unapproved existing-code changes.

Run from repository root:

```powershell
uv run inv docker-tests-nornir --selector=tests/services/nornir/test_http.py
uv run inv docker-tests-nornir --selector=tests/services/nornir/test_netconf.py
uv run inv checks
uv run inv docs-build
```

Read the current Docker report; a successful Invoke return alone is not a passing test suite.
Initial tests are separate short core checks: real two-spine GET, owned mutation/read-back,
inline payload rendering, nf:// payload rendering and one normal visible failure. Inputs and
payloads are inline; repetition is allowed. No Requests defaults/override tests or edge-case matrix.
Use existing nfclient and FileSharing infrastructure; do not create a generic test server.

Expected outcomes: actual distinct spine hostname data, correct supported owned mutation,
rendered payload values, visible failure and ownership-safe cleanup. All seven public verbs use
the same backend path; no retries, path rendering or JSON null-body support is introduced.
RESTCONF lab readiness remains unverified until evidence is recorded. Do not substitute eAPI.
