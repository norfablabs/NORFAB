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

log = logging.getLogger(__name__)

shell_agent = None

class ChatShellCommands(BaseModel):
    list_tools: Any = Field(None, description="List agent tools", alias="list-tools", json_schema_extra={"function": "call_list_tools"})

    @staticmethod
    def call_list_tools():
        global shell_agent
        log.critical("!!!!!!!!!")
        return shell_agent.list_tools()

class AgentChat(BaseModel):
    thread_id: StrictStr = Field(None, description="Chat identifier", alias="thread-id")
    agent_name: StrictStr = Field(None, description="Name of the agent profile", alias="agent-name")

    @staticmethod
    def run(message, **kwargs):
        global shell_agent
        NFCLIENT = builtins.NFCLIENT
        agent = NFCLIENT.get_agent(profile=kwargs.get("agent_name", "default"))
        shell_agent = agent
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
