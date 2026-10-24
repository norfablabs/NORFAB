from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field

from norfab.workers.nornir_worker.nornir_models import (
    NetconfCancelCommitInput,
    NetconfCommitInput,
    NetconfCopyConfigInput,
    NetconfDeleteConfigInput,
    NetconfDiscardChangesInput,
    NetconfEditConfigInput,
    NetconfGetCapabilitiesInput,
    NetconfGetConfigInput,
    NetconfGetInput,
    NetconfGetSchemaInput,
    NetconfLockInput,
    NetconfRpcInput,
    NetconfTransactionInput,
    NetconfUnlockInput,
    NetconfValidateInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_common import NorniHostsFilters


class CallGet(
    NetconfGetInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_get", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallGetConfig(
    NetconfGetConfigInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_get_config", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallEditConfig(
    NetconfEditConfigInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_edit_config", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallRpc(
    NetconfRpcInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_rpc", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallDeleteConfig(
    NetconfDeleteConfigInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_delete_config", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallCopyConfig(
    NetconfCopyConfigInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_copy_config", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallUnlock(
    NetconfUnlockInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_unlock", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallLock(
    NetconfLockInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_lock", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallDiscardChanges(
    NetconfDiscardChangesInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_discard_changes", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallCancelCommit(
    NetconfCancelCommitInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_cancel_commit", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallCommit(
    NetconfCommitInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_commit", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallValidate(
    NetconfValidateInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_validate", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallTransaction(
    NetconfTransactionInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_transaction", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallGetSchema(
    NetconfGetSchemaInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_get_schema", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class CallGetCapabilities(
    NetconfGetCapabilitiesInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        return NornirNetconfShell.run(*args, _task="netconf_get_capabilities", **kwargs)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class NornirNetconfShell(BaseModel):
    rpc: CallRpc = Field(None, description="Send a NETCONF operation XML or template")
    delete_config: CallDeleteConfig = Field(
        None,
        alias="delete-config",
        description="Delete a non-running NETCONF configuration",
    )
    copy_config: CallCopyConfig = Field(
        None,
        alias="copy-config",
        description="Copy configuration between NETCONF datastores",
    )
    unlock: CallUnlock = Field(None, description="Unlock a NETCONF datastore")
    lock: CallLock = Field(None, description="Lock a NETCONF datastore")
    discard_changes: CallDiscardChanges = Field(
        None,
        alias="discard-changes",
        description="Discard uncommitted candidate changes",
    )
    cancel_commit: CallCancelCommit = Field(
        None, alias="cancel-commit", description="Cancel a pending confirmed commit"
    )
    commit: CallCommit = Field(
        None, description="Commit NETCONF candidate configuration"
    )
    validate: CallValidate = Field(None, description="Validate NETCONF configuration")
    transaction: CallTransaction = Field(
        None, description="Apply configuration using a NETCONF transaction"
    )
    get: CallGet = Field(
        None, description="Retrieve configuration and operational state"
    )
    get_capabilities: CallGetCapabilities = Field(
        None, alias="get-capabilities", description="List NETCONF capabilities"
    )
    get_schema: CallGetSchema = Field(
        None, alias="get-schema", description="Retrieve a YANG module"
    )
    edit_config: CallEditConfig = Field(
        None, alias="edit-config", description="Edit NETCONF configuration"
    )
    get_config: CallGetConfig = Field(
        None,
        description="Get configuration",
        alias="get-config",
    )

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        task = kwargs.pop("_task")
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            task,
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        ret = log_error_or_result(result, verbose_result=verbose_result)

        return ret

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-netconf]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
