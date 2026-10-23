from nornir.core.task import Result, Task

from norfab.core.worker import Job


def task(task: Task, job: Job = None) -> Result:
    """Return injected job metadata and emit a per-host event."""
    task.name = "dummy_with_job"
    job.event(f"processing host '{task.host.name}'")
    return Result(
        host=task.host,
        result={"uuid": job.juuid, "task": job.task, "host": task.host.name},
    )
