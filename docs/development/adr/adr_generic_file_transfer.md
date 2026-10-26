# ADR - Lightweight Generic File Transfer



## Status



Accepted. MVP implemented on 2026-10-25.



Amended on 2026-10-25 to keep transfers within the normal job lifecycle.



Amended on 2026-10-26 to reuse the existing fetch pipeline, caching, and integrity checks.



Date: 2026-10-25.



## Context



Clients and workers need to fetch files from any worker and upload local files

to workers through the broker. The implementation must remain lightweight and

reuse the existing NFP command set.



Existing `nf://` downloads discover FileSharing workers and use their current

metadata and caching. Downloads now use the shared core serving task,

while `git://` resolution remains unchanged.



## Decision



Use receiver-requested chunks for generic transfers. The source is the peer

reading the file; the receiver is the peer writing it. Uploading means asking

the destination to start pulling from the source.



```text

Receiver -> PUT    {path, offset, size} -> Source

Receiver <- STREAM raw bytes          <- Source

```



`PUT` carries requests and metadata/error control replies only. `STREAM` carries raw file bytes in both directions,

including client-to-worker transfers. Do not encode file data as JSON or base64.



The receiver requests the first chunk and subsequent ranges. Downloads use the

existing fetch_file pipeline, size checks, and incremental MD5 verification.

The source opens, seeks, reads, and closes per chunk. Download completion uses

the advertised size and final job result; an empty file sends an empty chunk.

Uploads pull one chunk at a time and end on an empty chunk, then verify size/MD5.



Named-worker downloads query `file_stat` for size and checksum before checking

the cache. A cache miss submits one normal `serve_file` job; uploads retain

`receive_file`. There is never a job per chunk. An application task's

`job.fetch_file()` uses that application's job UUID. Files are fetched sequentially

within each job on each worker; parallel transfers use separate jobs or workers.

The source opens and closes the file per request, but worker serving retains a

running job. The receiver retains its output file and offset under that job.



### Local files in job requests



Pass local-file URLs into the application job unchanged:



```python

client.run_job(

    service="nornir",

    task="some_task",

    kwargs={"config": "file://configs/router.txt"},

)

```



This illustrates a custom task's input. When the task

needs the file, `job.fetch_file(url)` requests chunks from the submitting

client. There is no pre-staging, argument rewriting, or upload before execution.



| URL | Meaning |

| --- | --- |

| `nf://configs/router.txt` | Existing fetch from FileSharing workers |

| `file://configs/router.txt` | File relative to the submitting client's working directory |

| `file:///var/tmp/router.txt` | Absolute path on a POSIX client |

| `file:///C:/configs/router.txt` | Absolute path on a Windows client |



For a worker submitting a job through its embedded client, local paths refer to

that submitting worker's filesystem. Direct worker fetches identify the source

worker explicitly; do not reinterpret `nf://` as a worker-addressing scheme.



### Broker routing



Reuse existing NFP commands and message envelopes. No new command or protocol

version is introduced, but permitted message directions must change:



- Allow client-originated `STREAM` messages to reach the target worker.

- Allow worker-originated `PUT` chunk requests to reach the submitting client.

- Dispatch file requests and binary replies to the appropriate peer handlers.



The broker forwards messages without maintaining file-transfer state. This is

a routing and command-direction change, not a claim that current routing already

supports the exchange. Existing job-input `PUT` handling must remain intact;

file-read requests need an application-level discriminator.



### Implementation boundary



Keep chunk helpers embedded in the client and worker, using existing routing.

Use the same exchange for client-to-worker and worker-to-worker transfers.

An explicit upload operation starts a receiving task on the destination; a

running application job can pull its input directly from its submitting client.



Leave `LocalFilesTasks`, FileSharing discovery, and existing public fetch

interfaces in place. Keep directory listing, walking, and Git management on FileSharing.
All workers expose size/MD5 metadata through `file_stat`; published nf://
paths are resolved only by FileSharing. Exact helper names and payload

discrimination are described in the [file streaming guide](../../api_ref/core/api_reference_core_file_transfer.md#generic-client-and-worker-transfers).



The primary download interface is `client.fetch_file(path, worker=...)`, retaining

its result format, list support, read option, and cache checks.

Other helpers are

`client.upload_file(url, worker)`, and `job.fetch_file(url)`. The core

`receive_file` task pulls from its submitting client or a named source worker.

Workers use their embedded client for direct fetches and uploads.



Reverse read requests carry `file_read: true` and the requesting worker; the

message UUID identifies the running job. Client-side reads are limited to URLs explicitly

supplied in that active job's arguments. Successful chunks use raw STREAM data;

client metadata replies use PUT with `file_details` (size and MD5), and read

errors use PUT with `file_error`.

Worker read errors fail the serving job through normal results. Chunk size is

limited to 1 MiB. Chunk content is never stored in job records.



Client STREAM messages use `handle_stream` and the existing job-keyed

`file_transfers` map. RESPONSE messages always use `handle_response`. Incoming

PUT requests are handled on the existing client dispatcher, so

source reads do not block socket reception. Each worker Job has a binary-input

queue separate from its interactive input queue. There is no independent

`file_requests` registry or transfer UUID. The client requests the first download

chunk after the worker's normal starting event and waits for the final job result

after the final chunk.



## Alternatives Considered



- **Pre-stage local files:** rejected because it adds submission orchestration

  and changes when files are transferred.

- **Send file bytes through PUT:** rejected; file data belongs in STREAM in

  both directions.

- **Persist a job per chunk:** rejected because normal job persistence and

  dispatch are unnecessary overhead for a range read.

- **Bypass jobs for direct range reads:** replaced by one serving job per

  download, preserving normal dispatch, completion, and timeout handling.

- **Register clients as file-serving workers:** rejected because it adds a

  service lifecycle solely to support reverse transfers.

- **Generalize nf:// to address any worker:** rejected. Only FileSharing workers

  resolve published paths, using their existing publication-root checks.



## Consequences



- Source reads retain no open file between chunks; transfer lifetime belongs

  to a normal job. Serving occupies a worker job slot, so nested transfers can

  contend for job slots or time out when workers are saturated.

- Client source reads run on its existing dispatcher. Slow reads may delay job

  dispatch, but socket reception continues independently.

- Existing clients and workers need updated handlers for generic transfers.

- Downloads reuse the bounded fetch pipeline. Uploads retain one outstanding

  chunk request per job.

- Files must remain stable during a transfer. The MVP adds no snapshotting,

  automatic retries or recovery across restarts. Size and MD5 detect corruption,

  not source authenticity.

- Use existing timeouts and direct destination writes. Interrupted transfers

  may leave partial files.

- There is no new transfer database, broker registry, staging service, or

  dedicated scheduling subsystem.



## Consolidation amendment — 2026-10-26



FileSharing and direct worker downloads now submit the same `serve_file` task.

The client requests offset zero on job start for both, then uses one pipeline

and stream handler. FileSharing resolves nf:// using `safe_path`; other workers

reject it. Metadata discovery, Git resolution, cache paths, and checksums remain.

The old FileSharing fetch_file task and its models are removed; direct callers

must use the client helper or the documented serve_file control exchange.

Core workers provide listing, walking, and safe path resolution.


## Metadata consolidation — 2026-10-26

Core file_stat replaces FileSharing file_details. It accepts strings or lists
and returns size, MD5, and existence metadata with per-path failures. Only
FileSharing resolves nf:// within its publication root. The client uses one
metadata request for published and native paths when a source worker is named.
Worker metadata and serving methods read files independently of the client;
client upload reads retain their own implementation. No shared helper module
is introduced. CLI details commands remain; direct callers migrate to file_stat.
The removed task's REST/MCP exposure is not carried over to the native task.

## Core browsing — 2026-10-26

list_files and walk are core worker tasks. safe_path resolves native paths and
FileSharing-only confined nf:// paths for browsing, metadata, serving, and Git
mounts. The LocalFilesTasks mixin is removed. Native walk results are absolute
paths; published walk results remain nf:// URLs. Native browsing uses the job
API and is not exposed through REST or MCP.
