from __future__ import annotations

import threading
import time
from typing import Any

from fastmcp import FastMCP

from .models import AnswerQuestionRequest, RunRequest, RunResponse, StatusRequest, TailLogsRequest
from .runner import run_in_background
from .state import append_event, load_state, multitasker_home, new_run_id, run_dir, save_state

mcp = FastMCP(name="multitasker")


def _start_thread(target, *, name: str) -> None:
    t = threading.Thread(target=target, name=name, daemon=True)
    t.start()


@mcp.tool(name="repo_task.run")
def repo_task_run(req: RunRequest) -> dict[str, Any]:
    run_id = new_run_id()
    state: dict[str, Any] = {
        "run_id": run_id,
        "created_at": time.time(),
        "updated_at": time.time(),
        "status": "queued",
        "request": req.model_dump(),
        "questions": {},
    }
    save_state(run_id, state)
    append_event(run_id, {"ts": time.time(), "type": "created"})

    _start_thread(lambda: run_in_background(run_id), name=f"run-{run_id}")
    return RunResponse(run_id=run_id).model_dump()


@mcp.tool(name="repo_task.status")
def repo_task_status(req: StatusRequest) -> dict[str, Any]:
    return load_state(req.run_id)


@mcp.tool(name="repo_task.tail_logs")
def repo_task_tail_logs(req: TailLogsRequest) -> dict[str, Any]:
    p = run_dir(req.run_id) / "run.log"
    if not p.exists():
        return {"run_id": req.run_id, "log": ""}

    data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"run_id": req.run_id, "log": "\n".join(data[-req.lines :])}


@mcp.tool(name="repo_task.answer")
def repo_task_answer(req: AnswerQuestionRequest) -> dict[str, Any]:
    state = load_state(req.run_id)
    q = state.setdefault("questions", {}).setdefault(req.question_id, {})
    q["answer"] = req.answer
    q["answered_at"] = time.time()
    save_state(req.run_id, state)
    append_event(req.run_id, {"ts": time.time(), "type": "answer", "id": req.question_id})
    return {"ok": True}


@mcp.tool(name="repo_task.list_runs")
def repo_task_list_runs(limit: int = 20) -> dict[str, Any]:
    runs_root = multitasker_home() / "runs"
    items: list[dict[str, Any]] = []

    for d in sorted(runs_root.glob("run_*/"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            rid = d.name
            st = load_state(rid)
            items.append(
                {
                    "run_id": rid,
                    "status": st.get("status"),
                    "created_at": st.get("created_at"),
                    "updated_at": st.get("updated_at"),
                    "pr_url": st.get("pr_url"),
                }
            )
        except Exception:
            continue
        if len(items) >= limit:
            break

    return {"runs": items}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
