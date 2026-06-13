# NorFab Docker Deployment

Run NorFab as a single all-in-one container using the published
`docker.io/dmulyalin/norfab:aio-latest` image. It is the quickest Docker option
for trying NorFab or running the broker and configured workers on one host.

The supplied inventory starts these components in the same container:

- NorFab broker
- Nornir worker
- NetBox worker
- FastAPI worker
- Workflow worker

The FastAPI service is published on host port `8000`. The inventory and worker
configuration under `norfab/` are bind-mounted into the container at
`/etc/norfab`.

## Start the deployment

From the repository root:

```bash
cd docker/norfab-docker
docker compose pull
docker compose up -d
docker compose logs -f norfab
```

Open `http://localhost:8000/docs` to view the FastAPI Swagger UI.

Stop and remove the container with:

```bash
docker compose down
```

## Configure the deployment

Edit `norfab/inventory.yaml` to select the workers to start. Service-specific
settings are stored in the `norfab/nornir`, `norfab/netbox`,
`norfab/fastapi`, and `norfab/workflow` directories.

Restart the container after changing the inventory:

```bash
docker compose restart norfab
```

This Compose file publishes the FastAPI port only. It does not expose the
broker port for remote NorFab clients.
