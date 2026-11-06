# Data Model: HTTP Tasks

All models live in norfab/workers/nornir_worker/nornir_models.py. Use strict scalar types,
Union[None,T], direct defaults, descriptions, use_enum_values=True and populate_by_name=True.
No database entities are introduced.

## HttpCommonArgs

Compose NornirHostsFilters with existing structured/text/XML/tests processor mixins as applicable.
Do not inherit NornirCommonArgs, which exposes retry controls. Define extra="forbid".
Explicitly carry needed result/file processor controls from NornirCommonArgs without refactoring
that shared model: on_failed=False, to_dict=True, add_details=False, progress=True,
run_num_workers=20 (positive integer), tf=None, tf_skip_failed=False, diff=None, diff_last=1.
Retain existing processor field semantics; unused processor fields must not become request kwargs.
Reject all retry/reconnect/connector-specific arguments rather than accepting ignored options.

## HttpRequestArgs

| Field | Shape/default | Meaning |
| --- | --- | --- |
| url | nullable strict string / None | Literal HTTP(S) URL or relative resource; omitted uses backend rules |
| params | nullable dictionary / None | Query names and JSON-compatible values |
| headers | nullable string-to-string dictionary / None | Explicit whole-map replacement |
| auth | nullable two-string list or tuple / None | Explicit basic-auth credentials |
| verify | nullable strict bool or strict string / None | Verification flag or worker-local CA path |
| cert | nullable string or two-string sequence / None | Worker-local client cert or cert/key pair |
| request_timeout | nullable positive number or two-number sequence / None | Connect/read seconds; maps to timeout |
| allow_redirects | nullable strict bool / None | Backend redirect behavior when omitted |
| transport | nullable http/https enum / None | Override inventory transport for URL construction |
| base_url | nullable strict string / None | Override inventory base path/URL |

Nullable request options mean omitted; forward only explicitly non-null values so inventory
remains effective. No files, streaming Response objects, arbitrary Python callbacks, Sessions,
or transport adapter objects are accepted over the job protocol. Reuse existing request pass-through conventions where appropriate; do not model the entire Requests API.

## Operation Models

HttpGetInput, HttpHeadInput, HttpOptionsInput, HttpDeleteInput use common request fields.
HttpPostInput, HttpPutInput, HttpPatchInput additionally expose:

- json_: nullable JsonValue, alias json. Structured JSON passes as-is; string input is a JSON
  document/template or nf:// file reference, rendered then decoded. Initial RESTCONF use focuses on object/array payloads; no special scalar encoding interface is required.
- data: nullable strict string for raw text/XML/patch documents or inline/nf:// templates.
- job_data: existing JSON-compatible context value or supported data-file URL.

Reject simultaneous non-null json and data. No mandatory nonempty payload: empty-body operations
are allowed. None means no JSON body; explicit JSON null bodies are not required. Define shell field overrides only to parse JSON
or other CLI string forms; inherit all unchanged fields.

## HttpResult

Inherit NornirSerializedResult or use a named HttpResult with its same result payload shape.
result is dict keyed by host or list records depending on to_dict. Backend subtask keys are
get/post/put/patch/delete/head/options. Nested response payload is arbitrary JsonValue or text.
add_details preserves standard Nornir fields. No new response status/header envelope.
No-match returns existing status no_match and empty result in the requested serialization form.

## Inventory Profile

connection_options.http resolves endpoint hostname/port/credentials plus extras transport,
base_url, verify, headers, timeout using existing Nornir inheritance. Host ports distinguish the
two spine targets. HTTP settings must not inherit SSH port by omission in the lab profiles.
The cached connection is configuration bookkeeping, not an authenticated persistent session.

## Lifecycle and Ownership

validated -> filtered -> payload prepared per host -> one backend execution -> processed -> serialized.
No match exits before preparation. Preparation/HTTP errors become safe per-host failures.
Always release connection lock and execute watchdog cleanup. No persistent temporary payload state.
Mutation fixtures own resource names, read back changes, and clean up only those resources even
after failure; no Netbox data ownership changes are needed for HTTP-only tests.
