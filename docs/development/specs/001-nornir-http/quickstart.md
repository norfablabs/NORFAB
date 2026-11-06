# HTTP Task Validation

After implementation, verify RESTCONF support and reachability on both spines and configure
HTTP inventory profiles as described in research.md. Preserve existing connections and scope TLS
exceptions to the lab. Obtain confirmation before specifically unapproved existing-code changes.

Run from repository root:

```powershell
uv run inv docker-tests-nornir --selector=tests/services/nornir/test_restconf.py
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
rendered payload values, visible failure and ownership-safe cleanup. All four public verbs use
the same backend path; no NorFab-owned retries or path rendering or JSON null-body support is introduced.
RESTCONF lab readiness verified on 2026-11-07; real GETs returned both spine hostnames.

## Validation Results ? 2026-11-07

From tests/, using the existing public-client fixture and loopback broker endpoint:

```powershell
$env:NORFAB_TEST_WORKERS='nornir-worker-1,filesharing-worker-1'
$env:BROKER_ENDPOINT='tcp://127.0.0.1:5555'
uv run --project .. pytest services/nornir/test_restconf.py -q --tb=short
```

Result: 5 passed, including both-spine GET, owned PUT/read-back/delete, inline JSON rendering,
nf:// template download/rendering and visible missing-resource failure. Runs use normal configured
RetryRunner behavior. Owned Loopback987/988/989 interfaces were removed by test cleanup.

Related regression: TestNetconfGet running-config cases with ncclient and subtree filtering,
using nornir-worker-1 and nornir-worker-2: 2 passed, 210 deselected.
Changed/new RESTCONF files pass focused Ruff checks; all six changed Python files pass Black.
uv run inv docs-build passed (existing documentation/navigation warnings remain).

uv run inv checks stopped at repository-wide Black findings in unrelated files. Separate
uv run inv lint reported 2788 repository-wide findings and uv run inv dead-code returned findings
(exit 3), including dynamic task/shell entry points. None were suppressed or auto-fixed to make
checks pass. Existing registration files retain pre-existing annotation findings; new RESTCONF
files, tests and model additions pass focused lint.

No full integration suite or package release was run. PATCH dispatch is implemented through the
same runner; core mutation coverage exercises PUT and DELETE rather than every device operation.

Live PICLE command `nornir restconf get workers nornir-worker-1 FL ceos-spine-1 url
openconfig-system:system/state/hostname` returned ceos-spine-1 with no job warnings/errors.
Windows validation used PYTHONIOENCODING=utf-8 for Rich console output. Direct final reads
confirmed Loopback987/988/989 are absent (HTTP 404).

POST addition: TestRestconfPost.test_post_resource creates test-owned Loopback990 with an inline
JSON payload, reads its description through the public client and deletes it in finally.
Full RESTCONF suite after addition: 6 passed in 26.69 seconds. Focused Ruff and CLI schema checks pass.

Data-only payload follow-up: all 6 public-client tests passed in 28.96 seconds after removing
json task support. Inline payloads are JSON text in data; nf:// files also use data.

## OpenConfig interfaces getter validation - 2026-11-07

From tests/, with NORFAB_TEST_WORKERS=nornir-worker-1,filesharing-worker-1:

```bash
uv run --project .. pytest services/nornir/test_restconf.py -q --tb=short
```

Seven tests passed in 26.39 seconds. The new test verifies Management0 in both
spine interface replies. cEOS returns the list under openconfig-interfaces:interface.
Explicit URL reads and existing mutation tests also pass. Focused Black and Ruff
checks passed. Model checks verified the CLI alias/presence flag, conflicting URL
rejection and absence of the getter field in write schemas.

The documentation build passed. Existing link warnings remain elsewhere. The GET
page inventory link now uses the current RESTCONF connection inventory heading.

## LLDP and system getter validation - 2026-11-07

With BROKER_ENDPOINT=tcp://127.0.0.1:5555 and the same worker selection,
the full RESTCONF file passed: 9 tests in 28.68 seconds. New tests verify
LLDP chassis type and system hostname on both spines. Black, Ruff and model/shell
checks passed. The documentation build passed with existing link warnings.
