from __future__ import annotations

import json
import os
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


@dataclass(frozen=True)
class CommandSpec:
    cmd: str
    args: list[str]
    model_flag: str | None = None


DEFAULT_CONFIG: dict[str, Any] = {
    "commands": {
        "copilot": {"cmd": "co", "args": [], "model_flag": "--model"},
        "codex": {"cmd": "cx", "args": []},
        "claude": {"cmd": "cc", "args": []},
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


def _resolve_command(agent_cli: str, model_family: str | None) -> list[str]:
    cfg = _load_config()
    cmd_cfg = cfg["commands"].get(agent_cli) or DEFAULT_CONFIG["commands"][agent_cli]
    spec = CommandSpec(
        cmd=cmd_cfg["cmd"],
        args=list(cmd_cfg.get("args", [])),
        model_flag=cmd_cfg.get("model_flag"),
    )

    cmd = [spec.cmd, *spec.args]
    if agent_cli == "copilot" and model_family and spec.model_flag:
        models = cfg.get("copilot_models", {}).get(model_family) or []
        if models:
            cmd += [spec.model_flag, models[-1]]
    return cmd


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
    parts.append(
        "If you need human input, emit a single line starting with MULTITASKER_QUESTION: followed by a JSON object with fields: {id,prompt,choices?,needs_user:true}."
    )
    parts.append("")
    parts.append(f"Run ID: {run_id}")
    parts.append(f"Branch: {branch}")
    parts.append("")
    parts.append("TASK")
    parts.append(f"Goal: {req.task.goal}")
    if req.task.context:
        parts.append(f"Context: {req.task.context}")
    if req.task.requirements:
        parts.append("Requirements:")
        parts += [f"- {x}" for x in req.task.requirements]
    if req.task.acceptance_criteria:
        parts.append("Acceptance criteria:")
        parts += [f"- {x}" for x in req.task.acceptance_criteria]
    parts.append("")
    parts.append("Workflow:")
    parts.append("- Implement the change.")
    parts.append("- Run existing tests/linters if present (only what's already in the repo).")
    parts.append("- Ensure changes are committed to the current branch.")
    parts.append("- After opening a PR, monitor PR status and address review comments when they make sense, then push updates.")
    parts.append("- Finish by printing a short human-readable summary of what changed and why.")
    return "\n".join(parts).strip() + "\n"


def _run_agent_interactive(
    cmd: list[str],
    cwd: Path,
    prompt: str,
    log_path: Path,
    *,
    on_question: Callable[[dict[str, Any]], str] | None = None,
) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as rawlog:
        rawlog.write(("\n$ " + " ".join(cmd) + "\n").encode("utf-8"))
        rawlog.flush()

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
        child.logfile = rawlog

        child.send(prompt)

        question_pattern = r"(?m)^MULTITASKER_QUESTION:\\s*(\\{.*\\})\\s*$"

        # Best-effort auto-answer for common confirmation prompts.
        auto_patterns = [
            r"\\(y/n\\)",
            r"\\(Y/n\\)",
            r"\\(y/N\\)",
            r"\\[y/N\\]",
            r"\\[Y/n\\]",
            r"Continue\\?",
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

    def set_status(status: str, **extra: Any) -> None:
        state.update({"status": status, **extra, "updated_at": time.time()})
        save_state(run_id, state)
        append_event(run_id, {"ts": time.time(), "type": "status", "status": status, **extra})

    try:
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

        def on_question(q: dict[str, Any]) -> str:
            qid = str(q.get("id") or f"q_{int(time.time())}")
            state.setdefault("questions", {})[qid] = {**q, "asked_at": time.time()}
            save_state(run_id, state)
            append_event(run_id, {"ts": time.time(), "type": "question", "id": qid})

            if q.get("needs_user"):
                set_status("waiting_for_user", question_id=qid)
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
        agent_cmd = _resolve_command(req.agent.cli, req.agent.model_family)
        prompt = _format_agent_prompt(req, run_id=run_id, branch=branch)

        rc = _run_agent_interactive(
            agent_cmd,
            cwd=repo_path,
            prompt=prompt,
            log_path=log_path,
            on_question=on_question,
        )
        append_event(run_id, {"ts": time.time(), "type": "agent_exit", "code": rc})

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
                merge_cmd = ["gh", "pr", "merge", "--auto", f"--{req.merge.method}", pr_url]
                _run(merge_cmd, cwd=repo_path, log_path=log_path)

            if pr_url:
                def monitor() -> None:
                    start = time.time()
                    while time.time() - start < 86400:
                        rc, out = _run_capture(
                            ["gh", "pr", "view", pr_url, "--json", "state,mergedAt,url"],
                            cwd=repo_path,
                            log_path=log_path,
                        )
                        if rc == 0:
                            try:
                                data = json.loads(out)
                            except Exception:
                                data = {}
                            if data.get("mergedAt") or data.get("state") == "MERGED":
                                append_event(run_id, {"ts": time.time(), "type": "merged", "url": pr_url})
                                try:
                                    shutil.rmtree(wdir)
                                except Exception:
                                    pass
                                state["workspace_cleaned"] = True
                                save_state(run_id, state)
                                break
                        time.sleep(60)

                if req.merge.auto:
                    set_status("waiting_for_merge", pr_url=pr_url)
                    monitor()
                else:
                    threading.Thread(target=monitor, name=f"monitor-{run_id}", daemon=True).start()

        set_status("done")

        state["summary"] = {
            "note": "See run.log for full details.",
            "pr": pr_output_tail,
            "log_tail": _tail(log_path, lines=200),
        }
        save_state(run_id, state)

    except Exception as e:
        set_status("error", error=str(e), log_tail=_tail(log_path, lines=200))
        return
