# Co-Task MCP

An MCP server that spawns parallel coding agents to work on repositories autonomously. Delegate tasks to Copilot CLI, Codex CLI, or Claude Code and get PRs back.

## Features

- 🚀 **Parallel Execution** - Run multiple coding tasks simultaneously
- 🤖 **Multi-Agent Support** - Use Copilot CLI, Codex CLI, or Claude Code
- 📦 **Automatic Git Workflow** - Clones repos, creates branches, opens PRs
- 🔔 **Native Notifications** - macOS notifications when tasks complete
- 🧹 **Auto-Cleanup** - Removes workspaces after PRs merge
- 🔒 **Session Isolation** - Tasks are scoped to the session that created them
- ⏹️ **Graceful Shutdown** - Tasks cancel when parent session closes

## Installation

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) package manager
- Git and GitHub CLI (`gh`)
- At least one coding CLI:
  - `co` - [GitHub Copilot CLI](https://githubnext.com/projects/copilot-cli)
  - `codex` - [OpenAI Codex CLI](https://github.com/openai/codex)
  - `claude` - [Claude Code CLI](https://claude.ai/code)

### Install

```bash
git clone https://github.com/crmitchelmore/co-task-mcp
cd co-task-mcp
uv sync
```

### Configure MCP Client

Add to your MCP client configuration (e.g., `~/.copilot/mcp-config.json`):

```json
{
  "mcpServers": {
    "multitasker": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/co-task-mcp", "python", "-m", "multitasker_mcp.server"],
      "type": "local",
      "tools": [
        "multitasker_run",
        "multitasker_status", 
        "multitasker_logs",
        "multitasker_list",
        "multitasker_cancel",
        "multitasker_cleanup",
        "multitasker_answer",
        "multitasker_wait"
      ]
    }
  }
}
```

## Quick Start

### Start a Single Task

```
Use multitasker to add input validation to https://github.com/user/repo
```

### Start Parallel Tasks

```
Use multitasker to run these 3 tasks on https://github.com/user/repo:
1. Add TypeScript types for the API layer
2. Create React components for the dashboard  
3. Set up Zustand state management
```

### Monitor Progress

The agent will automatically poll `multitasker_list` every 60 seconds until all tasks complete. You'll get macOS notifications as tasks finish.

## Tools

| Tool | Description |
|------|-------------|
| `multitasker_run` | Start a background coding task |
| `multitasker_list` | List all tasks from this session |
| `multitasker_status` | Get status of a single task |
| `multitasker_logs` | View task output logs |
| `multitasker_cancel` | Cancel a running task |
| `multitasker_cleanup` | Clean up workspace after PR merged |
| `multitasker_wait` | Wait for tasks with progress updates |
| `multitasker_answer` | Answer questions from tasks (human-in-the-loop) |

## Resources

The MCP server exposes these resources:

| URI | Description |
|-----|-------------|
| `multitasker://runs` | List all runs |
| `multitasker://runs/{run_id}/logs` | Full logs for a run |
| `multitasker://runs/{run_id}/state` | JSON state for a run |

## Configuration

Create `~/.multitasker/config.json` to customize agent commands:

```json
{
  "commands": {
    "copilot": {"cmd": "co", "args": [], "model_flag": "--model", "prompt_flag": "-p"},
    "codex": {"cmd": "codex", "args": [], "prompt_flag": null},
    "claude": {"cmd": "claude", "args": ["-p"], "prompt_flag": null}
  },
  "copilot_models": {
    "opus": ["claude-sonnet-4"],
    "gpt": ["gpt-4.1"],
    "gemini": ["gemini-2.5-pro"]
  }
}
```

## How It Works

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  MCP Client │────▶│  MCP Server │────▶│   Worker    │
│  (Copilot)  │     │  (FastMCP)  │     │  (Process)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                   │
                           ▼                   ▼
                    ┌─────────────┐     ┌─────────────┐
                    │    State    │     │  Coding CLI │
                    │ (~/.multi*) │     │ (co/cx/cc)  │
                    └─────────────┘     └─────────────┘
```

1. **Task Submission** - Call `multitasker_run` with repo URL and prompt
2. **Clone & Branch** - Worker clones repo and creates feature branch
3. **Agent Execution** - Spawns coding CLI with your prompt
4. **PR Creation** - Creates PR via `gh` when complete
5. **Cleanup** - Workspace removed after PR merges

## Documentation

See the [docs](./docs/) folder for detailed documentation:

- [Getting Started](./docs/getting-started.md)
- [Tools Reference](./docs/tools.md)
- [Architecture](./docs/architecture.md)

## Requirements

- Python 3.10+
- `git` and `gh` CLI tools
- One of: `co` (Copilot CLI), `codex` (Codex CLI), `claude` (Claude Code)

## License

MIT
