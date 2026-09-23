from picle.models import Outputters
from pydantic import BaseModel, Field

from norfab.workers.netbox_worker.netbox_models import DesignDeployInput

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .netbox_picle_shell_common import NetboxClientRunJobArgs


class DesignDeployShell(
    NetboxClientRunJobArgs,
    DesignDeployInput,
    use_enum_values=True,
    populate_by_name=True,
):
    @staticmethod
    def source_design(choice: str = None) -> list:
        return ClientRunJobArgs.walk_norfab_files(choice)

    @staticmethod
    def source_context(choice: str = None) -> list:
        return ClientRunJobArgs.walk_norfab_files(choice)

    @staticmethod
    def run(*args: object, **kwargs: object) -> object:
        workers = kwargs.pop("workers", "any")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "netbox",
            "design_deploy",
            workers=workers,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class DesignCommands(BaseModel):
    deploy: DesignDeployShell = Field(
        None, description="Deploy an additive NetBox design"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[netbox-design]#"
