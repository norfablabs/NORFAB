# NFAPI Reference

## Environment file loading

`NorFab` loads a `.env` file before it initializes `NorFabInventory`. By
default, it checks the directory containing `inventory.yaml`. When using
`inventory_data`, it checks `base_dir`, or the current directory when
`base_dir` is omitted. This makes the values available to inventory Jinja2
expressions and to NFCLI, broker, and worker processes.

The `python-dotenv` loader supports Bash-like assignments, comments, quoted and
multiline values, the optional `export` directive, and `${VAR}` expansion. It
replaces variables already present in the process environment by default, so
the local `.env` file takes precedence over shell and CI values.

```python
nf = NorFab(inventory="./inventory.yaml")  # Loads ./.env when present.
environment = nf.list_environment_variables()
```

Set `load_env_override=False` to preserve existing process variables instead:

```python
nf = NorFab(inventory="./inventory.yaml", load_env_override=False)
```

## Python API

::: norfab.core.nfapi.NorFab
