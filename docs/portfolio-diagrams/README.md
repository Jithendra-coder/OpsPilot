# OpsPilot architecture and execution flow

These Mermaid files are the editable topology and workflow sources. For the detailed runtime boundaries, storage choices, evidence scope, and limits, see [architecture and data flow](../architecture.md). They describe the implemented project and isolated Compose demo; no external infrastructure is changed by the action executor.

| Source | Coverage |
| --- | --- |
| [system-architecture.mmd](system-architecture.mmd) | Browser, CLI, API, LangGraph, bounded providers, storage, MCP, and the simulator-only action boundary. |
| [execution-flow.mmd](execution-flow.mmd) | Alert intake through evidence review, diagnosis, approval, execution, and server-side verification. |

The provider adapters read configured Prometheus, Loki, and Tempo sources. The Compose demo instruments its own checkout service and routes generated local telemetry to those providers. SQLite is the local default; PostgreSQL can store operational records and LangGraph checkpoints. The optional model can rank fixed deterministic candidates but cannot authorize a cause or action.
