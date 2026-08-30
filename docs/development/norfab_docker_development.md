# Develop NorFab with Docker

Use the Docker development environment to run the broker and all configured
workers in one container while importing NorFab from your local working tree.

The environment is defined in
[`docker/norfab-docker-dev`](https://github.com/norfablabs/NORFAB/tree/master/docker/norfab-docker-dev).

## Prerequisites

- Docker Engine or Docker Desktop
- Docker Compose v2 (`docker compose`)
- A local clone of the NorFab repository
- Host TCP ports `5555`, `8000`, and `8001` available

## Start the environment

From the repository root, build the all-in-one image and start the stack:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up --build
```

Add `-d` to run the container in the background. The `norfab` service contains
the broker, configured service workers, and built-in File Sharing worker.

| Interface | Address |
| --- | --- |
| Broker | `tcp://10.0.0.100:5555` |
| FastAPI | `http://localhost:8000` |
| FastMCP | `http://localhost:8001/mcp/` |

Follow the logs with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml logs -f norfab
```

## Verify the source mount

The Compose file mounts the repository's `norfab/` package directly over the
installed package in the container's Python `site-packages` directory. This
makes the local source take precedence while retaining all dependencies and
entry points installed by the image.

Confirm the import path:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  exec norfab \
  python -c "import norfab; print(norfab.__file__)"
```

The printed path should be under
`/usr/local/lib/pythonX.Y/site-packages/norfab`.

## Apply code changes

Python source changes are immediately visible inside the container, but the
running broker and worker processes must be restarted to load them:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml restart norfab
```

Rebuild the image after changing a Dockerfile or project dependency:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml build
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up -d
```

## Change the development inventory

Files under `docker/norfab-docker-dev/norfab/` are mounted at `/etc/norfab`:

- `inventory.yaml` defines the broker, workers, and all-in-one topology.
- Service subdirectories contain worker settings.
- `__norfab__/` contains development runtime data and logs.

The Compose project loads `docker/norfab-docker-dev/.env` into the container so
inventory templates can read the configured logging levels and credentials.
Restart the container after changing inventory files.

## Open a container shell

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml exec norfab sh
```

## Stop the environment

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml down
```

For a published-image deployment, follow the
[Docker deployment tutorial](../tutorials/norfab_docker_deployment.md).
