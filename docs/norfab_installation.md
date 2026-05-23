## Install NorFab

NorFab core runs equally well on both Windows and Linux. Some
services might work only on one or the other, in that case that
will be noted in service deployment details.

=== "pip"

    Install NorFab from PyPI:

    ```
    pip install norfab
    ```

    Install with extras for specific services:

    | Extra | Description |
    |-------|-------------|
    | `norfab[nfcli]` | Interactive CLI shell (`nfcli` command) |
    | `norfab[nornirservice]` | Nornir network automation service |
    | `norfab[netboxservice]` | NetBox DCIM/IPAM integration service |
    | `norfab[fastapiservice]` | FastAPI REST API service |
    | `norfab[agentservice]` | AI/LLM agent service (Ollama/LangChain) |
    | `norfab[clientagent]` | Client-side LangGraph AI agent |
    | `norfab[fastmcpservice]` | Model Context Protocol (MCP) server |
    | `norfab[fakenosservice]` | FakeNOS simulated devices (Python 3.10–3.12) |
    | `norfab[robot]` | Robot Framework test library |
    | `norfab[tui]` | Textual terminal UI |
    | `norfab[full]` | All of the above |

    Multiple extras can be combined:

    ```
    pip install norfab[nfcli,nornirservice,netboxservice]
    ```

    **Upgrade:**

    ```
    pip install --upgrade norfab
    ```

=== "git+pip"

    Install the latest development version directly from GitHub:

    ```
    pip install git+https://github.com/norfablabs/NORFAB.git
    ```

    With extras:

    ```
    pip install "norfab[nfcli,nornirservice] @ git+https://github.com/norfablabs/NORFAB.git"
    ```

    **Upgrade** (re-installs the latest commit):

    ```
    pip install --upgrade git+https://github.com/norfablabs/NORFAB.git
    ```

=== "Windows"

    Download and run the interactive installer script — it guides you through
    choosing a system-wide or virtual-environment install, selects service extras,
    and scaffolds a ready-to-run inventory for you.

    **Step 1** — Download [install_norfab_windows.ps1](https://raw.githubusercontent.com/norfablabs/NORFAB/main/install_norfab_windows.ps1)
    and move it into the folder where you want to install NorFab, then open PowerShell in that folder.

    **Step 2** — Unblock the file so Windows allows it to run, then execute it:

    ```powershell
    Unblock-File .\install_norfab_windows.ps1
    powershell -ExecutionPolicy Bypass -File .\install_norfab_windows.ps1
    ```

    Or skip the download entirely and run this single command in PowerShell from your target folder
    (downloads, unblocks, and runs automatically):

    ```powershell
    powershell -ExecutionPolicy Bypass -Command "iwr -useb 'https://raw.githubusercontent.com/norfablabs/NORFAB/main/install_norfab_windows.ps1' -OutFile \"$env:TEMP\install_norfab.ps1\"; & \"$env:TEMP\install_norfab.ps1\""
    ```

    !!! note "Prerequisite"
        Python 3.10 or later must be installed and on your PATH.
        Download from [python.org](https://www.python.org/downloads/).

    **Upgrade:**

    ```powershell
    pip install --upgrade norfab
    ```

    If you installed into a virtual environment, activate it first:

    ```powershell
    . "norfab-env\Scripts\Activate.ps1"
    pip install --upgrade norfab
    ```

=== "Linux"

    Install from PyPI, optionally with extras for the services you want to run:

    ```bash
    pip install norfab
    # or with extras, e.g.:
    pip install norfab[nfcli,nornirservice,netboxservice]
    ```

    Using a virtual environment (recommended):

    ```bash
    python3 -m venv norfab-env
    source norfab-env/bin/activate
    pip install norfab[nfcli,nornirservice]
    ```

    **Upgrade:**

    ```bash
    pip install --upgrade norfab
    # or inside a venv:
    source norfab-env/bin/activate && pip install --upgrade norfab
    ```

## Operating Systems Support

| Component      | Windows      | Linux        | MacOS        |
| -------------- | ------------ | ------------ | ------------ |
| NorFab Core    | :check_mark: | :check_mark: | :check_mark: |
| Nornir Service | :check_mark: | :check_mark: | :check_mark: |
| Netbox Service | :check_mark: | :check_mark: | :check_mark: |
