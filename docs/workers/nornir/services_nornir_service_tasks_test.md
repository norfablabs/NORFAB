---
tags:
  - nornir
---

# Nornir Service Test Task

> task api name: `test`

The Nornir Service `test` task designed to facilitate the execution of network tests. This task provides network operations engineers and network automation developers with tools to validate network configurations, ensure compliance, and monitor network performance. By leveraging the capabilities of the Nornir service, users can automate testing process, identify issues proactively, and maintain a robust network infrastructure.

Nornir service `test` task uses Nornir [TestsProcessor](https://nornir-salt.readthedocs.io/en/latest/Processors/TestsProcessor.html) to run the tests and support test suites definition in YAML format, where test suite YAML files can be stored on and sourced from broker.

## Nornir Test Sample Usage

Nornir service `test` task uses suites in YAML format to define tests, sample tests suite:

``` yaml title="suite_3.txt"
- name: Check ceos version
  task: "show version"
  test: contains
  pattern: "4.30.0F"
- name: Check NTP status
  test: ncontains
  pattern: "unsynchronised"
  task: "show ntp status"
- name: Check Mgmt Interface Status
  test: contains
  pattern: "is up, line protocol is up"
  task: "show interface management0" 
```

File `suite_3.txt` stored on broker and downloaded by Nornir service prior to running tests, below is an example of how to run the tests suite.

!!! example

    === "CLI"
    
        ```
        C:\nf>nfcli
        Welcome to NorFab Interactive Shell.
        nf#
        nf#nornir
        nf[nornir-test]#
        nf[nornir-test]#suite nf://nornir_test_suites/suite_3.txt FC spine,leaf
        --------------------------------------------- Job Events -----------------------------------------------
        07-Jan-2025 18:44:35 0c3309c54ee44397b055257a0d442e62 job started
        07-Jan-2025 18:44:35.207 nornir nornir-worker-1 ceos-spine-1, ceos-spine-2 task started - 'netmiko_send_commands'
        07-Jan-2025 18:44:35.211 nornir nornir-worker-2 ceos-leaf-1, ceos-leaf-2, ceos-leaf-3 task started - 'netmiko_send_commands'
        <omitted for brevity>
        07-Jan-2025 18:44:36 0c3309c54ee44397b055257a0d442e62 job completed in 1.391 seconds

        --------------------------------------------- Job Results --------------------------------------------

        +----+--------------+-----------------------------+----------+-------------------+
        |    | host         | name                        | result   | exception         |
        +====+==============+=============================+==========+===================+
        |  0 | ceos-leaf-1  | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  1 | ceos-leaf-1  | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        |  2 | ceos-leaf-1  | Check Mgmt Interface Status | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  3 | ceos-leaf-2  | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  4 | ceos-leaf-2  | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        |  5 | ceos-leaf-2  | Check Mgmt Interface Status | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  6 | ceos-leaf-3  | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  7 | ceos-leaf-3  | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        |  8 | ceos-leaf-3  | Check Mgmt Interface Status | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        |  9 | ceos-spine-1 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 10 | ceos-spine-1 | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 13 | ceos-spine-2 | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 12 | ceos-spine-2 | Check ceos version          | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        | 13 | ceos-spine-2 | Check NTP status            | FAIL     | Pattern in output |
        +----+--------------+-----------------------------+----------+-------------------+
        | 14 | ceos-spine-2 | Check Mgmt Interface Status | PASS     |                   |
        +----+--------------+-----------------------------+----------+-------------------+
        nf[nornir-test]#
        nf[nornir-test]#top
        nf#
        ```
        
        Demo
		
		  ![Nornir Cli Demo](../../images/nornir_test_demo.gif)
    
        In this example:

        - `nfcli` command starts the NorFab Interactive Shell.
        - `nornir` command switches to the Nornir sub-shell.
        - `test` command switches to the `test` task sub-shell.
        - `suite` argument refers to a path for `suite_3.txt` file with a set of tests to run. 
        - Devices filtered using `FC` - "Filter Contains" Nornir hosts targeting filter to only run tests on devices that contain `spine` or `leaf` in their hostname.
		
        `inventory.yaml` should be located in same folder where we start nfcli, unless `nfcli -i path_to_inventory.yaml` flag used. Refer to [Getting Started](../../norfab_getting_started.md) section on how to construct  `inventory.yaml` file
		
    === "Python"
    
        This code is complete and can run as is
		
        ```
        import pprint
        
        from norfab.core.nfapi import NorFab
        
        if __name__ == '__main__':
            nf = NorFab(inventory="inventory.yaml")
            nf.start()
            
            client = nf.make_client()
            
            res = client.run_job(
                service="nornir",
                task="test",
                kwargs={
                    "suite": "nf://nornir_test_suites/suite_3.txt",
                    "FC": "spine,leaf"          
                }
            )
            
            pprint.pprint(res)
            
            nf.destroy()
        ```

        Refer to [Getting Started](../../norfab_getting_started.md) section on how to construct  `inventory.yaml` file.

## Formatting Tests Output

NorFab interactive shell allows you to format the results of network tests into text tables. This is particularly useful for presenting test results in a clear and organized manner, making it easier to analyze and interpret the data. The NorFab interactive shell supports the `table` command, which relies on the [tabulate](https://pypi.org/project/tabulate/) module to generate text tables. By outputting test results in table format, you can quickly identify issues and take appropriate action.

## Markdown Results Output (client.run_job)

NorFab Python client can return Nornir `test` results as a **Markdown report** by passing `markdown=True` to `client.run_job(...)`.

This is convenient when you want to:

- Save results into a `.md` file
- Post results into ticketing systems / chat tools
- Render results in a UI (for example, using a Markdown renderer such as Markwon)

The content of the report depends on the `extensive` keyword in `kwargs`:

- `extensive=False` (default) produces a summary table and debug section, without per-test details and command outputs.
- `extensive=True` includes hierarchical per-host test details, device command outputs, devices inventory, and test suite definitions.

!!! example "Python: Markdown report (brief)"

    Sample python script that produces brief markdown tests report:

    ```python
    from norfab.core.nfapi import NorFab


    if __name__ == "__main__":
        nf = NorFab(inventory="inventory.yaml")
        nf.start()

        client = nf.make_client()

        report_md = client.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
            },
            markdown=True,
        )

        print(report_md)

        nf.destroy()
    ```

    <details>
    <summary>Sample output (extensive=False)</summary>

    ````markdown
    # Tests Execution Report

    ## Summary


    High-level table with all test results.
    |Host|Test Name|Result|Exception|
    | :--- | :--- | :--- | :--- |
    |ceos-leaf-1|check NTP status|❌ FAIL||
    |ceos-leaf-1|check ceos version|✅ PASS||
    |ceos-leaf-2|check NTP status|❌ FAIL||
    |ceos-leaf-2|check ceos version|✅ PASS||
    |ceos-leaf-3|check NTP status|❌ FAIL||
    |ceos-leaf-3|check ceos version|✅ PASS||
    |ceos-spine-1|check NTP status|❌ FAIL||
    |ceos-spine-1|check ceos version|✅ PASS||
    |ceos-spine-2|check NTP status|❌ FAIL||
    |ceos-spine-2|check ceos version|✅ PASS||

    ## Tests Details


    ❌ No detailed results available. Set `extensive` to `True` in input kwargs arguments.


    ## Device Outputs


    ❌ No hosts outputs available. Set `extensive` to `True` in input kwargs arguments.


    ## Debug


    This section contains detailed debugging information for troubleshooting and inspection. Includes input arguments and complete raw results data used to produce sections above.

    ❌ No hosts inventory available. Set `extensive` to `True` in input kwargs arguments.



    ❌ No hosts test suites available. Set `extensive` to `True` in input kwargs arguments.


    <details style="margin-left:20px;">
    <summary>Input Arguments (kwargs)</summary>

    ```json
    {
      "suite": "nf://nornir_test_suites/suite_1.txt",
      "FC": [
        "spine",
        "leaf"
      ]
    }
    ```

    </details>

    <details style="margin-left:20px;">
    <summary>Complete Results (JSON)</summary>

    ```json
    {
      "status": "202",
      "results": {
        "nornir-worker-5": {
          "result": {},
          "failed": false,
          "errors": [],
          "task": "nornir-worker-5:test",
          "messages": [
            "nornir-worker-5 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "6dab68539bc3410d850a78b4fe3c4300",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:12:21 2026",
          "task_completed": "Fri Jan  2 18:12:21 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-6": {
          "result": {},
          "failed": false,
          "errors": [],
          "task": "nornir-worker-6:test",
          "messages": [
            "nornir-worker-6 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "6dab68539bc3410d850a78b4fe3c4300",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:12:21 2026",
          "task_completed": "Fri Jan  2 18:12:21 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-4": {
          "result": {},
          "failed": false,
          "errors": [],
          "task": "nornir-worker-4:test",
          "messages": [
            "nornir-worker-4 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "6dab68539bc3410d850a78b4fe3c4300",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:12:21 2026",
          "task_completed": "Fri Jan  2 18:12:21 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-2": {
          "result": {
            "ceos-leaf-2": {
              "check ceos version": "PASS",
              "check NTP status": "FAIL"
            },
            "ceos-leaf-3": {
              "check ceos version": "PASS",
              "check NTP status": "FAIL"
            },
            "ceos-leaf-1": {
              "check ceos version": "PASS",
              "check NTP status": "FAIL"
            }
          },
          "failed": true,
          "errors": [],
          "task": "nornir-worker-2:test",
          "messages": [],
          "juuid": "6dab68539bc3410d850a78b4fe3c4300",
          "resources": [],
          "status": "completed",
          "task_started": "Fri Jan  2 18:12:21 2026",
          "task_completed": "Fri Jan  2 18:12:22 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-1": {
          "result": {
            "ceos-spine-1": {
              "check ceos version": "PASS",
              "check NTP status": "FAIL"
            },
            "ceos-spine-2": {
              "check ceos version": "PASS",
              "check NTP status": "FAIL"
            }
          },
          "failed": true,
          "errors": [],
          "task": "nornir-worker-1:test",
          "messages": [],
          "juuid": "6dab68539bc3410d850a78b4fe3c4300",
          "resources": [],
          "status": "completed",
          "task_started": "Fri Jan  2 18:12:21 2026",
          "task_completed": "Fri Jan  2 18:12:22 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        }
      },
      "errors": [],
      "workers": {
        "requested": [
          "nornir-worker-5",
          "nornir-worker-6",
          "nornir-worker-4",
          "nornir-worker-1",
          "nornir-worker-2"
        ],
        "done": "{'nornir-worker-5', 'nornir-worker-6', 'nornir-worker-4', 'nornir-worker-1', 'nornir-worker-2'}",
        "dispatched": "{'nornir-worker-5', 'nornir-worker-6', 'nornir-worker-4', 'nornir-worker-1', 'nornir-worker-2'}",
        "pending": "set()"
      }
    }
    ```

    </details>
    ````

    </details>

!!! example "Python: Markdown report (extensive)"

    This example produces detailed markdown report:

    ```python
    from norfab.core.nfapi import NorFab


    if __name__ == "__main__":
        nf = NorFab(inventory="inventory.yaml")
        nf.start()

        client = nf.make_client()

        report_md = client.run_job(
            "nornir",
            "test",
            kwargs={
                "suite": "nf://nornir_test_suites/suite_1.txt",
                "FC": ["spine", "leaf"],
                "extensive": True,
            },
            markdown=True,
        )

        print(report_md)

        nf.destroy()
    ```

    <details>
    <summary>Sample output (extensive=True)</summary>

    ````markdown
    # Tests Execution Report

    ## Summary


    High-level table with all test results.
    |Host|Test Name|Result|Exception|
    | :--- | :--- | :--- | :--- |
    |ceos-leaf-1|check NTP status|❌ FAIL|Pattern not in output|
    |ceos-leaf-1|check ceos version|✅ PASS||
    |ceos-leaf-2|check NTP status|❌ FAIL|Pattern not in output|
    |ceos-leaf-2|check ceos version|✅ PASS||
    |ceos-leaf-3|check NTP status|❌ FAIL|Pattern not in output|
    |ceos-leaf-3|check ceos version|✅ PASS||
    |ceos-spine-1|check NTP status|❌ FAIL|Pattern not in output|
    |ceos-spine-1|check ceos version|✅ PASS||
    |ceos-spine-2|check NTP status|❌ FAIL|Pattern not in output|
    |ceos-spine-2|check ceos version|✅ PASS||

    ## Tests Details


    Hierarchical expandable sections organized by device, then test name, containing complete test result details.
    <details style="margin-left:20px;">
    <summary>ceos-leaf-1 (2 tests, ✅ 1 passed, ❌ 1 failed)</summary>

    <details style="margin-left:40px;">
    <summary>check NTP status ❌ FAIL</summary>

    - **Result:** FAIL
    - **Criteria:** 1.1.1.1
    - **Exception:** Pattern not in output
    - **Task:** show ntp associations
    - **Test:** contains_lines
    - **Success:** False
    - **Failed:** True
    - **Changed:** False

    - **Comments:** N/A

    </details>

    <details style="margin-left:40px;">
    <summary>check ceos version ✅ PASS</summary>

    - **Result:** PASS
    - **Criteria:** cEOS
    - **Exception:** None
    - **Task:** show version
    - **Test:** contains
    - **Success:** True
    - **Failed:** False
    - **Changed:** False

    - **Comments:** N/A

    </details>

    </details>

    <details style="margin-left:20px;">
    <summary>ceos-leaf-2 (2 tests, ✅ 1 passed, ❌ 1 failed)</summary>

    <details style="margin-left:40px;">
    <summary>check NTP status ❌ FAIL</summary>

    - **Result:** FAIL
    - **Criteria:** 1.1.1.1
    - **Exception:** Pattern not in output
    - **Task:** show ntp associations
    - **Test:** contains_lines
    - **Success:** False
    - **Failed:** True
    - **Changed:** False

    - **Comments:** N/A

    </details>

    <details style="margin-left:40px;">
    <summary>check ceos version ✅ PASS</summary>

    - **Result:** PASS
    - **Criteria:** cEOS
    - **Exception:** None
    - **Task:** show version
    - **Test:** contains
    - **Success:** True
    - **Failed:** False
    - **Changed:** False

    - **Comments:** N/A

    </details>

    </details>

    <details style="margin-left:20px;">
    <summary>ceos-leaf-3 (2 tests, ✅ 1 passed, ❌ 1 failed)</summary>

    <details style="margin-left:40px;">
    <summary>check NTP status ❌ FAIL</summary>

    - **Result:** FAIL
    - **Criteria:** 1.1.1.1
    - **Exception:** Pattern not in output
    - **Task:** show ntp associations
    - **Test:** contains_lines
    - **Success:** False
    - **Failed:** True
    - **Changed:** False

    - **Comments:** N/A

    </details>

    <details style="margin-left:40px;">
    <summary>check ceos version ✅ PASS</summary>

    - **Result:** PASS
    - **Criteria:** cEOS
    - **Exception:** None
    - **Task:** show version
    - **Test:** contains
    - **Success:** True
    - **Failed:** False
    - **Changed:** False

    - **Comments:** N/A

    </details>

    </details>

    <details style="margin-left:20px;">
    <summary>ceos-spine-1 (2 tests, ✅ 1 passed, ❌ 1 failed)</summary>

    <details style="margin-left:40px;">
    <summary>check NTP status ❌ FAIL</summary>

    - **Result:** FAIL
    - **Criteria:** 1.1.1.1
    - **Exception:** Pattern not in output
    - **Task:** show ntp associations
    - **Test:** contains_lines
    - **Success:** False
    - **Failed:** True
    - **Changed:** False

    - **Comments:** N/A

    </details>

    <details style="margin-left:40px;">
    <summary>check ceos version ✅ PASS</summary>

    - **Result:** PASS
    - **Criteria:** cEOS
    - **Exception:** None
    - **Task:** show version
    - **Test:** contains
    - **Success:** True
    - **Failed:** False
    - **Changed:** False

    - **Comments:** N/A

    </details>

    </details>

    <details style="margin-left:20px;">
    <summary>ceos-spine-2 (2 tests, ✅ 1 passed, ❌ 1 failed)</summary>

    <details style="margin-left:40px;">
    <summary>check NTP status ❌ FAIL</summary>

    - **Result:** FAIL
    - **Criteria:** 1.1.1.1
    - **Exception:** Pattern not in output
    - **Task:** show ntp associations
    - **Test:** contains_lines
    - **Success:** False
    - **Failed:** True
    - **Changed:** False

    - **Comments:** N/A

    </details>

    <details style="margin-left:40px;">
    <summary>check ceos version ✅ PASS</summary>

    - **Result:** PASS
    - **Criteria:** cEOS
    - **Exception:** None
    - **Task:** show version
    - **Test:** contains
    - **Success:** True
    - **Failed:** False
    - **Changed:** False

    - **Comments:** N/A

    </details>

    </details>


    ## Device Outputs


    Expandable sections containing outputs collected during test execution for each host.
    <details style="margin-left:20px;">
    <summary>ceos-leaf-1 (2 commands)</summary>

    <details style="margin-left:40px;">
    <summary>show version</summary>

    ```
    Arista cEOSLab
    Hardware version:
    Serial number: CA49F479A3A974B25CEC002E92F7450D
    Hardware MAC address: 001c.7372.ebcd
    System MAC address: 001c.7372.ebcd

    Software image version: 4.30.0F-31408673.4300F (engineering build)
    Architecture: x86_64
    Internal build version: 4.30.0F-31408673.4300F
    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
    Image format version: 1.0
    Image optimization: None

    cEOS tools version: (unknown)
    Kernel version: 5.15.0-164-generic

    Uptime: 1 hour and 32 minutes
    Total memory: 32827152 kB
    Free memory: 15965824 kB

    ```

    </details>
    <details style="margin-left:40px;">
    <summary>show ntp associations</summary>

    ```
    NTP is disabled.
         remote          refid      st t when  poll reach   delay   offset  jitter
    ==============================================================================
    ```

    </details>
    </details>

    <details style="margin-left:20px;">
    <summary>ceos-leaf-2 (2 commands)</summary>

    <details style="margin-left:40px;">
    <summary>show version</summary>

    ```
    Arista cEOSLab
    Hardware version:
    Serial number: 16921D773C3C0A23581B1260734452FF
    Hardware MAC address: 001c.7393.6e5d
    System MAC address: 001c.7393.6e5d

    Software image version: 4.30.0F-31408673.4300F (engineering build)
    Architecture: x86_64
    Internal build version: 4.30.0F-31408673.4300F
    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
    Image format version: 1.0
    Image optimization: None

    cEOS tools version: (unknown)
    Kernel version: 5.15.0-164-generic

    Uptime: 1 hour and 32 minutes
    Total memory: 32827152 kB
    Free memory: 15965824 kB

    ```

    </details>
    <details style="margin-left:40px;">
    <summary>show ntp associations</summary>

    ```
    NTP is disabled.
         remote          refid      st t when  poll reach   delay   offset  jitter
    ==============================================================================
    ```

    </details>
    </details>

    <details style="margin-left:20px;">
    <summary>ceos-leaf-3 (2 commands)</summary>

    <details style="margin-left:40px;">
    <summary>show version</summary>

    ```
    Arista cEOSLab
    Hardware version:
    Serial number: D03FE1DE81A401F1AAD67A4B15E096C8
    Hardware MAC address: 001c.73f3.053c
    System MAC address: 001c.73f3.053c

    Software image version: 4.30.0F-31408673.4300F (engineering build)
    Architecture: x86_64
    Internal build version: 4.30.0F-31408673.4300F
    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
    Image format version: 1.0
    Image optimization: None

    cEOS tools version: (unknown)
    Kernel version: 5.15.0-164-generic

    Uptime: 1 hour and 32 minutes
    Total memory: 32827152 kB
    Free memory: 15965824 kB

    ```

    </details>
    <details style="margin-left:40px;">
    <summary>show ntp associations</summary>

    ```
    NTP is disabled.
         remote          refid      st t when  poll reach   delay   offset  jitter
    ==============================================================================
    ```

    </details>
    </details>

    <details style="margin-left:20px;">
    <summary>ceos-spine-1 (2 commands)</summary>

    <details style="margin-left:40px;">
    <summary>show version</summary>

    ```
    Arista cEOSLab
    Hardware version:
    Serial number: C4889628D19280228439023C4F0C3EE4
    Hardware MAC address: 001c.73a9.7d04
    System MAC address: 001c.73a9.7d04

    Software image version: 4.30.0F-31408673.4300F (engineering build)
    Architecture: x86_64
    Internal build version: 4.30.0F-31408673.4300F
    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
    Image format version: 1.0
    Image optimization: None

    cEOS tools version: (unknown)
    Kernel version: 5.15.0-164-generic

    Uptime: 1 hour and 32 minutes
    Total memory: 32827152 kB
    Free memory: 15965824 kB

    ```

    </details>
    <details style="margin-left:40px;">
    <summary>show ntp associations</summary>

    ```
    NTP is disabled.
         remote          refid      st t when  poll reach   delay   offset  jitter
    ==============================================================================
    ```

    </details>
    </details>

    <details style="margin-left:20px;">
    <summary>ceos-spine-2 (2 commands)</summary>

    <details style="margin-left:40px;">
    <summary>show version</summary>

    ```
    Arista cEOSLab
    Hardware version:
    Serial number: F8B8101D77067B49C0437B3711AA1719
    Hardware MAC address: 001c.735c.3067
    System MAC address: 001c.735c.3067

    Software image version: 4.30.0F-31408673.4300F (engineering build)
    Architecture: x86_64
    Internal build version: 4.30.0F-31408673.4300F
    Internal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c
    Image format version: 1.0
    Image optimization: None

    cEOS tools version: (unknown)
    Kernel version: 5.15.0-164-generic

    Uptime: 1 hour and 32 minutes
    Total memory: 32827152 kB
    Free memory: 15965824 kB

    ```

    </details>
    <details style="margin-left:40px;">
    <summary>show ntp associations</summary>

    ```
    NTP is disabled.
         remote          refid      st t when  poll reach   delay   offset  jitter
    ==============================================================================
    ```

    </details>
    </details>


    ## Debug


    This section contains detailed debugging information for troubleshooting and inspection. Includes input arguments and complete raw results data used to produce sections above.
    <details style="margin-left:20px;">
    <summary>Devices Inventory</summary>

    <details style="margin-left:40px;">
    <summary>ceos-leaf-1</summary>

    ```json
    {
      "name": "ceos-leaf-1",
      "connection_options": {
        "scrapli_netconf": {
          "extras": null,
          "hostname": null,
          "port": 8302,
          "username": null,
          "password": null,
          "platform": null
        },
        "napalm": {
          "extras": {
            "optional_args": {
              "transport": "https",
              "port": 4402
            }
          },
          "hostname": null,
          "port": null,
          "username": null,
          "password": null,
          "platform": null
        },
        "ncclient": {
          "extras": null,
          "hostname": null,
          "port": 8302,
          "username": null,
          "password": null,
          "platform": null
        }
      },
      "groups": [
        "eos_params"
      ],
      "data": {},
      "hostname": "192.168.1.130",
      "port": 2202,
      "username": "admin",
      "password": "admin",
      "platform": "arista_eos"
    }
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-leaf-2</summary>

    ```json
    {
      "name": "ceos-leaf-2",
      "connection_options": {
        "scrapli_netconf": {
          "extras": null,
          "hostname": null,
          "port": 8303,
          "username": null,
          "password": null,
          "platform": null
        },
        "napalm": {
          "extras": {
            "optional_args": {
              "transport": "https",
              "port": 4403
            }
          },
          "hostname": null,
          "port": null,
          "username": null,
          "password": null,
          "platform": null
        },
        "ncclient": {
          "extras": null,
          "hostname": null,
          "port": 8303,
          "username": null,
          "password": null,
          "platform": null
        }
      },
      "groups": [
        "eos_params"
      ],
      "data": {},
      "hostname": "192.168.1.130",
      "port": 2203,
      "username": "admin",
      "password": "admin",
      "platform": "arista_eos"
    }
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-leaf-3</summary>

    ```json
    {
      "name": "ceos-leaf-3",
      "connection_options": {
        "scrapli_netconf": {
          "extras": null,
          "hostname": null,
          "port": 8304,
          "username": null,
          "password": null,
          "platform": null
        },
        "napalm": {
          "extras": {
            "optional_args": {
              "transport": "https",
              "port": 4404
            }
          },
          "hostname": null,
          "port": null,
          "username": null,
          "password": null,
          "platform": null
        },
        "ncclient": {
          "extras": null,
          "hostname": null,
          "port": 8304,
          "username": null,
          "password": null,
          "platform": null
        }
      },
      "groups": [
        "eos_params"
      ],
      "data": {},
      "hostname": "192.168.1.130",
      "port": 2204,
      "username": "admin",
      "password": "admin",
      "platform": "arista_eos"
    }
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-spine-1</summary>

    ```json
    {
      "name": "ceos-spine-1",
      "connection_options": {
        "scrapli_netconf": {
          "extras": null,
          "hostname": null,
          "port": 8300,
          "username": null,
          "password": null,
          "platform": null
        },
        "napalm": {
          "extras": {
            "optional_args": {
              "transport": "https",
              "port": 4400
            }
          },
          "hostname": null,
          "port": null,
          "username": null,
          "password": null,
          "platform": null
        },
        "ncclient": {
          "extras": null,
          "hostname": null,
          "port": 8300,
          "username": null,
          "password": null,
          "platform": null
        }
      },
      "groups": [
        "eos_params"
      ],
      "data": {
        "interfaces": [
          "loopback0",
          "ethernet1"
        ]
      },
      "hostname": "192.168.1.130",
      "port": 2200,
      "username": "admin",
      "password": "admin",
      "platform": "arista_eos"
    }
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-spine-2</summary>

    ```json
    {
      "name": "ceos-spine-2",
      "connection_options": {
        "scrapli_netconf": {
          "extras": null,
          "hostname": null,
          "port": 8301,
          "username": null,
          "password": null,
          "platform": null
        },
        "napalm": {
          "extras": {
            "optional_args": {
              "transport": "https",
              "port": 4401
            }
          },
          "hostname": null,
          "port": null,
          "username": null,
          "password": null,
          "platform": null
        },
        "ncclient": {
          "extras": null,
          "hostname": null,
          "port": 8301,
          "username": null,
          "password": null,
          "platform": null
        }
      },
      "groups": [
        "eos_params"
      ],
      "data": {
        "interfaces": [
          "ethernet1"
        ]
      },
      "hostname": "192.168.1.130",
      "port": 2201,
      "username": "admin",
      "password": "admin",
      "platform": "arista_eos"
    }
    ```

    </details>
    </details>



    <details style="margin-left:20px;">
    <summary>Test suites definitions for each host</summary>

    <details style="margin-left:40px;">
    <summary>ceos-leaf-1 (2 tests)</summary>

    ```json
    [
      {
        "task": "show version",
        "test": "contains",
        "pattern": "cEOS",
        "name": "check ceos version"
      },
      {
        "test": "contains_lines",
        "pattern": [
          "1.1.1.1"
        ],
        "task": "show ntp associations",
        "name": "check NTP status"
      }
    ]
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-leaf-2 (2 tests)</summary>

    ```json
    [
      {
        "task": "show version",
        "test": "contains",
        "pattern": "cEOS",
        "name": "check ceos version"
      },
      {
        "test": "contains_lines",
        "pattern": [
          "1.1.1.1"
        ],
        "task": "show ntp associations",
        "name": "check NTP status"
      }
    ]
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-leaf-3 (2 tests)</summary>

    ```json
    [
      {
        "task": "show version",
        "test": "contains",
        "pattern": "cEOS",
        "name": "check ceos version"
      },
      {
        "test": "contains_lines",
        "pattern": [
          "1.1.1.1"
        ],
        "task": "show ntp associations",
        "name": "check NTP status"
      }
    ]
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-spine-1 (2 tests)</summary>

    ```json
    [
      {
        "task": "show version",
        "test": "contains",
        "pattern": "cEOS",
        "name": "check ceos version"
      },
      {
        "test": "contains_lines",
        "pattern": [
          "1.1.1.1"
        ],
        "task": "show ntp associations",
        "name": "check NTP status"
      }
    ]
    ```

    </details>
    <details style="margin-left:40px;">
    <summary>ceos-spine-2 (2 tests)</summary>

    ```json
    [
      {
        "task": "show version",
        "test": "contains",
        "pattern": "cEOS",
        "name": "check ceos version"
      },
      {
        "test": "contains_lines",
        "pattern": [
          "1.1.1.1"
        ],
        "task": "show ntp associations",
        "name": "check NTP status"
      }
    ]
    ```

    </details>

    </details>

    <details style="margin-left:20px;">
    <summary>Input Arguments (kwargs)</summary>

    ```json
    {
      "suite": "nf://nornir_test_suites/suite_1.txt",
      "FC": [
        "spine",
        "leaf"
      ],
      "extensive": true
    }
    ```

    </details>

    <details style="margin-left:20px;">
    <summary>Complete Results (JSON)</summary>

    ```json
    {
      "status": "202",
      "results": {
        "nornir-worker-5": {
          "result": {
            "test_results": [],
            "suite": {},
          },
          "failed": false,
          "errors": [],
          "task": "nornir-worker-5:test",
          "messages": [
            "nornir-worker-5 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "4f974374692749019e5cf23e842f5922",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:14:10 2026",
          "task_completed": "Fri Jan  2 18:14:10 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-4": {
          "result": {
            "test_results": [],
            "suite": {},
          },
          "failed": false,
          "errors": [],
          "task": "nornir-worker-4:test",
          "messages": [
            "nornir-worker-4 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "4f974374692749019e5cf23e842f5922",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:14:10 2026",
          "task_completed": "Fri Jan  2 18:14:10 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-6": {
          "result": {
            "test_results": [],
            "suite": {},
          },
          "failed": false,
          "errors": [],
          "task": "nornir-worker-6:test",
          "messages": [
            "nornir-worker-6 - nothing to do, no hosts matched by filters '{'FC': ['spine', 'leaf']}'"
          ],
          "juuid": "4f974374692749019e5cf23e842f5922",
          "resources": [],
          "status": "no_match",
          "task_started": "Fri Jan  2 18:14:10 2026",
          "task_completed": "Fri Jan  2 18:14:10 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-2": {
          "result": {
            "test_results": [
              {
                "result": "Arista cEOSLab\nHardware version: \nSerial number: 16921D773C3C0A23581B1260734452FF\nHardware MAC address: 001c.7393.6e5d\nSystem MAC address: 001c.7393.6e5d\n\nSoftware image version: 4.30.0F-31408673.4300F (engineering build)\nArchitecture: x86_64\nInternal build version: 4.30.0F-31408673.4300F\nInternal build ID: a35f0dc7-2d65-4f2a-a010-279cf445fd8c\nImage format version: 1.0\nImage optimization: None\n\ncEOS tools version: (unknown)\nKernel version: 5.15.0-164-generic\n\nUptime: 1 hour and 32 minutes\nTotal memory: 32827152 kB\nFree memory: 15965824 kB\n",
                "changed": false,
                "diff": "",
                "failed": false,
                "exception": null,
                "name": "show version",
                "connection_retry": 0,
                "task_retry": 0,
                "host": "ceos-leaf-2"
              }
            ],
            "suite": {},
          },
          "failed": true,
          "errors": [],
          "task": "nornir-worker-2:test",
          "messages": [],
          "juuid": "4f974374692749019e5cf23e842f5922",
          "resources": [],
          "status": "completed",
          "task_started": "Fri Jan  2 18:14:10 2026",
          "task_completed": "Fri Jan  2 18:14:11 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        },
        "nornir-worker-1": {
          "result": {
            "test_results": [],
            "suite": {},
          },
          "failed": true,
          "errors": [],
          "task": "nornir-worker-1:test",
          "messages": [],
          "juuid": "4f974374692749019e5cf23e842f5922",
          "resources": [],
          "status": "completed",
          "task_started": "Fri Jan  2 18:14:10 2026",
          "task_completed": "Fri Jan  2 18:14:11 2026",
          "service": "nornir",
          "diff": null,
          "dry_run": false
        }
      },
      "errors": [],
      "workers": {
        "requested": [
          "nornir-worker-1",
          "nornir-worker-4",
          "nornir-worker-6",
          "nornir-worker-2",
          "nornir-worker-5"
        ],
        "done": "{'nornir-worker-1', 'nornir-worker-4', 'nornir-worker-6', 'nornir-worker-2', 'nornir-worker-5'}",
        "dispatched": "{'nornir-worker-1', 'nornir-worker-4', 'nornir-worker-6', 'nornir-worker-2', 'nornir-worker-5'}",
        "pending": "set()"
      }
    }
    ```

    </details>
    ````

    </details>

## Using Jinja2 Templates to Generate Tests

Using Jinja2 Templates enables you to create dynamic test suites based on variables defined in your inventory or passed as job data. This approach allows you to tailor tests to specific devices or scenarios, ensuring that the tests are relevant and accurate. Jinja2 templates provide a powerful way to automate the creation of complex test cases, incorporating conditional logic, loops, and other advanced features to meet your testing requirements.

## Templating Tests with Inline Job Data

Inline Job Data allows you to define test parameters directly within the `job_data` argument, making it easy to customize tests on the fly. This feature is particularly useful for scenarios where test parameters need to be adjusted frequently or based on specific conditions. By templating tests with inline job data, you can ensure that your tests are always up-to-date and aligned with the current network state.

## Using Dry Run

The Using Dry Run feature allows you to generate the content of network test suites without actually performing any actions on the devices. This is useful for validation purposes, as it enables you to verify the correctness of your tests before running them. By using dry run, you can identify potential issues and make necessary adjustments, ensuring that your tests will execute successfully when run for real.

## Running a Subset of Tests

Running a Subset of Tests allows you to execute only a specific set of tests, rather than running the entire test suite. This is useful for targeted testing, such as validating changes in a particular part of the network configuration or focusing on specific devices features. By running a subset of tests, you can save time and resources, while still ensuring that critical aspects of the network are thoroughly tested.

## Returning Only Failed Tests

Returning only failed tests enables you to filter the test results to show only the tests that have failed. This is particularly useful for quickly identifying and addressing issues, as it allows you to focus on the areas that require attention. By returning only failed tests, you can streamline the troubleshooting process and ensure that network problems are resolved efficiently.

## NORFAB Nornir Test Shell Reference

The NORFAB Nornir Test Shell Reference provides a comprehensive set of command options for the Nornir `test` task. These commands allow you to control various aspects of the test execution, such as setting job timeouts, filtering devices, adding task details to results, and configuring retry mechanisms. By leveraging these command options, you can tailor the behavior of the tests to meet your specific network management needs, ensuring that your network remains reliable and performant.

NorFab shell supports these command options for Nornir `test` task:

```
nf#man tree nornir.test
root
└── nornir:    Nornir service
    └── test:    Run network tests
        ├── timeout:    Job timeout
        ├── workers:    Filter worker to target, default 'all'
        ├── add-details:    Add task details to results, default 'False'
        ├── num-workers:    RetryRunner number of threads for tasks execution
        ├── num-connectors:    RetryRunner number of threads for device connections
        ├── connect-retry:    RetryRunner number of connection attempts
        ├── task-retry:    RetryRunner number of attempts to run task
        ├── reconnect-on-fail:    RetryRunner perform reconnect to host on task failure
        ├── connect-check:    RetryRunner test TCP connection before opening actual connection
        ├── connect-timeout:    RetryRunner timeout in seconds to wait for test TCP connection to establish
        ├── creds-retry:    RetryRunner list of connection credentials and parameters to retry
        ├── tf:    File group name to save task results to on worker file system
        ├── tf-skip-failed:    Save results to file for failed tasks
        ├── diff:    File group name to run the diff for
        ├── diff-last:    File version number to diff, default is 1 (last)
        ├── table:    Table format (brief, terse, extend) or parameters or True, default 'brief'
        ├── headers:    Table headers
        ├── headers-exclude:    Table headers to exclude
        ├── sortby:    Table header column to sort by
        ├── reverse:    Table reverse the sort by order
        ├── FO:    Filter hosts using Filter Object
        ├── FB:    Filter hosts by name using Glob Patterns
        ├── FH:    Filter hosts by hostname
        ├── FC:    Filter hosts containment of pattern in name
        ├── FR:    Filter hosts by name using Regular Expressions
        ├── FG:    Filter hosts by group
        ├── FP:    Filter hosts by hostname using IP Prefix
        ├── FL:    Filter hosts by names list
        ├── FM:    Filter hosts by platform
        ├── FX:    Filter hosts excluding them by name
        ├── FN:    Negate the match
        ├── hosts:    Filter hosts to target
        ├── *suite:    Nornir suite nf://path/to/file.py
        ├── dry-run:    Return produced per-host tests suite content without running tests
        ├── subset:    Filter tests by name
        ├── failed-only:    Return test results for failed tests only
        ├── remove-tasks:    Include/Exclude tested task results
        └── job-data:    Path to YAML file with job data
nf#
```

``*`` - mandatory/required command argument

## Python API Reference

::: norfab.workers.nornir_worker.NornirWorker.test