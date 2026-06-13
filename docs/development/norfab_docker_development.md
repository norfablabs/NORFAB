# Develop NorFab with Docker

Use the Docker development environment to run the broker and service workers
in separate containers while importing the NorFab source from your local
working tree.

The environment is defined in
[`docker/norfab-docker-dev`](https://github.com/norfablabs/NORFAB/tree/master/docker/norfab-docker-dev).

## Prerequisites

- Docker Engine or Docker Desktop
- Docker Compose v2 (`docker compose`)
- A local clone of the NorFab repository
- Host TCP port `5555` available for the broker

## Start the environment

From the repository root, build the images and start the stack:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up --build
```

Add `-d` to run the containers in the background. The stack starts:

| Service | Role | Address |
| --- | --- | --- |
| `norfab-broker` | NorFab broker | `10.0.0.100:5555` |
| `norfab-service-nornir` | Nornir worker | `10.0.0.101` |
| `norfab-service-netbox` | NetBox workers | `10.0.0.102` |

Follow all logs with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml logs -f
```

## Verify the source mount

The Compose file mounts the repository's `norfab/` package at
`/opt/norfab/norfab` and sets `PYTHONPATH=/opt/norfab`. This makes the local
source take precedence over the NorFab package installed in each image.

Confirm the import path:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  exec norfab-service-nornir \
  python -c "import norfab; print(norfab.__file__)"
```

The printed path should start with `/opt/norfab/norfab`.

## Apply code changes

Python source changes are immediately visible inside the containers, but the
running worker process must be restarted to load them:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  restart norfab-service-nornir
```

Restart `norfab-broker` or `norfab-service-netbox` instead when a change
affects those components.

Rebuild the images after changing a Dockerfile or project dependencies:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml build
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up -d
```

## Change the development inventory

Files under `docker/norfab-docker-dev/norfab/` are mounted at `/etc/norfab` in
every container:

- `inventory.yaml` defines the broker, workers, and topology.
- `nornir/` contains Nornir worker settings.
- `netbox/` contains NetBox worker settings.

Restart the affected containers after changing inventory files.

## Open a container shell

Use `docker compose exec` to inspect a running service:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  exec norfab-service-nornir sh
```

## Stop the environment

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml down
```

For a published-image deployment, follow the
[Docker deployment tutorial](../tutorials/norfab_docker_deployment.md).
