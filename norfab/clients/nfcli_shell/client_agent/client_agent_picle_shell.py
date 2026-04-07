import builtins
import logging
from typing import Any, Optional

from picle.models import Outputters, PipeFunctionsModel
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

from ..common import ClientRunJobArgs, listen_events, log_error_or_result
from contextvars import ContextVar

log = logging.getLogger(__name__)

current_agent = ContextVar("current_agent", default=None)


class ListToolsCommand(BaseModel):
    name: StrictStr = Field(None, descritpion="Tools glob pattern filter")

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def run(*args, **kwargs):
        agent = current_agent.get()
        if agent:
            return agent.list_tools(**kwargs)
        return "Agent is not running"


class ChatShellCommands(BaseModel):
    list_tools: ListToolsCommand = Field(
        None, description="List agent tools", alias="list-tools"
    )


class AgentChat(BaseModel):
    thread_id: StrictStr = Field(None, description="Chat identifier", alias="thread-id")
    agent_name: StrictStr = Field(
        None, description="Name of the agent profile", alias="agent-name"
    )

    @staticmethod
    def run(message, **kwargs):
        NFCLIENT = builtins.NFCLIENT
        agent = NFCLIENT.get_agent(profile=kwargs.get("agent_name", "default"))
        current_agent.set(agent)
        return agent.invoke(message, thread_id=kwargs.get("thread_id"))

    class PicleConfig:
        chat_shell = True
        chat_prompt = "> "
        chat_commands_model = ChatShellCommands
        use_rich = True
        outputter = Outputters.outputter_rich_markdown


# ---------------------------------------------------------------------------------------------
# CLIENT AGENT MAIN SHELL MODEL
# ---------------------------------------------------------------------------------------------


class ClientAgentCommands(ClientRunJobArgs):
    chat: AgentChat = Field(
        None,
        description="Start agent chat",
    )

    class PicleConfig:
        subshell = True
        prompt = "client-agent#"
