from pydantic import BaseModel, StrictStr, Field

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

tools = {
    "get_available_services_and_tasks_summary": {
        "description": "Retrieve all available services and tasks names in dictionary format of {service_name: list[tasks_names]}",
        "norfab": {"service": "all", "task": "list_tasks", "kwargs": {"brief": True}},
    },
    "get_service_task_details": {
        "description": "Retrieve specific NorFab service task detailed information",
        "input_schema": {
            "properties": {
                "service": {
                    "type": "string",
                    "description": "Lowercase NorFab service name to get task information for",
                },
                "name": {
                    "type": "string",
                    "description": "Lowercase Task name to get information for",
                },
            },
            "required": ["service", "name"],
        },
        "norfab": {"task": "list_tasks", "kwargs": {}},
    },
}
