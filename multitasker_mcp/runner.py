from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pexpect

from .models import RunRequest
from .state import append_event, load_state, run_dir, save_state, workspace_dir


def _notify(title: str, message: str) -> None:
    """Send a system notification."""
    if platform.system() == "Darwin":
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True,
        )
    # Could add Linux (notify-send) or Windows support here


def _start_cleanup_watcher(run_id: str, pr_url: str, workspace_dir: str, repo_path: str) -> None:
    """Start a detached process to watch for PR merge and cleanup workspace."""
    import sys
    subprocess.Popen(
        [sys.executable, "-m", "multitasker_mcp.cleanup", run_id, pr_url, workspace_dir, repo_path],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )


@dataclass(frozen=True)
class CommandSpec:
    cmd: str
    args: list[str]
    model_flag: str | None = None
    prompt_flag: str | None = None  # None means positional argument


DEFAULT_CONFIG: dict[str, Any] = {
    "commands": {
        "copilot": {"cmd": "copilot", "args": ["--allow-all-tools", "--allow-all-paths"], "model_flag": "--model", "prompt_flag": "-p"},
        "codex": {"cmd": "codex", "args": ["--dangerously-bypass-approvals-and-sandbox"], "prompt_flag": None},  # positional
        "claude": {"cmd": "claude", "args": ["--dangerously-skip-permissions", "-p"], "prompt_flag": None},  # -p is print, prompt is positional
    },
    # Best-effort defaults; override in ~/.multitasker/config.json as needed.
    "copilot_models": {
        "opus": ["claude-3-5-opus-latest"],
        "gpt": ["gpt-4o"],
        "codex": ["gpt-4o"],
        "gemini": ["gemini-2.0-pro"],
    },
}


def _load_config() -> dict[str, Any]:
    cfg_path = Path(os.path.expanduser("~/.multitasker/config.json"))
    if not cfg_path.exists():
        return DEFAULT_CONFIG

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return DEFAULT_CONFIG

    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg.update(raw)
    cfg["commands"].update(raw.get("commands", {}))
    cfg["copilot_models"].update(raw.get("copilot_models", {}))
    return cfg


def _resolve_command(agent_cli: str, model_family: str | None) -> tuple[list[str], str | None]:
    """Returns (base_command, prompt_flag). prompt_flag is None for positional prompt."""
    cfg = _load_config()
    cmd_cfg = cfg["commands"].get(agent_cli) or DEFAULT_CONFIG["commands"][agent_cli]
    spec = CommandSpec(
        cmd=cmd_cfg["cmd"],
        args=list(cmd_cfg.get("args", [])),
        model_flag=cmd_cfg.get("model_flag"),
        prompt_flag=cmd_cfg.get("prompt_flag"),
    )

    cmd = [spec.cmd, *spec.args]
    if agent_cli == "copilot" and model_family and spec.model_flag:
        models = cfg.get("copilot_models", {}).get(model_family) or []
        if models:
            cmd += [spec.model_flag, models[-1]]
    return cmd, spec.prompt_flag


def _run(cmd: list[str], cwd: Path, log_path: Path) -> int:
    rc, _ = _run_capture(cmd, cwd=cwd, log_path=log_path)
    return rc


def _run_capture(cmd: list[str], cwd: Path, log_path: Path) -> tuple[int, str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "GIT_PAGER": "cat",
        "PAGER": "cat",
        "CI": "1",
    }

    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        text=True,
    )

    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n$ {' '.join(cmd)}\n")
        log.write(p.stdout)
        if p.stdout and not p.stdout.endswith("\n"):
            log.write("\n")

    return p.returncode, p.stdout


def _tail(path: Path, lines: int = 200) -> str:
    if not path.exists():
        return ""
    data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(data[-lines:])


def _format_agent_prompt(req: RunRequest, run_id: str, branch: str) -> str:
    parts: list[str] = []
    parts.append("You are an autonomous CLI coding agent working in a git repository.")
    parts.append(
        "You have FULL approval to make changes, run commands, commit, push, open PRs, and enable auto-merge per instructions."
    )
    parts.append("")
    parts.append(f"Run ID: {run_id}")
    parts.append(f"Branch: {branch}")
    parts.append("")
    parts.append("TASK:")
    parts.append(req.task.goal)
    parts.append("")
    parts.append("When done, commit your changes, push, and create a PR if requested.")
    return "\n".join(parts).strip()


def _find_newest_session(before_sessions: set[str]) -> str | None:
    """Find the newest session ID created after before_sessions snapshot."""
    session_dir = Path.home() / ".copilot" / "session-state"
    if not session_dir.exists():
        return None
    
    current_sessions = {f.stem for f in session_dir.glob("*.jsonl")}
    new_sessions = current_sessions - before_sessions
    
    if not new_sessions:
        return None
    
    # Return the newest by modification time
    newest = max(
        new_sessions,
        key=lambda s: (session_dir / f"{s}.jsonl").stat().st_mtime
    )
    return newest


def _get_existing_sessions() -> set[str]:
    """Get set of existing session IDs."""
    session_dir = Path.home() / ".copilot" / "session-state"
    if not session_dir.exists():
        return set()
    return {f.stem for f in session_dir.glob("*.jsonl")}


def _run_agent(
    cmd: list[str],
    cwd: Path,
    prompt: str,
    log_path: Path,
    prompt_flag: str | None = None,
    resume_session: str | None = None,
    state_callback: Callable[[], None] | None = None,
) -> tuple[int, str | None]:
    """Run agent in non-interactive mode. Returns (exit_code, session_id)."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Snapshot existing sessions to find the new one
    before_sessions = _get_existing_sessions()
    
    # Build command
    if resume_session:
        full_cmd = cmd + ["--resume", resume_session]
    elif prompt_flag:
        full_cmd = cmd + [prompt_flag, prompt]
    else:
        full_cmd = cmd + [prompt]  # positional argument
    
    with log_path.open("a", encoding="utf-8") as logfile:
        if resume_session:
            logfile.write(f"\n$ {' '.join(cmd)} --resume {resume_session}\n")
        else:
            logfile.write(f"\n$ {' '.join(cmd)} {'%s ' % prompt_flag if prompt_flag else ''}'<prompt>'\n")
        logfile.flush()
        
        env = {
            **os.environ,
            "GIT_PAGER": "cat",
            "PAGER": "cat",
        }
        
        logfile.write(f"[Starting process: {' '.join(full_cmd[:3])}...]\n")
        logfile.flush()
        
        process = subprocess.Popen(
            full_cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
            text=True,
        )
        
        # Store PID for signal handler in worker.py
        import multitasker_mcp.worker as worker_module
        worker_module._current_runner_pid = process.pid
        
        logfile.write(f"[Process started with PID {process.pid}]\n")
        logfile.flush()
        
        last_output_time = time.time()
        
        # Stream output to log file with activity tracking
        for line in process.stdout:
            logfile.write(line)
            logfile.flush()
            last_output_time = time.time()
            # Periodic state update callback
            if state_callback:
                state_callback()
        
        process.wait()
        
        logfile.write(f"\n[Process exited with code {process.returncode}]\n")
        logfile.flush()
        
        # Find the session ID that was created/used
        session_id = resume_session or _find_newest_session(before_sessions)
        
        return process.returncode or 0, session_id


# Keep the old interactive version for potential future use with Q&A
def _run_agent_interactive(
    cmd: list[str],
    cwd: Path,
    prompt: str,
    log_path: Path,
    *,
    on_question: Callable[[dict[str, Any]], str] | None = None,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as logfile:
        logfile.write("\n$ " + " ".join(cmd) + "\n")
        logfile.flush()

        child = pexpect.spawn(
            cmd[0],
            cmd[1:],
            cwd=str(cwd),
            env={
                **os.environ,
                "GIT_PAGER": "cat",
                "PAGER": "cat",
                "CI": "1",
            },
            encoding="utf-8",
            codec_errors="replace",
            timeout=None,
        )
        child.logfile = logfile

        # Wait for copilot to be ready, then send prompt with newline to submit
        child.expect([r"Describe a task", r"●", pexpect.TIMEOUT], timeout=30)
        child.sendline(prompt)

        question_pattern = r"(?m)^MULTITASKER_QUESTION:\s*(\{.*\})\s*$"

        # Best-effort auto-answer for common confirmation prompts.
        auto_patterns = [
            r"\(y/n\)",
            r"\(Y/n\)",
            r"\(y/N\)",
            r"\[y/N\]",
            r"\[Y/n\]",
            r"Continue\?",
        ]

        while True:
            i = child.expect([pexpect.EOF, question_pattern, *auto_patterns], timeout=None)
            if i == 0:
                break

            if i == 1:
                try:
                    payload = json.loads(child.match.group(1))
                except Exception:
                    payload = {"id": f"q_{int(time.time())}", "prompt": "(unparseable)"}

                if on_question:
                    answer = on_question(payload)
                else:
                    answer = ""
                child.sendline(answer)
                continue

            child.sendline("y")

        return child.exitstatus or 0


def run_in_background(run_id: str) -> None:
    state = load_state(run_id)
    req = RunRequest.model_validate(state["request"])

    rdir = run_dir(run_id)
    wdir = workspace_dir(run_id)
    log_path = rdir / "run.log"

    def is_cancelled() -> bool:
        return load_state(run_id).get("status") == "cancelled"

    def set_status(status: str, **extra: Any) -> None:
        state.update({"status": status, **extra, "updated_at": time.time()})
        save_state(run_id, state)
        append_event(run_id, {"ts": time.time(), "type": "status", "status": status, **extra})

    try:
        if is_cancelled():
            return

        set_status("cloning")

        repo_path = wdir / "repo"
        if repo_path.exists():
            shutil.rmtree(repo_path)

        _run(["git", "clone", req.repo.url, str(repo_path)], cwd=wdir, log_path=log_path)

        if req.repo.ref:
            _run(["git", "checkout", req.repo.ref], cwd=repo_path, log_path=log_path)

        branch = state.get("branch") or f"multitasker/{run_id}"
        _run(["git", "checkout", "-b", branch], cwd=repo_path, log_path=log_path)
        state["branch"] = branch
        save_state(run_id, state)

        if is_cancelled():
            return

        def on_question(q: dict[str, Any]) -> str:
            qid = str(q.get("id") or f"q_{int(time.time())}")
            state.setdefault("questions", {})[qid] = {**q, "asked_at": time.time()}
            save_state(run_id, state)
            append_event(run_id, {"ts": time.time(), "type": "question", "id": qid})

            if q.get("needs_user"):
                set_status("waiting_for_user", question_id=qid)
                prompt_text = q.get("prompt", "Input needed")[:80]
                _notify("Multitasker Waiting", f"{run_id}: {prompt_text}")
                start = time.time()
                while time.time() - start < 3600:
                    latest = load_state(run_id)
                    ans = (latest.get("questions", {}).get(qid) or {}).get("answer")
                    if ans:
                        state.update(latest)
                        set_status("running_agent")
                        return str(ans)
                    time.sleep(1)
                set_status("running_agent")
                return ""

            choices = q.get("choices")
            if isinstance(choices, list) and choices:
                return str(choices[0])
            return "y"

        set_status("running_agent")
        agent_cmd, prompt_flag = _resolve_command(req.agent.cli, req.agent.model_family)
        prompt = _format_agent_prompt(req, run_id=run_id, branch=branch)

        # Check if we have a session to resume
        resume_session = state.get("agent_session_id")
        
        # Callback to update state periodically during agent execution
        last_update = [time.time()]
        def update_state_periodically():
            now = time.time()
            if now - last_update[0] > 30:  # Update every 30 seconds
                state["updated_at"] = now
                save_state(run_id, state)
                last_update[0] = now
        
        rc, session_id = _run_agent(
            agent_cmd,
            cwd=repo_path,
            prompt=prompt,
            log_path=log_path,
            prompt_flag=prompt_flag,
            resume_session=resume_session,
            state_callback=update_state_periodically,
        )
        
        # Save session ID for potential resume
        if session_id:
            state["agent_session_id"] = session_id
            save_state(run_id, state)
        
        append_event(run_id, {"ts": time.time(), "type": "agent_exit", "code": rc, "session_id": session_id})

        # Check if agent made any commits
        _, git_log = _run_capture(["git", "log", "--oneline", "-1"], cwd=repo_path, log_path=log_path)
        has_commits = bool(git_log.strip())

        if rc != 0 and not has_commits:
            set_status("error", error=f"Agent exited with code {rc} and made no commits", log_tail=_tail(log_path, lines=200), agent_session_id=session_id)
            _notify("Multitasker Error", f"{run_id} agent failed (code {rc})")
            return

        set_status("creating_pr" if req.pr.create else "finalizing")

        pr_output_tail = None
        if req.pr.create:
            _run(["git", "push", "-u", "origin", branch], cwd=repo_path, log_path=log_path)

            pr_cmd = ["gh", "pr", "create", "--head", branch]
            if req.pr.base:
                pr_cmd += ["--base", req.pr.base]
            pr_cmd += ["--title", req.pr.title or req.task.goal[:120]]
            pr_cmd += ["--body", req.pr.body or "Created by multitasker MCP runner."]

            _, pr_out = _run_capture(pr_cmd, cwd=repo_path, log_path=log_path)
            pr_output_tail = pr_out.strip() or _tail(log_path, lines=60)

            m = re.search(r"https://github.com/\S+/pull/\d+", pr_out)
            pr_url = m.group(0) if m else None
            if pr_url:
                state["pr_url"] = pr_url
                save_state(run_id, state)

            if req.merge.auto and pr_url:
                merge_cmd = ["gh", "pr", "merge", "--auto", f"--{req.merge.method}"]
                if not req.merge.require_checks:
                    merge_cmd.append("--admin")  # bypass checks if not required
                merge_cmd.append(pr_url)
                _run(merge_cmd, cwd=repo_path, log_path=log_path)

            if pr_url:
                # Start a detached cleanup watcher process
                _start_cleanup_watcher(run_id, pr_url, str(wdir), str(repo_path))

        set_status("done")

        state["summary"] = {
            "note": "See run.log for full details.",
            "pr": pr_output_tail,
            "log_tail": _tail(log_path, lines=200),
        }
        save_state(run_id, state)
        
        # Notify on completion
        pr_info = f" - PR: {state.get('pr_url', 'none')}" if req.pr.create else ""
        _notify("Multitasker Complete", f"{run_id} finished{pr_info}")

    except Exception as e:
        set_status("error", error=str(e), log_tail=_tail(log_path, lines=200))
        _notify("Multitasker Error", f"{run_id} failed: {str(e)[:50]}")
        return
