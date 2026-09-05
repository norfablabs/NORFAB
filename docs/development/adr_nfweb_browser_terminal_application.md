# ADR: NFWeb Browser Terminal

- **Status:** Proposed
- **Date:** 5 September 2026
- **Scope:** Browser-native NFCLI experience in NFWeb

## Context

NFWeb needs a keyboard-first terminal with command editing, history, Tab
completion, contextual help, validation, streaming output, cancellation, and
interactive prompts.

The terminal must provide the same NORFAB command experience as NFCLI. It is not
an operating-system terminal and does not expose PowerShell, Bash, CMD, a PTY, or
arbitrary subprocesses.

NORFAB already uses Pydantic models for validation and schema generation. These
models can also describe commands, arguments, help, and completion to the browser.

## Decision

Add an NFWeb `terminal` application using:

- **xterm.js** for terminal rendering and keyboard input;
- a **TypeScript command engine** for parsing, editing, history, help, and
  completion;
- **Pydantic models** for command arguments and WebSocket messages;
- a **Python command registry** for the full built-in and plugin NFCLI command
  tree;
- a **Tornado WebSocket** for execution, streaming output, prompts, and
  cancellation.

Registered handlers run in the NFWeb process and use its native `NFPClient`.
Python remains authoritative for validation and execution.

The first release is deliberately unrestricted:

- the terminal is enabled by default;
- NFWeb listens on `0.0.0.0` by default;
- any client that can reach NFWeb may connect;
- cross-origin HTTP and WebSocket access is allowed;
- there is no authentication, authorization, TLS requirement, CSRF protection,
  or command permission filtering;
- every registered command, including change operations, is available.

## NFCLI Parity

The browser terminal must support the NFCLI interactive experience:

- the same command hierarchy, aliases, and installed plugin commands;
- positional arguments, options, flags, quoting, and escaping;
- Tab completion and contextual `?` help;
- `help` and `command --help`;
- NFCLI-compatible output processors and pipes;
- command history and reverse history search;
- interactive prompts and input;
- streaming output, progress, timeout handling, and Ctrl+C cancellation;
- cursor movement, line editing, Ctrl+L, and bracketed paste.

Parity applies to NFCLI commands, not host shell syntax. Shell operators,
redirects, command substitution, background processes, and arbitrary NORFAB
`service`/`task`/`kwargs` calls are not supported.

## Architecture

```text
Browser
  xterm.js + TypeScript command engine
      | GET /api/v1/terminal/commands
      | WebSocket /api/v1/terminal/session
      v
NFWeb terminal application
  Pydantic models + command registry + handlers
      v
NFPClient -> NORFAB broker and workers
```

xterm.js handles rendering and keyboard events only. The TypeScript engine owns
the interactive command-line behavior. Python handlers own command validation
and execution.

Each command registry entry contains:

- a stable command ID, path, and aliases;
- a Pydantic argument model;
- help text and completion metadata;
- an execution handler;
- timeout and cancellation settings.

The browser receives a versioned, display-safe command catalogue generated from
the registry and Pydantic JSON Schema. Dynamic completion uses registered server
providers. Every execution request is validated again by the server.

Only one foreground command runs per browser session. Output and history remain
bounded to avoid accidental browser or server exhaustion. These are resource
controls, not access restrictions.

## Configuration

```yaml
client:
  nfweb:
    host: 0.0.0.0
    terminal:
      enabled: true
      command_timeout: 600
      completion_timeout: 5
      history_size: 200
      max_output_bytes: 1048576
```

No security configuration is required for the first release. Operators may add
firewall or reverse-proxy controls externally, but NFWeb does not require them.

## Consequences

Benefits:

- browser users receive an NFCLI-equivalent interactive shell;
- Pydantic provides one source for validation, help, and completion metadata;
- commands remain explicit, typed, and testable;
- no host shell, PTY, browser Python runtime, or production Node.js runtime is
  needed.

Trade-offs:

- NFWeb must maintain the TypeScript parser and line editor;
- Python and TypeScript protocol types must remain synchronized;
- any reachable client or website can execute change commands without identifying
  or authenticating a user;
- adding security later will require a separate design decision.

## Implementation

1. Add terminal configuration, Pydantic protocol models, and the command registry.
2. Register the complete built-in and installed-plugin NFCLI command tree.
3. Build the TypeScript editor, parser, help, completion, and history.
4. Add the xterm.js view, command catalogue endpoint, and unrestricted WebSocket.
5. Add command execution, streaming, prompts, timeouts, and cancellation.
6. Add NFCLI parity tests and user documentation.

## Acceptance Criteria

- The terminal is enabled by default and listens through NFWeb on `0.0.0.0`.
- Remote and cross-origin clients connect without authentication or authorization.
- Built-in and installed-plugin commands match the NFCLI command surface.
- Read and change commands execute without permission filtering.
- Help, completion, parsing, history, prompts, output, and Ctrl+C behave like NFCLI.
- Every command has a Pydantic model and explicit registry entry.
- The server validates every request.
- No host shell, PTY, subprocess, or generic NORFAB job endpoint is exposed.
- xterm.js assets are pinned and bundled with NFWeb.
- Backend, frontend, browser, and documentation checks pass.

## Alternatives

| Option | Reason not selected |
| --- | --- |
| Server-side PTY | Exposes the host operating-system shell rather than NFCLI |
| Browser Python runtime | Adds a large runtime without native NORFAB connectivity |
| Plain React console | Does not provide terminal and ANSI behavior |
| Generic NORFAB job form | Does not provide the NFCLI command experience |

## References

- [NFWeb platform architecture](adr_web_ui_topology_architecture.md)
- [NFWeb Developer Guide](nfweb_developer_guide.md)
- [Task Pydantic Models Guide](adr_tasks_pydantic_models_guide.md)
- [xterm.js documentation](https://xtermjs.org/docs/)
- [Tornado WebSocket documentation](https://www.tornadoweb.org/en/stable/websocket.html)
