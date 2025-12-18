from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any


def multitasker_home() -> Path:
    base = Path(os.path.expanduser("~/.multitasker"))
    base.mkdir(parents=True, exist_ok=True)
    (base / "runs").mkdir(parents=True, exist_ok=True)
    (base / "workspaces").mkdir(parents=True, exist_ok=True)
    return base


def new_run_id() -> str:
    return f"run_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def run_dir(run_id: str) -> Path:
    d = multitasker_home() / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def workspace_dir(run_id: str) -> Path:
    d = multitasker_home() / "workspaces" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, data: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(path)


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, indent=2, sort_keys=True))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def append_event(run_id: str, event: dict[str, Any]) -> None:
    p = run_dir(run_id) / "events.jsonl"
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def load_state(run_id: str) -> dict[str, Any]:
    p = run_dir(run_id) / "state.json"
    if not p.exists():
        return {"run_id": run_id, "status": "unknown"}
    return read_json(p)


def save_state(run_id: str, state: dict[str, Any]) -> None:
    write_json(run_dir(run_id) / "state.json", state)
