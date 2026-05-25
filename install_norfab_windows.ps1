#Requires -Version 5.1
<#
.SYNOPSIS
    NorFab Windows Installation Script

.DESCRIPTION
    Interactive installer for NorFab (Network Automations Fabric).
    Installs NorFab into either the system-wide Python or a local virtual environment,
    lets you choose which service extras to install, then scaffolds an inventory.yaml
    and per-service worker configuration files ready to run with `nfcli`.

    *** HOW TO RUN THIS SCRIPT ***

    Option A - single command, downloads and runs directly from GitHub (recommended):
        powershell -ExecutionPolicy Bypass -Command "iwr -useb 'https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_windows.ps1' -OutFile \"$env:TEMP\install_norfab.ps1\"; & \"$env:TEMP\install_norfab.ps1\""

    Option B - if you have already downloaded the file:
        powershell -ExecutionPolicy Bypass -File .\install_norfab_windows.ps1

    Option C - allow scripts for your user account (persists), then run normally:
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
        .\install_norfab_windows.ps1

    PREREQUISITES
        - Python 3.10 or later must be installed and on your PATH
          Download: https://www.python.org/downloads/

.EXAMPLE
    powershell -ExecutionPolicy Bypass -Command "iwr -useb 'https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_windows.ps1' -OutFile `"$env:TEMP\install_norfab.ps1`"; & `"$env:TEMP\install_norfab.ps1`""
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

function Write-Header {
    param([string]$Text)
    $line = "=" * 70
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host $line -ForegroundColor Cyan
    Write-Host ""
}

function Write-Step {
    param([string]$Text)
    Write-Host "[*] $Text" -ForegroundColor Yellow
}

function Write-Success {
    param([string]$Text)
    Write-Host "[+] $Text" -ForegroundColor Green
}

function Write-Info {
    param([string]$Text)
    Write-Host "    $Text" -ForegroundColor Gray
}

function Read-Choice {
    param(
        [string]$Prompt,
        [string[]]$ValidValues,
        [string]$Default = ""
    )
    while ($true) {
        $hint = if ($Default) { " [default: $Default]" } else { "" }
        $answer = Read-Host "$Prompt$hint"
        if ($answer -eq "" -and $Default -ne "") { return $Default }
        if ($ValidValues -contains $answer.ToLower()) { return $answer.ToLower() }
        Write-Host "    Please enter one of: $($ValidValues -join ', ')" -ForegroundColor Red
    }
}

function Read-YesNo {
    param([string]$Prompt, [bool]$Default = $true)
    $defaultStr = if ($Default) { "Y/n" } else { "y/N" }
    $answer = Read-Host "$Prompt [$defaultStr]"
    if ($answer -eq "") { return $Default }
    return ($answer.ToLower() -eq "y" -or $answer.ToLower() -eq "yes")
}

function Show-Menu {
    param(
        [string]$Title,
        [hashtable[]]$Items
    )
    Write-Host ""
    Write-Host "  $Title" -ForegroundColor White
    Write-Host "  $("-" * ($Title.Length))" -ForegroundColor DarkGray
    for ($i = 0; $i -lt $Items.Count; $i++) {
        $item  = $Items[$i]
        $index = ($i + 1).ToString().PadLeft(2)
        $name  = $item.Name
        $desc  = $item.Description
        Write-Host "  [$index] $name" -ForegroundColor Cyan -NoNewline
        Write-Host " - $desc" -ForegroundColor Gray
    }
    Write-Host "   [A] Select ALL services" -ForegroundColor Magenta
    Write-Host "   [0] Continue (no additional services)" -ForegroundColor DarkGray
    Write-Host ""
}

# ---------------------------------------------------------------------------
# Service definitions  (name, pip-extra, worker-service-key, description)
# ---------------------------------------------------------------------------

$Services = @(
    @{
        Name        = "nornirservice"
        Extra       = "nornirservice"
        ServiceKey  = "nornir"
        WorkerName  = "nornir-worker-1"
        Folder      = "nornir"
        Description = "Nornir network automation (SSH/Netconf/SNMP/gNMI)"
        WorkerFiles = @{
            "nornir/common.yaml"          = @"
service: nornir
broker_endpoint: "tcp://127.0.0.1:__BROKER_PORT__"

# Nornir runner configuration
runner:
  plugin: RetryRunner
  options:
    num_workers: 100
    num_connectors: 10
    connect_retry: 1
    connect_backoff: 1000
    connect_splay: 100
    task_retry: 1
    task_backoff: 1000
    task_splay: 100
    reconnect_on_fail: True
    task_timeout: 600

# Host inventory - add your devices here
hosts: {}
groups: {}
defaults: {}
logging: {}
user_defined: {}
"@
            "nornir/nornir-worker-1.yaml" = @"
# Override or extend settings from common.yaml for this specific worker
hosts:
  ios-device-1:
    hostname: 192.168.1.1
    platform: cisco_ios
    username: admin
    password: admin
"@
        }
        WorkersSection = @"

  nornir-*:
    - nornir/common.yaml
  nornir-worker-1:
    - nornir/nornir-worker-1.yaml
"@
    },
    @{
        Name        = "netboxservice"
        Extra       = "netboxservice"
        ServiceKey  = "netbox"
        WorkerName  = "netbox-worker-1"
        Folder      = "netbox"
        Description = "NetBox DCIM/IPAM integration"
        WorkerFiles = @{
            "netbox/netbox-worker-1.yaml" = @"
service: netbox
cache_use: True   # True | False | refresh | force
cache_ttl: 31557600
netbox_connect_timeout: 10
netbox_read_timeout: 300
branch_create_timeout: 120
grapqhl_max_workers: 4
instances:
  prod:
    default: True
    url: "http://192.168.1.100:8000/"
    token: "CHANGE_ME_netbox_api_token"
    ssl_verify: False
"@
        }
        WorkersSection = @"

  netbox-worker-1:
    - netbox/netbox-worker-1.yaml
"@
    },
    @{
        Name        = "fastapiservice"
        Extra       = "fastapiservice"
        ServiceKey  = "fastapi"
        WorkerName  = "fastapi-worker-1"
        Folder      = "fastapi"
        Description = "FastAPI REST API service"
        WorkerFiles = @{
            "fastapi/fastapi-worker-1.yaml" = @"
service: fastapi
auth_bearer:
  token_ttl: null

# FastAPI application settings
# https://fastapi.tiangolo.com/reference/fastapi/#fastapi.FastAPI
fastapi:
  title: FastAPI
  docs_url: "/docs"
  redoc_url: "/redoc"

# Uvicorn server settings
# https://www.uvicorn.org/#config-and-server-instances
uvicorn:
  host: "0.0.0.0"
  port: __FASTAPI_PORT__
"@
        }
        WorkersSection = @"

  fastapi-worker-1:
    - fastapi/fastapi-worker-1.yaml
"@
    },
    @{
        Name        = "agentservice"
        Extra       = "agentservice"
        ServiceKey  = "agent"
        WorkerName  = "agent-worker-1"
        Folder      = "agent"
        Description = "AI/LLM agent service (LangChain/Ollama)"
        WorkerFiles = @{
            "agent/agent-worker-1.yaml" = @"
service: agent
broker_endpoint: "tcp://127.0.0.1:__BROKER_PORT__"
llm_flavour: ollama        # ollama | openai | anthropic
llm_model: llama3.1:8b
llm_temperature: 0.5
llm_base_url: "http://127.0.0.1:11434"
"@
        }
        WorkersSection = @"

  agent-worker-1:
    - agent/agent-worker-1.yaml
"@
    },
    @{
        Name        = "fastmcpservice"
        Extra       = "fastmcpservice"
        ServiceKey  = "fastmcp"
        WorkerName  = "fastmcp-worker-1"
        Folder      = "fastmcp"
        Description = "Model Context Protocol (MCP) server"
        WorkerFiles = @{
            "fastmcp/fastmcp-worker-1.yaml" = @"
service: fastmcp

# MCP server bind settings
host: "127.0.0.1"
port: __FASTMCP_PORT__

tools:
  policy:
    - service: "*"
      tasks: ["*"]
      action: allow

fastmcp: {}
uvicorn: {}
"@
        }
        WorkersSection = @"

  fastmcp-worker-1:
    - fastmcp/fastmcp-worker-1.yaml
"@
    },
    @{
        Name        = "fakenosservice"
        Extra       = "fakenosservice"
        ServiceKey  = "fakenos"
        WorkerName  = "fakenos-worker-1"
        Folder      = "fakenos"
        Description = "FakeNOS simulated network devices (Python 3.10-3.12 only)"
        WorkerFiles = @{
            "fakenos/fakenos-worker-1.yaml" = @"
service: fakenos

# networks:
#   lab-network-1:
#     inventory: fakenos/lab-network-1-inventory.yaml
"@
        }
        WorkersSection = @"

  fakenos-worker-1:
    - fakenos/fakenos-worker-1.yaml
"@
    },
    @{
        Name        = "workflow"
        Extra       = $null   # no separate pip extra - included in core
        ServiceKey  = "workflow"
        WorkerName  = "workflow-worker-1"
        Folder      = "workflow"
        Description = "Workflow orchestration service (built-in, no extra pip packages)"
        WorkerFiles = @{
            "workflow/workflow-worker-1.yaml" = @"
service: workflow
"@
        }
        WorkersSection = @"

  workflow-worker-1:
    - workflow/workflow-worker-1.yaml
"@
    },
    @{
        Name        = "containerlab"
        Extra       = $null   # no separate pip extra - included in core
        ServiceKey  = "containerlab"
        WorkerName  = "containerlab-worker-1"
        Folder      = "containerlab"
        Description = "ContainerLab integration (built-in, no extra pip packages)"
        WorkerFiles = @{
            "containerlab/containerlab-worker-1.yaml" = @"
service: containerlab
"@
        }
        WorkersSection = @"

  containerlab-worker-1:
    - containerlab/containerlab-worker-1.yaml
"@
    }
)

# Optional add-ons (not workers, just pip extras)
$Addons = @(
    @{ Name = "nfcli";       Extra = "nfcli";       Description = "Interactive CLI shell (nfcli command)" }
    @{ Name = "robot";       Extra = "robot";        Description = "Robot Framework test library" }
    @{ Name = "tui";         Extra = "tui";          Description = "Textual terminal UI (--tui flag)" }
    @{ Name = "clientagent"; Extra = "clientagent";  Description = "Client-side LangGraph AI agent" }
)

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

Write-Header "NorFab Windows Installer"
Write-Host "  This script will:" -ForegroundColor White
Write-Info  "  1. Install NorFab (system-wide Python or local venv)"
Write-Info  "  2. Let you choose which service extras to install"
Write-Info  "  3. Create a NorFab environment folder with inventory files"
Write-Host ""
Write-Host "  TIP: share this one-liner with others to install NorFab:" -ForegroundColor DarkYellow
Write-Info  "  powershell -ExecutionPolicy Bypass -Command `"iwr -useb 'https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_windows.ps1' -OutFile '`$env:TEMP\install_norfab.ps1'; & '`$env:TEMP\install_norfab.ps1'`""
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1 - Verify Python is available
# ---------------------------------------------------------------------------

Write-Step "Checking Python installation..."
try {
    $pythonCmd = "python"
    $pyVersion = & python --version 2>&1
    Write-Success "Found: $pyVersion"
} catch {
    Write-Host "[!] Python not found on PATH. Please install Python 3.10+ and re-run." -ForegroundColor Red
    exit 1
}

# Ensure pip is available
try {
    & python -m pip --version | Out-Null
} catch {
    Write-Host "[!] pip not found. Run: python -m ensurepip --upgrade" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# Step 2 - System or local install
# ---------------------------------------------------------------------------

Write-Header "Installation Type"
Write-Host "  [1] System  - install into the global Python (requires admin for system Python)" -ForegroundColor Cyan
Write-Host "  [2] Local   - create a virtual environment in a chosen folder" -ForegroundColor Cyan
Write-Host ""
$installType = Read-Choice -Prompt "Choose installation type (1/2)" -ValidValues @("1","2") -Default "2"

$venvPath = $null
if ($installType -eq "2") {
    $defaultVenvName = "norfab-env"
    $venvName = Read-Host "Virtual environment folder name [default: $defaultVenvName]"
    if ($venvName -eq "") { $venvName = $defaultVenvName }

    $venvPath = Join-Path (Get-Location) $venvName

    Write-Step "Creating virtual environment at: $venvPath"
    & python -m venv $venvPath
    Write-Success "Virtual environment created."

    # Point pip/python to the venv
    $pipExe    = Join-Path $venvPath "Scripts\pip.exe"
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
} else {
    $pipExe    = "pip"
    $pythonExe = "python"
}

# ---------------------------------------------------------------------------
# Step 3 - Choose services
# ---------------------------------------------------------------------------

Write-Header "Select Services to Install"

$menuItems = @()
foreach ($svc in $Services) {
    $menuItems += @{ Name = $svc.Name; Description = $svc.Description }
}

$selectedServices = @()
$selectionDone    = $false

while (-not $selectionDone) {
    Show-Menu -Title "Available NorFab Services" -Items $menuItems

    # Show currently selected
    if ($selectedServices.Count -gt 0) {
        Write-Host "  Currently selected: " -ForegroundColor White -NoNewline
        Write-Host ($selectedServices -join ", ") -ForegroundColor Green
        Write-Host ""
    }

    $input = (Read-Host "Enter number(s) to toggle, A for all, 0 to continue").Trim()

    if ($input -eq "0") {
        $selectionDone = $true
    } elseif ($input.ToLower() -eq "a") {
        $selectedServices = $Services | ForEach-Object { $_.Name }
        $selectionDone = $true
    } else {
        # Support comma/space-separated entries like "1,3 5"
        $tokens = $input -split "[,\s]+" | Where-Object { $_ -ne "" }
        foreach ($token in $tokens) {
            if ($token -match "^\d+$") {
                $idx = [int]$token - 1
                if ($idx -ge 0 -and $idx -lt $Services.Count) {
                    $svcName = $Services[$idx].Name
                    if ($selectedServices -contains $svcName) {
                        $selectedServices = $selectedServices | Where-Object { $_ -ne $svcName }
                        Write-Host "    Deselected: $svcName" -ForegroundColor DarkYellow
                    } else {
                        $selectedServices += $svcName
                        Write-Host "    Selected:   $svcName" -ForegroundColor Green
                    }
                } else {
                    Write-Host "    Invalid number: $token" -ForegroundColor Red
                }
            } else {
                Write-Host "    Invalid input: $token" -ForegroundColor Red
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Step 4 - Choose add-ons (CLI, Robot, TUI, etc.)
# ---------------------------------------------------------------------------

Write-Header "Optional Add-ons"
$selectedAddons = @()
foreach ($addon in $Addons) {
    $want = Read-YesNo -Prompt "Install $($addon.Name) - $($addon.Description)?" -Default ($addon.Name -eq "nfcli")
    if ($want) { $selectedAddons += $addon.Name }
}

# ---------------------------------------------------------------------------
# Step 5 - Build pip install command and install
# ---------------------------------------------------------------------------

Write-Header "Installing NorFab"

# Collect all extras (services with an Extra, plus chosen add-ons)
$extras = @()
foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    if ($svc.Extra) { $extras += $svc.Extra }
}
foreach ($addonName in $selectedAddons) {
    $addon = $Addons | Where-Object { $_.Name -eq $addonName }
    $extras += $addon.Extra
}

# Deduplicate
$extras = $extras | Sort-Object -Unique

if ($extras.Count -gt 0) {
    $packageSpec = "norfab[$($extras -join ',')]"
} else {
    $packageSpec = "norfab"
}

Write-Step "Running: $pipExe install `"$packageSpec`""
Write-Host ""

& $pipExe install "$packageSpec"

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[!] pip install failed (exit code $LASTEXITCODE). Check the output above." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Success "NorFab installed successfully."

# ---------------------------------------------------------------------------
# Step 6 - Create NorFab environment (inventory files)
# ---------------------------------------------------------------------------

Write-Header "Create NorFab Environment"

$defaultEnvDir = "norfab-project"
$envDirInput   = Read-Host "Folder to create NorFab environment in [default: $defaultEnvDir, '.' for current directory]"
if ($envDirInput -eq "") { $envDirInput = $defaultEnvDir }
$envDir = $envDirInput

# Port configuration
Write-Host ""
Write-Step "Configure ports"
$brokerPortInput = Read-Host "Broker port [default: 5555]"
$brokerPort = if ($brokerPortInput -eq "") { "5555" } else { $brokerPortInput }

$fastapiPort = "8000"
if ($selectedServices -contains "fastapiservice") {
    $fastapiPortInput = Read-Host "FastAPI service port [default: 8000]"
    $fastapiPort = if ($fastapiPortInput -eq "") { "8000" } else { $fastapiPortInput }
}

$fastmcpPort = "8001"
if ($selectedServices -contains "fastmcpservice") {
    $fastmcpPortInput = Read-Host "FastMCP service port [default: 8001]"
    $fastmcpPort = if ($fastmcpPortInput -eq "") { "8001" } else { $fastmcpPortInput }
}

if ($envDir -ne ".") {
    Write-Step "Creating environment directory: $envDir"
    New-Item -ItemType Directory -Path $envDir -Force | Out-Null
}

Write-Step "Generating inventory files..."

# Build inventory.yaml
$workersSection  = ""
$topologyWorkers = ""

foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    $workersSection  += $svc.WorkersSection
    $topologyWorkers += "`n    - $($svc.WorkerName)"
}

if ($topologyWorkers -eq "") {
    $topologyBlock = @"
topology:
  broker: True
  workers: []
"@
} else {
    $topologyBlock = @"
topology:
  broker: True
  workers:$topologyWorkers
"@
}

if ($workersSection -eq "") {
    $workersBlock = "workers: {}"
} else {
    $workersBlock = "workers:$workersSection"
}

$inventoryContent = @"
# NorFab Inventory
# Generated by install_norfab_windows.ps1

# Broker settings
broker:
  endpoint: "tcp://127.0.0.1:$brokerPort"
  # shared_key: "CHANGE_ME"  # uncomment and set after running: nfcli --show-broker-shared-key

# Logging configuration
logging:
  handlers:
    terminal:
      level: WARNING
    file:
      level: DEBUG

# Worker inventory file mappings
$workersBlock

# Topology: what to start on this node
$topologyBlock
"@

$inventoryPath = Join-Path $envDir "inventory.yaml"
Set-Content -Path $inventoryPath -Value $inventoryContent -Encoding UTF8
Write-Success "Created: $inventoryPath"

# Write per-service worker config files
foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    foreach ($filePath in $svc.WorkerFiles.Keys) {
        $fullPath = Join-Path $envDir $filePath
        $dir = Split-Path $fullPath -Parent
        if (-not (Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $fileContent = $svc.WorkerFiles[$filePath]
        $fileContent = $fileContent -replace '__BROKER_PORT__', $brokerPort
        $fileContent = $fileContent -replace '__FASTAPI_PORT__', $fastapiPort
        $fileContent = $fileContent -replace '__FASTMCP_PORT__', $fastmcpPort
        Set-Content -Path $fullPath -Value $fileContent -Encoding UTF8
        Write-Success "Created: $fullPath"
    }
}

# ---------------------------------------------------------------------------
# Step 7 - Validate generated YAML files
# ---------------------------------------------------------------------------

Write-Step "Validating generated YAML files..."
$yamlValid = $true
try {
    & $pythonExe -c "import yaml" 2>$null
    $yamlAvailable = $LASTEXITCODE -eq 0
} catch {
    $yamlAvailable = $false
}

if (-not $yamlAvailable) {
    Write-Host "    [!] PyYAML not available — skipping validation. Run: pip install pyyaml" -ForegroundColor DarkYellow
} else {
    $filesToValidate = @($inventoryPath)
    foreach ($svcName in $selectedServices) {
        $svc = $Services | Where-Object { $_.Name -eq $svcName }
        foreach ($fp in $svc.WorkerFiles.Keys) {
            $filesToValidate += Join-Path $envDir $fp
        }
    }
    foreach ($yf in $filesToValidate) {
        $result = & $pythonExe -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]).read())" $yf 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Host "    [!] Invalid YAML: $yf" -ForegroundColor Red
            Write-Host "        $result" -ForegroundColor Red
            $yamlValid = $false
        } else {
            Write-Host "    [ok] $yf" -ForegroundColor DarkGreen
        }
    }
    if ($yamlValid) {
        Write-Success "All YAML files are valid."
    } else {
        Write-Host "[!] Some YAML files have errors — review the files above before running NorFab." -ForegroundColor Red
    }
}

# ---------------------------------------------------------------------------
# Step 8 - Activation hint
# ---------------------------------------------------------------------------

Write-Header "Installation Complete"

# Ask to cd into the project folder
if ($envDir -ne ".") {
    $doCd = Read-YesNo -Prompt "Change directory to '$envDir' now?" -Default $true
} else {
    $doCd = $false
}

# Ask to activate venv
$doActivate = $false
if ($venvPath) {
    $doActivate = Read-YesNo -Prompt "Activate the virtual environment now?" -Default $true
}

if ($doCd)       { Set-Location $envDir }
if ($doActivate) { $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"; . $activateScript }

Write-Host ""
Write-Host "  To start NorFab:" -ForegroundColor White
if ($venvPath) {
    $activateScript = Join-Path $venvPath "Scripts\Activate.ps1"
    Write-Host "      . `"$activateScript`"" -ForegroundColor Cyan
    Write-Host "                                   # activate the virtual environment" -ForegroundColor DarkGray
}
if ($envDir -ne ".") {
    Write-Host "      cd `"$envDir`"" -ForegroundColor Cyan
}
Write-Host "      nfcli" -ForegroundColor Green
Write-Host ""
Write-Host "  nfcli will start the broker, all workers and an interactive shell." -ForegroundColor Gray
Write-Host ""
Write-Host "  Other useful commands:" -ForegroundColor White
Write-Info  "  nfcli -b -l INFO               # broker only, with INFO logging"
Write-Info  "  nfcli -w -l INFO               # workers only, with INFO logging"
Write-Info  "  nfcli -c                        # client shell only (connect to a running broker)"
Write-Info  "  nfcli --show-broker-shared-key # display broker public key for remote clients"
Write-Info  "  nfcli --create-env <name>      # scaffold a new environment"
Write-Host ""
Write-Host "  Documentation:" -ForegroundColor White
Write-Host "      https://docs.norfablabs.com/" -ForegroundColor DarkCyan
Write-Host ""
$line = "=" * 70
Write-Host $line -ForegroundColor Cyan
Write-Host ""
Write-Host ""
Write-Host "  nfcli will start the broker, all workers and an interactive shell." -ForegroundColor Gray
Write-Host ""
Write-Host "  Other useful commands:" -ForegroundColor White
Write-Info  "  nfcli -b -l INFO               # broker only, with INFO logging"
Write-Info  "  nfcli -w -l INFO               # workers only, with INFO logging"
Write-Info  "  nfcli -c                        # client shell only (connect to a running broker)"
Write-Info  "  nfcli --show-broker-shared-key # display broker public key for remote clients"
Write-Info  "  nfcli --create-env <name>      # scaffold a new environment"
Write-Host ""
Write-Host "  Documentation:" -ForegroundColor White
Write-Host "      https://docs.norfablabs.com/" -ForegroundColor DarkCyan
Write-Host ""
$line = "=" * 70
Write-Host $line -ForegroundColor Cyan
Write-Host ""
