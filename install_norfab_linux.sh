#!/usr/bin/env bash
# NorFab Linux interactive installer. Requires Bash and Python 3.10+ with venv.
# Run: bash install_norfab_linux.sh
# Download and run (prompts read from the terminal):
# bash -c "$(curl -fsSL https://raw.githubusercontent.com/norfablabs/NORFAB/master/install_norfab_linux.sh)"
# Existing inventory and selected worker configuration files are preserved.

set -euo pipefail

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
write_header() { printf '\n======================================================================\n  %s\n======================================================================\n\n' "$1"; }
write_step() { printf '[*] %s\n' "$1"; }
write_success() { printf '[+] %s\n' "$1"; }
write_info() { printf '    %s\n' "$1"; }
# Use a separate descriptor so pip and Python cannot consume prompt responses.
if [[ -t 0 ]]; then
    exec 3<&0
elif { exec 3</dev/tty; } 2>/dev/null; then
    :
else
    printf '[!] Run this installer from an interactive terminal.\n' >&2
    exit 1
fi
read_answer() {
    printf '%s ' "$1"
    if ! IFS= read -r answer <&3; then
        printf '\n[!] Input closed; installation stopped.\n' >&2
        exit 1
    fi
    # Match the Windows installer by trimming surrounding whitespace.
    answer="${answer#"${answer%%[![:space:]]*}"}"
    answer="${answer%"${answer##*[![:space:]]}"}"
}
read_choice() {
    local prompt=$1 default=$2
    shift 2
    while true; do
        read_answer "$prompt [default: $default]"
        answer=${answer:-$default}
        local choice
        for choice in "$@"; do
            [[ $answer == "$choice" ]] && return 0
        done
        write_info "Please enter one of: $*"
    done
}
read_yes_no() {
    local hint='y/N'
    [[ $2 == y ]] && hint='Y/n'
    while true; do
        read_answer "$1 [$hint]"
        answer=${answer:-$2}
        case ${answer,,} in
            y|yes) return 0 ;;
            n|no) return 1 ;;
            *) write_info 'Please enter Y or N.' ;;
        esac
    done
}
read_port() {
    local prompt=$1 default=$2
    while true; do
        read_answer "$prompt [default: $default]"
        answer=${answer:-$default}
        if [[ $answer =~ ^[0-9]{1,5}$ ]] && (( 10#$answer >= 1 && 10#$answer <= 65535 )); then
            answer=$((10#$answer))
            return 0
        fi
        write_info 'Please enter a port from 1 to 65535.'
    done
}

# ---------------------------------------------------------------------------
# Service definitions (same choices and templates as the Windows installer)
# ---------------------------------------------------------------------------
service_names=(nornirservice netboxservice fastapiservice agentservice fastmcpservice fakenosservice workflow containerlab)
service_descriptions=(
    'Nornir network automation (SSH/Netconf/SNMP/gNMI)'
    'NetBox DCIM/IPAM integration'
    'FastAPI REST API service'
    'AI/LLM agent service (LangChain/Ollama)'
    'Model Context Protocol (MCP) server'
    'FakeNOS simulated network devices (Python 3.10-3.12 only)'
    'Workflow orchestration service (built-in, no extra pip packages)'
    'ContainerLab integration (built-in, no extra pip packages)'
)
service_keys=(nornir netbox fastapi agent fastmcp fakenos workflow containerlab)
selected=(0 0 0 0 0 0 0 0)

write_worker_files() {
    case $1 in
        0)
            mkdir -p "$env_dir/nornir"
            cat > "$env_dir/nornir/common.yaml" <<EOF
service: nornir
broker_endpoint: "tcp://127.0.0.1:$broker_port"

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
EOF
            yaml_files+=("$env_dir/nornir/common.yaml")
            mkdir -p "$env_dir/nornir"
            cat > "$env_dir/nornir/nornir-worker-1.yaml" <<EOF
# Override or extend settings from common.yaml for this specific worker
hosts:
  ios-device-1:
    hostname: 192.168.1.1
    platform: cisco_ios
    username: admin
    password: admin
EOF
            yaml_files+=("$env_dir/nornir/nornir-worker-1.yaml")
            ;;
        1)
            mkdir -p "$env_dir/netbox"
            cat > "$env_dir/netbox/netbox-worker-1.yaml" <<EOF
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
EOF
            yaml_files+=("$env_dir/netbox/netbox-worker-1.yaml")
            ;;
        2)
            mkdir -p "$env_dir/fastapi"
            cat > "$env_dir/fastapi/fastapi-worker-1.yaml" <<EOF
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
  port: $fastapi_port
EOF
            yaml_files+=("$env_dir/fastapi/fastapi-worker-1.yaml")
            ;;
        3)
            mkdir -p "$env_dir/agent"
            cat > "$env_dir/agent/agent-worker-1.yaml" <<EOF
service: agent
broker_endpoint: "tcp://127.0.0.1:$broker_port"
llm_flavour: ollama        # ollama | openai | anthropic
llm_model: llama3.1:8b
llm_temperature: 0.5
llm_base_url: "http://127.0.0.1:11434"
EOF
            yaml_files+=("$env_dir/agent/agent-worker-1.yaml")
            ;;
        4)
            mkdir -p "$env_dir/fastmcp"
            cat > "$env_dir/fastmcp/fastmcp-worker-1.yaml" <<EOF
service: fastmcp

# MCP server bind settings
host: "127.0.0.1"
port: $fastmcp_port

tools:
  policy:
    - service: "*"
      tasks: ["*"]
      action: allow

fastmcp: {}
uvicorn: {}
EOF
            yaml_files+=("$env_dir/fastmcp/fastmcp-worker-1.yaml")
            ;;
        5)
            mkdir -p "$env_dir/fakenos"
            cat > "$env_dir/fakenos/fakenos-worker-1.yaml" <<EOF
service: fakenos

# networks:
#   lab-network-1:
#     inventory: fakenos/lab-network-1-inventory.yaml
EOF
            yaml_files+=("$env_dir/fakenos/fakenos-worker-1.yaml")
            ;;
        6)
            mkdir -p "$env_dir/workflow"
            cat > "$env_dir/workflow/workflow-worker-1.yaml" <<EOF
service: workflow
EOF
            yaml_files+=("$env_dir/workflow/workflow-worker-1.yaml")
            ;;
        7)
            mkdir -p "$env_dir/containerlab"
            cat > "$env_dir/containerlab/containerlab-worker-1.yaml" <<EOF
service: containerlab
EOF
            yaml_files+=("$env_dir/containerlab/containerlab-worker-1.yaml")
            ;;
    esac
}

# Step 1 - Verify Python is available
write_header 'NorFab Linux Installer'
write_info '1. Install NorFab (system Python or local venv)'
write_info '2. Choose service extras and optional add-ons'
write_info '3. Create a NorFab environment with inventory files'
write_step 'Checking Python installation...'
python_exe=$(command -v python3 || command -v python || true)
if [[ -z $python_exe ]] || ! "$python_exe" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    write_info 'Python 3.10+ is required. Install Python and its venv support, then rerun.'
    exit 1
fi
write_success "Found: $("$python_exe" --version)"

# Step 2 - System or local install
write_header 'Installation Type'
write_info '[1] System - install into the current Python (may require elevated permissions)'
write_info '[2] Local  - create a virtual environment in a chosen folder'
read_choice 'Choose installation type (1/2)' 2 1 2
venv_path=''
if [[ $answer == 2 ]]; then
    read_answer 'Virtual environment folder name [default: norfab-env]'
    venv_path=$("$python_exe" -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "${answer:-norfab-env}")
    if [[ -e $venv_path && ! -f $venv_path/pyvenv.cfg ]]; then
        write_info "Target exists and is not a virtual environment: $venv_path"
        exit 1
    fi
    if [[ -f $venv_path/pyvenv.cfg ]]; then
        write_info "Reusing virtual environment: $venv_path"
    else
        write_step "Creating virtual environment at: $venv_path"
        "$python_exe" -m venv "$venv_path"
        write_success 'Virtual environment created.'
    fi
    python_exe="$venv_path/bin/python"
fi
if ! "$python_exe" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
    write_info 'The selected environment requires Python 3.10 or later.'
    exit 1
fi
if ! "$python_exe" -m pip --version >/dev/null 2>&1; then
    if [[ -n $venv_path ]]; then
        write_step 'pip is missing; bootstrapping it in the virtual environment...'
        if ! "$python_exe" -m ensurepip --upgrade; then
            write_info 'Could not bootstrap pip. Install venv/ensurepip support for the Python used by this environment, then rerun.'
            write_info 'On Debian/Ubuntu, install the matching python3-venv or python3.X-venv package.'
            exit 1
        fi
        if ! "$python_exe" -m pip --version; then
            write_info 'pip is still unavailable after bootstrapping. Repair the virtual environment or choose a new folder, then rerun.'
            exit 1
        fi
        write_success 'pip is ready.'
    else
        write_info 'pip is required. Install pip for the chosen Python, then rerun.'
        exit 1
    fi
fi

# Step 3 - Choose services
write_header 'Select Services to Install'
while true; do
    printf '\n  Available NorFab Services\n'
    for i in "${!service_names[@]}"; do
        printf '  [%2d] %s - %s\n' "$((i+1))" "${service_names[i]}" "${service_descriptions[i]}"
        [[ ${selected[i]} == 0 ]] || write_info "Currently selected: ${service_names[i]}"
    done
    write_info '[A] Select ALL services'
    write_info '[0] Continue (keep current selection)'
    read_answer 'Enter number(s) to toggle, A for all, 0 to continue'
    [[ $answer == 0 ]] && break
    if [[ $answer == a || $answer == A ]]; then
        selected=(1 1 1 1 1 1 1 1)
        break
    fi
    tokens=()
    read -r -a tokens <<< "${answer//,/ }"
    for token in "${tokens[@]}"; do
        if [[ $token =~ ^0*[1-8]$ ]]; then
            i=$((10#$token - 1))
            selected[i]=$((1-selected[i]))
        else
            write_info "Invalid input: $token"
        fi
    done
done

# Step 4 - Choose add-ons
write_header 'Optional Add-ons'
extras=()
for i in "${!service_names[@]}"; do
    if [[ ${selected[i]} == 1 && $i -lt 6 ]]; then
        extras+=("${service_names[i]}")
    fi
done
# CLI and TUI are always installed; Robot Framework is optional.
extras+=(nfcli tui)
if read_yes_no 'Install robot - Robot Framework library?' n; then
    extras+=(robot)
fi

# Step 5 - Build pip install command and install
if [[ ${selected[5]} == 1 ]] && ! "$python_exe" -c 'import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] < (3, 13)))'; then
    write_info 'FakeNOS requires Python 3.10-3.12. Restart with a supported Python or deselect FakeNOS.'
    exit 1
fi
write_header 'Installing NorFab'
package_spec=norfab
if (( ${#extras[@]} )); then
    joined=$(IFS=,; printf '%s' "${extras[*]}")
    package_spec="norfab[$joined]"
fi
write_step "Running: $python_exe -m pip install $package_spec"
if "$python_exe" -m pip install "$package_spec"; then
    write_success 'NorFab installed successfully.'
else
    status=$?
    write_info "pip install failed (exit code $status). Check the output above."
    write_info 'For externally managed system Python, rerun and choose Local installation.'
    exit "$status"
fi

# Step 6 - Create NorFab environment
write_header 'Create NorFab Environment'
env_dir=''
if read_yes_no 'Create a NorFab folder with inventory and worker configuration files?' y; then
read_answer "Folder to create NorFab environment in [default: norfab-project, '.' for current directory]"
env_dir=$("$python_exe" -c 'import os, sys; print(os.path.abspath(sys.argv[1]))' "${answer:-norfab-project}")
write_step 'Configure ports'
read_port 'Broker port' 5555
broker_port=$answer
fastapi_port=8000
fastmcp_port=8001
if [[ ${selected[2]} == 1 ]]; then
    while true; do
        read_port 'FastAPI service port (must differ from broker)' 8000
        fastapi_port=$answer
        [[ $fastapi_port == "$broker_port" ]] || break
    done
fi
if [[ ${selected[4]} == 1 ]]; then
    while true; do
        read_port 'FastMCP service port (must differ from other services)' 8001
        fastmcp_port=$answer
        [[ $fastmcp_port != "$broker_port" ]] || continue
        [[ ${selected[2]} == 1 && $fastmcp_port == "$fastapi_port" ]] || break
    done
fi
# Check all targets before writing any configuration, including dangling symlinks.
target_paths=("$env_dir/inventory.yaml")
for i in "${!service_names[@]}"; do
    [[ ${selected[i]} == 1 ]] || continue
    key=${service_keys[i]}
    target_paths+=("$env_dir/$key/$key-worker-1.yaml")
    [[ $key != nornir ]] || target_paths+=("$env_dir/nornir/common.yaml")
done
for target in "${target_paths[@]}"; do
    if [[ -e $target || -L $target ]]; then
        write_info "Configuration already exists: $target. Choose a new environment folder."
        exit 1
    fi
done
mkdir -p "$env_dir"
write_step 'Generating inventory files...'
yaml_files=("$env_dir/inventory.yaml")
{
    cat <<EOF
# NorFab Inventory
# Generated by install_norfab_linux.sh
broker:
  endpoint: "tcp://127.0.0.1:$broker_port"
  # shared_key: "CHANGE_ME"  # set after running: nfcli --show-broker-shared-key
logging:
  handlers:
    terminal:
      level: WARNING
    file:
      level: DEBUG
EOF
    if [[ "${selected[*]}" == '0 0 0 0 0 0 0 0' ]]; then
        printf 'workers: {}\ntopology:\n  broker: True\n  workers: []\n'
    else
        printf 'workers:\n'
        for i in "${!service_names[@]}"; do
            [[ ${selected[i]} == 1 ]] || continue
            key=${service_keys[i]}
            if [[ $key == nornir ]]; then
                printf '  nornir-*:\n    - nornir/common.yaml\n'
            fi
            printf '  %s-worker-1:\n    - %s/%s-worker-1.yaml\n' "$key" "$key" "$key"
        done
        printf 'topology:\n  broker: True\n  workers:\n'
        for i in "${!service_names[@]}"; do
            [[ ${selected[i]} == 1 ]] || continue
            printf '    - %s-worker-1\n' "${service_keys[i]}"
        done
    fi
} > "$env_dir/inventory.yaml"
for i in "${!service_names[@]}"; do
    [[ ${selected[i]} == 1 ]] || continue
    write_worker_files "$i"
done
for file in "${yaml_files[@]}"; do write_success "Created: $file"; done

# Step 7 - Validate generated YAML files
write_step 'Validating generated YAML files...'
if "$python_exe" -c 'import yaml' 2>/dev/null; then
    "$python_exe" - "${yaml_files[@]}" <<'PYEOF'
import sys
import yaml
for path in sys.argv[1:]:
    with open(path, encoding="utf-8") as stream:
        yaml.safe_load(stream)
    print(f"    [ok] {path}")
PYEOF
    write_success 'All YAML files are valid.'
else
    write_info 'PyYAML not available - skipping validation.'
fi

fi # environment creation

# Step 8 - Commands to run in the caller's terminal
write_header 'Installation Complete'
write_info 'Run these commands in your Bash terminal:'
if [[ -n $env_dir ]]; then
    printf '      cd -- %q\n' "$env_dir"
else
    write_info 'Folder creation skipped. Run nfcli from your existing NorFab configuration folder.'
fi
scripts_dir=$("$python_exe" -c 'import sysconfig; print(sysconfig.get_path("scripts"))')
printf '      %q\n' "$scripts_dir/nfcli"
write_info 'nfcli starts the broker, selected workers and interactive shell.'
write_info 'Documentation: https://docs.norfablabs.com/'
