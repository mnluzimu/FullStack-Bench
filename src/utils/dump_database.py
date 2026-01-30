# pip install psycopg2-binary
import time
from typing import Dict, List, Any

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


# --------------------------------------------------------------------------- #
# 1. Helper: connect with retry                                               #
# --------------------------------------------------------------------------- #
def _connect_with_retry(
    db_config: Dict[str, str],
    timeout: int = 60,
    delay: float = 1.0,
) -> psycopg2.extensions.connection:
    """
    Keep trying to open a psycopg2 connection for *timeout* seconds.
    """
    deadline = time.time() + timeout

    while True:
        try:
            return psycopg2.connect(
                host=db_config["db_host"],
                port=db_config["db_port"],
                user=db_config["db_username"],
                password=db_config["db_password"],
                dbname=db_config["db_name"],
            )
        except psycopg2.OperationalError as exc:
            # Give up when the overall timeout has elapsed
            if time.time() >= deadline:
                raise RuntimeError(
                    f"Could not connect to PostgreSQL after {timeout}s"
                ) from exc

            # Optional: comment-out the next line to silence the log
            print(f"[db-retry] {exc}. Retrying in {delay:.1f}s…")

            time.sleep(delay)


# --------------------------------------------------------------------------- #
# 2. Main routine: dump_database                                              #
# --------------------------------------------------------------------------- #
def dump_database(
    db_config: Dict[str, str],
    limit: int = 5,
    connect_timeout: int = 60,
) -> Dict[str, Dict[str, Any]]:
    """
    Scan every table and return at most *limit* rows per table.

    Output format:
    {
        "schema.table": {
            "columns": List[str],      #  <-- NEW
            "total_rows": int,
            "truncated": bool,
            "rows": List[dict]
        },
        ...
    }
    """
    result: Dict[str, Dict[str, Any]] = {}

    conn = _connect_with_retry(db_config, timeout=connect_timeout)
    try:
        with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Discover ordinary user tables
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )

            for t in cur.fetchall():
                schema, table = t["table_schema"], t["table_name"]
                identifier = f"{schema}.{table}"

                # ------------------------------------------------------------------
                # 1. Column names (metadata)
                # ------------------------------------------------------------------
                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = %s AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    (schema, table),
                )
                columns = [row["column_name"] for row in cur.fetchall()]

                # ------------------------------------------------------------------
                # 2. Row count
                # ------------------------------------------------------------------
                cur.execute(
                    sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(table)
                    )
                )
                total_rows = cur.fetchone()["count"]

                # ------------------------------------------------------------------
                # 3. Sample rows
                # ------------------------------------------------------------------
                cur.execute(
                    sql.SQL("SELECT * FROM {}.{} LIMIT {}").format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.Literal(limit),
                    )
                )
                rows: List[dict] = cur.fetchall()  # RealDictCursor → dict per row

                result[identifier] = {
                    "columns": columns,          #  <-- NEW
                    "total_rows": total_rows,
                    "truncated": total_rows > limit,
                    "rows": rows,
                }
    finally:
        conn.close()

    return result


# --------------------------------------------------------------------------- #
# 3. Example usage                                                            #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import json

    db_config = {
        "db_host": "localhost",
        "db_port": "5432",
        "db_username": "myappuser",
        "db_password": "myapppassword",
        "db_name": "myapp",
    }

    dump = dump_database(db_config, limit=5, connect_timeout=60)
    # default=str converts non-JSON-serialisable types (Decimal, UUID, datetime…)
    print(json.dumps(dump, indent=2, default=str))