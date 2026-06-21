from typing import List, Union

try:
    from ttp_templates import list_templates, list_templates_refs

    HAS_TTP_TEMPLATES = True
except Exception:
    HAS_TTP_TEMPLATES = False

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictBool, StrictStr

from norfab.workers.nornir_worker.nornir_models import (
    NapalmGettersEnum,
    ParseNapalmInput,
    ParseTTPInput,
    ParseTextfsmInput,
)

from ..common import ClientRunJobArgs, log_error_or_result, run_future_job
from .nornir_picle_shell_cli import (
    NrCliPluginNapalm,
    NrCliPluginNetmiko,
    NrCliPluginScrapli,
)
from .nornir_picle_shell_common import (
    NorniHostsFilters,
)


class NapalmGettersModel(
    ParseNapalmInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    getters: NapalmGettersEnum = Field(..., description="Select NAPALM getters")

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "parse_napalm",
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


class TTPParseNrCliPluginNetmiko(NrCliPluginNetmiko):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "netmiko"
        return TTPParseModel.run(*args, **kwargs)


class TTPParseNrCliPluginScrapli(NrCliPluginScrapli):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "scrapli"
        return TTPParseModel.run(*args, **kwargs)


class TTPParseNrCliPluginNapalm(NrCliPluginNapalm):
    @staticmethod
    def run(*args: object, **kwargs: object):
        kwargs["plugin"] = "napalm"
        return TTPParseModel.run(*args, **kwargs)


class TTPParseNrCliPlugins(BaseModel):
    netmiko: TTPParseNrCliPluginNetmiko = Field(
        None, description="Use Netmiko plugin to collect output from devices"
    )
    scrapli: TTPParseNrCliPluginScrapli = Field(
        None, description="Use Scrapli plugin to collect output from devices"
    )
    napalm: TTPParseNrCliPluginNapalm = Field(
        None, description="Use NAPALM plugin to collect output from devices"
    )


class TTPParseModel(
    ParseTTPInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    commands: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of commands to collect form devices",
        json_schema_extra={"multiline": True},
    )
    plugin: TTPParseNrCliPlugins = Field(
        None, description="CLI connection plugin parameters"
    )
    enable: StrictBool = Field(
        None, description="Enter exec mode", json_schema_extra={"presence": True}
    )
    strict: StrictBool = Field(
        True,
        description="Strict mode, raise error on empty results",
        json_schema_extra={"presence": True},
    )

    @staticmethod
    def source_template(choice) -> list:
        if choice and choice.startswith("nf://"):
            return ClientRunJobArgs.walk_norfab_files(choice)
        elif choice and choice.startswith("ttp://") and HAS_TTP_TEMPLATES:
            return list_templates_refs()
        else:
            return ["nf://", "ttp://"]

    @staticmethod
    def source_get() -> list:
        if HAS_TTP_TEMPLATES:
            return [t.replace(".txt", "") for t in list_templates()["get"]]
        return []

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "parse_ttp",
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


class TextFSMParseModel(
    ParseTextfsmInput,
    NorniHostsFilters,
    ClientRunJobArgs,
    use_enum_values=True,
    populate_by_name=True,
):
    template: StrictStr = Field(None, description="Path to a TextFSM template file")
    commands: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of commands to parse form devices",
        json_schema_extra={"multiline": True},
    )

    @staticmethod
    def source_template(choice) -> list:
        return ClientRunJobArgs.walk_norfab_files(choice)

    @staticmethod
    def run(*args: object, **kwargs: object):
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = run_future_job(
            "nornir",
            "parse_textfsm",
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


class NornirParseShell(BaseModel):
    napalm: NapalmGettersModel = Field(
        None, description="Parse devices output using NAPALM getters"
    )
    ttp: TTPParseModel = Field(
        None, description="Parse devices output using TTP templates"
    )
    textfsm: TextFSMParseModel = Field(
        None, description="Parse devices output using TextFSM templates"
    )

    class PicleConfig:
        subshell = True
        prompt = "nf[nornir-parse]#"
        outputter = Outputters.outputter_nested
        pipe = PipeFunctionsModel
