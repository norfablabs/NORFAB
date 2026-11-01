import builtins
import logging
from contextvars import ContextVar

from picle.chat import ChatSession
from picle.models import Outputters
from pydantic import (
    BaseModel,
    Field,
    StrictBool,
    StrictStr,
)

from norfab.core.agent import AgentProgress

from ..common import ClientRunJobArgs

log = logging.getLogger(__name__)

current_agent = ContextVar("current_agent", default=None)


class AgentProgressPrinter:
    """Format local agent progress for the chat terminal."""

    def __init__(self, chat: ChatSession) -> None:
        self.chat = chat

    def __call__(self, message: str, severity: str = "INFO") -> None:
        if message == "thinking...":
            self.chat.set_status(message, spinner=True)
            return
        self.chat.set_status()
        self.chat.write(message)


class ListToolsCommand(BaseModel):
    name: StrictStr = Field(None, description="Tools glob pattern filter")

    class PicleConfig:
        outputter = Outputters.outputter_nested

    @staticmethod
    def run(*args: object, **kwargs: object) -> list | str:
        agent = current_agent.get()
        if agent:
            return agent.list_tools(**kwargs)
        return "Agent is not running"


class ChatShellCommands(BaseModel):
    rename: StrictStr = Field(
        None,
        description="Rename the current conversation",
        json_schema_extra={"function": "rename_conversation"},
    )

    @staticmethod
    def rename_conversation(rename: str, **kwargs: object) -> str:
        """Rename the current thread without calling the model."""
        agent = current_agent.get()
        if agent is None:
            return "Send a message before renaming the conversation."
        try:
            agent.rename(rename)
        except ValueError as exc:
            return str(exc)
        return f"renamed conversation to {agent.thread_id}"

    list_tools: ListToolsCommand = Field(
        None, description="List agent tools", alias="list-tools"
    )
    resume: StrictStr = Field(
        None,
        description="List conversations or resume a thread ID",
        json_schema_extra={"presence": "", "function": "resume_conversation"},
    )

    @staticmethod
    def source_resume() -> list[str]:
        """Return saved thread IDs for the active agent's tab completion."""
        agent = current_agent.get()
        if agent is None:
            return []
        return [row["thread_id"] for row in agent.list_conversations(limit=None)]

    @staticmethod
    def resume_conversation(resume: str = "", **kwargs: object) -> str:
        """List saved threads or select one without calling the model."""
        agent = current_agent.get()
        if not resume:
            conversations = agent.list_conversations()
            return (
                "\n".join(
                    f"{row['thread_id']}  {row['updated_at']}  {row['title']}"
                    for row in conversations
                )
                or "No saved conversations for this profile."
            )
        try:
            agent.resume(resume)
        except ValueError as exc:
            return str(exc)
        return f"resumed conversation {resume}"


class AgentChat(BaseModel):
    progress: StrictBool = Field(
        True,
        description="Show thinking and tool activity",
        json_schema_extra={"presence": True},
    )
    thread_id: StrictStr = Field(None, description="Chat identifier", alias="thread-id")
    agent_name: StrictStr = Field(
        None, description="Name of the agent profile", alias="agent-name"
    )

    @staticmethod
    def chat_on_enter(
        agent_name: str = "default", thread_id: str = None, **kwargs: object
    ) -> None:
        """Select the agent at chat entry, including before slash commands."""
        agent = builtins.NFCLIENT.get_agent(profile=agent_name)
        if thread_id:
            agent.thread_id = thread_id
        current_agent.set(agent)

    @staticmethod
    def chat_on_exit(**kwargs: object) -> None:
        """Release the chat context while keeping the cached agent available."""
        current_agent.set(None)

    @staticmethod
    def run(message: str, chat: ChatSession, **kwargs: object) -> str:
        agent = current_agent.get()
        chat.set_footer(f"profile: {agent.profile} | thread: {agent.thread_id}")
        return agent.invoke(
            message,
            callbacks=(
                [AgentProgress(AgentProgressPrinter(chat))]
                if kwargs.get("progress", True)
                else None
            ),
        )

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
