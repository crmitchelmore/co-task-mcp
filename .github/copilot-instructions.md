# Copilot Instructions for Co-Task MCP

These instructions help GitHub Copilot understand how to use the Co-Task MCP effectively.

## Overview

Co-Task MCP is a tool for running parallel coding tasks on repositories. When a user asks you to work on multiple tasks simultaneously, or to delegate work to background agents, use the multitasker tools.

## When to Use Multitasker

Use multitasker when the user:
- Wants to run multiple coding tasks in parallel
- Asks to "delegate" or "spawn" work to other agents
- Wants background tasks that don't block the conversation
- Needs to work on multiple repositories simultaneously
- Mentions "multitasker" explicitly

## Workflow

### 1. Starting Tasks

Call `multitasker_run` for each task:

```
multitasker_run(
  repo_url="https://github.com/user/repo",
  prompt="Add input validation to the signup form",
  agent="copilot"  # or "codex" or "claude"
)
```

### 2. Polling for Completion (REQUIRED)

After starting tasks, you MUST poll for completion:

1. Wait 60 seconds
2. Call `multitasker_list` to check status
3. If `all_complete` is false, repeat from step 1
4. When all tasks are done, report results to user

**Example polling loop:**
```
# After starting tasks
sleep 60
multitasker_list()
# Check all_complete field
# If false, wait and poll again
```

### 3. Reporting Results

When all tasks complete, summarize:
- Number of tasks completed
- PR URLs for successful tasks
- Any errors encountered

## Tool Quick Reference

| Tool | When to Use |
|------|-------------|
| `multitasker_run` | Start a new background task |
| `multitasker_list` | Poll for task status (use every 60s) |
| `multitasker_status` | Check a specific task |
| `multitasker_logs` | Debug task issues |
| `multitasker_cancel` | Stop a running task |
| `multitasker_cleanup` | Remove workspace manually |

## Example Conversations

### Single Task

**User:** "Use multitasker to add tests to my repo"

**Response:**
1. Call `multitasker_run(repo_url="...", prompt="Add comprehensive tests")`
2. Poll `multitasker_list` every 60 seconds
3. Report the PR URL when done

### Multiple Tasks

**User:** "Run 3 parallel tasks on my repo: add types, add tests, add docs"

**Response:**
1. Call `multitasker_run` three times (can be parallel)
2. Poll `multitasker_list` every 60 seconds
3. Wait for `all_complete: true`
4. Report all PR URLs

### Checking Status

**User:** "What's the status of my multitasker tasks?"

**Response:**
1. Call `multitasker_list`
2. Report status of each task
3. Include PR URLs for completed tasks

## Important Notes

1. **Always poll** - Tasks run in the background, you must check status
2. **60 second interval** - Don't poll too frequently
3. **Session scoped** - You can only see tasks from the current session
4. **PR creation** - Tasks automatically create PRs when complete
5. **Notifications** - Users get macOS notifications when tasks complete
