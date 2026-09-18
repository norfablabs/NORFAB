"""Pydantic models for NorFab topology configuration."""

from typing import Dict, List, Union

from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)


class WorkerTopologyConfig(BaseModel):
    """Per-worker topology settings."""

    depends_on: List[StrictStr] = Field(
        None,
        description="List of worker names that must be running before this worker starts",
    )


TopologyWorkerEntry = Union[StrictStr, Dict[StrictStr, WorkerTopologyConfig]]


class TopologyConfig(BaseModel):
    """NorFab deployment topology configuration."""

    broker: StrictBool = Field(
        True,
        description="Start broker as part of this topology",
    )
    workers: List[TopologyWorkerEntry] = Field(
        None,
        description="Ordered list of workers to start in this topology",
    )
    workers_start_interval: Union[StrictFloat, StrictInt] = Field(
        0.5,
        ge=0,
        description="Seconds to wait between worker process starts",
    )

    @model_validator(mode="after")
    def validate_dependency_cycles(self) -> "TopologyConfig":
        """Reject circular worker dependencies."""
        graph = {}
        for entry in self.workers or []:
            if isinstance(entry, str):
                graph.setdefault(entry, [])
            else:
                for name, config in entry.items():
                    graph.setdefault(name, []).extend(config.depends_on or [])

        states = {}
        path = []

        def visit(name: str) -> None:
            if states.get(name) == 1:
                cycle = path[path.index(name) :] + [name]
                raise ValueError(
                    f"Circular worker dependency detected: {' -> '.join(cycle)}"
                )
            if states.get(name) == 2:
                return

            states[name] = 1
            path.append(name)
            for dependency in graph.get(name, []):
                visit(dependency)
            path.pop()
            states[name] = 2

        for worker_name in graph:
            visit(worker_name)

        return self
