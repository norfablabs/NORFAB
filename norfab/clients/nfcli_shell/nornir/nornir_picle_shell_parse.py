import builtins
from enum import Enum
from typing import List, Union, Any

try:
    from ttp_templates import list_templates_refs, list_templates

    HAS_TTP_TEMPLATES = True
except Exception as e:
    HAS_TTP_TEMPLATES = False

from picle.models import Outputters, PipeFunctionsModel
from pydantic import BaseModel, Field, StrictStr, StrictBool, model_validator

from ..common import ClientRunJobArgs, listen_events, log_error_or_result
from .nornir_picle_shell_common import (
    NorniHostsFilters,
    NornirCommonArgs,
)
from .nornir_picle_shell_cli import (
    NrCliPluginNetmiko,
    NrCliPluginScrapli,
    NrCliPluginNapalm,
)
from norfab.workers.nornir_worker.parse_task import ParseTTPInput


class NapalmGettersEnum(str, Enum):
    get_arp_table = "get_arp_table"
    get_bgp_config = "get_bgp_config"
    get_bgp_neighbors = "get_bgp_neighbors"
    get_bgp_neighbors_detail = "get_bgp_neighbors_detail"
    get_config = "get_config"
    get_environment = "get_environment"
    get_facts = "get_facts"
    get_firewall_policies = "get_firewall_policies"
    get_interfaces = "get_interfaces"
    get_interfaces_counters = "get_interfaces_counters"
    get_interfaces_ip = "get_interfaces_ip"
    get_ipv6_neighbors_table = "get_ipv6_neighbors_table"
    get_lldp_neighbors = "get_lldp_neighbors"
    get_lldp_neighbors_detail = "get_lldp_neighbors_detail"
    get_mac_address_table = "get_mac_address_table"
    get_network_instances = "get_network_instances"
    get_ntp_peers = "get_ntp_peers"
    get_ntp_servers = "get_ntp_servers"
    get_ntp_stats = "get_ntp_stats"
    get_optics = "get_optics"
    get_probes_config = "get_probes_config"
    get_probes_results = "get_probes_results"
    get_route_to = "get_route_to"
    get_snmp_information = "get_snmp_information"
    get_users = "get_users"
    get_vlans = "get_vlans"
    is_alive = "is_alive"
    ping = "ping"
    traceroute = "traceroute"


class NapalmGettersModel(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    getters: Union[NapalmGettersEnum, List[NapalmGettersEnum]] = Field(
        ..., description="Select NAPALM getters"
    )

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "nornir",
            "parse_napalm",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class TTPStructureOptions(str, Enum):
    list_ = "list"
    dictionary = "dictionary"
    flat_list = "flat_list"


class TTPParseNrCliPluginNetmiko(NrCliPluginNetmiko):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "netmiko"
        return TTPParseModel.run(*args, **kwargs)


class TTPParseNrCliPluginScrapli(NrCliPluginScrapli):
    @staticmethod
    def run(*args, **kwargs):
        kwargs["plugin"] = "scrapli"
        return TTPParseModel.run(*args, **kwargs)


class TTPParseNrCliPluginNapalm(NrCliPluginNapalm):
    @staticmethod
    def run(*args, **kwargs):
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
    NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs, ParseTTPInput
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
    def source_template(choice):
        if choice and choice.startswith("nf://"):
            return ClientRunJobArgs.walk_norfab_files()
        elif choice and choice.startswith("ttp://") and HAS_TTP_TEMPLATES:
            return list_templates_refs()
        else:
            return ["nf://", "ttp://"]

    @staticmethod
    def source_get():
        if HAS_TTP_TEMPLATES:
            return [t.replace(".txt", "") for t in list_templates()["get"]]
        return []

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "nornir",
            "parse_ttp",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
            timeout=timeout,
            nowait=nowait,
        )

        if nowait:
            return result, Outputters.outputter_nested

        return log_error_or_result(result, verbose_result=verbose_result)

    class PicleConfig:
        outputter = Outputters.outputter_nested


class TextFSMParseModel(NorniHostsFilters, NornirCommonArgs, ClientRunJobArgs):
    template: StrictStr = Field(None, description="Path to a TextFSM template file")
    commands: Union[StrictStr, List[StrictStr]] = Field(
        None,
        description="List of commands to parse form devices",
        json_schema_extra={"multiline": True},
    )

    @staticmethod
    def source_template(choice):
        return ClientRunJobArgs.walk_norfab_files()

    @staticmethod
    @listen_events
    def run(uuid, *args, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        workers = kwargs.pop("workers", "all")
        timeout = kwargs.pop("timeout", 600)
        verbose_result = kwargs.pop("verbose_result", False)
        nowait = kwargs.pop("nowait", False)

        result = NFCLIENT.run_job(
            "nornir",
            "parse_textfsm",
            workers=workers,
            args=args,
            kwargs=kwargs,
            uuid=uuid,
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
