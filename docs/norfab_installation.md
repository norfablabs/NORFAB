## Install NorFab

Install NorFab from PyPI

```
pip install norfab
```

NorFab core runs equally well on both Windows and Linux. Some 
services might work only on one or the other, in that case that
will be noted in service deployment details.

## Extras

Several extra installations supported tailoring certain services
dependencies that you want to run on a given node.

To install all dependencies for all services can use ``full`` extras:

```
pip install norfab[full]
```

### NORFAB CLI Dependencies

To install NorFab Interactive CLI dependencies

```
pip install norfab[nfcli]
```

### Robot Client Dependencies

To install Robot library dependencies

```
pip install norfab[robot]
```

### Nornir Service Dependencies

To install Nornir service dependencies

```
pip install norfab[nornirservice]
```

### Netbox Service Dependencies

To install Netbox service dependencies

```
pip install norfab[netboxservice]
```

### FastAPI Service Dependencies

To install FastAPI service dependencies

```
pip install norfab[fastapiservice]
```

### Ollama Agent Service Dependencies

To install Ollama Agent service dependencies

```
pip install norfab[agentservice]
```

## Operating Systems Support

| Component      | Windows      | Linux        | MacOS        |
| -------------- | ------------ | ------------ | ------------ |
| NorFab Core    | :check_mark: | :check_mark: | :check_mark: |
| Nornir Service | :check_mark: | :check_mark: | :check_mark: |
| Netbox Service | :check_mark: | :check_mark: | :check_mark: |
