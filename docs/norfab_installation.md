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

    Install the latest code directly from GitHub:

    ```
    pip install git+https://github.com/norfablabs/NORFAB.git@master
    ```

    With extras:

    ```
    pip install "norfab[nfcli,nornirservice] @ git+https://github.com/norfablabs/NORFAB.git@master"
    ```

    **Upgrade** (re-installs the latest commit):

    ```
    pip install --upgrade git+https://github.com/norfablabs/NORFAB.git@master
    ```

=== "Windows"

    Download and run the interactive installer script — it guides you through
    choosing a system-wide or virtual-environment install, selects service extras,
    and scaffolds a ready-to-run inventory for you:

    ```powershell
    iex (irm https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_windows.ps1)
    ```

    Run this command in Windows PowerShell 5.1 or PowerShell 7+. `irm` downloads
    the script and `iex` runs it. After installation, run the printed commands
    to start `nfcli`. Installer settings stay local to the script, and failures
    report an error without closing your terminal.

    !!! note "Prerequisite"
        Python 3.10 or later must be installed and on your PATH.
        Download from [python.org](https://www.python.org/downloads/).

    To install manually, run these commands in PowerShell:

    ```powershell
    python -m pip install norfab
    # Or include the CLI, TUI, and selected services:
    python -m pip install "norfab[nfcli,tui,nornirservice,netboxservice]"
    ```

    Using a virtual environment (recommended):

    ```powershell
    python -m venv norfab-env
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\norfab-env\Scripts\Activate.ps1
    python -m pip install "norfab[nfcli,tui,nornirservice,netboxservice]"
    ```

    Choose extras from the table in the **pip** tab to match the services you
    need. With the `nfcli` extra installed, create a new inventory folder:

    ```powershell
    nfcli --create-env norfab-project
    Set-Location norfab-project
    ```

    Review `inventory.yaml` and the worker configuration files, enabling only
    services whose extras you installed. Then start NorFab:

    ```powershell
    nfcli
    ```

    **Upgrade:**

    ```powershell
    python -m pip install --upgrade norfab
    ```

    If you installed into a virtual environment, activate it first. Run this
    from the folder containing `norfab-env`, or use your environment's actual path:

    ```powershell
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\norfab-env\Scripts\Activate.ps1
    python -m pip install --upgrade norfab
    ```

=== "Linux"

    Download and run the interactive Bash installer:

    ```bash
    bash -c "$(curl -fsSL https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_linux.sh)"
    ```

    Run this command from an interactive terminal with Bash and curl installed.
    It downloads and runs the installer while keeping terminal input available
    for prompts.

    Use Python 3.10+ with pip and venv support. The installer defaults to a local
    virtual environment, includes CLI and TUI, and lets you select services and
    Robot Framework. System installation follows your distribution's pip policy;
    choose Local if Python is externally managed.

    You can skip inventory creation. Existing inventory and selected worker files
    are preserved; choose a new folder if they already exist. After installation,
    run the printed commands in your terminal to start `nfcli`.

    To install manually:

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

=== "Docker"

    Run the published all-in-one NorFab image with the Compose files included
    in the repository:

    ```bash
    git clone https://github.com/norfablabs/NORFAB.git
    cd NORFAB/docker/norfab-docker
    docker compose up -d
    ```

    This starts the broker and inventory-defined workers in one container and
    publishes the FastAPI service on port `8000`.

    See the [Docker deployment tutorial](tutorials/norfab_docker_deployment.md)
    for configuration, verification, and shutdown steps. Contributors should
    use the [Docker development guide](development/norfab_docker_development.md)
    to run containers against their local source tree.

## Operating Systems Support

| Component      | Windows      | Linux        | MacOS        |
| -------------- | ------------ | ------------ | ------------ |
| NorFab Core    | :check_mark: | :check_mark: | :check_mark: |
| Nornir Service | :check_mark: | :check_mark: | :check_mark: |
| Netbox Service | :check_mark: | :check_mark: | :check_mark: |
