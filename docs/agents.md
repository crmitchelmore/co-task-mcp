# Agents

This document describes the coding agents supported by Co-Task MCP.

## Supported Agents

### GitHub Copilot CLI (`copilot`)

**Command:** `co` (or `github-copilot-cli`)

The default agent. Uses GitHub Copilot to generate and modify code.

**Features:**
- Model selection via `--model` flag
- Prompt passing via `-p` flag
- Session resume via `--resume` flag
- Full approval mode for autonomous operation

**Model Families:**
| Family | Models |
|--------|--------|
| `opus` | Claude Sonnet 4, Claude 3.5 Opus |
| `gpt` | GPT-4.1, GPT-4o |
| `codex` | OpenAI Codex models |
| `gemini` | Gemini 2.5 Pro |

**Configuration:**
```json
{
  "commands": {
    "copilot": {
      "cmd": "co",
      "args": [],
      "model_flag": "--model",
      "prompt_flag": "-p"
    }
  }
}
```

---

### OpenAI Codex CLI (`codex`)

**Command:** `codex`

Uses OpenAI's Codex models for code generation.

**Features:**
- Prompt as positional argument
- Full approval mode available

**Configuration:**
```json
{
  "commands": {
    "codex": {
      "cmd": "codex",
      "args": ["--full-auto"],
      "prompt_flag": null
    }
  }
}
```

---

### Claude Code (`claude`)

**Command:** `claude`

Uses Anthropic's Claude for code generation.

**Features:**
- Prompt via `-p` flag
- Print mode for non-interactive use

**Configuration:**
```json
{
  "commands": {
    "claude": {
      "cmd": "claude",
      "args": ["-p", "--dangerously-skip-permissions"],
      "prompt_flag": null
    }
  }
}
```

---

## Agent Selection

Specify the agent when starting a task:

```
multitasker_run(
  repo_url="https://github.com/user/repo",
  prompt="Add input validation",
  agent="copilot"  # or "codex" or "claude"
)
```

## Agent Comparison

| Feature | Copilot | Codex | Claude |
|---------|---------|-------|--------|
| Model Selection | ✅ | ❌ | ❌ |
| Session Resume | ✅ | ❌ | ❌ |
| Full Approval | ✅ | ✅ | ✅ |
| Interactive Q&A | ✅ | ✅ | ✅ |

## Adding New Agents

To add support for a new CLI agent:

1. Add command configuration to `~/.multitasker/config.json`:
   ```json
   {
     "commands": {
       "new_agent": {
         "cmd": "agent-cli",
         "args": ["--auto"],
         "model_flag": null,
         "prompt_flag": "--prompt"
       }
     }
   }
   ```

2. Update `models.py` to include the new agent in the `Literal` type
3. Update `runner.py` to handle any agent-specific logic

## Agent Prompts

All agents receive the same prompt structure:

```
You have FULL APPROVAL for all changes. Do not ask for confirmation.

TASK:
{user's prompt}

INSTRUCTIONS:
1. Implement the requested changes
2. Commit with descriptive messages
3. Push to the branch
4. Do NOT create a PR (the system will do this)
```

This ensures consistent behavior across agents while respecting each agent's CLI interface.

## Troubleshooting

### Agent Not Found

```
Error: command not found: co
```

Ensure the agent CLI is installed and in your PATH:

```bash
# Check if available
which co

# If using an alias, add to shell config
alias co='github-copilot-cli'
```

### Agent Hangs

If an agent appears stuck:

1. Check logs: `multitasker_logs(run_id="...")`
2. Look for prompts waiting for input
3. Cancel if needed: `multitasker_cancel(run_id="...")`

### Wrong Model

For Copilot, specify the model family:

```
multitasker_run(
  ...,
  agent="copilot",
  model="opus"  # Uses Claude models
)
```
