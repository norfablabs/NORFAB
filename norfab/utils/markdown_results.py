import json
from mdutils import MdUtils


def markdown_results(data: dict, service: str, task: str, kwargs: dict = None):
    kwargs = kwargs or {}
    if service == "nornir" and task == "test":
        return nornir_test_markdown(data, kwargs)
    else:
        return generic_markdown(data, kwargs)


def generic_markdown(data: dict, kwargs: dict = None):
    """
    Convert generic task results to markdown format with per-worker sections.
    """
    kwargs = kwargs or {}
    results = data.get("result_data", {})

    # Markdown generator
    md = MdUtils(file_name="task_results")

    # Extract service and task from first worker result for header
    service = "Unknown"
    task = "Unknown"

    # Process each worker's results
    if not results:
        md.new_paragraph(f"No results available: {data}")
        return md.file_data_text

    # Add main header
    first_worker = next(iter(results.values()))
    service = first_worker.get("service", "Unknown").title()
    task = first_worker.get("task", "Unknown").split(":")[-1].replace("_", " ").title()
    md.new_header(level=1, title=f"{service} service {task} results")

    # Add overall summary section
    md.new_header(level=2, title="Overall Summary")
    overall_status = data.get("status", "Unknown")
    status_indicator = "✅ Good" if overall_status == "COMPLETED" else "⚠️ Check Status"
    errors = data["errors"]
    workers_requested = data["workers_requested"]
    workers_completed = ", ".join(data["workers_completed"])
    workers_dispatched = ", ".join(data["workers_dispatched"])
    workers_pending = ", ".join(data["workers_started"])
    summary_text = (
        f"- **Overall Status:** {overall_status} {status_indicator}\n"
        f"- **Errors:** {len(errors)} error(s)\n"
        f"- **Workers Count:** {len(data['workers_dispatched'])}\n"
        f"- **Workers Requested:** {workers_requested}\n"
        f"- **Workers Done:** {workers_completed}\n"
        f"- **Workers Dispatched:** {workers_dispatched}\n"
        f"- **Workers Pending:** {workers_pending}\n"
        f"- **Error Details:** {', '.join(errors)}\n"
    )
    md.new_paragraph(summary_text)

    for worker_name, worker_data in results.items():
        # Create worker section header
        md.new_header(level=2, title=f"Worker: {worker_name}")

        # Prepare summary bullet points
        failed = worker_data.get("failed", False)
        status = worker_data.get("status", "Unknown")
        task_name = worker_data.get("task", "N/A")
        errors = worker_data.get("errors", [])
        messages = worker_data.get("messages", [])
        task_started = worker_data.get("task_started", "N/A")
        task_completed = worker_data.get("task_completed", "N/A")
        dry_run = worker_data.get("dry_run", False)

        # Create summary section with bullet points
        md.new_header(level=3, title="Summary")
        summary_text = (
            f"- **Task:** {task_name}\n"
            f"- **Status:** {status}\n"
            f"- **Failed:** {'❌ Yes' if failed else '✅ No'}\n"
            f"- **Started:** {task_started}\n"
            f"- **Completed:** {task_completed}\n"
            f"- **Dry Run:** {'Yes' if dry_run else 'No'}\n"
            f"- **Errors:** {', '.join(errors)}\n"
            f"- **Messages:** {', '.join(messages)}\n"
        )
        md.new_paragraph(summary_text)

        # Add results section as collapsible code block
        md.new_header(level=3, title="Results")
        result_data = worker_data.get("result", {})
        if result_data:
            results_json = json.dumps(result_data, indent=2, default=str)
            md.new_line(
                f"<details>\n"
                f"<summary>Click to expand results</summary>\n\n"
                f"```json\n{results_json}\n```\n\n"
                f"</details>\n"
            )
        else:
            md.new_paragraph("No results data available.")

    # Add debug section
    md.new_header(level=2, title="Debug Information")
    md.new_paragraph(
        "This section contains detailed debugging information for troubleshooting and inspection."
    )

    debug_html = (
        f"<details>\n"
        f"<summary>Input Arguments (kwargs)</summary>\n\n"
        f"```json\n{json.dumps(kwargs, indent=2, default=str)}\n```\n\n"
        f"</details>\n\n"
        f"<details>\n"
        f"<summary>Complete Results (JSON)</summary>\n\n"
        f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n\n"
        f"</details>\n"
    )
    md.new_line(debug_html)

    return md.file_data_text


def nornir_test_markdown(data: dict, kwargs: dict = None):
    """
    Convert Nornir test task results to markdown format.
    """
    results = data.get("result_data", {})

    # Unified hosts test results dictionary structure:
    # {
    #     "hostname": {
    #         "suite": {...},           # Test suite definitions
    #         "commands": [...],        # Command outputs
    #         "results": [...],         # Test results
    #     }
    # }
    hosts_tests_results = {}

    # Table data collection
    table_text = [
        "#",
        "Host",
        "Test Name",
        "Result",
        "Exception",
    ]  # Header row for summary table
    total_rows = 1  # Counter for total table rows (includes header)
    table_rows = []  # List to collect and sort table rows

    # HTML output buffers
    tests_details_html = ""  # HTML for hierarchical tests details section
    devices_commands_output_html = ""  # HTML for device command outputs section
    debug_html = ""  # HTML for debug section with kwargs and raw data
    hosts_test_suites_html = ""  # HTML for test suite definitions per host

    # Markdown generator
    md = MdUtils(file_name="nornir_test_results")

    if not results:
        md.new_paragraph("No results available.")
        return md.file_data_text

    # Process each worker's results and populate hosts_tests_results
    for worker_name, worker_data in results.items():
        worker_result = worker_data["result"]
        # Handle detailed result format (extensive=True)
        test_suite = worker_result.get("suite", {})
        test_results_list = worker_result.get("test_results", [])
        if test_results_list:
            for test_result in test_results_list:
                host = test_result.get("host", "unknown")
                name = test_result.get("name", "N/A")
                result = test_result.get("result", "N/A")
                exception = test_result.get("exception", "")
                hosts_tests_results.setdefault(
                    host, {"suite": {}, "commands": [], "results": []}
                )

                # Determine if this is a test result or command output
                # Test results have 'test' field and `success` field
                is_test_result = "success" in test_result and "test" in test_result

                # Only add test results to table
                if is_test_result:
                    status_icon = "✅ PASS" if result == "PASS" else "❌ FAIL"
                    table_rows.append([host, name, status_icon, exception or ""])
                    total_rows += 1
                    hosts_tests_results[host]["results"].append(test_result)
                # Store command outputs (non-test results)
                else:
                    hosts_tests_results[host]["commands"].append(test_result)
        # Store suite info
        if test_suite:
            for host, suite_tests in test_suite.items():
                hosts_tests_results.setdefault(
                    host, {"suite": {}, "commands": [], "results": []}
                )
                hosts_tests_results[host]["suite"] = suite_tests
        # Handle brief result format (extensive=False)
        if not all(k in worker_result for k in ["suite", "test_results"]):
            for device, tests in worker_result.items():
                for test_name, status in tests.items():
                    status_icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
                    table_rows.append([device, test_name, status_icon, ""])
                    total_rows += 1

    # Prepare table data
    if total_rows > 1:
        # Sort table rows by host name, then by test name
        table_rows.sort(key=lambda x: (x[0], x[1]))
        # Rebuild table_text with sorted rows
        for index, row in enumerate(table_rows, start=1):
            row.insert(0, index)
            table_text.extend(row)

    # Prepare Tests HTMLs
    if hosts_tests_results:
        for host in sorted(hosts_tests_results.keys()):
            host_results = hosts_tests_results[host]["results"]
            host_commands = hosts_tests_results[host]["commands"]
            host_suite = hosts_tests_results[host]["suite"]

            # Create hierarchical structure: Host > Test Name > Details
            if host_results:
                passed = sum(1 for test in host_results if test.get("result") == "PASS")
                failed = sum(1 for test in host_results if test.get("result") == "FAIL")

                tests_details_html += (
                    f'<details style="margin-left:20px;">\n'
                    f"<summary>{host} ({len(host_results)} tests, {passed} pass, {failed} fail)</summary>\n\n"
                )

                for test in sorted(host_results, key=lambda x: x.get("name", "")):
                    name = test.get("name", "N/A")
                    result = test.get("result", "N/A")
                    status_icon = "✅ PASS" if result == "PASS" else "❌ FAIL"

                    tests_details_html += (
                        f'<details style="margin-left:40px;">\n'
                        f"<summary>{name} {status_icon}</summary>\n\n"
                        f"- **Result:** {result}\n"
                        f"- **Criteria:** {test.get('criteria', 'N/A')}\n"
                        f"- **Exception:** {test.get('exception', 'N/A')}\n"
                        f"- **Task:** {test.get('task', 'N/A')}\n"
                        f"- **Test:** {test.get('test', 'N/A')}\n"
                        f"- **Success:** {test.get('success', 'N/A')}\n"
                        f"- **Failed:** {test.get('failed', 'N/A')}\n"
                        f"- **Changed:** {test.get('changed', 'N/A')}\n\n"
                        f"- **Comments:** {test.get('Comments', 'N/A')}\n\n"
                        f"</details>\n\n"
                    )

                tests_details_html += "</details>\n\n"

            # Prepare Device Output HTML
            if host_commands:
                cmds_html = ""
                for cmd in host_commands:
                    cmd_name = cmd.get("name", "Command")
                    cmd_output = str(cmd.get("result", ""))
                    cmds_html += (
                        f'<details style="margin-left:40px;">\n'
                        f"<summary>{host} - '{cmd_name}'</summary>\n\n"
                        f"```\n{cmd_output}\n```\n\n"
                        f"</details>\n"
                    )

                devices_commands_output_html += (
                    f'<details style="margin-left:20px;">\n'
                    f"<summary>{host} ({len(host_commands)} commands collected)</summary>\n\n"
                    f"{cmds_html}"
                    f"</details>\n\n"
                )

            # Prepare Test Suites HTML if available
            if host_suite:
                if not hosts_test_suites_html:
                    hosts_test_suites_html += (
                        '\n<details style="margin-left:20px;">\n'
                        "<summary>Test suites definitions for each host</summary>\n\n"
                    )
                suite_json = json.dumps(host_suite, indent=2)
                hosts_test_suites_html += (
                    f'<details style="margin-left:40px;">\n'
                    f"<summary>{host} ({len(host_suite)} tests)</summary>\n\n"
                    f"```json\n{suite_json}\n```\n\n"
                    f"</details>\n"
                )

        # complete Test Suites HTML section
        if hosts_test_suites_html:
            hosts_test_suites_html += "\n</details>\n"

    # Prepare Debug section HTML
    debug_html = (
        f'<details style="margin-left:20px;">\n'
        f"<summary>Input Arguments (kwargs)</summary>\n\n"
        f"```json\n{json.dumps(kwargs, indent=2, default=str)}\n```\n\n"
        f"</details>\n\n"
        f'<details style="margin-left:20px;">\n'
        f"<summary>Complete Results (JSON)</summary>\n\n"
        f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n\n"
        f"</details>\n"
    )

    # ==================== MD OUTPUT SECTION ====================

    # Add main header
    md.new_header(level=1, title="Tests Execution Report")

    # Tests Summary section
    md.new_header(level=2, title="Summary")
    if total_rows > 1:
        md.new_paragraph(f"Total tests completed - {total_rows - 1}\n\n")
        md.new_table(columns=5, rows=total_rows, text=table_text, text_align="left")
    else:
        md.new_paragraph("❌ Failed to produce summary results.\n\n")

    # Tests Details section
    md.new_header(level=2, title="Tests Details")
    if tests_details_html:
        md.new_paragraph(
            "Hierarchical expandable sections organized by device, then test name, containing complete test result details."
        )
        md.new_line(tests_details_html)
    else:
        md.new_paragraph(
            "❌ No detailed results available. Set `extensive` to `True` in input kwargs arguments.\n\n"
        )

    # Device Output section
    md.new_header(level=2, title="Device Outputs")
    if devices_commands_output_html:
        md.new_paragraph(
            "Expandable sections containing outputs collected during test execution for each host."
        )
        md.new_line(devices_commands_output_html)
    else:
        md.new_paragraph(
            "❌ No hosts outputs available. Set `extensive` to `True` in input kwargs arguments.\n\n"
        )

    # Debug section
    md.new_header(level=2, title="Debug")
    md.new_paragraph(
        "This section contains detailed debugging information for troubleshooting and inspection. Includes input arguments and complete raw results data used to produce sections above."
    )
    # Test Suites section (if available)
    if hosts_test_suites_html:
        md.new_line(hosts_test_suites_html)
    else:
        md.new_paragraph(
            "❌ No hosts test suites available. Set `extensive` to `True` in input kwargs arguments.\n\n"
        )
    # Debug details section
    md.new_line(debug_html)

    return md.file_data_text
