# Tools Reference

Complete documentation for all Co-Task MCP tools.

## multitasker_run

Start a background coding task. Returns immediately with a run ID.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `repo_url` | string | ✅ | - | Git URL (https or ssh) of the repository |
| `prompt` | string | ✅ | - | What you want the agent to do |
| `repo_ref` | string | ❌ | `null` | Git ref/branch/tag to base from |
| `agent` | string | ❌ | `"copilot"` | Which CLI: `copilot`, `codex`, or `claude` |
| `model` | string | ❌ | `null` | Model family (copilot only): `opus`, `gpt`, `codex`, `gemini` |
| `create_pr` | boolean | ❌ | `true` | Whether to create a PR when done |
| `pr_base` | string | ❌ | `null` | Base branch for PR (defaults to repo default) |

### Response

```json
{
  "run_id": "run_20251218_235959_abc12345",
  "status": "queued",
  "next_action": "POLL: Call multitasker_list every 60 seconds until all tasks show status 'done'"
}
```

### Example

```
Start a multitasker task on https://github.com/user/repo to add input validation
```

---

## multitasker_list

List all tasks from the current session. **Use this for polling.**

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | ❌ | `20` | Maximum number of runs to return |

### Response

```json
{
  "runs": [
    {
      "run_id": "run_20251218_235959_abc12345",
      "status": "running_agent",
      "created_at": 1734566399.0,
      "updated_at": 1734566450.0,
      "pr_url": null,
      "complete": false
    }
  ],
  "all_complete": false,
  "running_count": 1,
  "total_count": 1,
  "message": "1 task(s) still running. Call multitasker_list again in 60 seconds.",
  "next_action": "POLL: Wait 60 seconds, then call multitasker_list again"
}
```

### Task Statuses

| Status | Description |
|--------|-------------|
| `queued` | Task created, waiting to start |
| `cloning` | Cloning the repository |
| `running_agent` | Coding CLI is executing |
| `creating_pr` | Creating the pull request |
| `done` | Task completed successfully |
| `error` | Task failed with an error |
| `cancelled` | Task was cancelled |

---

## multitasker_status

Get detailed status of a single task.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | ✅ | The run ID to check |

### Response

```json
{
  "run_id": "run_20251218_235959_abc12345",
  "status": "done",
  "pr_url": "https://github.com/user/repo/pull/123",
  "error": null,
  "updated_at": 1734566500.0,
  "complete": true
}
```

---

## multitasker_logs

Get recent log output from a task.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `run_id` | string | ✅ | - | The run ID to get logs for |
| `lines` | integer | ❌ | `200` | Number of log lines to return |

### Response

```json
{
  "run_id": "run_20251218_235959_abc12345",
  "log": "$ git clone https://github.com/user/repo\nCloning into 'repo'...\n..."
}
```

---

## multitasker_cancel

Cancel a running task.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | ✅ | The run ID to cancel |

### Response

```json
{
  "ok": true
}
```

Or if the task is already complete:

```json
{
  "ok": false,
  "reason": "Run already in terminal state: done"
}
```

---

## multitasker_cleanup

Clean up the workspace for a completed task. Removes the cloned repository directory.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | ✅ | The run ID to clean up |

### Response

```json
{
  "ok": true,
  "message": "Cleaned up workspace for run_20251218_235959_abc12345"
}
```

**Note:** Workspaces are automatically cleaned up when PRs are merged. Use this tool for manual cleanup.

---

## multitasker_wait

Wait for running tasks to complete with real-time progress updates.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `timeout_minutes` | integer | ❌ | `30` | Maximum time to wait |

### Response

When all tasks complete:

```json
{
  "ok": true,
  "message": "All tasks complete",
  "tasks": [
    {"run_id": "...", "status": "done", "pr_url": "..."}
  ],
  "elapsed_minutes": 5.2
}
```

On timeout:

```json
{
  "ok": false,
  "reason": "Timeout waiting for tasks",
  "elapsed_minutes": 30.0
}
```

### Progress Updates

While waiting, the tool reports progress via MCP progress notifications:

```
0.33/1.0 - "1/3 tasks complete, 2 running"
0.67/1.0 - "2/3 tasks complete, 1 running"
1.0/1.0  - "3/3 tasks complete, 0 running"
```

---

## multitasker_answer

Answer a question from a running task (human-in-the-loop).

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `run_id` | string | ✅ | The run ID with a pending question |

### Behavior

This tool uses MCP elicitation to prompt the user for input:

1. Fetches pending questions from the task state
2. Presents the question via `ctx.elicit()`
3. Stores the answer for the worker to pick up

### Response

```json
{
  "ok": true,
  "question": "Should I use React or Vue for the frontend?",
  "answer": "React"
}
```

---

## Tool Annotations

All tools include MCP annotations for better client integration:

| Tool | readOnlyHint | destructiveHint | idempotentHint |
|------|--------------|-----------------|----------------|
| `multitasker_run` | ❌ | ❌ | ❌ |
| `multitasker_list` | ✅ | ❌ | ✅ |
| `multitasker_status` | ✅ | ❌ | ✅ |
| `multitasker_logs` | ✅ | ❌ | ✅ |
| `multitasker_cancel` | ❌ | ✅ | ❌ |
| `multitasker_cleanup` | ❌ | ✅ | ✅ |
| `multitasker_wait` | ❌ | ❌ | ❌ |
| `multitasker_answer` | ❌ | ❌ | ❌ |
