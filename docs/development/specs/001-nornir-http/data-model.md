# Data Model: HTTP Tasks

All models live in norfab/workers/nornir_worker/nornir_models.py. Use strict scalar types,
Union[None,T], direct defaults, descriptions, use_enum_values=True and populate_by_name=True.
No database entities are introduced.

## RestconfGetInput

Reuse NornirCommonArgs plus existing text/XML/structured/tests processor mixins. Retain their
aliases, defaults and runner controls; do not copy shared fields. Public RESTCONF-specific fields
are url, request_timeout, headers, params and verify, with backend options passed through.
Nornir owns retry behavior. NorFab consumes common options through existing utilities.

## HTTP Request Options

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

RestconfGetInput, RestconfDeleteInput use common request fields.
RestconfPostInput, RestconfPutInput, RestconfPatchInput explicitly declare:

- data: nullable strict string containing the request body or inline/nf:// Jinja2 template.
- job_data: existing JSON-compatible template context or supported data-file URL.

There is no json/json_ payload field. JSON bodies are text supplied through data, with Content-Type
set in HTTP inventory. Existing template utilities render the text without request JSON decoding.

## NornirSerializedResult

Inherit NornirSerializedResult or use a named HttpResult with its same result payload shape.
result is dict keyed by host or list records depending on to_dict. Backend subtask keys are
get/post/put/patch/delete. Nested response payload is arbitrary JsonValue or text.
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
