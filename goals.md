# Multitasker MCP tool — original requirements

Timestamp: 2025-12-18

## Problem / goal
Build an MCP tool that takes a well-defined task plus a repository, runs a CLI coding agent to implement the task, and returns a summary of what happened.

## High-level workflow
1. Caller (agent) invokes an MCP tool with:
   - a repository reference
   - a structured task
   - optional flags for PR creation and auto-merge
   - optional configuration for agent/model
2. The MCP server starts an *implementing agent* (initially GitHub Copilot CLI) to do the work.
3. When complete, the MCP tool returns a human-readable summary (and relevant metadata like PR URL).

## Required capabilities
### Execution
- Localhost-only for MVP.
- MCP transport: **stdio**.
- Runs are **asynchronous**.
- No max concurrency.
- Persist all state under `~/.multitasker/*` (create if missing).

### Repo handling
- Always create a **fresh local clone** of the repo to do work.
- Always create a **new branch** for the work.
- Cleanup local workspace when the PR is merged.

### Agent invocation
- Default implementing agent: **Copilot CLI** invoked via `co` alias.
- Future/alternate CLIs:
  - `cx` for Codex CLI
  - `cc` for Claude Code
- Task should be passed to the agent as **structured input**:
  - goal
  - requirements
  - acceptance criteria

### Model selection (Copilot only)
- Request can specify a model family: `opus`, `gpt`, `codex`, or `gemini`.
- The server should map the family to the **most recent / most powerful** model name available (including previews).
- (Other CLIs may not support multiple models; model selection is primarily for Copilot.)

### Q&A / human-in-the-loop
- By default, the implementing agent’s questions should be **auto-answered**.
- If a question needs a user decision, the run should **pause** and request input using a push mechanism.
- “Full approval” is provided up-front for actions (i.e., no per-command approval gating for MVP).

### PR workflow
- Create a PR from the working branch when done (optional flag).
- Optionally enable auto-merge with conditions.
- The implementing agent should be instructed to follow PR status and address review comments when they make sense.

## Output requirements
- Return a **human-readable summary** to the caller when the run completes.
