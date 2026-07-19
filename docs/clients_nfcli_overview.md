---
tags:
  - nfcli
---

# NORFAB CLI Overview

NORFAB comes with an interactive command line shell interface invoked using ``nfcli`` to work with the system. The CLI provides a powerful and flexible way to interact with NORFAB, enabling users to manage and automate network operations efficiently.

NORFAB CLI designed as a *modal* operating system. The term modal 
describes a system that has various modes of operation, each having its own 
domain of operation. The CLI uses a hierarchical structure for the modes.

You can access a lower-level mode only from a higher-level mode. For example, 
to access the Nornir mode, you must be in the privileged EXEC mode. Each mode 
is used to accomplish particular tasks and has a specific set of commands that 
are available in this mode. For example, to configure a router interface, you 
must be in Nornir configuration mode. All configurations that you enter in 
configuration mode apply only to this function.

NORFAB CLI build using [PICLE package](https://github.com/dmulyalin/picle).

## Local environment file

At startup, NFCLI uses NFAPI to detect a `.env` file in the directory that
contains `inventory.yaml`. Variables are loaded before inventory Jinja2
rendering and are inherited by locally started broker and worker processes.
Values in `.env` override variables already exported by the shell or supplied
by CI.

```bash
# .env
LAB_USERNAME=operator
LAB_PASSWORD="local development password"
```

Reference the values from inventory with the `env` Jinja2 dictionary:

```yaml
defaults:
  username: '{{ env.get("LAB_USERNAME") }}'
  password: '{{ env.get("LAB_PASSWORD") }}'
```

See the [NFAPI environment file reference](api_reference_core_norfab_nfapi.md#environment-file-loading)
for the supported file syntax and API controls.

It is important to remember that in PICLE Shell, when you enter a command, the 
command is executed. If you enter an incorrect command in a production environment, 
it can negatively impact it.






