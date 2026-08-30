# NorFab Docker Development Environment

Run the broker and all configured workers in one all-in-one container for local
development. The image installs NorFab's `full` dependency set, while a bind
mount replaces the installed `norfab` package with the repository's local
source code.

The container starts:

- the NorFab broker on port `5555`;
- Nornir, NetBox, FastAPI, Workflow, FastMCP, and FakeNOS workers;
- the built-in File Sharing worker;
- FastAPI on port `8000` and FastMCP on port `8001`.

## Start the environment

From the repository root:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up --build
```

Add `-d` to run in the background. Follow the logs with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml logs -f norfab
```

Stop and remove the container with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml down
```

## Work on the code

The local `norfab/` package is mounted directly over the package installed in
the container's Python `site-packages` directory. Source edits are immediately
visible in the container, but restart it to reload the running processes:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml restart norfab
```

Confirm the active import path and the current poll timeout with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  exec norfab \
  python -c "import norfab; from norfab.core import NFP; print(norfab.__file__); print(NFP.ZMQ_SEND_RECV_POLL_TIMEOUT_MS)"
```

The package path should be under `/usr/local/lib/pythonX.Y/site-packages/norfab`.

Rebuild the image after changing a Dockerfile or Python dependency:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml build
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up -d
```

## Configure the environment

The Compose project reads `docker/norfab-docker-dev/.env` for the Python
version, logging levels, and service credentials, and injects those values into
the container. Files under `docker/norfab-docker-dev/norfab/` are mounted at
`/etc/norfab`:

- `inventory.yaml` defines the broker, workers, and all-in-one topology;
- service subdirectories contain worker settings;
- `__norfab__/` stores runtime databases, certificates, and logs.

Restart the container after changing inventory files.

## Open a container shell

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml exec norfab sh
```
