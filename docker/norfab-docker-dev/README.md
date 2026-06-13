# NorFab Docker Development Environment

Run a multi-container NorFab environment for local development.
It builds role-specific images and mounts the repository's `norfab` Python
package into each container, so the containers import the code in your working
tree.

The Compose stack starts:

- `norfab-broker` at `10.0.0.100`
- `norfab-service-nornir` at `10.0.0.101`
- `norfab-service-netbox` at `10.0.0.102`

Host port `5555` is forwarded to the broker.

## Start the environment

From the repository root:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml up --build
```

Run it in the background by adding `-d`. Stop and remove the containers with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml down
```

## Work on the code

The local `norfab/` package is mounted at `/opt/norfab/norfab`, and
`PYTHONPATH=/opt/norfab` makes it take precedence over the package installed in
the image.

Confirm the active import path with:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  exec norfab-service-nornir \
  python -c "import norfab; print(norfab.__file__)"
```

Restart the affected service after changing Python code:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml \
  restart norfab-service-nornir
```

Rebuild the images when a Dockerfile or Python dependency changes:

```bash
docker compose -f docker/norfab-docker-dev/docker-compose.yaml build
```

The files under `norfab-docker-dev/norfab/` provide the broker and worker
inventory mounted at `/etc/norfab`.

