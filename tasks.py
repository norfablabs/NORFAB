"""Repository development tasks.

Run ``poetry run inv --list`` to discover commands. Paths are anchored to this
file so tasks behave the same way from the repository root or a subdirectory.
"""

# Invoke task signatures are a command-line interface, so inferred argument
# types are clearer here than annotations repeated across every task callback.
# ruff: noqa: ANN001, ANN201, ANN202

import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from invoke import Collection, task
from invoke.exceptions import Exit

ROOT = Path(__file__).resolve().parent
NFWEB_FRONTEND_DIR = ROOT / "norfab" / "clients" / "nfweb" / "frontend"
NFWEB_NODE_MODULES_DIR = NFWEB_FRONTEND_DIR / "node_modules"
DOCKER_DIR = ROOT / "docker" / "norfab-docker-tests"
COMPOSE_FILE = DOCKER_DIR / "compose.yaml"
DISTRIBUTED_FILE = DOCKER_DIR / "compose.distributed.yaml"
DISTRIBUTED_DIR = DOCKER_DIR / "distributed-basic"

# The distributed broker owns the test keypair. Only its public certificate is
# copied into client runtime directories; the private certificate never leaves
# the broker directory.
BROKER_PUBLIC_KEY = (
    DISTRIBUTED_DIR
    / "broker"
    / "__norfab__"
    / "files"
    / "broker"
    / "public_keys"
    / "broker.key"
)
CLIENT_BROKER_PUBLIC_KEYS = (
    # NorFab first looks for a broker certificate local to the environment.
    DISTRIBUTED_DIR
    / "client"
    / "__norfab__"
    / "files"
    / "broker"
    / "public_keys"
    / "broker.key",
    # The named pytest client also keeps its own public-key cache.
    DISTRIBUTED_DIR
    / "client"
    / "__norfab__"
    / "files"
    / "client"
    / "distributed-core-tests"
    / "public_keys"
    / "broker.key",
)

# Public Invoke suite name -> (Docker Compose service, default pytest marker).
# This single mapping drives task registration, aliases, image builds, and the
# sequential all-suites runner.
SUITES = {
    "core": ("core-tests", "core"),
    "nornir": ("nornir-service-tests", "nornir"),
    "netbox": ("netbox-service-tests", "netbox"),
    "fakenos": ("fakenos-service-tests", "fakenos"),
    "containerlab": ("containerlab-service-tests", "containerlab"),
    "workflow": ("workflow-service-tests", "workflow"),
    "agent": ("agent-tests", "clientagent"),
    "fastmcp": ("fastmcp-service-tests", "fastmcp"),
    "fastapi": ("fastapi-service-tests", "fastapi"),
    "filesharing": ("filesharing-service-tests", "filesharing"),
    "dummy": ("dummy-service-tests", "dummy"),
    "nfcli": ("nfcli-tests", "nfcli"),
}


def _run(args, *, env=None, check=True):
    """Run a command from the repository root and return its exit status.

    Args:
        args: Command and arguments, passed directly without a shell.
        env: Optional complete subprocess environment.
        check: End the Invoke task with the command's status when true.
    """
    command = [str(arg) for arg in args]
    # list2cmdline is used only for readable output; subprocess receives the
    # original argument list and does not evaluate it through a shell.
    print(f"+ {subprocess.list2cmdline(command)}", flush=True)
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    except OSError as exc:
        # Convert process-launch failures into an Invoke-friendly message
        # instead of exposing an implementation traceback to task users.
        raise Exit(f"Unable to run {command[0]}: {exc}", code=1) from None

    if check and result.returncode:
        raise Exit(
            f"Command failed with exit status {result.returncode}: "
            f"{subprocess.list2cmdline(command)}",
            code=result.returncode,
        )
    return result.returncode


def _required_executable(name):
    """Return an executable path or explain the missing build prerequisite."""
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"Required executable is not available on PATH: {name}")
    return executable


def _compose(compose_file=COMPOSE_FILE):
    """Return the common Docker Compose command prefix for a Compose file."""
    return [
        "docker",
        "compose",
        "--project-directory",
        DOCKER_DIR,
        "-f",
        compose_file,
    ]


def _environment(python_version=""):
    """Copy the current environment and optionally select a runner Python."""
    env = os.environ.copy()
    if python_version:
        env["PYTHON_VERSION"] = python_version
    return env


def _prepare_runtime(service, shard=None):
    """Create and return a suite or file-shard runtime directory."""
    runtime = DOCKER_DIR / service
    runtime = runtime / "parallel" / shard if shard else runtime
    runtime = runtime / "__norfab__"
    (runtime / "artifacts").mkdir(parents=True, exist_ok=True)
    return runtime


def _suite_test_root(suite):
    """Find a suite test root from the repository's directory conventions."""
    candidates = (
        ROOT / "tests" / "services" / suite,
        ROOT / "tests" / "clients" / suite,
        ROOT / "tests" / suite,
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ValueError(f"No test directory found for suite {suite!r}")


def _discover_test_files(suite, selector=""):
    """Discover ``test_*.py`` below a suite root or selected directory."""
    if "::" in selector:
        raise ValueError("--parallel-runs does not support pytest node IDs")
    selected = ROOT / selector if selector else _suite_test_root(suite)
    if selector and not selected.exists():
        selected = ROOT / "tests" / selector
    selected = selected.resolve()
    tests_root = (ROOT / "tests").resolve()
    if selected != tests_root and tests_root not in selected.parents:
        raise ValueError(f"Parallel test selection is outside {tests_root}")
    if selected.is_file():
        if not selected.match("test_*.py"):
            raise ValueError(f"Parallel test selection is not a test file: {selected}")
        return selected.parent, [selected]
    if not selected.is_dir():
        raise ValueError(f"Parallel test selection does not exist: {selected}")
    test_files = sorted(selected.rglob("test_*.py"))
    if not test_files:
        raise ValueError(f"No test_*.py files found below {selected}")
    return selected, test_files


def _prepare_distributed_certificate(force=False):
    """Install the test broker's public certificate in allowlisted locations.

    A different cached certificate is preserved unless ``force`` is true.
    """
    for public_key in CLIENT_BROKER_PUBLIC_KEYS:
        destination = public_key.resolve()
        # Keep certificate writes inside the test tree even if constants are
        # changed incorrectly in a future edit.
        if DOCKER_DIR.resolve() not in destination.parents:
            raise RuntimeError(f"Certificate destination is outside {DOCKER_DIR}")
        if (
            destination.exists()
            and destination.read_bytes() == BROKER_PUBLIC_KEY.read_bytes()
        ):
            continue
        if destination.exists() and not force:
            raise RuntimeError(
                "Distributed client broker certificate differs; rerun with "
                "--force-certificates"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        shutil.copy2(BROKER_PUBLIC_KEY, temporary)
        # Replace atomically so an interrupted copy cannot leave a partial key.
        os.replace(temporary, destination)
        print(f"Prepared broker public certificate: {destination}", flush=True)


@task(name="docs-build", help={"strict": "Treat MkDocs warnings as errors."})
def docs_build(_context, strict=False):
    """Build the documentation site."""
    args = [sys.executable, "-m", "mkdocs", "build"]
    if strict:
        args.append("--strict")
    _run(args)


@task(name="docs-serve", help={"address": "MkDocs listen address and port."})
def docs_serve(_context, address="127.0.0.1:8000"):
    """Serve documentation until interrupted."""
    _run([sys.executable, "-m", "mkdocs", "serve", "--dev-addr", address])


@task(name="package-build")
def package_build(_context):
    """Build NFWeb, remove its dependencies, then build Python packages."""
    npm = _required_executable("npm")
    if not NFWEB_NODE_MODULES_DIR.is_dir():
        _run([npm, "--prefix", NFWEB_FRONTEND_DIR, "ci"])

    _run([npm, "--prefix", NFWEB_FRONTEND_DIR, "run", "build"])
    shutil.rmtree(NFWEB_NODE_MODULES_DIR)
    print(f"Removed generated dependencies: {NFWEB_NODE_MODULES_DIR}", flush=True)
    _run(["poetry", "build"])


@task(name="format")
def format_code(_context):
    """Format Python files with Black."""
    _run([sys.executable, "-m", "black", "."])


@task(name="format-check")
def format_check(_context):
    """Check Python formatting without changing files."""
    _run([sys.executable, "-m", "black", "--check", "."])


@task(name="lint")
def lint(_context):
    """Lint the repository with Ruff."""
    _run([sys.executable, "-m", "ruff", "check", "."])


@task(name="dead-code")
def dead_code(_context):
    """Report unused code with Vulture; do not suppress or modify findings."""
    _run([sys.executable, "-m", "vulture"])


@task(name="checks")
def checks(context):
    """Run non-mutating formatting, lint, and dead-code checks."""
    failures = []
    # Run every check even if an earlier one fails, producing one useful
    # baseline rather than stopping at the first existing repository issue.
    for check in (format_check, lint, dead_code):
        try:
            check(context)
        except subprocess.CalledProcessError:
            failures.append(check.name)
    if failures:
        raise RuntimeError(f"Checks failed: {', '.join(failures)}")


def _run_suite(
    suite,
    selector="",
    marker="",
    keyword="",
    pytest_args="",
    build=False,
    python_version="",
    runtime=None,
    junit_name="",
):
    """Run one mapped pytest suite in Compose and return its exit status."""
    service, default_marker = SUITES[suite]
    runtime = runtime or _prepare_runtime(service)
    args = _compose() + ["run", "--rm"]
    if build:
        args.append("--build")
    if junit_name:
        args += [
            "--volume",
            f"{runtime.resolve()}:/workspace/tests/nf_tests_inventory/__norfab__",
            "--env",
            "PYTEST_JUNIT_XML="
            f"/workspace/tests/nf_tests_inventory/__norfab__/artifacts/{junit_name}",
        ]
    # Arguments after the service replace its Compose `command`, so always add
    # a marker explicitly to avoid accidentally running the entire repository.
    args += [service, "-m", marker or default_marker]
    if selector:
        args.append(selector)
    if keyword:
        args += ["-k", keyword]
    if pytest_args:
        args += shlex.split(pytest_args)
    return _run(args, env=_environment(python_version), check=False)


def _run_suite_parallel(
    suite,
    selector="",
    marker="",
    keyword="",
    pytest_args="",
    build=False,
    python_version="",
    parallel_runs=1,
):
    """Run discovered test files with at most ``parallel_runs`` containers."""
    if parallel_runs < 1:
        raise ValueError("--parallel-runs must be a positive integer")
    service, _default_marker = SUITES[suite]
    test_root, test_files = _discover_test_files(suite, selector)
    if build:
        _run(
            _compose() + ["build", service],
            env=_environment(python_version),
        )

    def run_file(test_file):
        relative_file = test_file.relative_to(test_root)
        runtime = _prepare_runtime(service, relative_file.with_suffix(""))
        test_selector = test_file.relative_to(ROOT).as_posix()
        return test_selector, _run_suite(
            suite,
            test_selector,
            marker,
            keyword,
            pytest_args,
            False,
            python_version,
            runtime,
            f"{test_file.stem}-junit.xml",
        )

    workers = min(parallel_runs, len(test_files))
    print(
        f"Running {len(test_files)} {suite} test containers, "
        f"at most {workers} at a time",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(run_file, test_files))

    print(f"Docker suite {suite} parallel results:")
    for test_file, return_code in results:
        status = "passed" if return_code == 0 else f"status {return_code} (ignored)"
        print(f"  {test_file}: {status}")
    return max((return_code for _test_file, return_code in results), default=0)


def _suite_task(suite):
    """Create an Invoke task and singular alias for one entry in ``SUITES``."""

    # A task factory keeps every Docker suite's options and behavior identical
    # without maintaining a near-duplicate function for each service.
    @task(
        aliases=(f"docker-test-{suite}",),
        help={
            "selector": "Test path, directory, or node ID.",
            "marker": "Override the suite's pytest marker.",
            "keyword": "Pytest -k expression.",
            "pytest_args": "Additional quoted pytest arguments.",
            "build": "Build the runner image before testing.",
            "python_version": "Docker runner Python version.",
            "parallel_runs": "Maximum concurrent per-file test containers.",
        },
    )
    def run(
        _context,
        selector="",
        marker="",
        keyword="",
        pytest_args="",
        build=False,
        python_version="",
        parallel_runs=0,
    ):
        # Individual tasks are intended for interactive use, so report test
        # failures without turning them into an Invoke traceback.
        if parallel_runs:
            return_code = _run_suite_parallel(
                suite,
                selector,
                marker,
                keyword,
                pytest_args,
                build,
                python_version,
                parallel_runs,
            )
        else:
            return_code = _run_suite(
                suite, selector, marker, keyword, pytest_args, build, python_version
            )
        if return_code:
            print(f"Docker suite {suite} exited with status {return_code} (ignored)")

    run.__doc__ = f"Run the {suite} Docker suite and report, but ignore, test failures."
    return run


@task(
    name="docker-tests-prepare",
    help={"force_certificates": "Replace a different cached client broker key."},
)
def docker_tests_prepare(_context, force_certificates=False):
    """Create runtime directories and validate both Compose files."""
    for service, _marker in SUITES.values():
        _prepare_runtime(service)
    for compose_file in (COMPOSE_FILE, DISTRIBUTED_FILE):
        _run(_compose(compose_file) + ["config", "--quiet"])
    _prepare_distributed_certificate(force_certificates)


@task(
    name="docker-tests-build",
    help={
        "suite": "Build one suite instead of all suites.",
        "python_version": "Docker runner Python version.",
    },
)
def docker_tests_build(_context, suite="", python_version=""):
    """Build Docker test runner images."""
    if suite and suite not in SUITES:
        raise ValueError(f"Unknown suite {suite!r}; choose from {', '.join(SUITES)}")
    services = [SUITES[suite][0]] if suite else [item[0] for item in SUITES.values()]
    _run(_compose() + ["build", *services], env=_environment(python_version))


@task(
    name="docker-tests-all",
    help={
        "fail_fast": "Stop after the first failed suite.",
        "build": "Build runner images before testing.",
        "python_version": "Docker runner Python version.",
        "parallel_runs": "Maximum concurrent per-file test containers.",
    },
)
def docker_tests_all(
    _context,
    fail_fast=False,
    build=False,
    python_version="",
    parallel_runs=0,
):
    """Run every Docker suite sequentially and summarize failures."""
    failures = []
    # Unlike individual suite tasks, the aggregate retains each status and
    # ultimately fails so it remains suitable for a full validation run.
    for suite in SUITES:
        if parallel_runs:
            return_code = _run_suite_parallel(
                suite,
                build=build,
                python_version=python_version,
                parallel_runs=parallel_runs,
            )
        else:
            return_code = _run_suite(suite, build=build, python_version=python_version)
        if return_code:
            failures.append(suite)
            if fail_fast:
                break
    if failures:
        raise RuntimeError(f"Docker test suites failed: {', '.join(failures)}")


@task(
    name="docker-tests-distributed",
    help={"force_certificates": "Replace a different cached client broker key."},
)
def docker_tests_distributed(_context, force_certificates=False):
    """Run distributed broker/worker/client tests and always tear them down."""
    services = [
        "distributed-broker",
        "distributed-netbox-worker",
        "distributed-nornir-worker",
        "distributed-dummy-worker",
    ]
    compose = _compose(DISTRIBUTED_FILE)
    _prepare_distributed_certificate(force_certificates)
    try:
        _run(compose + ["up", "-d", *services])
        time.sleep(3)
        # Dependencies are already running; --no-deps prevents Compose from
        # recreating them immediately before the client test starts.
        _run(compose + ["run", "--rm", "--no-deps", "distributed-client"])
    finally:
        # Cleanup also runs when pytest fails or the task is interrupted.
        _run(compose + ["down", "--remove-orphans"])


@task(name="docker-tests-down")
def docker_tests_down(_context):
    """Stop both Docker test projects without deleting runtime artifacts."""
    for compose_file in (COMPOSE_FILE, DISTRIBUTED_FILE):
        _run(_compose(compose_file) + ["down", "--remove-orphans"])


@task(name="docker-tests-config")
def docker_tests_config(_context):
    """Validate both Docker Compose configurations."""
    for compose_file in (COMPOSE_FILE, DISTRIBUTED_FILE):
        _run(_compose(compose_file) + ["config", "--quiet"])


# Register explicitly declared tasks first. Invoke loads the collection from
# the conventional module-level ``ns`` name below.
namespace = Collection()
for invoke_task in (
    docs_build,
    docs_serve,
    package_build,
    format_code,
    format_check,
    lint,
    dead_code,
    checks,
    docker_tests_prepare,
    docker_tests_build,
    docker_tests_all,
    docker_tests_distributed,
    docker_tests_down,
    docker_tests_config,
):
    namespace.add_task(invoke_task)

# Generate canonical plural names such as ``docker-tests-nornir``. The task
# factory also registers the singular ``docker-test-nornir`` alias.
for suite_name in SUITES:
    namespace.add_task(
        _suite_task(suite_name),
        name=f"docker-tests-{suite_name}",
    )

ns = namespace
