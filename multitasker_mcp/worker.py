#!/usr/bin/env python3
"""Worker process for running background tasks."""
from __future__ import annotations

import signal
import sys

# Global reference to allow signal handler to access it
_current_runner_pid: int | None = None


def _handle_sigterm(signum, frame):
    """Handle SIGTERM by cleaning up and exiting."""
    import os
    if _current_runner_pid:
        try:
            os.kill(_current_runner_pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    sys.exit(0)


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <run_id>", file=sys.stderr)
        sys.exit(1)
    
    # Set up signal handler for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_sigterm)
    
    run_id = sys.argv[1]
    
    from .runner import run_in_background
    run_in_background(run_id)


if __name__ == "__main__":
    main()
