# Bug hunt

Repository state at start: clean `master`. Findings below are triaged one at a time. No implementation or test files were changed.

## 1. `create_ip` cannot promote an already assigned IP to primary

- **Status:** Fixed.
- **Severity:** Medium. An otherwise successful task silently leaves the device's primary IP unchanged.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:632-665`; input contract at `norfab/workers/netbox_worker/netbox_models.py:2264-2267`.
- **Trigger:** Call `create_ip` with `device`, `interface`, and `is_primary=True` when the matching IP is already assigned to that interface. The existing assignment makes the condition at line 638 false. `nb_device` remains `None`, so the primary-IP save at line 663 never occurs. The current test at `tests/services/netbox/test_ipam.py:2651` only checks that a fresh allocation succeeds; it never asserts the device's primary IP or retries an existing assignment.
- **Proposed fix:** Handle primary assignment independently of whether the IP/interface association changed. Set the device's `primary_ip4` or `primary_ip6` according to the allocated address family, and save only if the requested primary differs. Add an integration test through `create_ip` that first assigns an address without `is_primary`, then calls it again with `is_primary=True` and checks the NetBox device record.
- **Evidence:** Code-path inspection. A live NetBox instance was not used for this finding.

## 2. Circuit test-data seeding fails on NetBox below 3.5

- **Severity:** Medium for the supported legacy test environment.
- **Location:** `tests/netbox_data.py:3552-3561`.
- **Trigger:** Run `create_circuits()` when `NB_VERSION < 3.5`. Line 3560 calls `circuit.pop("provider_account")`, but `circuit` is not assigned until line 3561. This raises `UnboundLocalError`; the surrounding `except` logs it and skips the circuit. Ruff reports the undefined name as F821.
- **Proposed fix:** Remove `provider_account` from a copy of `item` before the create call, and use that copy throughout the iteration. Test the legacy version branch with a small explicit circuit record and an endpoint that records the create payload.
- **Evidence:** Ruff F821 and code-path inspection. No legacy NetBox service was available for an integration run.

## 3. Circuit test-data seeding mutates its reusable fixture records

- **Severity:** Medium for repeated population runs in one Python process.
- **Location:** `tests/netbox_data.py:2791-2867,3552-3557,3630-3631` and the matching B-side termination handling.
- **Trigger:** `create_circuits()` pops `termination_a` and `termination_b` directly from dictionaries in the module-level `circuits` list. A second call raises `KeyError` before reaching NetBox. The first call also removes cable data from termination dictionaries. This makes fixture setup dependent on call order and prevents reliable retries after partial failure.
- **Proposed fix:** Copy each circuit and its nested termination dictionaries before removing setup-only keys. Keep the module-level fixture records intact. Add a test that runs preparation twice against the same literal record and checks that both create payloads match.
- **Evidence:** Code-path inspection; the mutation and second-call failure follow directly from Python `dict.pop` semantics.

## 4. `create_ip` ignores the requested IP status

- **Status:** Fixed.
- **Severity:** Medium. Callers can request `reserved` or `deprecated` and receive an IP with NetBox's default status while the task reports success.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:159-179,463-550,577-665`; input contract at `norfab/workers/netbox_worker/netbox_models.py:2260-2263`.
- **Trigger:** Call `create_ip(prefix=..., status="reserved")` for a new or existing IP. The code forwards `status` to child-prefix creation and peer creation, but never sets `nb_ip.status` or passes it to IP creation. The IP therefore keeps its existing or default status.
- **Proposed fix:** Apply the requested status to the IP record in the same metadata update block as role and description. Ensure the new-IP path includes it and the existing-IP path updates it only when different. Add public-task integration cases for new and existing addresses, then read the status back from NetBox.
- **Evidence:** Complete read of the `create_ip` body and `rg` search of every `status` reference in that task. No live NetBox run.

## 5. `create_ip` reports success when requested peer allocation fails

- **Status:** Fixed.
- **Severity:** Medium. A link can be left with only one endpoint address while the initiating task reports success.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:440-453,682-691`.
- **Trigger:** Request `create_ip` for a connected interface with `create_peer_ip=True` when the peer's allocation fails, for example because its interface cannot be resolved or the subnet has no remaining IP. The recursive peer call returns a failed `Result`; the caller merely omits `ret.result["peer"]` and returns its own successful result.
- **Proposed fix:** Propagate the peer result's failure into the parent result, with the peer error and clear indication that the local IP may already have been created. Cover this with an integration case through the public task where the peer allocation is made to fail after the local allocation.
- **Evidence:** Code-path inspection of the recursive call and its sole `failed == False` branch. No live NetBox run.

## 6. NetBox IP tests delete addresses they did not create

- **Severity:** High for runs against a shared or reused NetBox instance; the test suite can destroy existing IP records.
- **Location:** `tests/services/netbox/common.py:91-113` and repeated calls in `tests/services/netbox/test_ipam.py`, including `test_create_ip_is_primary` at line 2655.
- **Trigger:** Run the `create_ip` integration tests when a target prefix such as `10.0.0.0/24` already contains IP records. The `delete_ips` helper lists every address under the prefix and deletes it before the test allocates any addresses. It does not track which records the test created.
- **Proposed fix:** Give each test a dedicated prefix that it first verifies is free, or record IDs created by that test and delete only those IDs in `finally`. Avoid using the broad deletion helper in test setup. This follows the repository rule to never delete pre-existing data.
- **Evidence:** Helper and call-site inspection. I did not run these tests because they would mutate a NetBox instance without a known isolated fixture.

## 7. `delete_fetched_files` can delete outside its cache directory

- **Severity:** High. A caller of the public client method can accidentally remove unrelated local files or directories.
- **Location:** `norfab/core/client.py:1625-1663`.
- **Trigger:** Pass an absolute path or a path beginning with `..` as `filepath`. `os.path.join(files_folder, filepath)` accepts both; the absolute path replaces `files_folder`, and `..` escapes it. The method then calls `os.remove` or `shutil.rmtree` on glob matches without checking that their resolved paths remain under `fetchedfiles`.
- **Proposed fix:** Resolve the cache root and every matched path and reject any match whose `os.path.commonpath` is not the cache root. Validate the supplied pattern before glob expansion as well. Apply the same containment approach already used by `fetch_file` at lines 1726-1736. Add a public-client test using a temporary sibling file that must remain intact after an escaping pattern.
- **Evidence:** Code-path inspection and a non-destructive Python check showing that `os.path.join` preserves `..` and replaces the base for absolute paths. I did not call the deletion method.

## 8. Constructing an inventory consumes the caller's configuration dictionary

- **Status:** Fixed.
- **Severity:** Medium. Reusing an inventory dictionary for a second NorFab instance fails or starts with missing configuration.
- **Location:** `norfab/core/inventory.py:361-412`. `NorFabInventory.__init__` passes the caller's `data` directly to `load_data`, which removes all recognized top-level keys with `pop`.
- **Trigger:** Construct `NorFabInventory(data=shared_dict)` and then reuse `shared_dict`. The first constructor empties it; the second sees a falsey `data` value and raises the generic missing-inventory `RuntimeError`. Some NFAPI tests already work around this by passing `inventory_data.copy()`.
- **Proposed fix:** Copy the input at the boundary before `load_data` removes keys. Use a deep copy if nested inventory objects can also be mutated during initialization. Add a public-constructor test checking that the input remains equal to its original value and can create two inventories.
- **Evidence:** Isolated run of the public `NorFabInventory` constructor with a minimal broker/topology dictionary printed `input_after_first {}`. No service startup or repository files were involved.

## 9. Agent CLI tool-filter help is missing because of a field typo

- **Severity:** Low. The `list-tools` command's `name` argument lacks its intended description in generated CLI/model metadata.
- **Location:** `norfab/clients/nfcli_shell/client_agent/client_agent_picle_shell.py:19-20`.
- **Trigger:** Inspect the Pydantic schema or CLI help for `ListToolsCommand.name`. `Field(..., descritpion=...)` misspells `description`, so Pydantic treats it as deprecated extra schema data rather than the field description.
- **Proposed fix:** Change the keyword to `description` and check the command's public help/schema. The repository's spelling rule also calls for correcting this typo.
- **Evidence:** `poetry run pytest -q core/test_simple_inventory_datastore.py` passed all 22 tests but emitted a Pydantic warning that explicitly identified `descritpion` as an unsupported extra keyword. A repo search found one occurrence.

## 10. NetBox IP cleanup helper reads only the first API page

- **Severity:** Medium for test reliability when a prefix contains more addresses than the NetBox response page size.
- **Location:** `tests/services/netbox/common.py:91-115`.
- **Trigger:** Call `delete_ips` on a prefix whose IP list spans multiple NetBox REST pages. The helper iterates only `ips["result"]["results"]` from one GET response and never follows `next`. It therefore leaves later-page addresses in place, which can alter allocation results in subsequent tests.
- **Proposed fix:** Replace this broad cleanup approach with per-test tracking of created IDs, as in finding 6. If a generic helper remains necessary, follow NetBox pagination and limit deletion to records explicitly owned by the test.
- **Evidence:** Code-path inspection of the REST response handling. No destructive NetBox run.

## 11. Invalid configured hooks are dropped while inventory loading succeeds

- **Status:** Fixed.
- **Severity:** Medium when a startup or exit hook is required for initialization or cleanup.
- **Location:** `norfab/core/inventory.py:127-165,395-413`.
- **Trigger:** Put a misspelled module or function name in an inventory hook. `make_hooks` catches the import error, logs it, and continues without that hook. `NorFabInventory` succeeds, so later startup or exit logic proceeds without the configured function. The helper's own docstring says loading errors raise an exception.
- **Proposed fix:** Raise a configuration error that identifies the attach point and function when a hook cannot be imported. Add an inventory-constructor test for an invalid hook and assert that startup fails before work begins.
- **Evidence:** Code-path inspection; existing `test_hooks_load` covers only valid hooks.
- **Resolution:** Hook loading now raises a `ValueError` identifying the attach point and function. An inventory-constructor test verifies that an invalid hook prevents inventory loading.

## 12. Task input validation discards Pydantic's converted values

- **Severity:** Medium. An input accepted by a task's schema can still fail inside the task because it receives the original type.
- **Location:** `norfab/core/worker.py:445-458,615-620`.
- **Trigger:** A task input model declares `value: int`, and the caller supplies `"1"`. Pydantic accepts and converts the value, but `validate_input` discards the model instance. The wrapper calls the task with the original string. A task computing `value + 1` raises `TypeError` after validation succeeds.
- **Proposed fix:** Decide at the task boundary whether accepted inputs should be normalized or whether models should reject coercible types. If normalization is intended, pass validated model values to the function while preserving special arguments and public signatures. Add a public task-call test that checks the value actually received by the task.
- **Evidence:** Isolated call to a `@Task(input=M)` function with `M.value: int`: `value=1` returned 2; `value="1"` raised `TypeError` inside the function after validation. The check ran in a separate Python process and changed no files.

## 13. Task output validation accepts non-`Result` return values

- **Severity:** Medium. A task can return an arbitrary value despite declaring an output model, leaving downstream worker/client handling to fail later.
- **Location:** `norfab/core/worker.py:458-463,625-628`.
- **Trigger:** A decorated task returns a string or dictionary rather than `Result`. `validate_output` only invokes the output model inside `if isinstance(ret, Result)`, so it skips validation and the wrapper returns the invalid value unchanged.
- **Proposed fix:** Reject return values that are not `Result` (or explicitly support and validate mappings if that is part of the intended task contract). Add a public decorated-task test for a wrong return type.
- **Evidence:** Isolated `Task(input=M, output=Result)` call with a function returning `"unexpected"` returned that string without an error.

## 14. Workflow reports a successful task after a condition error or stopped failed step

- **Severity:** Medium. A caller checking the workflow task's top-level `failed` field can treat an incomplete or failed workflow as successful.
- **Location:** `norfab/workers/workflow_worker/workflow_worker.py:318-319,360-375,388-407`.
- **Trigger:** A `run_if_*` condition refers to a missing prior step, or a step fails while `stop_on_failure=True`. The worker records an inner failed/error step and breaks, but returns the initial `Result` without setting `ret.failed` or `ret.errors`. Existing workflow tests check nested step data but do not assert the outer task result for these paths.
- **Proposed fix:** Define whether an aborted workflow is a failed task, then set the outer failure and error fields for condition errors and stop-on-failure cases. Add public workflow-task integration assertions for both the nested step and top-level result.
- **Evidence:** Code-path inspection against `tests/services/workflow/test_run.py:177-230`. No live workflow service run.

## 15. Inline workflow execution removes metadata from the caller's dictionary

- **Severity:** Low for direct in-process callers that reuse a workflow definition.
- **Location:** `norfab/workers/workflow_worker/workflow_worker.py:304-331`.
- **Trigger:** Call `run` twice with the same inline dictionary. The first call removes `name`, `description`, and `remove_no_match_results` using `pop`. The second call uses defaults, so its result key and filtering behavior can differ. The URL path produces a fresh dictionary and avoids this issue.
- **Proposed fix:** Copy the workflow dictionary before removing metadata, or read the metadata with `get` and iterate only step entries. Add a public task test that reuses the same inline definition and verifies both results are identical.
- **Evidence:** Code-path inspection of the public task. No service run. The URL filename-derived `workflow_name` at lines 322-324 is also dead code because line 329 overwrites it unconditionally.

## 16. Containerlab command collection can block indefinitely before checking its timeout

- **Severity:** High for long-running or noisy Containerlab commands; a task can hang beyond its declared timeout.
- **Location:** `norfab/workers/containerlab_worker/containerlab_worker.py:315-347`.
- **Trigger:** The helper calls blocking `proc.stderr.readline()` inside its timeout loop and reads stdout only after the child exits. A child that emits no newline on stderr can block that read, so the timeout check is not reached. A child that fills the stdout pipe while the parent reads stderr can also block on writing stdout, leaving both processes waiting.
- **Proposed fix:** Drain stdout and stderr concurrently with `communicate(timeout=...)` or dedicated reader threads, then terminate/kill and reap the child on timeout. Keep forwarding progress events if needed without blocking either pipe. Add a focused subprocess test using a bounded child that writes enough stdout to fill a pipe and another that stays quiet beyond the timeout.
- **Evidence:** Code-path inspection of the subprocess loop. No Containerlab process was launched.

## 17. Containerlab `inspect` masks a command failure with a `None` membership error

- **Severity:** Low to medium. A failed named-lab inspection returns an unrelated Python error rather than its Containerlab diagnostics.
- **Location:** `norfab/workers/containerlab_worker/containerlab_worker.py:349-358,570-598`.
- **Trigger:** Call `inspect(lab_name=...)` and have the Containerlab command exit nonzero or produce no expected output. `run_containerlab_command` sets `ret.failed=True` and leaves `ret.result=None`. `inspect` then evaluates `lab_name not in ret.result`, raising `TypeError` and masking the original `ret.errors`. The existing missing-lab test asserts only `failed`, so it does not catch the diagnostic loss.
- **Proposed fix:** Return the failed `Result` before checking whether the lab name appears in parsed output. Check that the result is a suitable collection before membership testing. Assert the original command error in the public `inspect` integration test.
- **Evidence:** Code-path inspection; no Containerlab service run.

## 18. Starting an existing FakeNOS network loses control of the old process

- **Status:** Fixed.
- **Severity:** High. The old network can remain running after its process handle and stop event are discarded.
- **Location:** `norfab/workers/fakenos_worker/fakenos_worker.py:345-405`.
- **Trigger:** Call the public `start` task twice with the same network name. There is no existing-name guard. The second call starts a new child and overwrites `self.networks[network]`; subsequent `stop` or worker shutdown can reach only the new child. Port binding can also fail in the second child while the original remains live.
- **Proposed fix:** Make `start` return the existing live network for the same name, or fail with an explicit already-running error. Use the dedicated `restart` task to replace it. Add a public service test that calls `start` twice and verifies that one tracked process remains and `stop` terminates it.
- **Evidence:** Lifecycle code-path inspection. Existing start tests use distinct network names; no duplicate-start test was found. No FakeNOS service run.

## 19. FakeNOS child errors are returned as successful string results

- **Severity:** Medium. An inspection can report a nonsensical host count and `failed=False` after the child fails to enumerate hosts.
- **Location:** `norfab/workers/fakenos_worker/fakenos_worker.py:80-107,167-192,458-491`.
- **Trigger:** The child catches an exception from `_get_hosts_as_list`, stores an error message string in `result_queue`, and the parent only raises queue values that are `Exception` objects. The string passes through as `hosts`; `inspect_networks` computes `len(hosts)` and returns success.
- **Proposed fix:** Send a structured success/error envelope through the queue and raise or mark the task failed when the child reports an error. Add a public inspection test for a child-side failure and assert that the returned task is failed with the original message.
- **Evidence:** Code-path inspection of both sides of the queue. No FakeNOS service run.

## 20. FastAPI and FastMCP discovery stop retrying a service after a partial failure

- **Severity:** Medium. Some task endpoints or MCP tools can remain missing until discovery is manually retriggered or the worker restarts.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:168-173,187-245` and `norfab/workers/fastmcp_worker/fastmcp_worker.py:405-410,424-486`.
- **Trigger:** FastAPI records a service key before all its routes register; a later exception ends the cycle, and subsequent cycles skip that service. FastMCP does the same before constructing all tools. It also catches individual tool-construction errors, leaving the service marked discovered despite a missing tool. Later startup cycles skip the service in both workers.
- **Proposed fix:** Mark a service complete only after all its eligible tasks have been processed successfully. Retry missing routes and tools on later cycles. Add integration cases where an initial transient failure is corrected during startup discovery.
- **Evidence:** Code-path inspection of both retry loops. No FastAPI or FastMCP service run.

## 21. One-cycle API discovery calls sleep after their work is finished

- **Severity:** Low to medium. Explicit discovery jobs have avoidable latency after doing their work.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:258-261,671-685` and `norfab/workers/fastmcp_worker/fastmcp_worker.py:488-491,890-913`.
- **Trigger:** The public FastAPI `discover` task calls its loop with `cycles=1` and still sleeps ten seconds after decrementing to zero. FastMCP's one-cycle discovery follows the same pattern and sleeps five seconds.
- **Proposed fix:** Sleep only when another cycle will run and the worker has not been asked to exit in both workers. Add focused public discovery timing assertions or equivalent deterministic checks around the final-cycle branch.
- **Evidence:** Code-path inspection. No service run.

## 22. Re-storing a bearer token under another user corrupts ownership metadata

- **Severity:** Medium. Listing and deleting tokens by username can disagree about who owns a valid token.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:496-531,533-575,583-624` and the same store/list/delete pattern in `norfab/workers/fastmcp_worker/fastmcp_worker.py:767-863`.
- **Trigger:** Store token `T` for user A, then call `bearer_token_store(username=B, token=T)`. The second call reuses the cached value containing `username=A` but writes it with cache tag B. Listing B's tokens shows an entry labeled A; deleting A's tokens by tag leaves T active, while deleting B's tokens removes A's token.
- **Proposed fix:** Reject an attempt to bind an existing token to a different username, or explicitly replace both value and tag in one documented operation, in both workers. Add public task tests covering duplicate token storage across two usernames, listing, revocation, and `bearer_token_check`.
- **Evidence:** Code-path inspection of the cache value/tag handling. Existing tests use a single username per token. No live FastAPI worker run.

## 23. NFWeb topology history can disappear for the same device set after selection

- **Severity:** Low to medium for mixed-case device names in a multi-device scope.
- **Location:** `norfab/clients/nfweb/topology/collector.py:62,201-209` and `norfab/clients/nfweb/topology/history.py:60-72,87-109`.
- **Trigger:** Start NFWeb with configured devices `['a', 'B']`. The collector stores the scope as `['B', 'a']` using default sorting. Selecting those same devices in the browser stores `['a', 'B']` using casefold sorting. History queries compare device lists for exact equality, so snapshots from the first scope no longer appear even though the device set is identical.
- **Proposed fix:** Canonicalize device scopes with one sort rule at both initialization and selection, and consider comparing normalized sets when reading older snapshots. Add a history/collector test with mixed-case names that selects the same set after startup.
- **Evidence:** Code-path inspection plus an isolated Python check confirming the two sort orders differ for `['a', 'B']`. No NFWeb server run.

## 24. NFWeb can serve topology snapshots after the retention window expires

- **Severity:** Medium for the documented maximum history window and stale browser state.
- **Location:** `norfab/clients/nfweb/topology/history.py:20-41,60-85,161-170` and `norfab/clients/nfweb/topology/web.py:182-189`.
- **Trigger:** Insert a snapshot, then leave NFWeb idle beyond the configured retention window. Cleanup runs at store initialization and after inserts only. `history()` and `logs()` apply a cutoff at read time, but `latest()` and `get(snapshot_id)` do not. A new WebSocket connection can receive an expired snapshot as its latest state, and a direct snapshot request can retrieve expired data before another insert triggers cleanup.
- **Proposed fix:** Apply the retention cutoff in `latest()` and `get()` queries as well as periodic cleanup for bounded on-disk storage. Add a store test that advances time beyond retention without inserting another snapshot and checks all read methods.
- **Evidence:** Code-path inspection. No NFWeb server run.

## 25. NFWeb monitoring keeps and serves expired samples after polling failures

- **Severity:** Low to medium. A prolonged collection failure leaves the dashboard showing stale data as its latest sample and retains history past the configured window.
- **Location:** `norfab/clients/nfweb/monitoring/collector.py:44-52,89-114` and `norfab/clients/nfweb/monitoring/web.py:35-56,94-108`.
- **Trigger:** Collect one monitoring sample, then have later `collect_once` calls raise for longer than `retention_minutes`. `collect` returns from its exception handler before pruning `history`. The `latest` property and HTTP/history/WebSocket handlers return the old sample without checking its age.
- **Proposed fix:** Prune history against current UTC time on reads or on every collection attempt, including failed attempts, and make `latest` return `None` when its sample has expired. Add a collector/API test that advances beyond retention while collection raises.
- **Evidence:** Code-path inspection. Existing monitoring tests cover normal sample pruning, not repeated failures beyond retention.

## 26. File downloads can leave their destination open and skip integrity checks

- **Severity:** Medium for failed or empty downloads, especially on Windows where open handles can block later file operations.
- **Location:** `norfab/core/client.py:1740-1822` and `norfab/workers/filesharing_worker/local_files_tasks.py:251-268`.
- **Trigger:** Fetch an empty file. The client opens the destination, but the worker sends no `STREAM` chunk, so `handle_stream` never closes the handle or verifies the hash. The client reports success and removes the transfer entry. A failed fetch after opening the destination follows the same no-cleanup path and can leave a partial file open.
- **Proposed fix:** Own and close the destination in a `finally` block in `NFPClient.fetch_file`, including success, empty file, exception, and failed-job paths. Verify the final file hash after the worker job returns, including zero-byte files, and remove or clearly mark partial files on failure. Add public file-sharing integration cases for an empty file and a mid-transfer failure.
- **Evidence:** Code-path inspection. Existing fetch tests do not cover empty files or cleanup after failure.

## 27. `NFPClient.fetch_file` accepts a zero chunk size and then divides by zero

- **Severity:** Low. A bad public argument raises unexpectedly and leaves a transfer entry behind.
- **Location:** `norfab/core/client.py:1665-1672,1740-1763`.
- **Trigger:** Call `fetch_file(..., chunk_size=0)` for an existing file. The method records `self.file_transfers[uuid]`, then computes `size_bytes / chunk_size` and raises `ZeroDivisionError` without removing the entry. Negative chunk sizes can also produce nonsensical request counts.
- **Proposed fix:** Validate `chunk_size > 0` and `pipeline > 0` before creating a transfer entry or making network calls. Add public-client boundary tests for zero and negative values and assert that no transfer state remains.
- **Evidence:** Code-path inspection of the argument boundary and division. No file transfer run.

## 28. Every NFWeb monitoring collector test fails during setup

- **Severity:** Medium for test coverage: the monitoring behavior under test is never reached.
- **Location:** `tests/clients/nfweb/test_monitoring.py:15-39` and the broker/worker process records at lines 47-51 and 81-85; required model field at `norfab/core/monitoring.py:16-27`.
- **Trigger:** Run `poetry run pytest -q clients/nfweb/test_monitoring.py` from `tests/`. All five tests fail in `make_client()` because its `ClientMonitoringStats.process` data omits required `threads`. The broker and worker process records in the same helper omit it too, so fixing only the first record would still leave later validation failures.
- **Proposed fix:** Update the test's explicit process records to the current monitoring schema, then rerun all five tests to expose any further stale fields. Longer term, exercise NFWeb through its public interface with a real client/service where practical, as the repository test guidance requires.
- **Evidence:** Focused pytest run: 5 failed, all at the `process.threads` validation error during setup. The whole NFWeb Python suite produced 43 passed and the same 5 failures. No service was started.

## 29. Nornir test assertions raise `NameError` when they should report a failure

- **Severity:** Low to medium for diagnosis: failing integration assertions lose the actual mismatch and report an unrelated name error.
- **Location:** `tests/services/nornir/test_parse.py:464-468` and `tests/services/nornir/test_tests.py:359-364`.
- **Trigger:** In `test_nornir_parse_ttp_with_host_filter`, if worker 2 returns unexpected results, the assertion message evaluates `nornir-worker-2` as an expression with undefined names. In `test_nornir_test_remove_tasks_false`, a traceback in task output evaluates undefined `test_name` instead of the available `task_name`.
- **Proposed fix:** Use a literal worker label or an in-scope variable in the first assertion, and `task_name` in the second. Re-run the focused integration tests; a small isolated failing-assertion check can verify each message without changing service behavior.
- **Evidence:** Ruff F821 and assertion-path inspection. No Nornir service run.

## 30. NetBox prefix tests delete pre-existing child prefixes

- **Severity:** High for a shared or reused NetBox instance.
- **Location:** `tests/services/netbox/common.py:64-88`, called throughout `tests/services/netbox/test_ipam.py`.
- **Trigger:** Run a prefix allocation test when its parent prefix already contains child prefixes. The setup helper queries all prefixes `within` the parent and deletes every returned record, without identifying which ones the test created. This is the prefix equivalent of finding 6 and violates the repository rule to preserve pre-existing data. It also processes only the first paginated REST response, leaving any later pages in place.
- **Proposed fix:** Give tests a dedicated verified-free parent prefix and delete only child prefix IDs created by that test in `finally`. If a generic cleanup helper remains, follow pagination and require explicit ownership of every deleted record.
- **Evidence:** Helper and call-site inspection. I did not run the destructive NetBox tests.

## 31. Agent dynamic-model builders carry unused model-name arguments

- **Severity:** Maintenance only; no behavioral failure established.
- **Location:** `norfab/core/agent.py:271-276,282-284` and `norfab/workers/agent_worker/agent_worker.py:164-171,176-180`.
- **Trigger:** Both `make_pydantic_model` implementations receive `model_name` but always return `models["Model"]` without using it. Their callers pass the tool name, suggesting the generated model was intended to have a distinct name, but currently the argument has no effect.
- **Proposed fix:** If model names are not needed, remove the unused argument from these internal builders and call sites. If they are needed for schema/tool diagnostics, use the argument when generating or selecting the model and add a public agent tool-discovery check.
- **Evidence:** Vulture reported both parameters at 100% confidence; code-path inspection confirmed they are unused.

## 32. NFCLI SNMP shell has three unused imports

- **Severity:** Maintenance only; no behavioral failure established.
- **Location:** `norfab/clients/nfcli_shell/nornir/nornir_picle_shell_snmp.py:8,20,30`.
- **Trigger:** Module import loads `StrictBool`, `SnmpMultiSetInput`, and `TabulateTableModel`, but the module never references them.
- **Proposed fix:** Remove the imports after checking whether any were intended for a missing command model. Ruff can apply the safe import removal once that review is complete.
- **Evidence:** `poetry run ruff check norfab --select F401,F541` reported exactly these three production-code F401 findings and no F541 findings.

## 33. NFCLI file completion crashes when File Sharing is unavailable

- **Severity:** Low to medium for interactive CLI usability during a service outage.
- **Location:** `norfab/clients/nfcli_shell/common.py:325-350`.
- **Trigger:** A completion request calls `walk_norfab_files` while the `filesharing.walk` job fails, returns no worker result, or returns `result=None`. The helper immediately takes the first response item and iterates `wres["result"]`, raising `StopIteration` or `TypeError` instead of returning no completions. It also ignores the worker's `failed` flag.
- **Proposed fix:** Treat an empty or failed response as an empty completion list and log the service error at an appropriate level. Add a focused CLI completion test for an unavailable File Sharing worker through the public completion interface.
- **Evidence:** Code-path inspection; `nfcli/test_shell_common.py` passed 7 tests but does not cover this outage case.

## 34. A second read of completed job events can wait forever

- **Severity:** Medium for clients that subscribe to or re-read a job future's events more than once.
- **Location:** `norfab/core/client.py:623-656`.
- **Trigger:** Finish an `NFPJobFuture`, consume `future.events()` once, then call `future.events()` again without a timeout. `mark_done` queues one terminal marker. The first iterator consumes it; the second blocks on an empty queue because `events()` never checks `done_event` when the queue is empty. Concurrent consumers have the same one-marker problem.
- **Proposed fix:** Make `events()` stop when `done_event` is set and the event queue is drained, with a bounded wake-up strategy for a blocking read. Document whether event consumption is single-consumer, and test the chosen public future behavior after completion.
- **Evidence:** Code-path inspection of queue and marker handling. No service run.

## 35. NFWeb monitoring fails to publish a partial sample when the worker stats job times out

- **Severity:** Medium. A common fabric outage leaves the browser on an old sample instead of showing an updated failure state.
- **Location:** `norfab/clients/nfweb/monitoring/collector.py:94-105,119-145` and `norfab/core/client.py:658-681,1890-1921`.
- **Trigger:** `NFPClient.run_job(..., task="get_stats")` returns `None` on timeout. `MonitoringCollector.collect_once` immediately calls `worker_reply.items()`, raising `AttributeError`. The outer `collect` catches it and publishes no snapshot, even though the method otherwise builds a `partial` or `failed` snapshot with worker errors. A missing broker reply can similarly fail at `broker_reply.get`.
- **Proposed fix:** Normalize absent broker and worker replies to explicit errors before iterating or accessing them, then publish a snapshot with unreachable/degraded components. Add a public NFWeb monitoring test with timed-out broker and worker calls, verifying a new error-bearing sample.
- **Evidence:** Code-path inspection of the documented `run_job` timeout return and monitoring collector. No broker outage was induced.

## 36. Agent tool calls discard configured `job_data` after the first invocation

- **Severity:** Medium. Repeated calls to the same tool can receive different task arguments without any change in agent configuration.
- **Location:** `norfab/core/agent.py:217-242` and `norfab/workers/agent_worker/agent_worker.py:119-147`.
- **Trigger:** Define a tool with `norfab.kwargs.job_data`. The first call uses `pop("job_data", {})` on the stored tool dictionary, removing that configuration. A second call to the same runnable sees no configured `job_data`. If the first call also merges LLM-provided values, it mutates the popped dictionary that came from the definition.
- **Proposed fix:** Read the configured job data without mutating the tool definition, and copy it before merging per-call values. Apply the same change to both inline and worker agent implementations. Add a public tool invocation test that calls one tool twice and checks identical configured arguments.
- **Evidence:** Code-path inspection of both implementations. No LLM or agent service run.

## 37. Textual worker monitoring ignores its service and worker filters

- **Severity:** Low to medium. The panel displays and polls workers outside the scope configured by its caller.
- **Location:** `norfab/clients/textual/apps/monitoring.py:127-148,426-450`.
- **Trigger:** Construct `WorkerStatsPanel(services=["nornir", "netbox"], workers=...)`, as the monitoring screen does. The constructor stores both filters, but `fetch_data` always calls `run_job(service="all", workers="all", task="get_stats")` and never uses `self.services` or `self.target_workers` for filtering. It can also incur unnecessary calls to unrelated workers on each refresh.
- **Proposed fix:** Apply the configured worker selector when fetching, then filter rows by the configured service list, or simplify the public panel arguments if the intended behavior is truly all workers. Add a panel test through its public behavior with two services and a restricted worker selection.
- **Evidence:** Code-path inspection and reference search showing the stored filters have no other reads. No Textual UI run.

## 38. Textual monitoring performs blocking broker jobs during screen mounting

- **Severity:** Medium for startup responsiveness when broker or workers are slow or unavailable.
- **Location:** `norfab/clients/textual/apps/monitoring.py:71-77,147-148,321-325`.
- **Trigger:** Mount the monitoring screen while a broker or worker request is slow. `BasePanel.on_mount` calls `self.fetch_data()` synchronously on the UI thread. `WorkerStatsPanel.fetch_data` runs a blocking `NFPClient.run_job` without a short timeout, so the interface can freeze until the job's default timeout. Subsequent refreshes correctly use an executor, but the initial mount does not.
- **Proposed fix:** Schedule the first paint through the same async/executor path used by `_do_refresh`, and show a loading state until it completes. Set bounded monitoring request timeouts appropriate for the refresh interval. Add a UI lifecycle check with a deliberately slow client response.
- **Evidence:** Code-path inspection. No Textual UI run.

## 39. Robot library destroys NorFab at the end of the first suite

- **Severity:** Medium for Robot runs containing multiple suites or nested suites.
- **Location:** `norfab/clients/robot_client.py:22-45`.
- **Trigger:** `NorFabRobot` declares `ROBOT_LIBRARY_SCOPE = "GLOBAL"`, so one library instance can serve the whole Robot run. Its listener calls `self.nf.destroy()` on every `end_suite` event. After the first suite finishes, later suites retain the global library instance but its client and fabric are shut down.
- **Proposed fix:** Align teardown with the global library lifetime, for example by using an end-of-run listener hook or a reference-counted suite lifecycle. Add a Robot integration run containing two suites in one process and verify both can execute jobs.
- **Evidence:** Lifecycle code-path inspection. Existing Robot fixtures are separate suite files; no multi-suite run was performed.

## 40. Robot `nr.test` can crash while reporting a failed task

- **Severity:** Low to medium. The original task failure is obscured and the keyword cannot finish its normal error report.
- **Location:** `norfab/clients/robot_client.py:113-132`.
- **Trigger:** A task result has `failed=True` and `exception=None`, which is allowed by the result structure. The condition enters the failure branch, then formats `result["exception"].strip()`, raising `AttributeError` before the intended `ContinuableFailure` and detailed test log.
- **Proposed fix:** Format the exception defensively, falling back to the task result or a generic failure message. Add a Robot keyword integration case for a failed task without an exception string.
- **Evidence:** Code-path inspection of the short-circuit condition and unconditional `.strip()` call. No Robot suite run.

## 41. Robot keyword state leaks after an exception or client timeout

- **Severity:** Medium for multi-keyword test cases because later keywords can target the wrong workers.
- **Location:** `norfab/clients/robot_client.py:15-19,47-61,63-137,222-279,286-343`.
- **Trigger:** Call `Workers` and then an `nr.*` keyword whose client job times out or whose result processing raises. Each keyword calls `clean_global_data()` only after processing its result, so the exception skips cleanup. The module-global `DATA["workers"]` remains and can affect the next keyword or test case. Some host state is popped earlier, making the leaked selection inconsistent.
- **Proposed fix:** Keep per-library-instance state and clear it in a `finally` block around each job keyword. Add a Robot integration case with a failing keyword followed by another keyword that should use default targeting.
- **Evidence:** Code-path inspection of all three job keywords and global state cleanup. No Robot suite run.

## 42. NFCLI `create ip bulk` crashes when the optional interface list is omitted

- **Severity:** Medium for a documented optional CLI argument.
- **Location:** `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_create_ip_bulk.py:35-40,66-79`.
- **Trigger:** Run the bulk IP command without `interface-list`. The model declares `interface_list` optional with default `None`, but `CreateIpBulk.run` evaluates `"[" in kwargs["interface_list"]` unconditionally. If the key is absent it raises `KeyError`; if present as `None` it raises `TypeError`, before submitting any job.
- **Proposed fix:** Parse JSON only when `interface_list` is a string. Keep the optional argument absent or `None` when not supplied. Add a public shell command test for bulk IP allocation without an interface list.
- **Evidence:** Model and command-path inspection. No NetBox job run.

## 43. NetBox `create_ip_bulk` reports success when individual allocations fail

- **Severity:** Medium to high for automation that trusts the bulk task's `failed` field.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:799-830`.
- **Trigger:** One selected interface's `create_ip` call returns a failed `Result`, for example because allocation is exhausted or its interface lookup fails. `create_ip_bulk` stores only `create_ip.result` and never checks `create_ip.failed` or propagates `create_ip.errors`. The bulk result remains successful even when some interface allocations failed.
- **Proposed fix:** Accumulate per-interface status and errors, mark the bulk task failed or partial when any allocation fails, and preserve enough detail to identify affected device/interfaces. Add a public bulk-task integration case with one successful and one failed allocation.
- **Evidence:** Code-path inspection of the entire bulk loop. No NetBox service run.

## 44. NetBox `create_ip_bulk` crashes when its optional `devices` argument is omitted

- **Severity:** Low to medium. The published input model and task docstring both allow `devices=None`, but the task fails before querying interfaces.
- **Location:** `norfab/workers/netbox_worker/netbox_models.py:2287-2300` and `norfab/workers/netbox_worker/ip_tasks.py:710-715,769-785`.
- **Trigger:** Call the public bulk task with a prefix and an interface selector but no `devices`. The first log line handles `None` with `len(devices or [])`, then the event message calls `len(devices)` and raises `TypeError`. The downstream `get_interfaces` task also accepts `devices=None`.
- **Proposed fix:** Decide whether omitted devices means all matching devices or is invalid. If all is supported, handle `None` consistently. If it is invalid, make `devices` required in the input model and documentation so validation fails at the boundary. Add a public bulk-task test for the chosen contract.
- **Evidence:** Code-path and input-model inspection. No NetBox service run.

## Static-checker triage

- `poetry run vulture norfab tests --min-confidence 80` reported the two unused `model_name` parameters recorded in finding 31, plus callback parameters in `nfapi.py` whose names are required by the callback signatures.
- `poetry run ruff check norfab --select F821,F841` passed. A repository-wide Ruff run has many existing annotation/style findings; `tests/netbox_data.py` accounts for most F821 warnings because `nb` is installed into module globals at runtime in `main()`. Those `nb` warnings are not independently reported as bugs.
- `poetry run pytest -q core/test_simple_inventory_datastore.py` from `tests/` passed: 22 tests. It emitted the warning recorded in finding 9. A core DB test attempt stalled while starting its shared fixture and was interrupted; it yielded no result. Running collection from the repository root fails for that inventory test because its path assumes the documented `tests/` working directory; collection from `tests/` succeeds.
- `poetry run pytest -q clients/nfweb/test_history.py` from `tests/` passed: 3 tests. Those tests do not cover the idle-expiration read path in finding 24.
- `poetry run pytest -q clients/nfweb --disable-warnings --tb=line` from `tests/` yielded 43 passed and 5 failed, all covered by finding 28. `poetry run pytest -q nfcli/test_shell_common.py --disable-warnings --tb=line` passed: 7 tests.
