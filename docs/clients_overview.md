# NORFAB Clients Overview

NORFAB provides multiple client interfaces to interact with automation fabric, catering to different use cases and user preferences. These clients include:

## 1. Robot Framework Client

The Robot Framework Client integrates NORFAB with the Robot Framework, enabling users to define and execute workflows using a domain-specific language (DSL). It is ideal for users who prefer a keyword-driven approach to automation.

**Key Features:**
- Supports ROBOT keywords for targeting hosts, running tests, and executing CLI or configuration tasks.
- Seamlessly integrates with Robot Framework's test suite.

Refer to [Robot Client Documentation](clients_robot_client_overview.md) for more details.

---

## 2. FastAPI REST API Client

The FastAPI Service provides a RESTful API interface to interact with NORFAB. It is designed for developers who prefer using HTTP-based APIs for automation and integration with other systems.

**Key Features:**
- High-performance REST API built with FastAPI.
- Automatic API documentation with Swagger UI and ReDoc.
- Secure access using bearer token authentication.

Refer to [FastAPI Service Documentation](workers/fastapi/services_fastapi_service.md) for more details.

---

## 3. Command Line Interface (CLI)

The NORFAB CLI (`nfcli`) is an interactive shell interface for managing and automating network operations. It is suitable for users who prefer a command-line approach.

**Key Features:**
- Modal design with hierarchical modes for specific tasks.
- Built using the PICLE package for a robust shell experience.

Refer to [CLI Documentation](clients_nfcli_overview.md) for more details.

---

## 4. Python API Client

The Python API Client provides a programmatic interface for developers to integrate NORFAB capabilities into their Python applications. It is ideal for advanced automation and custom integrations.

**Key Features:**
- Direct access to NORFAB's core functionality via Python.
- Flexible and extensible for custom automation workflows.

Refer to [Python API Documentation](clients_python_api_overview.md) for more details.

---

## Conclusion

Each NORFAB client is tailored to specific use cases, ensuring flexibility and ease of use for different types of users. Whether you prefer a graphical interface, command-line tools, or programmatic APIs, NORFAB has a client to meet your needs.
