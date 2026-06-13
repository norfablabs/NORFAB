# NorFab Docker Image Definitions

This directory contains the Dockerfiles used to build NorFab images for
different runtime roles. It does not contain a standalone Compose deployment.

| Dockerfile | Purpose |
| --- | --- |
| `Dockerfile.norfab.aio` | Broker and inventory-defined workers in one container |
| `Dockerfile.norfab.broker` | Broker-only container |
| `Dockerfile.norfab.nornir` | Nornir service worker container |
| `Dockerfile.norfab.netbox` | NetBox service worker container |
| `Dockerfile.norfab.fastapi` | FastAPI service worker container |
| `Dockerfile.norfab.workflow` | Workflow service worker container |

Each image installs NorFab from PyPI. Worker images also install the matching
optional dependency set. Runtime inventory must be mounted at `/etc/norfab`.

## Build an image

Run builds from the repository root so the file paths are consistent:

```bash
docker build \
  -f docker/norfab-docker-build/Dockerfile.norfab.aio \
  -t norfab:aio-local \
  .
```

For example, build the Nornir worker image with:

```bash
docker build \
  -f docker/norfab-docker-build/Dockerfile.norfab.nornir \
  -t norfab:nornir-local \
  .
```

Use [the development Compose variant](../norfab-docker-dev/README.md) to build
the role-specific images and run them together with the local NorFab source
mounted into each container.

