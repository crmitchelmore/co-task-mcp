# Getting Started with Co-Task MCP

This guide will help you set up and start using Co-Task MCP to run parallel coding tasks.

## Prerequisites

### Required Tools

1. **Python 3.10+** - The MCP server is written in Python
2. **uv** - Fast Python package manager
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
3. **Git** - For cloning repositories
4. **GitHub CLI** - For creating PRs
   ```bash
   brew install gh
   gh auth login
   ```

### At Least One Coding CLI

- **GitHub Copilot CLI** (`co`) - Recommended
- **OpenAI Codex CLI** (`codex`)
- **Claude Code** (`claude`)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/crmitchelmore/co-task-mcp
cd co-task-mcp
```

### 2. Install Dependencies

```bash
uv sync
```

### 3. Configure Your MCP Client

Add to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "multitasker": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/path/to/co-task-mcp",
        "python", "-m", "multitasker_mcp.server"
      ],
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

**Important:** Replace `/path/to/co-task-mcp` with the actual path where you cloned the repository.

### 4. Restart Your MCP Client

If using Copilot CLI, exit and restart it to pick up the new configuration.

## Your First Task

### Single Task

Tell Copilot to use multitasker:

```
Use multitasker to add a health check endpoint to https://github.com/your/repo
```

Copilot will:
1. Call `multitasker_run` to start the task
2. Poll `multitasker_list` every 60 seconds
3. Report the result when complete

### Multiple Parallel Tasks

```
Use multitasker to run these tasks on https://github.com/your/repo:
1. Add input validation to the signup form
2. Create unit tests for the auth module
3. Add TypeScript types to the API layer
```

Each task runs in parallel with its own:
- Cloned repository
- Feature branch
- Pull request

## Monitoring Tasks

### Check Status

```
Check the status of my multitasker tasks
```

### View Logs

```
Show me the logs for the multitasker task run_20251218_...
```

### Cancel a Task

```
Cancel the multitasker task run_20251218_...
```

## Notifications

On macOS, you'll receive native notifications when:
- A task completes successfully
- A task fails with an error
- A task needs your input (human-in-the-loop)

## What Happens Under the Hood

1. **multitasker_run** creates a new run with a unique ID
2. A worker process spawns in the background
3. The worker:
   - Clones the repository to `~/.multitasker/workspaces/`
   - Creates a feature branch `multitasker/{run_id}`
   - Runs the coding CLI with your prompt
   - Creates a PR when complete
4. State is saved to `~/.multitasker/runs/{run_id}/`
5. When the PR merges, the workspace is automatically cleaned up

## Troubleshooting

### "Command not found: co"

Make sure you have Copilot CLI installed and the `co` alias configured:

```bash
# Check if copilot is available
which copilot || which co

# If using an alias, make sure it's in your shell config
alias co='github-copilot-cli'
```

### "Repository not found"

Make sure:
1. The repository URL is correct
2. You have access to the repository
3. `gh` is authenticated: `gh auth status`

### Tasks Stuck in "running_agent"

Check the logs for the task:

```
Show multitasker logs for run_20251218_...
```

Common issues:
- The coding CLI is waiting for input
- Rate limiting from the API
- Network issues

### MCP Server Not Connecting

1. Check the path in your MCP config is correct
2. Try running the server directly to see errors:
   ```bash
   cd /path/to/co-task-mcp
   uv run python -m multitasker_mcp.server
   ```

## Next Steps

- Read the [Tools Reference](./tools.md) for detailed tool documentation
- Learn about [Configuration](./configuration.md) options
- Understand the [Architecture](./architecture.md)
