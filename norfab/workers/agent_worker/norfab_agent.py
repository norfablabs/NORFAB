from pydantic import BaseModel, StrictStr, Field

llm = {
    "provider": "ollama",
    "model": "qwen3:8b",
    "base_url": "http://127.0.0.1:11434",
}

name = "NorFab"

system_prompt = """
Your name is 'NorFab Agent', you are an expert AI assistant specializing in 
NORFAB (Network Automation Fabric), a distributed automation framework for 
managing network infrastructure and executing complex tasks across multiple 
workers and services.
"""

# -------------------------------------------------------------------------
# Tools definitions
# -------------------------------------------------------------------------


class get_service_task_information_input(BaseModel):
    service: StrictStr = Field(
        None, description="NorFab service name to get task information for"
    )
    name: StrictStr = Field(None, description="Task name to get information for")


tools = {
    "get_available_services_and_tasks_summary": {
        "description": "Retrieve all available services and tasks names in dictionary format of {service_name: list[tasks_names]}",
        "norfab": {"service": "all", "task": "list_tasks", "kwargs": {"brief": True}},
    },
    "get_service_task_details": {
        "description": "Retrieve NorFab services tasks information",
        "model_args_schema": get_service_task_information_input,
        "norfab": {"task": "list_tasks", "kwargs": {}},
    },
}
