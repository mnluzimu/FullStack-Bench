#!/usr/bin/env python3
"""
DBWatcher – follow a PostgreSQL ≥10 CSV log and return all statements that
appeared *after* a check-point.  Now robust when no log directory / no log
files exist yet.

Usage
-----

    >>> w = DBWatcher("/var/lib/postgresql/14/main")
    >>> w.set_ckpt()               # mark “now” (gracefully does nothing
    ...                             # if there is nothing to mark)
    >>> # … application runs …
    >>> for q in w.get_new_entries():
    ...     print(q["sql"], q["duration_ms"])
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any, Dict, List, Iterable
import re
import itertools

def _utf8_open(path: pathlib.Path, mode="r"):
    """
    Open text file with a deterministic codec.
    errors='replace' => bad bytes become � instead of crashing.
    """
    return path.open(mode, encoding="utf-8", errors="replace")


# Helper: does the first cell look like an ISO timestamp?
def _looks_like_log_row(first_cell: str) -> bool:
    # yyyy-mm-dd hh:mm:ss...
    return first_cell[:4].isdigit() and first_cell[4] == "-"

# Typical SQL keywords you want to detect
_SQL_KEYWORDS = (
    "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "MERGE", "WITH", "BEGIN", "COMMIT", "ROLLBACK", "EXPLAIN",
    "VACUUM", "COPY", "GRANT", "REVOKE"
)

# Regex   ① optional leading “statement:”  ② one of the keywords ③ word boundary
_SQL_RE = re.compile(
    r"\b(?:%s)\b" % "|".join(_SQL_KEYWORDS),   # any keyword, surrounded by word boundaries
    re.IGNORECASE | re.DOTALL,
)

def filter_sql_entries(
    entries: List[Dict[str, Any]],
    *,
    keep_durations: bool = False
) -> List[Dict[str, Any]]:
    """
    Return only those items whose msg begins with (or later contains)
    a recognised SQL command.  If *keep_durations* is True, lines that
    start with “duration:” are also retained, because they belong to the
    immediately-preceding statement in Postgres logs.

    Parameters
    ----------
    entries : list of {"ts": ..., "msg": ...}
    keep_durations : bool (default False)
        Keep rows whose msg starts with "duration:".

    Examples
    --------
    >>> recent = db_watcher.get_new_entries()
    >>> sql_only = filter_sql_entries(recent)
    """
    out: List[Dict[str, Any]] = []

    for e in entries:
        m = e.get("message", "")
        if _SQL_RE.search(m):
            out.append(e)
        elif keep_durations and m.lstrip().lower().startswith("duration:"):
            out.append(e)

    return out

class DBWatcher:
    """
    Parameters
    ----------
    data_dir : str | Path
        PostgreSQL *data* directory (the one that contains PG_VERSION).

    Notes
    -----
    • Works for PostgreSQL 10–15 (tested with 14).  
    • Expects `log_destination = 'csvlog'`.  
    • Every call to `get_new_entries()` also advances the checkpoint.
    """

    # ────────────────────────────────────────────────────────────────
    # construction helpers
    # ────────────────────────────────────────────────────────────────
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        print(f"Initializing watcher at {self.data_dir}")
        self.log_dir = self._find_log_dir()
        self._ckpt: Dict[Path, int] = {}  # {logfile → byte_offset}
        self._header_cache: Dict[Path, List[str]] = {}

    def _find_log_dir(self) -> Path:
        """
        Return the directory PostgreSQL will *eventually* write CSV logs to.
        We do **not** require the directory to exist yet – that is the whole
        point of the edge-case handling.
        """
        for name in ("log", "pg_log"):
            p = self.data_dir / name
            if p.exists():
                return p
        # default – the server will create it on first use
        return self.data_dir / "log"

    # ────────────────────────────────────────────────────────────────
    # public API
    # ────────────────────────────────────────────────────────────────
    def set_ckpt(self) -> None:
        # self._ckpt = {p: sum(1 for _ in p.open()) for p in self._csv_logs()}
        # print(self._csv_logs())
        self._ckpt = {p: len(self._read_from(p, 0)) for p in self._csv_logs()}
        # print(f"Checkpoint set: {self._ckpt}")

    def get_new_entries(self) -> List[Dict[str, Any]]:
        if not self.log_dir.exists():
            return []

        entries: List[Dict[str, Any]] = []

        # for path in sorted(self._csv_logs(), key=lambda p: p.stat().st_mtime)[-1]:
        path = sorted(self._csv_logs(), key=lambda p: p.stat().st_mtime)[-1]
        start = self._ckpt.get(path, 0)
        new_rows = self._read_from(path, start)
        entries.extend(new_rows)

        # we have read `len(new_rows)` additional CSV rows
        self._ckpt[path] = start + len(new_rows)     # <- keep *line* count

        # forget vanished files
        self._ckpt = {p: off for p, off in self._ckpt.items() if p.exists()}
        
        # print(f"DBWatcher found {len(entries)} new log entries, filtering SQL...")
        # print(f"Sample entries: {entries}")
        return filter_sql_entries(entries)

    # ────────────────────────────────────────────────────────────────
    # internal helpers
    # ────────────────────────────────────────────────────────────────
    def _csv_logs(self) -> List[Path]:
        """
        Return a list of *.csv* files or an empty list if none exists yet.
        """
        if not self.log_dir.exists():
            return []
        return list(self.log_dir.glob("*.csv"))

    def _read_from(self, path: str, start_pos: int) -> List[Dict[str, Any]]:
        """
        Read log lines starting at `start_pos` and return a list of dicts with at
        least   {"ts": ..., "msg": ...}
        """
        path = Path(path)
        out: List[Dict[str, Any]] = []

        with _utf8_open(path) as fh:
            reader = csv.reader(fh)

            # Peek at first row
            first_row = next(reader, None)
            if first_row is None:                      # empty file
                return out

            # ---------- 1. Figure out column indices ----------
            if _looks_like_log_row(first_row[0]):
                # No header → Postgres fixed layout
                IDX_TS  = 0     # log_time
                IDX_MSG = 13    # message (14th field, zero-based 13)
                header_present = False
            else:
                # There *is* a header
                header_present = True
                names = [c.strip() for c in first_row]
                try:
                    IDX_TS  = names.index("ts")
                except ValueError:
                    IDX_TS  = names.index("log_time")
                try:
                    IDX_MSG = names.index("msg")
                except ValueError:
                    IDX_MSG = names.index("message")

            # ---------- 2. Iterate again (include the first row) ----------
            if not header_present:
                # we already consumed first_row as data
                data_iter: Iterable[List[str]] = (first_row, *reader)
            else:
                data_iter = reader                    # header already skipped

            pos = 0
            for row in data_iter:
                # print({"timestamp": row[IDX_TS], "message": row[IDX_MSG]})
                if pos >= start_pos:
                    try:
                        out.append(
                            {"timestamp": row[IDX_TS], "message": row[IDX_MSG]}
                        )
                    except IndexError:
                        # malformed line → skip or log a warning
                        continue
                pos += 1
        return out