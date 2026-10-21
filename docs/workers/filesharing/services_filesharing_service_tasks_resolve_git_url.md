---
tags:
  - filesharing
  - git
---

# Filesharing Resolve Git URL Task

> task api name: `resolve_git_url`

The `resolve_git_url` task validates a `git://` file URL, synchronizes its
configured remote, and returns the file's published `nf://` URL. The task does
not stream file content. `NFPClient.fetch_file()` calls it automatically before
using the existing File Sharing transfer flow.

## Output

Returns results keyed by original Git URL. Each entry contains `failed`, `errors`,
and `result`; successful results contain the file's published `nf://` URL using
its remote's configured mount. Missing files, invalid paths, and failed remotes
produce individual failures. Each valid referenced remote is synchronized once
per request. The `url` argument accepts a string or list. A string retains the original single-file result containing the published URL directly, or a failed result.

## Examples

=== "CLI"

    Use the client-level file command, which resolves the URL automatically:

    ```bash
    nf#file copy url git://network-assets/templates/base.j2 read
    ```

=== "Python"

    Direct task invocation:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            service="filesharing",
            task="resolve_git_url",
            workers="filesharing-worker-1",
            kwargs={"url": ["git://network-assets/templates/base.j2"]},
        )
        print(result)
    ```

    Normal file retrieval:

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        result = client.fetch_file(
            "git://network-assets/templates/base.j2",
            read=True,
        )
        print(result["content"])
    ```

## Notes

- The remote must already be configured or registered with
  `create_remote_git`.
- Resolution synchronizes the complete configured branch before returning.
- The returned URL uses the configured mount, which may differ from the remote
  name.
- Git access and credentials remain inside the File Sharing worker.

## Python API Reference

::: norfab.workers.filesharing_worker.git_tasks.GitTasks.resolve_git_url

Batch entry errors are also collected in the outer result's `errors` list, while successful entries remain available.
