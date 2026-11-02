# Active bug hunt

Reviewed against the working tree on 1 November 2026. Only current, actionable behavioral defects and documentation discrepancies are listed. Existing finding IDs are preserved; gaps identify removed findings. New findings start at 45. No production code or tracked tests were changed.

Each entry distinguishes reproduced behavior from static code-path evidence. Severity reflects the stated trigger, not an unconditional impact. External Netbox, network-device, Containerlab and Robot integration scenarios were not run. This is a broad audit, not proof that unlisted paths are bug-free.

## Core

### 7. `delete_fetched_files` can delete outside its cache directory

- **Severity:** High. A caller of the public client method can accidentally remove unrelated local files or directories.
- **Location:** `norfab/core/client.py:1835-1873`.
- **Trigger:** Pass an absolute path or a path beginning with `..` as `filepath`. `os.path.join(files_folder, filepath)` accepts both; the absolute path replaces `files_folder`, and `..` escapes it. The method then calls `os.remove` or `shutil.rmtree` on glob matches without checking that their resolved paths remain under `fetchedfiles`.
- **Proposed fix:** Resolve the cache root and every matched path and reject any match whose `os.path.commonpath` is not the cache root. Validate the supplied pattern before glob expansion as well. Apply the same containment approach already used by `fetch_file` in fetch_file. Add a public-client test using a temporary sibling file that must remain intact after an escaping pattern.
- **Evidence:** Code-path inspection and a non-destructive Python check showing that `os.path.join` preserves `..` and replaces the base for absolute paths. I did not call the deletion method.

### 12. Task input validation discards Pydantic's converted values

- **Severity:** Medium. An input accepted by a task's schema can still fail inside the task because it receives the original type.
- **Location:** `norfab/core/worker.py:570-574,719-727`.
- **Trigger:** A task input model declares `value: int`, and the caller supplies `"1"`. Pydantic accepts and converts the value, but `validate_input` discards the model instance. The wrapper calls the task with the original string. A task computing `value + 1` raises `TypeError` after validation succeeds.
- **Proposed fix:** Decide at the task boundary whether accepted inputs should be normalized or whether models should reject coercible types. If normalization is intended, pass validated model values to the function while preserving special arguments and public signatures. Add a public task-call test that checks the value actually received by the task.
- **Evidence:** Isolated call to a `@Task(input=M)` function with `M.value: int`: `value=1` returned 2; `value="1"` raised `TypeError` inside the function after validation. The check ran in a separate Python process and changed no files.

### 27. FileSharing downloads still accept zero or negative transfer settings

- **Severity:** Low to medium.
- **Location:** `norfab/core/client.py:1942-1946,2050-2070`.
- **Trigger:** Call fetch_file('nf://...', chunk_size=0) without worker. Argument validation runs only when worker is supplied. After metadata retrieval the client opens/truncates the cache destination, then divides by zero while constructing transfer state, before its cleanup try/finally. Negative chunk sizes or nonpositive pipeline values also bypass the boundary validation.
- **Proposed fix:** Validate transfer settings for all source modes before metadata calls or local file changes; ensure destination ownership begins inside cleanup protection.
- **Evidence:** Isolated public-method probe reproduced ZeroDivisionError after one metadata call. Unlike the old implementation, the failed dictionary construction does not insert a transfer registry entry.

### 34. A second read of completed job events can wait forever

- **Severity:** Medium for clients that subscribe to or re-read a job future's events more than once.
- **Location:** `norfab/core/client.py:702-718`.
- **Trigger:** Finish an `NFPJobFuture`, consume `future.events()` once, then call `future.events()` again without a timeout. `mark_done` queues one terminal marker. The first iterator consumes it; the second blocks on an empty queue because `events()` never checks `done_event` when the queue is empty. Concurrent consumers have the same one-marker problem.
- **Proposed fix:** Make `events()` stop when `done_event` is set and the event queue is drained, with a bounded wake-up strategy for a blocking read. Document whether event consumption is single-consumer, and test the chosen public future behavior after completion.
- **Evidence:** Isolated current-code probe consumed events once, then confirmed a second iterator remained blocked in a daemon thread after completion. No service required.

### 45. Loading one worker inventory contaminates other workers' inherited configuration

- **Severity:** High.
- **Location:** `norfab/core/inventory.py:110-124,318-343`.
- **Trigger:** A shared wildcard dictionary supplies nested lists/dictionaries and a worker-specific entry overrides or extends them. Recursive merging assigns the shared objects by reference, then modifies them while applying the specific entry. Later workers inherit that first worker's settings; callers can also mutate future inventory results through a returned dictionary.
- **Evidence:** Isolated `WorkersInventory` probe: wildcard `items=[1]`, worker a `items=[2]`; loading a then b returns `[1,2]` for both. Constructor deep-copy fix does not prevent this internal aliasing.
- **Proposed fix:** Deep-copy each source before merging and verify worker inventories remain independent across lookup orders.

### 46. Explicit worker selectors bypass the requested service

- **Severity:** High for jobs that change configuration.
- **Location:** `norfab/core/broker.py:797-809,890-891`.
- **Trigger:** Request service nornir with a named Netbox worker while nornir has active workers. Both single-name and list selectors look up the global worker map without checking membership in the selected service. Common task names execute on the wrong service; service-specific names fail there instead of being rejected by routing.
- **Evidence:** Isolated `NFPBroker.filter_workers` call for service nornir and target netbox-1 selected a worker with service netbox.
- **Proposed fix:** Restrict explicit targets to the selected service, except for intentional service=all dispatch. Cover both string and list selectors.

### 47. Missing or unselected worker dependencies hang startup before its timeout begins

- **Severity:** High.
- **Location:** `norfab/core/nfapi.py:443-458,560-604`; `norfab/models/norfab_configuration_topology.py:58-89`.
- **Trigger:** A worker depends on an undefined worker, or a selected subset omits a dependency. Validation rejects cycles but accepts missing references. start_worker returns without starting the dependent; the outer startup loop waits forever. workers_init_timeout is measured only after this loop, and no exit-event check breaks it.
- **Evidence:** Model probe accepts worker a depending on missing. Control-flow inspection establishes repeated returns without progress; no hanging process launched.
- **Proposed fix:** Validate dependencies against the effective startup selection, or expand it, and enforce a deadline and cancellation throughout scheduling.

### 48. Startup hooks never run for a broker-only or client-only instance

- **Severity:** Medium.
- **Location:** `norfab/core/nfapi.py:546-548,616-618`.
- **Trigger:** Start with run_workers=False or an empty worker list. The early return skips all startup hooks, including when the broker has successfully started.
- **Evidence:** Public NorFab construction/start with no broker/workers and a recording hook produced zero hook calls.
- **Proposed fix:** Run startup hooks after requested components initialize even when there are no workers; test broker-only and client-only lifecycles.

### 49. A failing exit hook prevents all fabric cleanup

- **Severity:** High for resource cleanup.
- **Location:** `norfab/core/nfapi.py:652-675`.
- **Trigger:** An exit hook raises. destroy propagates before setting exiting or any client/worker/broker exit events, leaving the fabric running. Repeated destroy also repeats hooks before checking the idempotence guard.
- **Evidence:** Public lifecycle probe with a raising hook leaves clients_exit_event unset after destroy fails. No child processes started.
- **Proposed fix:** Ensure cleanup runs in finally, aggregate hook failures, and run hooks once per lifecycle.

### 50. Watchdog shutdown only terminates the watchdog thread

- **Severity:** High.
- **Location:** `norfab/core/monitoring.py:267-279`; `norfab/core/worker.py:1763-1766`.
- **Trigger:** memory_threshold_action=shutdown and RSS exceeds threshold. check_ram raises SystemExit inside WorkerWatchDog.run, which terminates that Python thread rather than the worker process. The worker continues accepting work without further health checks.
- **Evidence:** Isolated thread probe with RSS=2 MiB and threshold=1 MiB exited the check thread while the worker exit event remained unset.
- **Proposed fix:** Signal controlled worker shutdown and ensure its job loop observes it; test the worker process actually exits.

### 51. Disabling watchdog startup breaks monitoring tasks

- **Severity:** Medium.
- **Location:** `norfab/core/worker.py:1763-1766,2825-2829,2843`; `norfab/workers/nornir_worker/nornir_worker.py:444-446`.
- **Trigger:** Set supported autostart_watchdog=False. No self.watchdog exists, but get_stats and get_watchdog_configuration dereference it unconditionally. Nornir connection/task operations also access the missing watchdog.
- **Evidence:** Initialization and complete task paths inspected; Nornir's custom initialization has the same conditional assignment.
- **Proposed fix:** Separate watchdog object creation from starting its thread, or make consumers explicitly support disabled watchdogs.

### 52. Agent discovery crashes when one service returns a timeout result

- **Severity:** Medium.
- **Location:** `norfab/core/agent.py:125-135,825-830`.
- **Trigger:** Default agent construction discovers a registered service whose list_tasks times out or returns a failed Result with result=None. The response is truthy, and iteration over wres.get('result', []) raises TypeError; default [] does not replace explicit None. One unavailable service prevents building the agent.
- **Evidence:** Isolated _make_norfab_tools call with the current public timeout envelope reproduced TypeError at line 135.
- **Proposed fix:** Check worker failure and payload shape before iterating; log and skip unavailable service discovery.

### 53. Agent filesystem tools follow links outside their promised directory boundary

- **Severity:** High when filesystem tools are enabled.
- **Location:** `norfab/core/agent.py:493-503,535-542,575-583,620-638`.
- **Trigger:** A symlink or Windows junction inside the permitted working directory points outside it. _safe_path uses abspath and a lexical prefix check; read/write/edit then follow the link and access external files despite the stated directory confinement.
- **Evidence:** Static path and file-open inspection. No external files read or changed.
- **Proposed fix:** Resolve real paths (including existing destination parents) before checking containment and test symlink/junction escapes for read and write tools.

### 54. Completed job futures and unconsumed events accumulate for the entire client lifetime

- **Severity:** Medium for long-running clients.
- **Location:** `norfab/core/client.py:682,699,1383-1386,2338,2463-2464`.
- **Trigger:** Repeated run_job calls, including normal polling dashboards, retain every future in client.job_futures. Each future retains its final result snapshot and unbounded event queue even when the caller never requests events. Dispatcher scans all retained futures every iteration, so memory and idle scanning cost grow with total historical jobs.
- **Evidence:** Complete reference search found insertion and reads but no eviction/removal path; events are always queued. No load test run.
- **Proposed fix:** Remove completed futures from the client's active registry while allowing caller-held handles to remain usable, and define bounded retention for unconsumed events.

### 55. Worker result reads do not enforce the submitting client's ownership

- **Severity:** High for confidentiality between fabric clients.
- **Location:** `norfab/core/worker.py:1420-1456` (contrast PUT ownership check at `:1304-1306`).
- **Trigger:** A different connected client sends GET for a known job UUID. _get retrieves solely by UUID and returns persisted results to the requester without comparing job_info.client_address. Result payloads can contain configuration or secrets. UUID knowledge is required; this is not a claim that UUIDs can be guessed.
- **Evidence:** Complete GET lookup/routing path inspected; ownership is persisted in the job record but unused here.
- **Proposed fix:** Require requester ownership before returning state/results and cover cross-client reads through the public protocol.

## Workers

### 5. `create_ip` still reports success when requested peer allocation fails

- **Severity:** Medium.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:949-965`.
- **Trigger:** Request peer allocation when its recursive create_ip raises or returns failed=True. The partial fix now appends peer errors, but never sets ret.failed=True. Local allocation remains reported successful even though the requested peer operation failed.
- **Proposed fix:** Propagate peer failure to the parent failed flag and preserve the warning that the local IP may already exist. Assert the top-level flag and errors through the public task.
- **Evidence:** Rechecked current code and Result model, task executor and client response handling: none derives failed from errors. Earlier Fixed status was incorrect.

### 14. Workflow reports a successful task after a condition error or stopped failed step

- **Severity:** Medium. A caller checking the workflow task's top-level `failed` field can treat an incomplete or failed workflow as successful.
- **Location:** `norfab/workers/workflow_worker/workflow_worker.py:318-331,360-407`.
- **Trigger:** A `run_if_*` condition refers to a missing prior step, or a step fails while `stop_if_fail=True`. The worker records an inner failed/error step and breaks, but returns the initial `Result` without setting `ret.failed` or `ret.errors`. Existing workflow tests check nested step data but do not assert the outer task result for these paths.
- **Proposed fix:** Define whether an aborted workflow is a failed task, then set the outer failure and error fields for condition errors and stop-on-failure cases. Add public workflow-task integration assertions for both the nested step and top-level result.
- **Evidence:** Code-path inspection against `tests/services/workflow/test_run.py:177-230`. No live workflow service run.

### 15. Inline workflow execution removes metadata from the caller's dictionary

- **Severity:** Low for direct in-process callers that reuse a workflow definition.
- **Location:** `norfab/workers/workflow_worker/workflow_worker.py:322-331`.
- **Trigger:** Call `run` twice with the same inline dictionary. The first call removes `name`, `description`, and `remove_no_match_results` using `pop`. The second call uses defaults, so its result key and filtering behavior can differ. The URL path produces a fresh dictionary and avoids this issue.
- **Proposed fix:** Copy the workflow dictionary before removing metadata, or read the metadata with `get` and iterate only step entries. Add a public task test that reuses the same inline definition and verifies both results are identical.
- **Evidence:** Code-path inspection of the public task. No service run. The URL filename-derived `workflow_name` at lines 322-324 is also dead code because line 329 overwrites it unconditionally.

### 16. Containerlab command collection can block indefinitely before checking its timeout

- **Severity:** High for long-running or noisy Containerlab commands; a task can hang beyond its declared timeout.
- **Location:** `norfab/workers/containerlab_worker/containerlab_worker.py:325-353`.
- **Trigger:** The helper calls blocking `proc.stderr.readline()` inside its timeout loop and reads stdout only after the child exits. A child that emits no newline on stderr can block that read, so the timeout check is not reached. A child that fills the stdout pipe while the parent reads stderr can also block on writing stdout, leaving both processes waiting.
- **Proposed fix:** Drain stdout and stderr concurrently with `communicate(timeout=...)` or dedicated reader threads, then terminate/kill and reap the child on timeout. Keep forwarding progress events if needed without blocking either pipe. Add a focused subprocess test using a bounded child that writes enough stdout to fill a pipe and another that stays quiet beyond the timeout.
- **Evidence:** Code-path inspection of the subprocess loop. No Containerlab process was launched.

### 19. FakeNOS child errors are returned as successful string results

- **Severity:** Medium. An inspection can report a nonsensical host count and `failed=False` after the child fails to enumerate hosts.
- **Location:** `norfab/workers/fakenos_worker/fakenos_worker.py:99-107,190-195,499-507`.
- **Trigger:** The child catches an exception from `_get_hosts_as_list`, stores an error message string in `result_queue`, and the parent only raises queue values that are `Exception` objects. The string passes through as `hosts`; `inspect_networks` computes `len(hosts)` and returns success.
- **Proposed fix:** Send a structured success/error envelope through the queue and raise or mark the task failed when the child reports an error. Add a public inspection test for a child-side failure and assert that the returned task is failed with the original message.
- **Evidence:** Code-path inspection of both sides of the queue. No FakeNOS service run.

### 20. FastAPI and FastMCP discovery stop retrying a service after a partial failure

- **Severity:** Medium. Some task endpoints or MCP tools can remain missing until discovery is manually retriggered or the worker restarts.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:185-254`; `norfab/workers/fastmcp_worker/fastmcp_worker.py:409-466`.
- **Trigger:** FastAPI records a service key before all its routes register; a later exception ends the cycle, and subsequent cycles skip that service. FastMCP does the same before constructing all tools. It also catches individual tool-construction errors, leaving the service marked discovered despite a missing tool. Later startup cycles skip the service in both workers.
- **Proposed fix:** Mark a service complete only after all its eligible tasks have been processed successfully. Retry missing routes and tools on later cycles. Add integration cases where an initial transient failure is corrected during startup discovery.
- **Evidence:** Code-path inspection of both retry loops. No FastAPI or FastMCP service run.

### 21. One-cycle API discovery calls sleep after their work is finished

- **Severity:** Low to medium. Explicit discovery jobs have avoidable latency after doing their work.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:272-273`; `norfab/workers/fastmcp_worker/fastmcp_worker.py:489-490`.
- **Trigger:** The public FastAPI `discover` task calls its loop with `cycles=1` and still sleeps ten seconds after decrementing to zero. FastMCP's one-cycle discovery follows the same pattern and sleeps five seconds.
- **Proposed fix:** Sleep only when another cycle will run and the worker has not been asked to exit in both workers. Add focused public discovery timing assertions or equivalent deterministic checks around the final-cycle branch.
- **Evidence:** Code-path inspection. No service run.

### 22. Re-storing a bearer token under another user corrupts ownership metadata

- **Severity:** Medium. Listing and deleting tokens by username can disagree about who owns a valid token.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:533-545`; `norfab/workers/fastmcp_worker/fastmcp_worker.py:779-789` and their list/delete tasks.
- **Trigger:** Store token `T` for user A, then call `bearer_token_store(username=B, token=T)`. The second call reuses the cached value containing `username=A` but writes it with cache tag B. Listing B's tokens shows an entry labeled A; deleting A's tokens by tag leaves T active, while deleting B's tokens removes A's token.
- **Proposed fix:** Reject an attempt to bind an existing token to a different username, or explicitly replace both value and tag in one documented operation, in both workers. Add public task tests covering duplicate token storage across two usernames, listing, revocation, and `bearer_token_check`.
- **Evidence:** Code-path inspection of the cache value/tag handling. Existing tests use a single username per token. No live FastAPI worker run.

### 43. NetBox `create_ip_bulk` reports success when individual allocations fail

- **Severity:** Medium to high for automation that trusts the bulk task's `failed` field.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:1077-1096`.
- **Trigger:** One selected interface's `create_ip` call returns a failed `Result`, for example because allocation is exhausted or its interface lookup fails. `create_ip_bulk` stores only `create_ip.result` and never checks `create_ip.failed` or propagates `create_ip.errors`. The bulk result remains successful even when some interface allocations failed.
- **Proposed fix:** Accumulate per-interface status and errors, mark the bulk task failed or partial when any allocation fails, and preserve enough detail to identify affected device/interfaces. Add a public bulk-task integration case with one successful and one failed allocation.
- **Evidence:** Code-path inspection of the entire bulk loop. No NetBox service run.

### 44. NetBox `create_ip_bulk` crashes when its optional `devices` argument is omitted

- **Severity:** Low to medium. The published input model and task docstring both allow `devices=None`, but the task fails before querying interfaces.
- **Location:** `norfab/workers/netbox_worker/ip_tasks.py:1043-1049` and `CreateIpBulkInput` in `norfab/workers/netbox_worker/netbox_models.py`.
- **Trigger:** Call the public bulk task with a prefix and an interface selector but no `devices`. The first log line handles `None` with `len(devices or [])`, then the event message calls `len(devices)` and raises `TypeError`. The downstream `get_interfaces` task also accepts `devices=None`.
- **Proposed fix:** Decide whether omitted devices means all matching devices or is invalid. If all is supported, handle `None` consistently. If it is invalid, make `devices` required in the input model and documentation so validation fails at the boundary. Add a public bulk-task test for the chosen contract.
- **Evidence:** Code-path and input-model inspection. No NetBox service run.

### 56. Netbox caches cross-contaminate configured instances

- **Severity:** High, wrong-source inventory can drive automation.
- **Location:** `norfab/workers/netbox_worker/devices_tasks.py:270,310`; `norfab/workers/netbox_worker/interfaces_tasks.py:298,406`; `norfab/workers/netbox_worker/circuits_tasks.py:205,401`; shared cache instantiated once in `norfab/workers/netbox_worker/netbox_worker.py:605-620`.
- **Trigger:** query same device name/circuit CID from two configured instances with cache="force" (or cache=True and matching timestamps). Keys contain task and object identity but omit instance, so instance B receives A's records.
- **Evidence:** probe preloaded A's r1 cache record, queried instance-B with force, got serial INSTANCE-A.
- **Proposed fix:** namespace read/write/cache-management keys by instance; cover same names/CIDs in two instances via public client.

### 57. Failed Git publication is never retried for the same commit

- **Severity:** High for configuration distribution: stale contents reported synchronized.
- **Location:** `norfab/workers/filesharing_worker/git_tasks.py:368-391,395-447`.
- **Trigger:** successfully publish old revision; fetch new revision and checkout succeeds; staging copy or snapshot replacement fails while old mount remains. Next sync compares private checkout HEAD to fetched SHA, decides unchanged, and skips publication, forever retaining old snapshot until another commit appears.
- **Evidence:** actual temporary Git repository probe: initial cloned, injected copy OSError failed, retry unchanged, published text old instead of new.
- **Proposed fix:** compare fetched SHA against last successfully published revision; update that revision only after swap succeeds. Retry failed publication even when checkout unchanged.

### 58. Containerlab enrichment discards dictionary branch and instance

- **Severity:** High when branch selects staging inventory; wrong branch/instance read.
- **Location:** `norfab/workers/nornir_worker/inventory_tasks.py:446-450`.
- **Trigger:** `nornir_inventory_load_containerlab(load_netbox={"branch":"review","instance":"secondary"})` without separate override args. kwargs.update retains options then unconditional assignments replace both with None. Docstring explicitly promises dictionary values when overrides omitted.
- **Evidence:** probe captured forwarded kwargs branch=None,instance=None.
- **Proposed fix:** apply separate branch/instance overrides only when supplied.

### 59. Nornir inventory reload crashes when Netbox is not configured

- **Severity:** Medium; public task cannot be used on a worker with no netbox setting (or False/null).
- **Location:** `norfab/workers/nornir_worker/inventory_tasks.py:242-249` (also startup invocation in `norfab/workers/nornir_worker/nornir_worker.py:1062-1063` occurs whenever key exists).
- **Trigger:** call public nornir_inventory_load_netbox without netbox=True/dict; kwargs is never initialized. An inventory explicitly setting netbox=False also triggers this at startup.
- **Evidence:** probe raised UnboundLocalError for kwargs.
- **Proposed fix:** handle disabled/missing Netbox configuration at boundary with explicit no-op/failure; only invoke startup loading when enabled.

### 60. Nornir file copy crashes for accepted local source paths

- **Severity:** Medium.
- **Location:** `norfab/workers/nornir_worker/file_copy_task.py:88-101`; model `norfab/workers/nornir_worker/nornir_models.py:864-867` advertises local path or URL.
- **Trigger:** pass local filename to file_copy. source_file_local is assigned only for URLs but always read for netmiko.
- **Evidence:** probe local.txt raised UnboundLocalError before device I/O.
- **Proposed fix:** initialize local source to source_file, then replace with fetched path for URLs; verify local-file semantics and integration coverage.

### 61. Renamed Nornir hosts use aliases as Netbox enrichment selectors

- **Severity:** Medium; wrong or absent interfaces/connections/circuits/BGP data.
- **Location:** `norfab/workers/netbox_worker/nornir_inventory_tasks.py:106-115,150-160,173-191,204-231`.
- **Trigger:** device config_context.nornir.name differs from real Netbox device name. hosts keys change to aliases, then enrichment queries devices=list(hosts). Netbox APIs need actual device names; responses are also indexed directly into hosts without reverse mapping.
- **Evidence:** probe real device r1 with alias alias captured get_interfaces(devices=['alias']).
- **Proposed fix:** preserve mapping Netbox name to Nornir host name for all child task selectors and response indexing.

### 62. Containerlab platform fallback produces an invalid node kind and image

- **Severity:** Medium; documented fallback yields undeployable topology.
- **Location:** `norfab/workers/netbox_worker/containerlab_inventory_tasks.py:209-224`; devices_tasks.py returns dict(device), retaining platform nested object.
- **Trigger:** device has platform but no norfab.containerlab.kind config. Assigns entire platform dict to node kind, then interpolates it into image.
- **Evidence:** probe produced kind={'name':'ceos','slug':'ceos'} and image="{'name': 'ceos', 'slug': 'ceos'}:latest".
- **Proposed fix:** derive supported Containerlab scalar kind from platform name/slug (or explicit mapping); test config-context-absent case.

### 63. Containerlab deploy accepts omitted lab name but crashes after topology retrieval

- **Severity:** Medium.
- **Location:** `norfab/workers/containerlab_worker/containerlab_worker.py:992-993,1102-1106`; `containerlab_models.py:217-222`.
- **Trigger:** deploy_netbox(devices=[...]) or filters without lab_name or tenant; only tenant is used as fallback, leaving lab_name None for os.path.join. Dry-run returns earlier and can falsely suggest request deployable.
- **Evidence:** direct control flow and Python path semantics. No Containerlab launched.
- **Proposed fix:** require/derive concrete safe lab name before external calls and use it consistently in topology and paths.

### 64. FastAPI and MCP asynchronous handlers block their server event loops

- **Severity:** High for concurrent API/tool requests and responsiveness under slow workers.
- **Location:** `norfab/workers/fastapi_worker/fastapi_worker.py:83-102`; `norfab/workers/fastmcp_worker/fastmcp_worker.py:1085-1115`.
- **Trigger:** slow run_job (default FastAPI timeout 600s) called directly inside async def endpoint/call_tool. Synchronous client waits block the event loop, preventing other requests on that loop and potentially health checks/streaming while job runs.
- **Evidence:** code path; no live server concurrency test.
- **Proposed fix:** run blocking client work in a worker thread or async client integration; verify parallel slow/fast requests.

### 65. Pynetbox operations ignore configured HTTP timeouts

- **Severity:** Medium to high; stalled Netbox requests hold task threads indefinitely.
- **Location:** `norfab/workers/netbox_worker/netbox_worker.py:540-543`.
- **Trigger:** Netbox accepts TCP connection but never returns a REST response. _get_pynetbox mounts ordinary HTTPAdapter with retries and never provides timeout, unlike GraphQL/direct REST paths. netbox_connect_timeout/netbox_read_timeout have no effect here.
- **Evidence:** adapter construction and requests timeout default; no hanging live network run.
- **Proposed fix:** enforce configured connect/read timeout through session adapter or pynetbox-supported session policy; verify stalled-response behavior.

## Clients

### 23. NFWeb topology history can disappear for the same device set after selection

- **Severity:** Low to medium for mixed-case device names in a multi-device scope.
- **Location:** `norfab/clients/nfweb/topology/collector.py:67,246-258` and `norfab/clients/nfweb/topology/history.py:60-72,87-109`.
- **Trigger:** Start NFWeb with configured devices `['a', 'B']`. The collector stores the scope as `['B', 'a']` using default sorting. Selecting those same devices in the browser stores `['a', 'B']` using casefold sorting. History queries compare device lists for exact equality, so snapshots from the first scope no longer appear even though the device set is identical.
- **Proposed fix:** Canonicalize device scopes with one sort rule at both initialization and selection, and consider comparing normalized sets when reading older snapshots. Add a history/collector test with mixed-case names that selects the same set after startup.
- **Evidence:** Code-path inspection plus an isolated Python check confirming the two sort orders differ for `['a', 'B']`. No NFWeb server run.

### 24. NFWeb can serve topology snapshots after the retention window expires

- **Severity:** Medium for the documented maximum history window and stale browser state.
- **Location:** `norfab/clients/nfweb/topology/history.py:20-41,60-85,161-170` and `norfab/clients/nfweb/topology/web.py:182-189`.
- **Trigger:** Insert a snapshot, then leave NFWeb idle beyond the configured retention window. Cleanup runs at store initialization and after inserts only. `history()` and `logs()` apply a cutoff at read time, but `latest()` and `get(snapshot_id)` do not. A new WebSocket connection can receive an expired snapshot as its latest state, and a direct snapshot request can retrieve expired data before another insert triggers cleanup.
- **Proposed fix:** Apply the retention cutoff in `latest()` and `get()` queries as well as periodic cleanup for bounded on-disk storage. Add a store test that advances time beyond retention without inserting another snapshot and checks all read methods.
- **Evidence:** Code-path inspection. No NFWeb server run.

### 25. NFWeb monitoring keeps and serves expired samples after polling failures

- **Severity:** Low to medium. A prolonged collection failure leaves the dashboard showing stale data as its latest sample and retains history past the configured window.
- **Location:** `norfab/clients/nfweb/monitoring/collector.py:44-52,89-114` and `norfab/clients/nfweb/monitoring/web.py:35-56,94-108`.
- **Trigger:** Collect one monitoring sample, then have later `collect_once` calls raise for longer than `retention_minutes`. `collect` returns from its exception handler before pruning `history`. The `latest` property and HTTP/history/WebSocket handlers return the old sample without checking its age.
- **Proposed fix:** Prune history against current UTC time on reads or on every collection attempt, including failed attempts, and make `latest` return `None` when its sample has expired. Add a collector/API test that advances beyond retention while collection raises.
- **Evidence:** Code-path inspection. Existing monitoring tests cover normal sample pruning, not repeated failures beyond retention.

### 35. NFWeb monitoring drops the entire sample when the client job fails

- **Severity:** Medium for monitoring reliability during client failures.
- **Location:** `norfab/clients/nfweb/monitoring/collector.py:119-145` and `norfab/core/client.py:721-748,2380-2396`.
- **Trigger:** `NFPClient.run_job` returns `None` on client failure or shutdown, or after a terminal failed job without result data. `collect_once` calls `worker_reply.items()` and raises `AttributeError`; `collect` records last_error but publishes no new snapshot, discarding already available broker statistics. Ordinary expiry now returns failed worker dictionaries and is handled by the collector; the original claim that every worker timeout causes this error is obsolete.
- **Proposed fix:** Normalize an absent worker reply into an explicit collection error and publish an error-bearing sample with the available broker/client data. Cover client-failure and ordinary-timeout results separately.
- **Evidence:** Current client result contract and collector control-flow inspection; no runtime client shutdown induced.

### 37. Textual worker monitoring ignores its service and worker filters

- **Severity:** Low to medium. The panel displays and polls workers outside the scope configured by its caller.
- **Location:** `norfab/clients/textual/apps/monitoring.py:127-148,426-450`.
- **Trigger:** Construct `WorkerStatsPanel(services=["nornir", "netbox"], workers=...)`, as the monitoring screen does. The constructor stores both filters, but `fetch_data` always calls `run_job(service="all", workers="all", task="get_stats")` and never uses `self.services` or `self.target_workers` for filtering. It can also incur unnecessary calls to unrelated workers on each refresh.
- **Proposed fix:** Apply the configured worker selector when fetching, then filter rows by the configured service list, or simplify the public panel arguments if the intended behavior is truly all workers. Add a panel test through its public behavior with two services and a restricted worker selection.
- **Evidence:** Code-path inspection and reference search showing the stored filters have no other reads. No Textual UI run.

### 38. Textual monitoring performs blocking broker jobs during screen mounting

- **Severity:** Medium for startup responsiveness when broker or workers are slow or unavailable.
- **Location:** `norfab/clients/textual/apps/monitoring.py:71-77,147-148,321-325`.
- **Trigger:** Mount the monitoring screen while a broker or worker request is slow. `BasePanel.on_mount` calls `self.fetch_data()` synchronously on the UI thread. `WorkerStatsPanel.fetch_data` runs a blocking `NFPClient.run_job` without a short timeout, so the interface can freeze until the job's default timeout. Subsequent refreshes correctly use an executor, but the initial mount does not.
- **Proposed fix:** Schedule the first paint through the same async/executor path used by `_do_refresh`, and show a loading state until it completes. Set bounded monitoring request timeouts appropriate for the refresh interval. Add a UI lifecycle check with a deliberately slow client response.
- **Evidence:** Code-path inspection. No Textual UI run.

### 39. Robot library destroys NorFab at the end of the first suite

- **Severity:** Medium for Robot runs containing multiple suites or nested suites.
- **Location:** `norfab/clients/robot_client.py:22-45`.
- **Trigger:** `NorFabRobot` declares `ROBOT_LIBRARY_SCOPE = "GLOBAL"`, so one library instance can serve the whole Robot run. Its listener calls `self.nf.destroy()` on every `end_suite` event. After the first suite finishes, later suites retain the global library instance but its client and fabric are shut down.
- **Proposed fix:** Align teardown with the global library lifetime, for example by using an end-of-run listener hook or a reference-counted suite lifecycle. Add a Robot integration run containing two suites in one process and verify both can execute jobs.
- **Evidence:** Lifecycle code-path inspection. Existing Robot fixtures are separate suite files; no multi-suite run was performed.

### 40. Robot `nr.test` can crash while reporting a failed task

- **Severity:** Low to medium. The original task failure is obscured and the keyword cannot finish its normal error report.
- **Location:** `norfab/clients/robot_client.py:113-132`.
- **Trigger:** A task result has `failed=True` and `exception=None`, which is allowed by the result structure. The condition enters the failure branch, then formats `result["exception"].strip()`, raising `AttributeError` before the intended `ContinuableFailure` and detailed test log.
- **Proposed fix:** Format the exception defensively, falling back to the task result or a generic failure message. Add a Robot keyword integration case for a failed task without an exception string.
- **Evidence:** Code-path inspection of the short-circuit condition and unconditional `.strip()` call. No Robot suite run.

### 41. Robot keyword state leaks after an exception or client timeout

- **Severity:** Medium for multi-keyword test cases because later keywords can target the wrong workers.
- **Location:** `norfab/clients/robot_client.py:15-19,47-61,63-137,222-279,286-343`.
- **Trigger:** Call `Workers` and then an `nr.*` keyword whose client job times out or whose result processing raises. Each keyword calls `clean_global_data()` only after processing its result, so the exception skips cleanup. The module-global `DATA["workers"]` remains and can affect the next keyword or test case. Some host state is popped earlier, making the leaked selection inconsistent.
- **Proposed fix:** Keep per-library-instance state and clear it in a `finally` block around each job keyword. Add a Robot integration case with a failing keyword followed by another keyword that should use default targeting.
- **Evidence:** Code-path inspection of all three job keywords and global state cleanup. No Robot suite run.

### 42. NFCLI `create ip bulk` crashes when the optional interface list is omitted

- **Severity:** Medium for a documented optional CLI argument.
- **Location:** `norfab/clients/nfcli_shell/netbox/netbox_picle_shell_create_ip_bulk.py:35-40,66-79`.
- **Trigger:** Run the bulk IP command without `interface-list`. The model declares `interface_list` optional with default `None`, but `CreateIpBulk.run` evaluates `"[" in kwargs["interface_list"]` unconditionally. If the key is absent it raises `KeyError`; if present as `None` it raises `TypeError`, before submitting any job.
- **Proposed fix:** Parse JSON only when `interface_list` is a string. Keep the optional argument absent or `None` when not supplied. Add a public shell command test for bulk IP allocation without an interface list.
- **Evidence:** Model and command-path inspection. No NetBox job run.

### 66. NFCLI job lookup crashes for an unknown UUID

- **Severity:** Low.
- **Location:** `norfab/clients/nfcli_shell/norfab_jobs_shell.py:63-75`; nullable DB contract `norfab/core/client.py:432-449`.
- **Trigger:** `show jobs uuid <missing-uuid>` without details. `get_job` returns None, command makes `[None]`, then indexes `j["uuid"]`.
- **Evidence:** Isolated call of public `NorFabJobsShellCommands.run(uuid='missing')` with mock public client DB returning None reproduces `TypeError: 'NoneType' object is not subscriptable` at line 75.
- **Proposed fix:** Return an empty list or explicit job-not-found message before projecting rows; test missing and present IDs.

### 67. FastAPI token listing crashes with verbose results or a failed worker

- **Severity:** Medium.
- **Location:** `norfab/clients/nfcli_shell/fastapi/fastapi_picle_shell_auth.py:87-91` and `norfab/clients/nfcli_shell/common.py:285-290`.
- **Trigger:** `fastapi auth list-tokens verbose-result` causes log_error_or_result to return each whole worker envelope. ListAuthToken iterates its string keys as token dictionaries and executes `**token`. The same occurs by default for failed worker envelopes (`verbose_on_fail=True`).
- **Evidence:** Isolated call of `ListAuthToken.run(verbose_result=True)` with a successful mocked run_future_job response reproduced `TypeError: 'str' object is not a mapping` at line 91. No token service mutation.
- **Proposed fix:** Preserve verbose/failure envelopes directly; flatten only successful token lists, with explicit handling of mixed successes/failures.

### 68. Clearing the shared topology selection leaves other browsers displaying the old graph

- **Severity:** Medium.
- **Location:** `norfab/clients/nfweb/topology/collector.py:246-258`, `norfab/clients/nfweb/topology/web.py:158-180`, `frontend/src/App.tsx:246-265,516-550`.
- **Trigger:** Open two browser clients, clear the selected devices in one. `select_devices([])` changes shared scope, clears caches, and returns None before collecting or invoking on_snapshot. Only the initiating browser handles the POST response by clearing its graph. Other browsers receive no reset message, retain the old graph and scope indefinitely, and periodic collect returns None for empty selection.
- **Evidence:** Inspection of complete selection, broadcast and browser callback paths. No browser runtime run.
- **Proposed fix:** Publish selection/reset state to every connected browser, including empty selections; update selection controls as well as the graph when shared scope changes.

### 69. Topology browser history retains expired snapshot IDs indefinitely

- **Severity:** Medium for long-lived sessions.
- **Location:** `norfab/clients/nfweb/frontend/src/App.tsx:246-265,275-281`; server expiry `norfab/clients/nfweb/topology/history.py:161-171`.
- **Trigger:** Leave topology open beyond configured retention. Initial history is fetched once; each live snapshot appends another timeline entry with no cutoff or cap. The server deletes old snapshots on inserts, but the browser retains those IDs indefinitely. Timeline entries outside retention fail with 404 and the client list grows without bound.
- **Evidence:** Static inspection of every setHistory call: only scope application resets/reloads history; normal live updates never remove old entries. No frontend dependencies installed, so no browser run.
- **Proposed fix:** Enforce a timestamp cutoff matching server retention, or periodically reconcile with scoped server history. Test a session spanning the cutoff.

### 70. BGP layer drops conflicting reverse-endpoint health observations

- **Severity:** Medium: an unhealthy BGP observation can be rendered healthy.
- **Location:** `norfab/clients/nfweb/topology/layers.py:870-879`.
- **Trigger:** Both selected endpoints report the same local/remote address pair in opposite directions, with first observation established and second not established (a transitional/asymmetric state). Symmetric `_link_id` matches; `seen` drops the second observation before its critical health reaches collector._merge. Result depends on worker/result order and stays healthy when the first endpoint is healthy.
- **Evidence:** Complete BGPLayer seen/health paths and symmetric `_link_id` at lines 265-268. Static, no network test.
- **Proposed fix:** Merge observations with worst_health instead of first-wins de-duplication; retain endpoint-specific state. Test both result orders.

### 71. Textual advertises a refresh keyboard shortcut that performs no refresh

- **Severity:** Low.
- **Location:** `norfab/clients/textual/app.py:133-136,174-175`.
- **Trigger:** Press Ctrl+R, displayed in the footer as Refresh. Binding dispatches `action_refresh`, whose body is only `pass`.
- **Evidence:** Binding/action inspection. Mouse Refresh in MonitoringScreen does have working behavior, confirming intended action exists separately.
- **Proposed fix:** Dispatch refresh to the mounted screen/panels and verify keyboard and button trigger equivalent refresh behavior.

### 72. FakeNOS scale profiles omit a required IPv6 BGP getter command

- **Severity:** Medium for the NFWeb scale-test environment.
- **Location:** `tests/clients/nfweb/test_collector.py:607-633` and `tests/nf_inventory_scale/fakenos/nos/spine01.site1.yaml` (other profiles not reached after first failure).
- **Trigger:** Current installed ttp_templates bgp_neighbors getter for this platform requests `show ipv6 bgp peers vrf all | json`; spine01.site1 profile lacks it. NFWeb scale getter coverage fails, and a real scale collection cannot provide the required canned output.
- **Evidence:** `poetry run pytest -q tests/clients/nfweb --confcutdir=tests/clients/nfweb --disable-warnings --tb=short`: 46 passed, 6 failed; first new failure explicitly lists the missing command. Five others are old #28.
- **Proposed fix:** Update applicable FakeNOS profiles with valid command outputs or pin/align getter templates with the test fixture contract; rerun coverage across all hosts.

## Tests

### 3. Circuit test-data seeding mutates its reusable fixture records

- **Severity:** Medium for repeated population runs in one Python process.
- **Location:** `tests/netbox_data.py:3863-3870,3940` and matching B-side termination handling.
- **Trigger:** `create_circuits()` pops `termination_a` and `termination_b` directly from dictionaries in the module-level `circuits` list. A second call raises `KeyError` before reaching NetBox. The first call also removes cable data from termination dictionaries. This makes fixture setup dependent on call order and prevents reliable retries after partial failure.
- **Proposed fix:** Copy each circuit and its nested termination dictionaries before removing setup-only keys. Keep the module-level fixture records intact. Add a test that runs preparation twice against the same literal record and checks that both create payloads match.
- **Evidence:** Code-path inspection; the mutation and second-call failure follow directly from Python `dict.pop` semantics.

### 6. NetBox IP tests delete addresses they did not create

- **Severity:** High for runs against a shared or reused NetBox instance; the test suite can destroy existing IP records.
- **Location:** `tests/services/netbox/common.py:67-70`; setup calls in `tests/services/netbox/test_ipam.py:2869,2912,2996`.
- **Trigger:** Run the `create_ip` integration tests when a target prefix such as `10.0.0.0/24` already contains IP records. The `delete_ips` helper lists every address under the prefix and deletes it before the test allocates any addresses. It does not track which records the test created.
- **Proposed fix:** Give each test a dedicated prefix that it first verifies is free, or record IDs created by that test and delete only those IDs in `finally`. Avoid using the broad deletion helper in test setup. This follows the repository rule to never delete pre-existing data.
- **Evidence:** Helper and call-site inspection. I did not run these tests because they would mutate a NetBox instance without a known isolated fixture.

### 28. Every NFWeb monitoring collector test fails during setup

- **Severity:** Medium for test coverage: the monitoring behavior under test is never reached.
- **Location:** `tests/clients/nfweb/test_monitoring.py:15-39` and the broker/worker process records at lines 47-51 and 81-85; required model field at `norfab/core/monitoring.py:16-27`.
- **Trigger:** Run `poetry run pytest -q tests/clients/nfweb --confcutdir=tests/clients/nfweb --disable-warnings --tb=short` from the repository root. All five tests fail in `make_client()` because its `ClientMonitoringStats.process` data omits required `threads`. The broker and worker process records in the same helper omit it too, so fixing only the first record would still leave later validation failures.
- **Proposed fix:** Update the test's explicit process records to the current monitoring schema, then rerun all five tests to expose any further stale fields. Longer term, exercise NFWeb through its public interface with a real client/service where practical, as the repository test guidance requires.
- **Evidence:** Focused pytest run: 5 failed, all at the `process.threads` validation error during setup. Current isolated NFWeb suite produced 46 passed and 6 failed: these same 5 setup failures plus the scale-profile getter mismatch reported separately. No service was started.

### 29. Nornir test assertions raise `NameError` when they should report a failure

- **Severity:** Low to medium for diagnosis: failing integration assertions lose the actual mismatch and report an unrelated name error.
- **Location:** `tests/services/nornir/test_parse.py:549`; `tests/services/nornir/test_tests.py:364`.
- **Trigger:** In `test_nornir_parse_ttp_with_host_filter`, if worker 2 returns unexpected results, the assertion message evaluates `nornir-worker-2` as an expression with undefined names. In `test_nornir_test_remove_tasks_false`, a traceback in task output evaluates undefined `test_name` instead of the available `task_name`.
- **Proposed fix:** Use a literal worker label or an in-scope variable in the first assertion, and `task_name` in the second. Re-run the focused integration tests; a small isolated failing-assertion check can verify each message without changing service behavior.
- **Evidence:** Ruff F821 and assertion-path inspection. No Nornir service run.

### 30. NetBox prefix tests delete pre-existing child prefixes

- **Severity:** High for a shared or reused NetBox instance.
- **Location:** `tests/services/netbox/common.py:61-64`; setup calls in `tests/services/netbox/test_ipam.py:3419,3438,3459,3489,3522`.
- **Trigger:** Run a prefix allocation test when its parent prefix already contains child prefixes. The setup helper queries all prefixes `within` the parent and deletes every returned record, without identifying which ones the test created. This is the prefix equivalent of finding 6 and violates the repository rule to preserve pre-existing data.
- **Proposed fix:** Give tests a dedicated verified-free parent prefix and delete only child prefix IDs created by that test in `finally`. If a generic cleanup helper remains, require explicit ownership of every deleted record.
- **Evidence:** Helper and call-site inspection. I did not run the destructive NetBox tests.

### 73. Netbox test HTTP timeout adapter does not bound ordinary requests
- **Severity:** Medium for test runs hanging during NetBox outages.
- **Location:** tests/services/netbox/common.py:19-24.
- **Trigger/impact:** get_pynetbox installs TimeoutHTTPAdapter expecting connect/read limits. requests.Session.request passes timeout=None explicitly when callers omit timeout; send uses kwargs.setdefault("timeout", (10, 60)), which preserves None. Most pynetbox requests therefore retain unlimited connect/read waits despite the promised bounded timeout, and retries do not bound an individual stalled read.
- **Evidence:** Python setdefault behavior plus installed requests.Session.request source: its send_kwargs always includes timeout=timeout, default None. Adapter has no alternative timeout override.
- **Proposed fix:** Replace missing or None timeout with the intended tuple; preserve explicit caller timeout. Verify through a prepared public requests.Session request and a bounded local HTTP server.

## Documentation

### 74. Netbox compatibility pages advertise versions the worker refuses to start against

- **Severity:** Medium.
- **Location:** docs/workers/netbox/services_netbox_service.md:18-22; docs/workers/nornir/services_nornir_service_inventory.md:30-33.
- **Trigger:** Follow advertised support for Netbox 3.6/4.0/4.1/4.2, or Nornir integration with 4.3. The current NetboxWorker sets compatible_ge_v4=(4,4,0), marks lower versions incompatible in get_compatibility, and raises from _verify_compatibility during startup. Users cannot deploy the documented integration against these versions.
- **Evidence:** norfab/workers/netbox_worker/netbox_worker.py:110-120,383-395,412-416. Current get_connections and GraphQL task pages already say >=4.4.
- **Proposed fix:** Update the service compatibility list and Nornir inventory integration version requirement to >=4.4.0; retain historical version details only in changelog.

### 75. FastMCP reject-sensitive example leaves actual configuration task exposed

- **Severity:** High for users copying the policy as an access restriction.
- **Location:** docs/workers/fastmcp/services_fastmcp_service_inventory.md:91-110 (Reject sensitive tasks), plus Allow specific tasks example at :75-88.
- **Trigger:** Copy policy rejecting nornir tasks cfg_deploy and cfg_rollback. Neither is a public Nornir task; actual configuration task is cfg. Default policy action is allow, so cfg remains exposed despite the example claiming to block destructive tasks. The allow-specific example also does not expose the intended cfg task.
- **Evidence:** norfab/workers/fastmcp_worker/fastmcp_worker.py:87-105 exact task glob matching and default allow; norfab/workers/nornir_worker/cfg_task.py:92 def cfg; no cfg_deploy/cfg_rollback definitions in current workers.
- **Proposed fix:** Replace stale names with actual task names (cfg, plus any intentionally restricted tasks such as netconf edits/gNMI/SNMP mutations). Explain the example scope and verify policy with actual discovery names.

### 76. FastAPI inventory example makes default bearer token creation fail

- **Severity:** Medium.
- **Location:** docs/workers/fastapi/services_fastapi_service_inventory.md:30-31.
- **Trigger:** Copy auth_bearer.token_ttl: None and create a token without explicit expire. YAML parses None as a string, not null; bearer_token_store forwards it to diskcache expire. diskcache raises TypeError when adding float current time to string.
- **Evidence:** norfab/workers/fastapi_worker/fastapi_worker.py:531-546 reads configured TTL unchanged. Reproduction in isolated TemporaryDirectory using yaml.safe_load and diskcache.Cache printed parsed value 'None' (str) and TypeError unsupported operand type(s) for +: 'float' and 'str'. No fabric or external service required.
- **Proposed fix:** Use token_ttl: null. Add inventory validation for positive integer/null at the boundary if improving implementation later.

### 77. FastAPI token docs promise no expiry even when a default TTL is configured

- **Severity:** Low.
- **Location:** docs/workers/fastapi/services_fastapi_service_task_auth.md:18,41; docs/workers/fastapi/services_fastapi_service.md:89.
- **Trigger:** Configure auth_bearer.token_ttl, then follow documented claim that omitting expire creates a nonexpiring token. Implementation applies configured TTL, so automation credentials unexpectedly expire relative to documented behavior.
- **Evidence:** bearer_token_store at norfab/workers/fastapi_worker/fastapi_worker.py:531-534; own docstring correctly describes inventory fallback.
- **Proposed fix:** Say omitted expire uses configured token_ttl; token is nonexpiring only if both are unset/null.

### 78. Installation guide promises FakeNOS on unsupported Python 3.10

- **Severity:** Low/medium for installation.
- **Location:** docs/tutorials/norfab_installation.md:26.
- **Trigger:** Install norfab[fakenosservice] on Python 3.10 expecting the documented simulator support (3.10–3.12). pyproject.toml:111 restricts fakenos to >=3.11,<3.13; resolver omits it on 3.10, and FakeNOS worker cannot import its backend.
- **Evidence:** Explicit dependency Python marker and extras mapping in pyproject.toml:111,227-229.
- **Proposed fix:** State Python 3.11–3.12 for this service; distinguish from core Python support.

## Validation and coverage

- Core inventory tests: **24 passed**. NFAPI lifecycle/logging tests: **16 passed, 1 deselected** (shared-service fixture excluded). Tests ran through Poetry, with the testing guide's `tests/` working directory and `--confcutdir=core` for isolation.
- Isolated NFWeb Python suite: **46 passed, 6 failed**. Five failures are missing `process.threads` in monitoring fixtures (28); the sixth is the FakeNOS IPv6 getter fixture mismatch listed above. Command: `poetry run pytest -q tests/clients/nfweb --confcutdir=tests/clients/nfweb --disable-warnings --tb=short`.
- Isolated probes reproduced inventory contamination, wrong-service routing, repeated-event blocking, ignored input coercion, watchdog shutdown failure, invalid transfer settings, skipped startup hooks, exit-hook cleanup failure, and agent discovery failure. Worker/client probes confirmed cache contamination, lost enrichment options, local-file copy and reload crashes, alias selectors, invalid Containerlab fallback, and two CLI crashes. Git publication retry was reproduced with real temporary local repositories.
- Strict full documentation build passed: `poetry run mkdocs build --strict --site-dir private/docs-audit-site`. Local Markdown links and API module references were checked; no confirmed broken-file links were found.
- Normal shared pytest fixture loading is blocked by the installed PICLE package lacking `picle.chat`. Root-relative inventory collection also fails because that test uses a path relative to `tests/`. Isolated runs above avoid these blockers; they do not replace full integration coverage.
- Reviewed core routing, jobs, lifecycle, inventory, monitoring, security, keepalives and agent paths; all nine worker families; Robot, Textual, NFCLI and NFWeb; installation, lifecycle/inventory/plugin and service documentation. Large Netbox design/BGP reconciliation paths, generated command trees and repetitive CLI forwarding models received targeted review rather than exhaustive line-by-line tracing. No frontend browser run; frontend dependencies were absent. No destructive Netbox cleanup tests were run.
