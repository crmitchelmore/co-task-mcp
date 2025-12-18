# Multitasker MCP

An MCP server that delegates coding tasks to CLI agents (Copilot CLI, Codex CLI, Claude Code).

## Features

- Accepts structured tasks with goals, requirements, and acceptance criteria
- Clones repositories and creates feature branches automatically
- Runs CLI coding agents asynchronously
- Creates PRs and optionally enables auto-merge
- Human-in-the-loop support for questions requiring user input
- Persists all state under `~/.multitasker/`

## Installation

```bash
pip install -e .
```

## Usage

### As MCP Server (stdio transport)

```bash
multitasker-mcp
```

Or via the run script:

```bash
./run.sh
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `repo_task.run` | Start a new task run |
| `repo_task.status` | Get status of a run |
| `repo_task.tail_logs` | Get recent log output |
| `repo_task.answer` | Answer a question from the agent |
| `repo_task.list_runs` | List recent runs |
| `repo_task.cancel` | Cancel a running task |

### Example Request

```json
{
  "repo": {
    "url": "git@github.com:user/repo.git",
    "ref": "main"
  },
  "task": {
    "goal": "Add input validation to the signup form",
    "requirements": ["Validate email format", "Validate password strength"],
    "acceptance_criteria": ["All tests pass", "No console errors"]
  },
  "agent": {
    "cli": "copilot",
    "model_family": "gpt"
  },
  "pr": {
    "create": true,
    "title": "Add signup form validation"
  },
  "merge": {
    "auto": true,
    "method": "squash"
  }
}
```

## Configuration

Create `~/.multitasker/config.json` to customize:

```json
{
  "commands": {
    "copilot": {"cmd": "co", "args": [], "model_flag": "--model"},
    "codex": {"cmd": "cx", "args": []},
    "claude": {"cmd": "cc", "args": []}
  },
  "copilot_models": {
    "opus": ["claude-3-5-opus-latest"],
    "gpt": ["gpt-4o"],
    "gemini": ["gemini-2.0-pro"]
  }
}
```

## Requirements

- Python 3.10+
- `git` and `gh` CLI tools
- One of: `co` (Copilot CLI), `cx` (Codex CLI), `cc` (Claude Code)
