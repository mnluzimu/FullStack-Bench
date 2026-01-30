#!/usr/bin/env python3
"""
kill_storm.py  –  brutally terminate a fork/zombie storm such as
"npm run dev" runaway trees.

Usage from shell:
    sudo python3 kill_storm.py "npm run dev"
or import and call:
    from kill_storm import nuke_processes
    nuke_processes("npm run dev")
"""

import os
import re
import signal
import subprocess
import sys
from typing import Iterable

PATTERN = re.compile(r".*")  # placeholder, replaced at runtime


def _pids_with_psutil(pattern: re.Pattern) -> Iterable[int]:
    """Yield PIDs whose cmdline matches the regex."""
    import psutil  # noqa: WPS433 (security—only stdlib or trusted)
    myself = os.getpid()
    for p in psutil.process_iter(attrs=("pid", "cmdline")):
        if p.info["pid"] == myself:
            continue
        try:
            cmd = " ".join(p.info["cmdline"])
        except (psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if pattern.search(cmd):
            yield p.info["pid"]


def _pids_with_ps(pattern: re.Pattern) -> Iterable[int]:
    """Portable fallback that uses plain `ps` parsing."""
    result = subprocess.run(
        ["ps", "-eo", "pid,args"], text=True, capture_output=True, check=True
    )
    myself = str(os.getpid())
    for line in result.stdout.splitlines()[1:]:
        pid, *cmd = line.strip().split(maxsplit=1)
        if pid == myself or not cmd:
            continue
        if pattern.search(cmd[0]):
            yield int(pid)


def nuke_processes(pattern_str: str, sig: int = signal.SIGKILL) -> None:
    """
    Send `sig` to every process whose full command line
    matches `pattern_str` (interpreted as a regular expression).

    Requires root (or ownership of the target PIDs) to deliver SIGKILL.
    """
    print(f"Cleaning up processes matching pattern: {pattern_str}", file=sys.stderr)
    global PATTERN
    PATTERN = re.compile(pattern_str)

    try:
        import psutil  # noqa: WPS433
        pid_iter = _pids_with_psutil(PATTERN)
    except ModuleNotFoundError:
        pid_iter = _pids_with_ps(PATTERN)

    victims = list(pid_iter)
    if not victims:
        print("No matching processes found.", file=sys.stderr)
        return

    for pid in victims:
        try:
            os.kill(pid, sig)
            # print(f"Sent signal {sig} to PID {pid}")
        except ProcessLookupError:  # already exited
            pass
        except PermissionError as exc:
            print(f"Permission error on PID {pid}: {exc}", file=sys.stderr)

    print(f"Total processes signalled: {len(victims)}")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("⚠️  Run as root (sudo) to guarantee SIGKILL delivery.", file=sys.stderr)
    pattern = r"npm run dev"
    nuke_processes(pattern)