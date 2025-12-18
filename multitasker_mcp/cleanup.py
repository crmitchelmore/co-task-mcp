#!/usr/bin/env python3
"""Cleanup watcher - monitors PR for merge and cleans up workspace."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .state import append_event, load_state, save_state


def watch_and_cleanup(run_id: str, pr_url: str, workspace_dir: str, repo_path: str) -> None:
    """Watch a PR and cleanup the workspace when it's merged."""
    max_wait = 7 * 24 * 60 * 60  # 7 days
    poll_interval = 5 * 60  # 5 minutes
    start = time.time()
    
    while time.time() - start < max_wait:
        try:
            result = subprocess.run(
                ["gh", "pr", "view", pr_url, "--json", "state,mergedAt,closedAt"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # Check if merged
                if data.get("mergedAt") or data.get("state") == "MERGED":
                    append_event(run_id, {"ts": time.time(), "type": "merged", "url": pr_url})
                    _cleanup_workspace(run_id, workspace_dir)
                    return
                
                # Check if closed without merge
                if data.get("closedAt") and data.get("state") == "CLOSED":
                    append_event(run_id, {"ts": time.time(), "type": "closed", "url": pr_url})
                    # Don't cleanup - user may want to reopen or reference the work
                    return
                    
        except Exception:
            pass  # Ignore errors, will retry
        
        time.sleep(poll_interval)


def _cleanup_workspace(run_id: str, workspace_dir: str) -> None:
    """Remove the workspace directory and update state."""
    try:
        wdir = Path(workspace_dir)
        if wdir.exists():
            shutil.rmtree(wdir)
        
        state = load_state(run_id)
        state["workspace_cleaned"] = True
        state["workspace_cleaned_at"] = time.time()
        save_state(run_id, state)
    except Exception:
        pass  # Best effort cleanup


def main() -> None:
    if len(sys.argv) != 5:
        print(f"Usage: {sys.argv[0]} <run_id> <pr_url> <workspace_dir> <repo_path>", file=sys.stderr)
        sys.exit(1)
    
    run_id, pr_url, workspace_dir, repo_path = sys.argv[1:5]
    watch_and_cleanup(run_id, pr_url, workspace_dir, repo_path)


if __name__ == "__main__":
    main()
