import os
import signal
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastmcp import FastMCP, Context
from mcp.types import ToolAnnotations
from pydantic import Field

from .models import RunRequest, RunResponse, RepoSpec, TaskSpec, AgentSpec, PRSpec, MergeSpec
from .state import append_event, load_state, multitasker_home, new_run_id, run_dir, save_state

# Track worker PIDs for cleanup on shutdown
_worker_pids: dict[str, int] = {}


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Lifecycle manager - cancels running tasks on shutdown."""
    yield
    # Shutdown: cancel all running tasks from this session
    for run_id, pid in list(_worker_pids.items()):
        try:
            # Update state to cancelled
            state = load_state(run_id)
            if state.get("status") not in ("done", "error", "cancelled"):
                state["status"] = "cancelled"
                state["updated_at"] = time.time()
                state["cancelled_reason"] = "session_closed"
                save_state(run_id, state)
                append_event(run_id, {"ts": time.time(), "type": "cancelled", "reason": "session_closed"})
            
            # Kill the worker process
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass  # Process already dead
        except Exception:
            pass


mcp = FastMCP(
    name="multitasker",
    lifespan=lifespan,
    instructions="""Multitasker MCP spawns background coding agents to work on repositories autonomously.

IMPORTANT - POLLING REQUIRED:
After starting tasks with multitasker_run, you MUST poll for completion:
1. Wait 60 seconds (use sleep or equivalent)
2. Call multitasker_list to check status of all tasks
3. If any task still has status "running_agent" or "queued", repeat from step 1
4. When all tasks show "done", "error", or "cancelled", report results to user

WORKFLOW:
1. multitasker_run - Start tasks (returns immediately with run_id)
2. POLL until complete - Call multitasker_list every 60 seconds
3. Report results when all tasks finish

TOOLS:
- multitasker_run: Start a background task (returns immediately)
- multitasker_status: Check single task progress  
- multitasker_list: Check ALL tasks from this session (use for polling)
- multitasker_logs: View task output
- multitasker_cancel: Stop a task
- multitasker_cleanup: Remove workspace after PR merged"""
)


def _start_background_task(run_id: str) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "multitasker_mcp.worker", run_id],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    # Track PID for cleanup on shutdown
    _worker_pids[run_id] = proc.pid


@mcp.tool(
    name="multitasker_run",
    description="MULTITASKER: Start a background coding task. Returns immediately with run_id. IMPORTANT: After starting tasks, you MUST poll multitasker_list every 60 seconds until all tasks complete.",
    annotations=ToolAnnotations(
        title="Start Background Task",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
    ),
)
def multitasker_run(
    repo_url: Annotated[str, Field(description="Git URL (https or ssh) of the repository")],
    prompt: Annotated[str, Field(description="What you want the agent to do - the task description")],
    ctx: Context,
    repo_ref: Annotated[str | None, Field(description="Git ref/branch/tag to base from")] = None,
    agent: Annotated[Literal["copilot", "codex", "claude"], Field(description="Which CLI agent to use")] = "copilot",
    model: Annotated[Literal["opus", "gpt", "codex", "gemini"] | None, Field(description="Model family (copilot only)")] = None,
    create_pr: Annotated[bool, Field(description="Whether to create a PR when done")] = True,
    pr_base: Annotated[str | None, Field(description="Base branch for PR")] = None,
) -> dict[str, Any]:
    session_id = ctx.session_id or "unknown"
    
    req = RunRequest(
        repo=RepoSpec(url=repo_url, ref=repo_ref),
        task=TaskSpec(goal=prompt, requirements=[], acceptance_criteria=[], context=None),
        agent=AgentSpec(cli=agent, model_family=model),
        pr=PRSpec(create=create_pr, base=pr_base, title=None),
        merge=MergeSpec(auto=False),
    )
    run_id = new_run_id()
    state: dict[str, Any] = {
        "run_id": run_id,
        "session_id": session_id,
        "created_at": time.time(),
        "updated_at": time.time(),
        "status": "queued",
        "request": req.model_dump(),
        "questions": {},
    }
    save_state(run_id, state)
    append_event(run_id, {"ts": time.time(), "type": "created", "session_id": session_id})

    _start_background_task(run_id)
    
    return {
        "run_id": run_id,
        "status": "queued",
        "next_action": "POLL: Call multitasker_list every 60 seconds until all tasks show status 'done'",
    }


@mcp.tool(
    name="multitasker_status",
    description="MULTITASKER: Get status of a single task. For polling multiple tasks, use multitasker_list instead.",
    annotations=ToolAnnotations(title="Check Task Status", readOnlyHint=True, idempotentHint=True),
)
def multitasker_status(
    run_id: Annotated[str, Field(description="The run ID to check status for")],
    ctx: Context,
) -> dict[str, Any]:
    state = load_state(run_id)
    status = state.get("status", "unknown")
    
    if state.get("session_id") != ctx.session_id:
        return {"error": "Task not found or access denied", "run_id": run_id}
    
    return {
        "run_id": run_id,
        "status": status,
        "pr_url": state.get("pr_url"),
        "error": state.get("error"),
        "updated_at": state.get("updated_at"),
        "complete": status in ("done", "error", "cancelled"),
    }


@mcp.tool(
    name="multitasker_logs",
    description="MULTITASKER: Get recent log output from a background task.",
    annotations=ToolAnnotations(title="View Task Logs", readOnlyHint=True, idempotentHint=True),
)
def multitasker_logs(
    run_id: Annotated[str, Field(description="The run ID to get logs for")],
    ctx: Context,
    lines: Annotated[int, Field(description="Number of log lines to return")] = 200,
) -> dict[str, Any]:
    state = load_state(run_id)
    
    if state.get("session_id") != ctx.session_id:
        return {"error": "Task not found or access denied", "run_id": run_id}
    
    p = run_dir(run_id) / "run.log"
    if not p.exists():
        return {"run_id": run_id, "log": ""}

    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"run_id": run_id, "log": "\n".join(data[-lines:])}


@mcp.tool(
    name="multitasker_list", 
    description="MULTITASKER: List all tasks from this session. USE THIS FOR POLLING - call every 60 seconds after starting tasks until all_complete is true.",
    annotations=ToolAnnotations(title="List Session Tasks", readOnlyHint=True, idempotentHint=True),
)
def multitasker_list(
    ctx: Context,
    limit: Annotated[int, Field(description="Maximum number of runs to return")] = 20,
) -> dict[str, Any]:
    runs_root = multitasker_home() / "runs"
    items: list[dict[str, Any]] = []
    session_id = ctx.session_id

    if not runs_root.exists():
        return {"runs": [], "all_complete": True, "message": "No tasks found"}

    for d in sorted(runs_root.glob("run_*/"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            rid = d.name
            st = load_state(rid)
            
            if st.get("session_id") != session_id:
                continue
                
            items.append({
                "run_id": rid,
                "status": st.get("status"),
                "created_at": st.get("created_at"),
                "updated_at": st.get("updated_at"),
                "pr_url": st.get("pr_url"),
                "complete": st.get("status") in ("done", "error", "cancelled"),
            })
        except Exception:
            continue
        if len(items) >= limit:
            break

    all_complete = all(item.get("complete", False) for item in items) if items else True
    running_count = sum(1 for item in items if not item.get("complete", False))
    
    result = {
        "runs": items,
        "all_complete": all_complete,
        "running_count": running_count,
        "total_count": len(items),
    }
    
    if all_complete:
        result["message"] = "All tasks complete! Review the PR URLs above."
    else:
        result["message"] = f"{running_count} task(s) still running. Call multitasker_list again in 60 seconds."
        result["next_action"] = "POLL: Wait 60 seconds, then call multitasker_list again"
    
    return result


@mcp.tool(
    name="multitasker_cancel",
    description="MULTITASKER: Cancel a background task before completion.",
    annotations=ToolAnnotations(title="Cancel Task", destructiveHint=True),
)
def multitasker_cancel(
    run_id: Annotated[str, Field(description="The run ID to cancel")],
    ctx: Context,
) -> dict[str, Any]:
    state = load_state(run_id)
    
    if state.get("session_id") != ctx.session_id:
        return {"ok": False, "reason": "Task not found or access denied"}
    
    if state.get("status") in ("done", "error", "cancelled"):
        return {"ok": False, "reason": f"Run already in terminal state: {state.get('status')}"}
    
    state["status"] = "cancelled"
    state["updated_at"] = time.time()
    save_state(run_id, state)
    append_event(run_id, {"ts": time.time(), "type": "cancelled"})
    return {"ok": True}


@mcp.tool(
    name="multitasker_cleanup",
    description="MULTITASKER: Clean up workspace for a completed/merged task. Removes cloned repo directory.",
    annotations=ToolAnnotations(title="Cleanup Workspace", destructiveHint=True, idempotentHint=True),
)
def multitasker_cleanup(
    run_id: Annotated[str, Field(description="The run ID to clean up")],
    ctx: Context,
) -> dict[str, Any]:
    import shutil
    from .state import workspace_dir
    
    state = load_state(run_id)
    
    if state.get("session_id") != ctx.session_id:
        return {"ok": False, "reason": "Task not found or access denied"}
    
    if state.get("workspace_cleaned"):
        return {"ok": True, "message": "Workspace already cleaned"}
    
    wdir = workspace_dir(run_id)
    if wdir.exists():
        shutil.rmtree(wdir)
    
    state["workspace_cleaned"] = True
    state["workspace_cleaned_at"] = time.time()
    save_state(run_id, state)
    
    return {"ok": True, "message": f"Cleaned up workspace for {run_id}"}


@mcp.prompt(
    name="parallel_tasks",
    description="Start multiple parallel background tasks on a repository",
)
def parallel_tasks_prompt(repo_url: str, task1: str, task2: str, task3: str = "") -> str:
    tasks = [task1, task2]
    if task3:
        tasks.append(task3)
    
    task_list = "\n".join(f"- Task {i+1}: {t}" for i, t in enumerate(tasks))
    
    return f"""Start {len(tasks)} parallel background tasks on {repo_url}:

{task_list}

For each task:
1. Call multitasker_run with the repo_url and the task description as the prompt
2. After starting ALL tasks, poll multitasker_list every 60 seconds until all_complete is true
3. Report the final status and PR URLs when all tasks finish"""


# ============================================================================
# RESOURCES - Expose logs as readable resources
# ============================================================================

@mcp.resource("multitasker://runs")
def list_runs_resource() -> str:
    """List all runs as a resource."""
    runs_root = multitasker_home() / "runs"
    if not runs_root.exists():
        return "No runs found"
    
    lines = ["# Multitasker Runs\n"]
    for d in sorted(runs_root.glob("run_*/"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]:
        try:
            st = load_state(d.name)
            status = st.get("status", "unknown")
            pr_url = st.get("pr_url", "")
            lines.append(f"- {d.name}: {status}" + (f" ({pr_url})" if pr_url else ""))
        except Exception:
            continue
    
    return "\n".join(lines)


@mcp.resource("multitasker://runs/{run_id}/logs")
def run_logs_resource(run_id: str) -> str:
    """Get logs for a specific run as a resource."""
    p = run_dir(run_id) / "run.log"
    if not p.exists():
        return f"No logs found for {run_id}"
    
    return p.read_text(encoding="utf-8", errors="replace")


@mcp.resource("multitasker://runs/{run_id}/state")
def run_state_resource(run_id: str) -> str:
    """Get state for a specific run as a resource."""
    import json
    state = load_state(run_id)
    return json.dumps(state, indent=2, default=str)


# ============================================================================
# TOOL WITH ELICITATION - Answer questions from sub-agents
# ============================================================================

@mcp.tool(
    name="multitasker_answer",
    description="MULTITASKER: Answer a question from a running background task. Use when a task needs human input.",
    annotations=ToolAnnotations(title="Answer Task Question"),
)
async def multitasker_answer(
    run_id: Annotated[str, Field(description="The run ID that has a pending question")],
    ctx: Context,
) -> dict[str, Any]:
    """Answer a pending question from a task using elicitation."""
    state = load_state(run_id)
    
    if state.get("session_id") != ctx.session_id:
        return {"ok": False, "reason": "Task not found or access denied"}
    
    questions = state.get("questions", {})
    pending = [(k, v) for k, v in questions.items() if v.get("status") == "pending"]
    
    if not pending:
        return {"ok": False, "reason": "No pending questions for this task"}
    
    # Get the oldest pending question
    question_id, question = pending[0]
    question_text = question.get("text", "Unknown question")
    choices = question.get("choices", [])
    
    # Use elicitation to get user input
    if choices:
        # Multiple choice question
        result = await ctx.elicit(
            message=f"Task {run_id} needs your input:\n\n{question_text}",
            response_type=choices,
        )
    else:
        # Free text question
        result = await ctx.elicit(
            message=f"Task {run_id} needs your input:\n\n{question_text}",
            response_type=str,
        )
    
    # Check result type
    from fastmcp.client.elicitation import AcceptedElicitation, DeclinedElicitation, CancelledElicitation
    
    if isinstance(result, AcceptedElicitation):
        # Store the answer
        questions[question_id]["status"] = "answered"
        questions[question_id]["answer"] = result.data
        questions[question_id]["answered_at"] = time.time()
        state["questions"] = questions
        save_state(run_id, state)
        append_event(run_id, {"ts": time.time(), "type": "question_answered", "question_id": question_id})
        
        return {"ok": True, "question": question_text, "answer": result.data}
    elif isinstance(result, DeclinedElicitation):
        return {"ok": False, "reason": "User declined to answer"}
    else:
        return {"ok": False, "reason": "User cancelled"}


# ============================================================================
# TOOL WITH PROGRESS - Wait for tasks with real-time updates
# ============================================================================

@mcp.tool(
    name="multitasker_wait",
    description="MULTITASKER: Wait for running tasks to complete with real-time progress updates. Use after starting tasks.",
    annotations=ToolAnnotations(title="Wait for Tasks"),
)
async def multitasker_wait(
    ctx: Context,
    timeout_minutes: Annotated[int, Field(description="Maximum time to wait in minutes")] = 30,
) -> dict[str, Any]:
    """Wait for tasks with progress reporting."""
    import asyncio
    
    session_id = ctx.session_id
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    poll_interval = 10  # seconds
    
    while True:
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed >= timeout_seconds:
            return {
                "ok": False,
                "reason": "Timeout waiting for tasks",
                "elapsed_minutes": round(elapsed / 60, 1),
            }
        
        # Get current task status
        runs_root = multitasker_home() / "runs"
        tasks = []
        
        if runs_root.exists():
            for d in sorted(runs_root.glob("run_*/"), key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    st = load_state(d.name)
                    if st.get("session_id") == session_id:
                        tasks.append({
                            "run_id": d.name,
                            "status": st.get("status"),
                            "pr_url": st.get("pr_url"),
                        })
                except Exception:
                    continue
        
        if not tasks:
            return {"ok": True, "message": "No tasks found", "tasks": []}
        
        # Count completed vs running
        completed = [t for t in tasks if t["status"] in ("done", "error", "cancelled")]
        running = [t for t in tasks if t["status"] not in ("done", "error", "cancelled")]
        
        # Report progress
        progress = len(completed) / len(tasks) if tasks else 1.0
        await ctx.report_progress(
            progress=progress,
            total=1.0,
            message=f"{len(completed)}/{len(tasks)} tasks complete, {len(running)} running"
        )
        
        # Check if all done
        if not running:
            return {
                "ok": True,
                "message": "All tasks complete",
                "tasks": tasks,
                "elapsed_minutes": round(elapsed / 60, 1),
            }
        
        # Wait before next poll
        await asyncio.sleep(poll_interval)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
