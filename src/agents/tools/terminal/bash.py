#!/usr/bin/env python3
"""
terminal_bash_slim.py
A lightweight tmux-backed bash wrapper with robust end-of-command detection.
No PS1 hacking – completion is detected by a unique sentinel line printed
after each command.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from enum import Enum, auto
from pathlib import Path
from typing import Any, Iterable

import bashlex
import libtmux

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
POLL_INTERVAL   = 0.5            # seconds
CAPTURE_TAIL    = 400            # lines to read from bottom of pane
HISTORY_LIMIT   = 10_000         # tmux scroll-back
NO_CHANGE_TO    = 30             # soft timeout when blocking=False

DONE_RE = re.compile(r"###DONE-(?P<id>[a-f0-9]{8})-(?P<code>\d+)###")

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def split_bash_commands(cmd: str) -> list[str]:
    """Return *top-level* commands separated by ≠ escaped `; | &`."""
    if not cmd.strip():
        return [""]
    try:
        nodes = bashlex.parse(cmd)
    except Exception:
        return [cmd]

    pieces, end = [], 0
    for n in nodes:
        if n.pos[0] > end:
            pieces.append(cmd[end : n.pos[0]].rstrip())
        pieces.append(cmd[n.pos[0] : n.pos[1]].rstrip())
        end = n.pos[1]
    tail = cmd[end:].rstrip()
    if tail:
        pieces.append(tail)
    return pieces


def escape_bash_special_chars(command: str) -> str:
    """Double-escape \\;&|>< outside of quotes so tmux sees the literal char."""
    try:
        root = bashlex.parse(command)
    except Exception:
        return command

    out, last = [], 0

    def walk(node: Any) -> None:
        nonlocal last
        if node.kind == "word":
            raw, last = command[last : node.pos[0]], node.pos[0]
            out.append(re.sub(r"\\([;&|><])", r"\\\\\1", raw))
            out.append(command[node.pos[0] : node.pos[1]])
            last = node.pos[1]
        for ch in getattr(node, "parts", []):
            walk(ch)

    for n in root:
        walk(n)
    out.append(command[last:])
    return "".join(out)


class _Status(Enum):
    RUNNING = auto()
    COMPLETE = auto()
    SOFT_TIMEOUT = auto()
    HARD_TIMEOUT = auto()


# --------------------------------------------------------------------------- #
#  Public dataclasses (kept identical to the original contract)
# --------------------------------------------------------------------------- #
class CmdRunAction:          # minimal stub for demo / type hints
    def __init__(
        self,
        command: str,
        *,
        source: str | None = None,
        is_input: bool = False,
        blocking: bool = True,
        timeout: int | None = None,
    ):
        self.command = command
        self.source = source
        self.is_input = is_input
        self.blocking = blocking
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"CmdRunAction (source={self.source}, is_input={self.is_input})"


class CmdOutputMetadata:     # minimal stub
    def __init__(self, *, exit_code: int | None = None, working_dir: str | None = None):
        self.exit_code = exit_code
        self.working_dir = working_dir
        self.suffix = ""

    def __repr__(self) -> str:
        return json.dumps(self.__dict__, indent=2)

    def to_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "working_dir": self.working_dir,
            "suffix": self.suffix,
        }


class CmdOutputObservation:  # minimal stub
    def __init__(self, command: str, content: str, metadata: CmdOutputMetadata):
        self.command = command
        self.content = content
        self.metadata = metadata

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "content": self.content,
            "metadata": self.metadata.to_dict(),
        }


class ErrorObservation(CmdOutputObservation):
    def __init__(self, content: str):
        super().__init__("", content, CmdOutputMetadata())


# --------------------------------------------------------------------------- #
# Core class
# --------------------------------------------------------------------------- #
class BashSession:
    """One tmux-backed bash session that can execute a single command at a time."""

    def __init__(
        self,
        work_dir: str | Path,
        username: str | None = None,
        *,
        no_change_timeout: int = NO_CHANGE_TO,
    ):
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.user = username
        self.no_change_timeout = no_change_timeout

        self._srv: libtmux.Server | None = None
        self._session: libtmux.Session | None = None
        self._pane: libtmux.Pane | None = None
        self._status = _Status.COMPLETE
        self._cwd = str(self.work_dir)
        self._boot_tmux()

    # ---- life-cycle ------------------------------------------------------ #
    def __enter__(self):
        self._boot_tmux()
        return self

    def __exit__(self, *_exc):
        self.close()
        return False  # Don't suppress exceptions

    def close(self) -> None:
        """Close the bash session and clean up resources."""
        # Kill only the specific session created by this BashSession
        # This preserves the tmux server and other sessions
        if self._session:
            try:
                self._session.kill_session()
            except Exception:
                # Session might already be dead, ignore errors
                pass
        # Clear references
        self._srv = None
        self._session = None
        self._pane = None
        self._status = _Status.COMPLETE

    # ---- public API ------------------------------------------------------ #
    @property
    def cwd(self) -> str:
        return self._cwd

    def _refresh_cwd(self) -> None:
        """Update self._cwd from the tmux pane (if available)."""
        if self._pane is None:
            return
        try:                               # libtmux ≥0.24: Pane.current_path
            new = self._pane.current_path
        except AttributeError:             # fallback for older libtmux
            new = self._pane.cmd(
                "display-message", "-p", "#{pane_current_path}"
            ).stdout[0]
        if new:                            # only overwrite on success
            self._cwd = os.path.expanduser(new)

    def execute(self, action: CmdRunAction) -> CmdOutputObservation | ErrorObservation:
        if self._pane is None:
            raise RuntimeError("session not initialised")

        raw_cmd = action.command.rstrip("\n")
        # ---------------------------------------------------------------- #
        #  Immediate interrupt – never wrap, never wait for a sentinel
        # ---------------------------------------------------------------- #
        if raw_cmd == "C-c":
            self._pane.send_keys("C-c", enter=False)   # send SIGINT
            time.sleep(0.05)                           # give bash a beat
            captured = self._capture()
            # clear screen & history so next command starts clean
            self._pane.send_keys("reset", enter=True)
            self._pane.cmd("clear-history")
            self._status = _Status.COMPLETE
            meta = CmdOutputMetadata(exit_code=None, working_dir=self._cwd)
            meta.suffix = "\n[interrupted by C-c]"
            return CmdOutputObservation(raw_cmd, captured.rstrip(), meta)

        # -------- safety checks ------------------------------------------- #
        if len(split_bash_commands(raw_cmd)) > 1 and not action.is_input:
            return ErrorObservation(
                "ERROR: Multiple top-level commands detected. "
                "Chain them with `&&` or run them separately."
            )

        if (
            self._status == _Status.RUNNING
            and not (action.is_input or raw_cmd == "C-c")
        ):
            return ErrorObservation(
                "ERROR: Previous command still running – send `is_input=true` "
                "or interrupt (C-c) first."
            )

        # -------- detect background commands ------------------------------ #
        # Check if this is a background command (ends with & but not escaped)
        is_background_cmd = (
            not action.is_input 
            and raw_cmd.rstrip().endswith('&') 
            and not raw_cmd.rstrip().endswith('\\&')
        )

        # -------- build what we send to the pane ------------------------- #
        if action.is_input:
            send_text = raw_cmd
        else:
            # For background commands, send without sentinels and return immediately
            if is_background_cmd:
                send_text = raw_cmd
                self._send_keys(send_text, ctrl=False)
                # For background commands, return immediately with a special exit code
                time.sleep(1.0)  # Give a moment for the command to start
                captured = self._capture()
                captured_processed = captured[captured.rfind(raw_cmd) + len(raw_cmd) :]
                captured_processed = captured_processed.split("root@")[0].rstrip() + "\n[background process started]"
                self._status = _Status.COMPLETE  # Background commands don't block the session
                meta = CmdOutputMetadata(exit_code=0, working_dir=self._cwd)
                return CmdOutputObservation(raw_cmd, captured_processed, meta)
            else:
                # For regular foreground commands, use the existing sentinel mechanism
                self._sentinel_id = uuid.uuid4().hex[:8]
                self._start_tag   = f"###START-{self._sentinel_id}###"
                self._done_tag    = f"###DONE-{self._sentinel_id}-"
                wrapped = (
                    f'printf "\\n{self._start_tag}\\n" ; '
                    f"{raw_cmd} ; "
                    f'printf "\\n{self._done_tag}$?###\\n"'
                )
                send_text = wrapped
                self._status = _Status.RUNNING
                
        self._send_keys(send_text, ctrl=False)

        start = time.time()
        last_change = start
        buf = ""

        while True:
            time.sleep(POLL_INTERVAL)
            new_buf = self._capture()
            self._refresh_cwd()
            # print("--new_buf--")
            # print(new_buf)
            # print("--end new_buf--")
            if new_buf != buf:
                buf, last_change = new_buf, time.time()

            # -------- look for *our* sentinel ----------------------------- #
            # Slice buffer so we only look at output *after* our START tag
            # print("self.start_tag:", self._start_tag)
            start_pos = buf.rfind(self._start_tag)
            # print("start_pos:", start_pos)
            sliced = buf
            if start_pos >= 0:
                sliced = buf[start_pos + len(self._start_tag):]
                # print("sliced: ", sliced)
                m = DONE_RE.search(sliced)
                if m and m.group("id") == self._sentinel_id:
                    exit_code = int(m.group("code"))
                    return self._wrap_complete(raw_cmd, sliced, exit_code)

            # -------- soft / hard timeouts -------------------------------- #
            if (
                not action.blocking
                and time.time() - last_change > self.no_change_timeout
            ):
                return self._wrap_timeout(raw_cmd, sliced, soft=True)

            # -------- pause if nothing new appeared for a while ------------- #
            if time.time() - last_change > self.no_change_timeout:
                # do NOT mark the session COMPLETE – we’re still inside
                # the same command, just waiting for user input.
                meta = CmdOutputMetadata(exit_code=-1, working_dir=self._cwd)
                meta.suffix = (
                    f"\n[waiting >{self.no_change_timeout}s - send "
                    "is_input=True or C-c]" )
                return CmdOutputObservation(raw_cmd, sliced.rstrip(), meta)

            if action.timeout and time.time() - start > action.timeout:
                return self._wrap_timeout(raw_cmd, buf, soft=False)

    # --------------------------------------------------------------------- #
    # internals
    # --------------------------------------------------------------------- #
    def _boot_tmux(self) -> None:
        self._srv = libtmux.Server()
        shell_cmd = "/bin/bash" if self.user not in {"root", "fullstack"} else f"su {self.user} -"
        # Store the session reference so we can kill it later
        self._session = self._srv.new_session(
            session_name=f"bash-{uuid.uuid4()}",
            start_directory=str(self.work_dir),
            kill_session=False,
            x=160, y=48,
        )
        self._session.set_option("history-limit", str(HISTORY_LIMIT), global_=True)
        win = self._session.new_window(
            window_name="bash",
            window_shell=shell_cmd,
            start_directory=str(self.work_dir),
            attach=True,
        )
        self._pane = win.active_pane
        time.sleep(0.1)  # wait for initial prompt
        self._refresh_cwd()
        self._pane.cmd("clear-history")

    # ------------------------------------------------------------------ #
    def _send_keys(self, text: str, *, ctrl: bool) -> None:
        if not text:
            return
        text = escape_bash_special_chars(text)
        self._pane.send_keys(text, enter=not ctrl)

    def _capture(self) -> str:
        return "\n".join(
            l.rstrip()
            for l in self._pane.cmd("capture-pane", "-J", "-pS", f"-{CAPTURE_TAIL}").stdout
        )

    # ------------------------------------------------------------------ #
    def _wrap_complete(self, cmd: str, buf: str, exit_code: int) -> CmdOutputObservation:
        self._refresh_cwd()
        # print("buf: ", buf)
        out = buf.rsplit(f"{self._done_tag}{exit_code}###", 1)[0].rstrip()
        # print("out: ", out)
        meta = CmdOutputMetadata(exit_code=exit_code, working_dir=self._cwd)
        meta.suffix = f"\n[exit {exit_code}]"
        self._status = _Status.COMPLETE

        # clear screen *and* scroll-back so old sentinels vanish
        self._pane.send_keys("reset", enter=True)
        time.sleep(0.05)
        self._pane.cmd("clear-history")
        return CmdOutputObservation(cmd, out, meta)

    def _wrap_timeout(self, cmd: str, buf: str, *, soft: bool) -> CmdOutputObservation:
        kind = "no new output" if soft else "hard timeout"
        self._refresh_cwd()
        meta = CmdOutputMetadata()
        meta.suffix = f"\n[{kind}]"
        self._status = _Status.SOFT_TIMEOUT if soft else _Status.HARD_TIMEOUT
        return CmdOutputObservation(cmd, buf.rstrip(), meta)


# --------------------------------------------------------------------------- #
# Demo usage                                                                  #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    print("Type 'exit' to quit.  Prefix interactive replies with '>' (e.g. '>y').")
    sh = BashSession(Path.cwd(), "root")

    try:
        while True:
            raw = input("$ ").rstrip("\n")
            if raw == "exit":
                break
            is_input = raw.startswith(">")
            cmd = raw[1:].lstrip() if is_input else raw
            obs = sh.execute(CmdRunAction(
                command=cmd,
                is_input=is_input,
                blocking=True,
                timeout=600,  # 10 min per command for demo
            ))
            print("============== command ==============")
            print(obs.command)
            print("============== observation ==============")
            print(obs.content)
            print("=============== metadata ================")
            print(obs.metadata)
            print("=========================================")
    except Exception as exc:
        print(f"Error: {exc}")
    finally:
        sh.close()
        print("Session closed.")
