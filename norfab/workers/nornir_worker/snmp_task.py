import logging
from typing import Any

from nornir_salt.plugins.functions import ResultSerializer
from nornir_salt.plugins.tasks import puresnmp_call

from norfab.core.worker import Job, Task
from norfab.models import Result

from .nornir_models import (
    SnmpBulkGetInput,
    SnmpBulkGetResult,
    SnmpBulkTableInput,
    SnmpBulkTableResult,
    SnmpBulkWalkInput,
    SnmpBulkWalkResult,
    SnmpGetInput,
    SnmpGetNextInput,
    SnmpGetNextResult,
    SnmpGetResult,
    SnmpMultiGetInput,
    SnmpMultiGetResult,
    SnmpMultiSetInput,
    SnmpMultiSetResult,
    SnmpMultiWalkInput,
    SnmpMultiWalkResult,
    SnmpSetInput,
    SnmpSetResult,
    SnmpTableInput,
    SnmpTableResult,
    SnmpWalkInput,
    SnmpWalkResult,
)

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# SNMP TASK MIXIN
# --------------------------------------------------------------------------

# Shared MCP safety metadata for read operations.
_SNMP_READ_MCP = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}

# Shared MCP safety metadata for write operations.
_SNMP_WRITE_MCP = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "idempotentHint": True,
    "openWorldHint": True,
}


class SnmpTask:
    """
    Mixin providing Nornir SNMP tasks backed by Nornir-Salt's ``puresnmp_call`` plugin.

    All public tasks delegate to ``_run_snmp`` which supplies the fixed ``call``
    argument, applies host filters, acquires the connections lock, serializes
    results, and performs watchdog connection tracking.
    """

    # ------------------------------------------------------------------
    # Internal shared SNMP runner
    # ------------------------------------------------------------------

    def _run_snmp(self, job: Job, call: str, **kwargs: Any) -> Result:
        """
        Shared runner for all SNMP operations.

        Args:
            job: NorFab Job object containing relevant metadata.
            call: The puresnmp method name to invoke (e.g. ``"get"``, ``"walk"``).
            **kwargs: Operation-specific arguments forwarded to ``puresnmp_call``.

        Returns:
            Result: Serialized Nornir task result.
        """
        add_details = kwargs.pop("add_details", False)
        to_dict = kwargs.pop("to_dict", True)
        ret = Result(
            task=f"{self.name}:snmp_{call}",
            result={} if to_dict else [],
        )

        filtered_nornir, _ = self.filter_hosts_and_validate(kwargs, ret)
        if ret.status == "no_match":
            return ret

        nr = self._add_processors(filtered_nornir, kwargs, job)

        with self.connections_lock:
            result = nr.run(task=puresnmp_call, call=call, **kwargs)

        ret.failed = result.failed
        ret.result = ResultSerializer(
            result,
            to_dict=to_dict,
            add_details=add_details,
        )

        self.watchdog.connections_update(nr, "puresnmp")
        self.watchdog.connections_clean()
        return ret

    # ------------------------------------------------------------------
    # Public SNMP task methods
    # ------------------------------------------------------------------

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpGetInput,
        output=SnmpGetResult,
        mcp={
            "annotations": {
                "title": "SNMP Get",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_get(self, job: Job, oid: str, **kwargs: Any) -> Result:
        """
        Perform an SNMP GET operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID to retrieve (e.g. ``"1.3.6.1.2.1.1.5.0"``).
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP GET results keyed by host.
        """
        return self._run_snmp(job, call="get", oid=oid, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpGetNextInput,
        output=SnmpGetNextResult,
        mcp={
            "annotations": {
                "title": "SNMP GetNext",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_getnext(self, job: Job, oid: str, **kwargs: Any) -> Result:
        """
        Perform an SNMP GETNEXT operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID from which to retrieve the next OID.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP GETNEXT results keyed by host.
        """
        return self._run_snmp(job, call="getnext", oid=oid, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpMultiGetInput,
        output=SnmpMultiGetResult,
        mcp={
            "annotations": {
                "title": "SNMP MultiGet",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_multiget(self, job: Job, oids: list[str], **kwargs: Any) -> Result:
        """
        Perform an SNMP MULTIGET operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oids: List of numeric OIDs to retrieve.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP MULTIGET results keyed by host.
        """
        return self._run_snmp(job, call="multiget", oids=oids, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpWalkInput,
        output=SnmpWalkResult,
        mcp={
            "annotations": {
                "title": "SNMP Walk",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_walk(
        self,
        job: Job,
        oid: str,
        errors: str = "strict",
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP WALK operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID at which to start the walk.
            errors: Error handling mode (``"strict"`` or ``"warn"``).
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP WALK results keyed by host.
        """
        return self._run_snmp(job, call="walk", oid=oid, errors=errors, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpMultiWalkInput,
        output=SnmpMultiWalkResult,
        mcp={
            "annotations": {
                "title": "SNMP MultiWalk",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_multiwalk(self, job: Job, oids: list[str], **kwargs: Any) -> Result:
        """
        Perform an SNMP MULTIWALK operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oids: List of numeric OIDs at which to start each walk.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP MULTIWALK results keyed by host.
        """
        return self._run_snmp(job, call="multiwalk", oids=oids, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpBulkGetInput,
        output=SnmpBulkGetResult,
        mcp={
            "annotations": {
                "title": "SNMP BulkGet",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_bulkget(
        self,
        job: Job,
        repeating_oids: list[str],
        scalar_oids: list[str] = None,
        max_list_size: int = 10,
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP BULKGET operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            repeating_oids: List of numeric OIDs for repeating (column) retrieval.
            scalar_oids: Optional list of numeric OIDs for scalar retrieval.
            max_list_size: Maximum number of OIDs per GETBULK request.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP BULKGET results keyed by host.
        """
        return self._run_snmp(
            job,
            call="bulkget",
            repeating_oids=repeating_oids,
            scalar_oids=scalar_oids,
            max_list_size=max_list_size,
            **kwargs,
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpBulkWalkInput,
        output=SnmpBulkWalkResult,
        mcp={
            "annotations": {
                "title": "SNMP BulkWalk",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_bulkwalk(
        self,
        job: Job,
        oids: list[str],
        bulk_size: int = 10,
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP BULKWALK operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oids: List of numeric OIDs at which to start each bulk walk.
            bulk_size: Maximum number of OIDs per GETBULK request.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP BULKWALK results keyed by host.
        """
        return self._run_snmp(
            job, call="bulkwalk", oids=oids, bulk_size=bulk_size, **kwargs
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpTableInput,
        output=SnmpTableResult,
        mcp={
            "annotations": {
                "title": "SNMP Table",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_table(self, job: Job, oid: str, **kwargs: Any) -> Result:
        """
        Perform an SNMP TABLE operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID at the root of the table to retrieve.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP TABLE results keyed by host.
        """
        return self._run_snmp(job, call="table", oid=oid, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpBulkTableInput,
        output=SnmpBulkTableResult,
        mcp={
            "annotations": {
                "title": "SNMP BulkTable",
                **_SNMP_READ_MCP,
            }
        },
    )
    def snmp_bulktable(
        self,
        job: Job,
        oid: str,
        bulk_size: int = 10,
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP BULKTABLE operation on network devices using GETBULK.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID at the root of the table to retrieve.
            bulk_size: Maximum number of OIDs per GETBULK request.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP BULKTABLE results keyed by host.
        """
        return self._run_snmp(
            job, call="bulktable", oid=oid, bulk_size=bulk_size, **kwargs
        )

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpSetInput,
        output=SnmpSetResult,
        mcp={
            "annotations": {
                "title": "SNMP Set",
                **_SNMP_WRITE_MCP,
            }
        },
    )
    def snmp_set(
        self,
        job: Job,
        oid: str,
        value: str,
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP SET operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            oid: Numeric OID to write.
            value: String value to write at the OID.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP SET results keyed by host.
        """
        return self._run_snmp(job, call="set", oid=oid, value=value, **kwargs)

    @Task(
        fastapi={"methods": ["POST"]},
        input=SnmpMultiSetInput,
        output=SnmpMultiSetResult,
        mcp={
            "annotations": {
                "title": "SNMP MultiSet",
                **_SNMP_WRITE_MCP,
            }
        },
    )
    def snmp_multiset(
        self,
        job: Job,
        mappings: dict[str, Any],
        **kwargs: Any,
    ) -> Result:
        """
        Perform an SNMP MULTISET operation on network devices.

        Args:
            job: NorFab Job object containing relevant metadata.
            mappings: Dictionary mapping numeric OIDs to values.
            **kwargs: Common Nornir host filter and processor arguments.

        Returns:
            Result: SNMP MULTISET results keyed by host.
        """
        return self._run_snmp(job, call="multiset", mappings=mappings, **kwargs)
