---
tags:
  - nornir
---

# Nornir Service Parse Tasks

> task api names: `parse_napalm`, `parse_ttp`, `parse_textfsm`

Three tasks for parsing network device CLI output into structured data:

- **`parse_napalm`** — retrieves structured data via [NAPALM](https://napalm.readthedocs.io) getters (e.g. `get_facts`, `get_interfaces`). No template required.
- **`parse_ttp`** — collects CLI output and parses it with a [TTP](https://ttp.readthedocs.io) template. Supports inline templates, `ttp://` paths from [ttp_templates](https://ttp-templates.readthedocs.io), `nf://` file paths, and HTTP URLs. Template input definitions drive which commands are collected automatically.
- **`parse_textfsm`** — collects CLI output and parses it with a [TextFSM](https://github.com/google/textfsm) template. When no template is provided, [NTC-Templates](https://github.com/networktocode/ntc-templates) auto-detection is used based on device platform and command.

## NORFAB Shell Reference

NorFab shell commands for Nornir parse tasks:

```
nf#man tree nornir.parse

R - required field, M - supports multiline input, D - dynamic key

root
└── nornir:    Nornir service
    └── parse:    Parse network devices output
        ├── napalm:    Parse devices output using NAPALM getters
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── progress:    Display progress events, default 'True'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── add-details:    Add task details to results, default 'False'
        │   ├── num-workers:    RetryRunner number of threads for tasks execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run task
        │   ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
        │   ├── connect-check:    RetryRunner test TCP connection before opening actual connection
        │   ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        │   ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results to on worker file system
        │   ├── tf-skip-failed:    Save results to file for failed tasks
        │   ├── diff:    File group name to run the diff for
        │   ├── diff-last:    File version number to diff, default is 1 (last)
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Filter hosts excluding them by name
        │   ├── FN:    Negate the match
        │   └── getters (R):    Select NAPALM getters
        ├── ttp:    Parse devices output using TTP templates
        │   ├── timeout:    Job timeout
        │   ├── workers:    Filter workers to target, default 'all'
        │   ├── verbose-result:    Control output details, default 'False'
        │   ├── progress:    Display progress events, default 'True'
        │   ├── nowait:    Do not wait for job to complete, default 'False'
        │   ├── add-details:    Add task details to results, default 'False'
        │   ├── num-workers:    RetryRunner number of threads for tasks execution
        │   ├── num-connectors:    RetryRunner number of threads for device connections
        │   ├── connect-retry:    RetryRunner number of connection attempts
        │   ├── task-retry:    RetryRunner number of attempts to run task
        │   ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
        │   ├── connect-check:    RetryRunner test TCP connection before opening actual connection
        │   ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        │   ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
        │   ├── tf:    File group name to save task results to on worker file system
        │   ├── tf-skip-failed:    Save results to file for failed tasks
        │   ├── diff:    File group name to run the diff for
        │   ├── diff-last:    File version number to diff, default is 1 (last)
        │   ├── FO:    Filter hosts using Filter Object
        │   ├── FB:    Filter hosts by name using Glob Patterns
        │   ├── FH:    Filter hosts by hostname
        │   ├── FC:    Filter hosts containment of pattern in name
        │   ├── FR:    Filter hosts by name using Regular Expressions
        │   ├── FG:    Filter hosts by group
        │   ├── FP:    Filter hosts by hostname using IP Prefix
        │   ├── FL:    Filter hosts by names list
        │   ├── FM:    Filter hosts by platform
        │   ├── FX:    Filter hosts excluding them by name
        │   ├── FN:    Negate the match
        │   ├── template:    TTP Template to parse commands output, supports ttp:// path
        │   ├── get:    Getter TTP Template name to use
        │   ├── commands (M):    List of commands to collect form devices
        │   ├── plugin:    CLI connection plugin parameters
        │   │   ├── netmiko:    Use Netmiko plugin to collect output from devices
        │   │   │   ├── enable:    Attempt to enter enable-mode
        │   │   │   ├── use-timing:    switch to send command timing method
        │   │   │   ├── expect-string:    Regular expression pattern to use for determining end of output
        │   │   │   ├── read-timeout:    Maximum time to wait looking for pattern
        │   │   │   ├── auto-find-prompt:    Use find_prompt() to override base prompt
        │   │   │   ├── strip-prompt:    Remove the trailing router prompt from the output
        │   │   │   ├── strip-command:    Remove the echo of the command from the output
        │   │   │   ├── normalize:    Ensure the proper enter is sent at end of command
        │   │   │   ├── use-textfsm:    Process command output through TextFSM template
        │   │   │   ├── textfsm-template:    Name of template to parse output with
        │   │   │   ├── use-ttp:    Process command output through TTP template
        │   │   │   ├── ttp-template:    Name of template to parse output with
        │   │   │   ├── use-genie:    Process command output through PyATS/Genie parser
        │   │   │   ├── cmd-verify:    Verify command echo before proceeding
        │   │   │   ├── interval:    Interval between sending commands
        │   │   │   ├── use-ps:    Use send command promptless method
        │   │   │   ├── use-ps-timeout:    Promptless mode absolute timeout
        │   │   │   ├── split-lines:    Split multiline string to individual commands
        │   │   │   ├── new-line-char:    Character to replace with new line before sending to device, default is _br_
        │   │   │   ├── repeat:    Number of times to repeat the commands
        │   │   │   ├── stop-pattern:    Stop commands repeat if output matches provided glob pattern
        │   │   │   ├── repeat-interval:    Time in seconds to wait between repeating commands
        │   │   │   └── return-last:    Returns requested last number of commands outputs
        │   │   ├── scrapli:    Use Scrapli plugin to collect output from devices
        │   │   │   ├── strip-prompt:    Strip prompt from returned output
        │   │   │   ├── failed-when-contains:    String or list of strings indicating failure if found in response
        │   │   │   ├── timeout-ops:    Timeout ops value for this operation
        │   │   │   ├── interval:    Interval between sending commands
        │   │   │   ├── split-lines:    Split multiline string to individual commands
        │   │   │   ├── new-line-char:    Character to replace with new line before sending to device, default is _br_
        │   │   │   ├── repeat:    Number of times to repeat the commands
        │   │   │   ├── stop-pattern:    Stop commands repeat if output matches provided glob pattern
        │   │   │   ├── repeat-interval:    Time in seconds to wait between repeating commands
        │   │   │   └── return-last:    Returns requested last number of commands outputs
        │   │   └── napalm:    Use NAPALM plugin to collect output from devices
        │   │       ├── interval:    Interval between sending commands
        │   │       ├── split-lines:    Split multiline string to individual commands
        │   │       └── new-line-char:    Character to replace with new line before sending to device, default is _br_
        │   ├── enable:    Enter exec mode
        │   └── structure:    TTP Results structure
        └── textfsm:    Parse devices output using TextFSM templates
            ├── timeout:    Job timeout
            ├── workers:    Filter workers to target, default 'all'
            ├── verbose-result:    Control output details, default 'False'
            ├── progress:    Display progress events, default 'True'
            ├── nowait:    Do not wait for job to complete, default 'False'
            ├── add-details:    Add task details to results, default 'False'
            ├── num-workers:    RetryRunner number of threads for tasks execution
            ├── num-connectors:    RetryRunner number of threads for device connections
            ├── connect-retry:    RetryRunner number of connection attempts
            ├── task-retry:    RetryRunner number of attempts to run task
            ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
            ├── connect-check:    RetryRunner test TCP connection before opening actual connection
            ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
            ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
            ├── tf:    File group name to save task results to on worker file system
            ├── tf-skip-failed:    Save results to file for failed tasks
            ├── diff:    File group name to run the diff for
            ├── diff-last:    File version number to diff, default is 1 (last)
            ├── FO:    Filter hosts using Filter Object
            ├── FB:    Filter hosts by name using Glob Patterns
            ├── FH:    Filter hosts by hostname
            ├── FC:    Filter hosts containment of pattern in name
            ├── FR:    Filter hosts by name using Regular Expressions
            ├── FG:    Filter hosts by group
            ├── FP:    Filter hosts by hostname using IP Prefix
            ├── FL:    Filter hosts by names list
            ├── FM:    Filter hosts by platform
            ├── FX:    Filter hosts excluding them by name
            ├── FN:    Negate the match
            ├── template:    Path to a TextFSM template file
            └── commands (M):    List of commands to parse form devices
nf#
```

## Python API Reference

::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.parse_napalm
::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.parse_ttp
::: norfab.workers.nornir_worker.nornir_worker.NornirWorker.parse_textfsm