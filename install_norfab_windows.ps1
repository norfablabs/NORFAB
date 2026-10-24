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

    Option A - download and run directly in PowerShell:
        iex (irm https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_windows.ps1)

    Option B - if you have already downloaded the file:
        powershell -ExecutionPolicy Bypass -File .\install_norfab_windows.ps1

    Option C - allow scripts for your user account (persists), then run normally:
        Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
        .\install_norfab_windows.ps1

    PREREQUISITES
        - Python 3.10 or later must be installed and on your PATH
          Download: https://www.python.org/downloads/

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\install_norfab_windows.ps1
#>

# Keep variables, helper functions, strict mode, and error preferences local even
# when Invoke-Expression evaluates the downloaded text in the caller's scope.
& {
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
        $answer = (Read-Host "$Prompt$hint").Trim()
        if ($answer -eq "" -and $Default -ne "") { return $Default }
        if ($ValidValues -contains $answer.ToLower()) { return $answer.ToLower() }
        Write-Host "    Please enter one of: $($ValidValues -join ', ')" -ForegroundColor Red
    }
}

function Read-YesNo {
    param([string]$Prompt, [bool]$Default = $true)
    $defaultStr = if ($Default) { "Y/n" } else { "y/N" }
    while ($true) {
        $answer = (Read-Host "$Prompt [$defaultStr]").Trim().ToLowerInvariant()
        if ($answer -eq "") { return $Default }
        if ($answer -in @('y', 'yes')) { return $true }
        if ($answer -in @('n', 'no')) { return $false }
        Write-Host '    Please enter Y or N.' -ForegroundColor Red
    }
}

function Read-Port {
    param([string]$Prompt, [int]$Default)
    while ($true) {
        $answer = (Read-Host "$Prompt [default: $Default]").Trim()
        if ($answer -eq '') { return $Default }
        $port = 0
        if ([int]::TryParse($answer, [ref]$port) -and $port -ge 1 -and $port -le 65535) {
            return $port
        }
        Write-Host '    Enter a port between 1 and 65535.' -ForegroundColor Red
    }
}

function Invoke-PythonChecked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed (exit code $LASTEXITCODE): $Executable $($Arguments -join ' ')"
    }
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
    Write-Host "   [0] Install without service workers (CLI and TUI included)" -ForegroundColor DarkGray
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

# CLI and TUI are always installed; Robot Framework is optional.
$Addons = @(
    @{ Name = "nfcli";       Extra = "nfcli";       Description = "Interactive CLI shell (nfcli command)" }
    @{ Name = "robot";       Extra = "robot";        Description = "Robot Framework library" }
    @{ Name = "tui";         Extra = "tui";          Description = "Textual terminal UI (--tui flag)" }
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
Write-Host "  To run this saved installer:" -ForegroundColor DarkYellow
Write-Info '  powershell -ExecutionPolicy Bypass -File .\install_norfab_windows.ps1'
Write-Host ""

# ---------------------------------------------------------------------------
# Step 1 - Verify Python is available
# ---------------------------------------------------------------------------

Write-Step "Checking Python installation..."
try {
    $pythonCmd = (Get-Command python -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
    $pyVersion = & $pythonCmd -c "import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 10) else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or later is required.' }
    Write-Success "Found: $pyVersion"
} catch {
    Write-Host "[!] Could not start a supported Python: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '    Python 3.10 or later must be available on PATH.' -ForegroundColor Red
    throw
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
    $defaultVenvName = ".venv"
    $venvName = (Read-Host "Virtual environment folder name [default: $defaultVenvName]").Trim()
    if ($venvName -eq "") { $venvName = $defaultVenvName }

    $venvPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($venvName)
    if ((Test-Path -LiteralPath $venvPath) -and -not (Test-Path -LiteralPath (Join-Path $venvPath 'pyvenv.cfg'))) {
        throw "Virtual environment target already exists and is not a venv: $venvPath. Choose a new folder."
    }

    if (Test-Path -LiteralPath (Join-Path $venvPath 'pyvenv.cfg')) {
        Write-Info "Reusing virtual environment: $venvPath"
    } else {
        Write-Step "Creating virtual environment at: $venvPath"
        Invoke-PythonChecked -Executable $pythonCmd -Arguments @('-m', 'venv', $venvPath)
        Write-Success "Virtual environment created."
    }

    # Point pip/python to the venv
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
} else {
    $pythonExe = $pythonCmd
}
$pyVersion = & $pythonExe -c "import sys; print(sys.version.split()[0]); sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'The selected environment requires Python 3.10 or later.' }
try {
    Invoke-PythonChecked -Executable $pythonExe -Arguments @('-m', 'pip', '--version') 2>$null | Out-Null
} catch {
    if (-not $venvPath) {
        throw 'pip is required. Install pip for the chosen Python, then rerun.'
    }
    Write-Step 'pip is missing; bootstrapping it in the virtual environment...'
    try {
        Invoke-PythonChecked -Executable $pythonExe -Arguments @('-m', 'ensurepip', '--upgrade')
    } catch {
        throw 'Could not bootstrap pip. Install or repair ensurepip support for this Python, then rerun.'
    }
    try {
        Invoke-PythonChecked -Executable $pythonExe -Arguments @('-m', 'pip', '--version')
    } catch {
        throw 'pip is still unavailable after bootstrapping. Repair the virtual environment or choose a new folder, then rerun.'
    }
    Write-Success 'pip is ready.'
}

# ---------------------------------------------------------------------------
# Step 3 - Choose services
# ---------------------------------------------------------------------------

$menuItems = @($Services | ForEach-Object { @{ Name = $_.Name; Description = $_.Description } })
while ($true) {
    Write-Header 'Select Services to Install'
    Show-Menu -Title 'Available NorFab Services' -Items $menuItems
    $selectionInput = (Read-Host 'Enter service number(s), separated by spaces or commas, A for all, or 0').Trim()
    $selectedServices = @()
    if ($selectionInput -eq 'a') {
        $selectedServices = @($Services | ForEach-Object { $_.Name })
    } elseif ($selectionInput -ne '0') {
        $tokens = @($selectionInput -split '[,\s]+' | Where-Object { $_ -ne '' })
        $validSelection = $tokens.Count -gt 0
        foreach ($token in $tokens) {
            $number = 0
            if ($token -match '^0*[1-8]$' -and [int]::TryParse($token, [ref]$number)) {
                $svcName = $Services[$number - 1].Name
                if ($selectedServices -notcontains $svcName) { $selectedServices += $svcName }
            } else {
                Write-Info "Invalid input: $token"
                $validSelection = $false
            }
        }
        if (-not $validSelection) { Write-Info 'Please select services from 1 to 8, A, or 0.'; continue }
    }
    Write-Header 'Continue to Install'
    Write-Info 'Selected services:'
    if ($selectedServices.Count -eq 0) {
        Write-Info '  None (CLI and TUI only)'
    } else {
        foreach ($svc in $Services) {
            if ($selectedServices -contains $svc.Name) { Write-Info "  $($svc.Name)" }
        }
    }
    Write-Info '[C] Continue installation'
    Write-Info '[R] Re-select services'
    Write-Info '[X] Cancel installation'
    $confirmation = Read-Choice -Prompt 'Choose C, R, or X' -ValidValues @('c', 'r', 'x') -Default 'c'
    if ($confirmation -eq 'c') { break }
    if ($confirmation -eq 'x') { Write-Info 'Installation cancelled.'; return }
}

# ---------------------------------------------------------------------------
# Step 4 - Choose add-ons (CLI, Robot, TUI, etc.)
# ---------------------------------------------------------------------------

Write-Header "Optional Add-ons"
$selectedAddons = @('nfcli', 'tui')
foreach ($addon in @($Addons | Where-Object { $_.Name -notin @('nfcli', 'tui') })) {
    $want = Read-YesNo -Prompt "Install $($addon.Name) - $($addon.Description)?" -Default $false
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
$extras = @($extras | Sort-Object -Unique)

if ($extras.Count -gt 0) {
    $packageSpec = "norfab[$($extras -join ',')]"
} else {
    $packageSpec = "norfab"
}

if ($selectedServices -contains 'fakenosservice' -and [version]$pyVersion -ge [version]'3.13') {
    throw 'FakeNOS requires Python 3.10-3.12. Restart with a supported Python or deselect FakeNOS.'
}

Write-Step "Running: $pythonExe -m pip install `"$packageSpec`""
Write-Host ""

Invoke-PythonChecked -Executable $pythonExe -Arguments @('-m', 'pip', 'install', $packageSpec)

Write-Host ""
Write-Success "NorFab installed successfully."

# ---------------------------------------------------------------------------
# Step 6 - Create NorFab environment (inventory files)
# ---------------------------------------------------------------------------

Write-Header "Create NorFab Environment"

$envDir = $null
$createEnvironment = $false
$projectDir = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath('./norfab')
$existingProject = Get-Item -LiteralPath $projectDir -Force -ErrorAction SilentlyContinue
if ($null -ne $existingProject) {
    Write-Info "NorFab project path already exists: $projectDir"
    Write-Info '[R] Remove the entire folder and recreate inventory and worker configuration files'
    Write-Info '[S] Skip creating files and preserve the existing project'
    $projectChoice = Read-Choice -Prompt 'Choose R or S' -ValidValues @('r', 's') -Default 's'
    if ($projectChoice -eq 'r') {
        if (-not $existingProject.PSIsContainer -or ($existingProject.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw 'Cannot recreate the project: the existing path must be a directory, not a symlink or junction.'
        }
        $expectedProject = [IO.Path]::GetFullPath((Join-Path (Get-Location).ProviderPath 'norfab'))
        $resolvedProject = (Resolve-Path -LiteralPath $projectDir).ProviderPath
        if (-not [string]::Equals($resolvedProject, $expectedProject, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Cannot recreate the project: path is outside the local norfab folder.'
        }
        $pythonPrefix = & $pythonExe -c 'import os, sys; print(os.path.realpath(sys.prefix))'
        if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the active Python environment.' }
        if ([string]::Equals($pythonPrefix, $resolvedProject, [StringComparison]::OrdinalIgnoreCase) -or
            $pythonPrefix.StartsWith($resolvedProject + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Cannot remove the project folder containing the active Python environment; choose skip.'
        }
        Remove-Item -LiteralPath $resolvedProject -Recurse -Force
        $createEnvironment = $true
        $envDir = $projectDir
    } else {
        Write-Info 'Skipping project file creation.'
        if ($existingProject.PSIsContainer) { $envDir = $projectDir }
    }
} elseif (Read-YesNo -Prompt 'Create ./norfab with inventory and worker configuration files?' -Default $true) {
    $envDir = $projectDir
    $createEnvironment = $true
}
if ($createEnvironment) {

# Port configuration
Write-Host ""
Write-Step "Configure ports"
$brokerPort = Read-Port -Prompt 'Broker port' -Default 5555

$fastapiPort = "8000"
if ($selectedServices -contains "fastapiservice") {
    do { $fastapiPort = Read-Port -Prompt 'FastAPI service port (must differ from broker)' -Default 8000 } while ($fastapiPort -eq $brokerPort)
}

$fastmcpPort = "8001"
if ($selectedServices -contains "fastmcpservice") {
    do { $fastmcpPort = Read-Port -Prompt 'FastMCP service port (must differ from other services)' -Default 8001 } while ($fastmcpPort -eq $brokerPort -or ($selectedServices -contains 'fastapiservice' -and $fastmcpPort -eq $fastapiPort))
}

# Check every target before writing any configuration; preserve existing projects.
$targetPaths = @((Join-Path $envDir 'inventory.yaml'))
foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    foreach ($relativePath in $svc.WorkerFiles.Keys) { $targetPaths += Join-Path $envDir $relativePath }
}
foreach ($target in $targetPaths) {
    if (Test-Path -LiteralPath $target) {
        throw "Configuration already exists: $target. Choose a new environment folder to preserve existing files."
    }
}

Write-Step "Creating environment directory: $envDir"
New-Item -ItemType Directory -Path $envDir -Force | Out-Null

Write-Step "Generating inventory files..."

# Build inventory.yaml
$workersSection  = ""
$topologyWorkers = ""

foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    $workersSection  += "`n" + $svc.WorkersSection.Trim("`r", "`n")
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
Set-Content -LiteralPath $inventoryPath -Value $inventoryContent -Encoding UTF8
Write-Success "Created: $inventoryPath"

# Write per-service worker config files
foreach ($svcName in $selectedServices) {
    $svc = $Services | Where-Object { $_.Name -eq $svcName }
    foreach ($filePath in $svc.WorkerFiles.Keys) {
        $fullPath = Join-Path $envDir $filePath
        $dir = Split-Path $fullPath -Parent
        if (-not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        $fileContent = $svc.WorkerFiles[$filePath]
        $fileContent = $fileContent -replace '__BROKER_PORT__', $brokerPort
        $fileContent = $fileContent -replace '__FASTAPI_PORT__', $fastapiPort
        $fileContent = $fileContent -replace '__FASTMCP_PORT__', $fastmcpPort
        Set-Content -LiteralPath $fullPath -Value $fileContent -Encoding UTF8
        Write-Success "Created: $fullPath"
    }
}

# ---------------------------------------------------------------------------
}

# Step 7 - Validate generated YAML files
# ---------------------------------------------------------------------------

if ($createEnvironment) {
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
    $yamlValidationCode = @'
import yaml, sys
try:
    with open(sys.argv[1], encoding='utf-8-sig') as stream:
        yaml.safe_load(stream)
except Exception as error:
    print(str(error))
    sys.exit(1)
'@
    foreach ($yf in $filesToValidate) {
        $result = & $pythonExe -c $yamlValidationCode $yf
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
        throw 'Generated YAML validation failed. Review the files above before running NorFab.'
    }
}

# ---------------------------------------------------------------------------
}

# Step 8 - Activation hint
# ---------------------------------------------------------------------------

Write-Header "Installation Complete"

# Print startup commands for both direct evaluation and saved-file invocation.
Write-Host ''
Write-Host '  Run these commands in your PowerShell terminal:' -ForegroundColor White
if ($envDir) {
    Write-Host ("      Set-Location -LiteralPath '{0}'" -f $envDir.Replace("'", "''")) -ForegroundColor Cyan
} else {
    Write-Info 'Folder creation skipped. Run nfcli from your existing NorFab configuration folder.'
}
if ($selectedAddons -contains 'nfcli') {
    if ($venvPath) {
        $activatePath = Join-Path $venvPath 'Scripts\Activate.ps1'
        Write-Host ("      & '{0}'" -f $activatePath.Replace("'", "''")) -ForegroundColor Cyan
        Write-Host '      nfcli' -ForegroundColor Green
    } else {
        $scriptsDir = & $pythonExe -c "import sysconfig; print(sysconfig.get_path('scripts'))"
        if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the Python scripts directory.' }
        $nfcliPath = Join-Path $scriptsDir 'nfcli.exe'
        Write-Host ("      & '{0}'" -f $nfcliPath.Replace("'", "''")) -ForegroundColor Green
    }
    Write-Info 'nfcli starts the broker, selected workers and interactive shell.'
} else {
    Write-Info 'The nfcli add-on was not selected. To install it using this Python:'
    Write-Host ("      & '{0}' -m pip install 'norfab[nfcli]'" -f $pythonExe.Replace("'", "''")) -ForegroundColor Cyan
}
Write-Host ''
Write-Info 'Documentation: https://docs.norfablabs.com/'
}
