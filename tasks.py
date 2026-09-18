"""Repository development tasks.

Run ``poetry run inv --list`` to discover commands. Paths are anchored to this
file so tasks behave the same way from the repository root or a subdirectory.
"""

# Invoke task signatures are a command-line interface, so inferred argument
# types are clearer here than annotations repeated across every task callback.
# ruff: noqa: ANN001, ANN201, ANN202

import csv
import json
import math
import os
import shlex
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree

from invoke import Collection, task
from invoke.exceptions import Exit

ROOT = Path(__file__).resolve().parent
NFWEB_FRONTEND_DIR = ROOT / "norfab" / "clients" / "nfweb" / "frontend"
NFWEB_NODE_MODULES_DIR = NFWEB_FRONTEND_DIR / "node_modules"
DOCKER_DIR = ROOT / "docker" / "norfab-docker-tests"
COMPOSE_FILE = DOCKER_DIR / "compose.yaml"
DISTRIBUTED_FILE = DOCKER_DIR / "compose.distributed.yaml"
DISTRIBUTED_DIR = DOCKER_DIR / "distributed-basic"
IDLE_PROFILE_SERVICE = "idle-norfab"

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
# all-suites runner.
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

# The aggregate starts the regular pytest runners concurrently. Containerlab
# has host-level networking/runtime requirements and remains an explicit task;
# the idle profiler and distributed topology are separate Compose workflows
# and are intentionally not represented in SUITES.
ALL_SUITES = tuple(suite for suite in SUITES if suite != "containerlab")
DOCKER_REPORTS_DIR = DOCKER_DIR / "reports"

# NetBox is large enough to warrant one dedicated container per test module.
# Group names intentionally match filenames so task names stay predictable.
NETBOX_TEST_GROUPS = {
    path.stem.removeprefix("test_"): path.relative_to(ROOT).as_posix()
    for path in sorted((ROOT / "tests" / "services" / "netbox").glob("test_*.py"))
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


def _docker_size_bytes(value):
    """Convert a Docker stats size such as ``12.5MiB`` to bytes."""
    value = value.strip()
    number = "".join(
        character for character in value if character.isdigit() or character in ".-"
    )
    unit = value[len(number) :].strip()
    factors = {
        "B": 1,
        "kB": 1_000,
        "MB": 1_000_000,
        "GB": 1_000_000_000,
        "TB": 1_000_000_000_000,
        "KiB": 1_024,
        "MiB": 1_048_576,
        "GiB": 1_073_741_824,
        "TiB": 1_099_511_627_776,
    }
    if not number or unit not in factors:
        raise ValueError(f"Unsupported Docker size: {value!r}")
    return float(number) * factors[unit]


def _docker_stats(container_id):
    """Read one Docker container stats sample as normalized numeric values."""
    command = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        container_id,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise Exit(f"Unable to run docker stats: {exc}", code=1) from None
    if result.returncode:
        raise Exit(
            result.stderr.strip() or "docker stats failed", code=result.returncode
        )
    data = json.loads(result.stdout.strip())
    memory_used = data["MemUsage"].split("/", maxsplit=1)[0]
    block_read, block_write = data["BlockIO"].split("/", maxsplit=1)
    return {
        "cpu_percent": float(data["CPUPerc"].strip().rstrip("%")),
        "memory_bytes": _docker_size_bytes(memory_used),
        "block_read_bytes": _docker_size_bytes(block_read),
        "block_write_bytes": _docker_size_bytes(block_write),
    }


def _percentile(values, percentile):
    """Return a nearest-rank percentile for a non-empty numeric sequence."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


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
    container_name="",
):
    """Run one mapped pytest suite in Compose and return its exit status."""
    service, default_marker = SUITES[suite]
    runtime = runtime or _prepare_runtime(service)
    # Restrict collection before applying the marker. Collecting the entire
    # tests tree imports unrelated worker modules whose task decorators share
    # a process-global registry that Linux worker processes can inherit.
    selector = selector or _suite_test_root(suite).relative_to(ROOT).as_posix()
    args = _compose() + ["run", "--rm"]
    if container_name:
        args += ["--name", container_name]
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

    max_workers = min(parallel_runs, len(test_files))
    print(
        f"Running {len(test_files)} {suite} test containers, "
        f"at most {max_workers} at a time",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(run_file, test_files))

    print(f"Docker suite {suite} parallel results:")
    for test_file, return_code in results:
        status = "passed" if return_code == 0 else f"status {return_code} (ignored)"
        print(f"  {test_file}: {status}")
    return max((return_code for _test_file, return_code in results), default=0)


def _run_netbox_group(group, build=False, python_version=""):
    """Run one named NetBox task group in a dedicated Compose container."""
    if group not in NETBOX_TEST_GROUPS:
        raise ValueError(
            f"Unknown NetBox test group {group!r}; choose from "
            f"{', '.join(NETBOX_TEST_GROUPS)}"
        )
    service = SUITES["netbox"][0]
    if build:
        _run(_compose() + ["build", service], env=_environment(python_version))
    runtime = DOCKER_DIR / service / "groups" / group / "__norfab__"
    (runtime / "artifacts").mkdir(parents=True, exist_ok=True)
    container_name = f"norfab-tests-netbox-{group}-{uuid4().hex[:8]}"
    return _run_suite(
        "netbox",
        selector=NETBOX_TEST_GROUPS[group],
        marker="netbox",
        python_version=python_version,
        runtime=runtime,
        junit_name=f"{group}-junit.xml",
        container_name=container_name,
    )


def _run_netbox_groups(build=False, python_version=""):
    """Run each NetBox test file in its own concurrent Compose container."""
    service = SUITES["netbox"][0]
    if build:
        _run(_compose() + ["build", service], env=_environment(python_version))

    def run_group(group):
        return group, _run_netbox_group(group, python_version=python_version)

    print(
        f"Running {len(NETBOX_TEST_GROUPS)} NetBox test-file containers concurrently",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=len(NETBOX_TEST_GROUPS)) as executor:
        results = list(executor.map(run_group, NETBOX_TEST_GROUPS))

    print("NetBox test-file results:")
    for group, return_code in results:
        status = "passed" if return_code == 0 else f"failed (status {return_code})"
        print(f"  {group}: {status}")
    return max((return_code for _group, return_code in results), default=0)


def _netbox_group_task(group):
    """Create an Invoke task for one NetBox test-module Docker runner."""

    @task(
        help={
            "build": "Build the NetBox runner image before testing.",
            "python_version": "Docker runner Python version.",
        }
    )
    def run(_context, build=False, python_version=""):
        started_at = datetime.now().astimezone()
        previous_junit = _junit_snapshot()
        return_code = _run_netbox_group(group, build, python_version)
        _write_docker_test_report(
            [("netbox", return_code)],
            previous_junit,
            started_at,
            python_version,
            report_name=f"docker-tests-netbox-{group}",
            invocation={"Selector": NETBOX_TEST_GROUPS[group]},
        )
        if return_code:
            print(
                f"Docker NetBox group {group} exited with status "
                f"{return_code} (ignored)"
            )

    run.__doc__ = f"Run test_{group}.py in a dedicated NetBox container."
    return run


def _junit_snapshot():
    """Return modification signatures for existing Docker JUnit artifacts."""
    return {
        path.resolve(): (path.stat().st_mtime_ns, path.stat().st_size)
        for path in DOCKER_DIR.glob("*-tests/**/artifacts/*-junit.xml")
    }


def _markdown_cell(value):
    """Escape text for use in a Markdown table cell."""
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _write_docker_test_report(
    results,
    previous_junit,
    started_at,
    python_version,
    report_name="docker-tests-all",
    invocation=None,
):
    """Write a consolidated Markdown report from JUnit files changed this run."""
    report_suites = tuple(suite for suite, _return_code in results)
    report_data = {}
    for suite, return_code in results:
        service = SUITES[suite][0]
        junit_files = []
        for path in (DOCKER_DIR / service).glob("**/artifacts/*-junit.xml"):
            resolved = path.resolve()
            signature = (path.stat().st_mtime_ns, path.stat().st_size)
            if previous_junit.get(resolved) != signature:
                junit_files.append(path)

        counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
        duration = 0.0
        failures = []
        parse_errors = []
        for junit_file in sorted(junit_files):
            try:
                root = ElementTree.parse(junit_file).getroot()
            except (ElementTree.ParseError, OSError) as exc:
                parse_errors.append(f"{junit_file.relative_to(DOCKER_DIR)}: {exc}")
                continue
            for testcase in root.iter("testcase"):
                duration += float(testcase.get("time", 0) or 0)
                failure = testcase.find("failure")
                error = testcase.find("error")
                skipped = testcase.find("skipped")
                if failure is not None:
                    counts["failed"] += 1
                    problem = failure
                elif error is not None:
                    counts["errors"] += 1
                    problem = error
                elif skipped is not None:
                    counts["skipped"] += 1
                    continue
                else:
                    counts["passed"] += 1
                    continue
                test_name = "::".join(
                    part
                    for part in (testcase.get("classname"), testcase.get("name"))
                    if part
                )
                details = (problem.text or problem.get("message") or "").strip()
                failures.append((test_name or "unknown test", details))

        report_data[suite] = {
            "return_code": return_code,
            "junit_files": junit_files,
            "counts": counts,
            "duration": duration,
            "failures": failures,
            "parse_errors": parse_errors,
        }

    completed_at = datetime.now().astimezone()
    total_duration = sum(item["duration"] for item in report_data.values())
    totals = {
        key: sum(item["counts"][key] for item in report_data.values())
        for key in ("passed", "failed", "errors", "skipped")
    }
    lines = [
        "# Docker Test Report",
        "",
        f"- Started: {started_at.isoformat(timespec='seconds')}",
        f"- Completed: {completed_at.isoformat(timespec='seconds')}",
        f"- Python runner: {python_version or 'Compose default'}",
        f"- JUnit test duration: {total_duration:.2f}s",
    ]
    if invocation:
        lines.extend(
            f"- {label}: `{_markdown_cell(value)}`"
            for label, value in invocation.items()
            if value not in (None, "", False, 0)
        )
    lines += [
        "",
        "| Suite | Passed | Failed | Errors | Skipped | Duration | Status |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for suite in report_suites:
        item = report_data[suite]
        counts = item["counts"]
        if not item["junit_files"]:
            status = f"NO REPORT (container status {item['return_code']})"
        elif item["parse_errors"]:
            status = f"INVALID REPORT (container status {item['return_code']})"
        elif item["return_code"] or counts["failed"] or counts["errors"]:
            status = f"FAIL (container status {item['return_code']})"
        else:
            status = "PASS"
        lines.append(
            f"| {_markdown_cell(suite)} | {counts['passed']} | {counts['failed']} | "
            f"{counts['errors']} | {counts['skipped']} | {item['duration']:.2f}s | "
            f"{_markdown_cell(status)} |"
        )
    lines += [
        "",
        f"**Total:** {totals['passed']} passed, {totals['failed']} failed, "
        f"{totals['errors']} errors, {totals['skipped']} skipped.",
    ]

    problems_found = False
    for suite in report_suites:
        item = report_data[suite]
        if not item["failures"] and not item["parse_errors"] and item["junit_files"]:
            continue
        if not problems_found:
            lines += ["", "## Failures and report problems"]
            problems_found = True
        lines += ["", f"### {suite}"]
        if not item["junit_files"]:
            lines += ["", "No JUnit XML file was produced for this run."]
        for parse_error in item["parse_errors"]:
            lines += ["", f"Could not parse `{parse_error}`."]
        for test_name, details in item["failures"]:
            lines += ["", f"#### `{test_name}`"]
            if details:
                lines += ["", "```text", details.replace("```", "` ` `"), "```"]

    lines += ["", "## JUnit artifacts"]
    for suite in report_suites:
        files = report_data[suite]["junit_files"]
        lines += ["", f"### {suite}"]
        if files:
            lines.extend(
                f"- `{path.relative_to(ROOT).as_posix()}`" for path in sorted(files)
            )
        else:
            lines.append("- No report generated")

    DOCKER_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = DOCKER_REPORTS_DIR / (
        f"{report_name}-{started_at.strftime('%Y%m%d-%H%M%S-%f')}.md"
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Docker test report: {report_path}", flush=True)
    return report_path


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
        started_at = datetime.now().astimezone()
        previous_junit = _junit_snapshot()
        if suite == "netbox" and not any(
            (selector, marker, keyword, pytest_args, parallel_runs)
        ):
            return_code = _run_netbox_groups(build, python_version)
        elif parallel_runs:
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
        _write_docker_test_report(
            [(suite, return_code)],
            previous_junit,
            started_at,
            python_version,
            report_name=f"docker-tests-{suite}",
            invocation={
                "Selector": selector
                or _suite_test_root(suite).relative_to(ROOT).as_posix(),
                "Marker": marker or SUITES[suite][1],
                "Keyword": keyword,
                "Pytest arguments": pytest_args,
                "Parallel runs": parallel_runs,
            },
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
        "build": "Build runner images before testing.",
        "python_version": "Docker runner Python version.",
        "parallel_runs": "Maximum concurrent per-file test containers.",
    },
)
def docker_tests_all(
    _context,
    build=False,
    python_version="",
    parallel_runs=0,
):
    """Run Docker suites concurrently, excluding special-purpose runners."""
    started_at = datetime.now().astimezone()
    previous_junit = _junit_snapshot()
    if build:
        services = [SUITES[suite][0] for suite in ALL_SUITES]
        _run(_compose() + ["build", *services], env=_environment(python_version))

    def run_suite(suite):
        if suite == "netbox" and not parallel_runs:
            return_code = _run_netbox_groups(python_version=python_version)
        elif parallel_runs:
            return_code = _run_suite_parallel(
                suite,
                python_version=python_version,
                parallel_runs=parallel_runs,
            )
        else:
            return_code = _run_suite(suite, python_version=python_version)
        return suite, return_code

    # Unlike individual suite tasks, the aggregate retains each status and
    # ultimately fails so it remains suitable for a full validation run.
    print(
        f"Running {len(ALL_SUITES)} Docker test suites concurrently: "
        f"{', '.join(ALL_SUITES)}",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=len(ALL_SUITES)) as executor:
        results = list(executor.map(run_suite, ALL_SUITES))

    failures = [suite for suite, return_code in results if return_code]
    print("Docker all-suites results:")
    for suite, return_code in results:
        status = "passed" if return_code == 0 else f"failed (status {return_code})"
        print(f"  {suite}: {status}")
    _write_docker_test_report(results, previous_junit, started_at, python_version)
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


@task(
    name="docker-profile-idle",
    help={
        "duration": "Total profiling period in seconds (default: 600).",
        "interval": "Seconds between Docker stats samples.",
        "warmup": "Initial seconds excluded from stability checks.",
        "max_cpu_average": "Maximum stable average CPU percentage.",
        "max_cpu_p95": "Maximum stable p95 CPU percentage.",
        "max_memory_growth_mb": "Maximum stable memory growth in MiB.",
        "max_write_growth_mb": "Maximum stable block-write growth in MiB.",
        "build": "Build the idle profiling image before starting.",
        "fail_unstable": "Return a failure status when thresholds are exceeded.",
    },
)
def docker_profile_idle(
    _context,
    duration=600,
    interval=5,
    warmup=30,
    max_cpu_average=10.0,
    max_cpu_p95=20.0,
    max_memory_growth_mb=32.0,
    max_write_growth_mb=10.0,
    build=False,
    fail_unstable=False,
):
    """Profile an idle NorFab container and report resource stability."""
    duration = float(duration)
    interval = float(interval)
    warmup = float(warmup)
    if duration <= 0 or interval <= 0:
        raise ValueError("--duration and --interval must be greater than zero")
    if warmup < 0 or warmup >= duration:
        raise ValueError("--warmup must be non-negative and shorter than --duration")

    runtime = _prepare_runtime(IDLE_PROFILE_SERVICE)
    artifact = runtime / "artifacts" / "idle-profile.csv"
    compose = _compose()
    up_args = compose + ["up", "-d"]
    if build:
        up_args.append("--build")
    up_args.append(IDLE_PROFILE_SERVICE)

    samples = []
    try:
        _run(up_args)
        ps_result = subprocess.run(
            compose + ["ps", "-q", IDLE_PROFILE_SERVICE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        container_id = ps_result.stdout.strip()
        if ps_result.returncode or not container_id:
            _run(compose + ["logs", IDLE_PROFILE_SERVICE], check=False)
            raise Exit("Idle NorFab container did not remain running", code=1)

        print(
            f"Profiling {IDLE_PROFILE_SERVICE} for {duration:g}s every "
            f"{interval:g}s ({warmup:g}s warm-up)",
            flush=True,
        )
        started = time.monotonic()
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= duration:
                break
            sample = _docker_stats(container_id)
            sample["elapsed_seconds"] = round(elapsed, 3)
            sample["included"] = elapsed >= warmup
            samples.append(sample)
            remaining = duration - (time.monotonic() - started)
            if remaining > 0:
                time.sleep(min(interval, remaining))
    finally:
        _run(compose + ["rm", "-f", "-s", IDLE_PROFILE_SERVICE], check=False)

    measured = [sample for sample in samples if sample["included"]]
    if not measured:
        raise Exit("Profiling completed without any post-warm-up samples", code=1)

    with artifact.open("w", newline="", encoding="utf-8") as profile_file:
        writer = csv.DictWriter(profile_file, fieldnames=samples[0].keys())
        writer.writeheader()
        writer.writerows(samples)

    cpu_values = [sample["cpu_percent"] for sample in measured]
    memory_growth = max(0, measured[-1]["memory_bytes"] - measured[0]["memory_bytes"])
    read_growth = max(
        0, measured[-1]["block_read_bytes"] - measured[0]["block_read_bytes"]
    )
    write_growth = max(
        0, measured[-1]["block_write_bytes"] - measured[0]["block_write_bytes"]
    )
    cpu_average = sum(cpu_values) / len(cpu_values)
    cpu_p95 = _percentile(cpu_values, 0.95)
    stable = all(
        (
            cpu_average <= float(max_cpu_average),
            cpu_p95 <= float(max_cpu_p95),
            memory_growth <= float(max_memory_growth_mb) * 1_048_576,
            write_growth <= float(max_write_growth_mb) * 1_048_576,
        )
    )
    mib = 1_048_576
    print(f"NorFab idle profile: {'STABLE' if stable else 'UNSTABLE'}")
    print(
        f"  CPU: average {cpu_average:.2f}%, p95 {cpu_p95:.2f}%, "
        f"peak {max(cpu_values):.2f}%"
    )
    print(
        f"  Memory: start {measured[0]['memory_bytes'] / mib:.1f} MiB, "
        f"peak {max(item['memory_bytes'] for item in measured) / mib:.1f} MiB, "
        f"growth {memory_growth / mib:.1f} MiB"
    )
    print(
        f"  Block I/O growth: read {read_growth / mib:.2f} MiB, "
        f"write {write_growth / mib:.2f} MiB"
    )
    print(f"  Samples: {len(measured)}; CSV: {artifact}")
    if not stable:
        print(
            "  Limits: "
            f"CPU average {float(max_cpu_average):.2f}%, "
            f"CPU p95 {float(max_cpu_p95):.2f}%, "
            f"memory growth {float(max_memory_growth_mb):.1f} MiB, "
            f"write growth {float(max_write_growth_mb):.1f} MiB"
        )
        if fail_unstable:
            raise Exit("NorFab idle resource profile exceeded stability limits", code=1)


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
    docker_profile_idle,
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

# Register task-level NetBox runners such as
# ``docker-tests-netbox-sync-bgp-peerings``. They reuse the Compose service
# image but run in explicitly named, dedicated containers and runtime folders.
for group_name in NETBOX_TEST_GROUPS:
    namespace.add_task(
        _netbox_group_task(group_name),
        name=f"docker-tests-netbox-{group_name}",
    )

ns = namespace
