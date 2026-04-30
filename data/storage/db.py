"""DuckDB connection manager — singleton, thread-safe."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from loguru import logger

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None


def _db_path() -> str:
    import os
    return os.getenv("DUCKDB_PATH", "./data/storage/fund.duckdb")


def get_connection() -> duckdb.DuckDBPyConnection:
    global _conn
    with _lock:
        if _conn is None:
            path = _db_path()
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            _conn = duckdb.connect(path, config={"threads": 4, "memory_limit": "2GB"})
            _init_schema(_conn)
            logger.info(f"DuckDB connected: {path}")
    return _conn


def _init_schema(conn: duckdb.DuckDBPyConnection) -> None:
    schema_path = Path(__file__).parent / "schema.sql"
    if schema_path.exists():
        conn.execute(schema_path.read_text())
        logger.debug("Schema initialized")


def execute(sql: str, params: list[Any] | None = None) -> duckdb.DuckDBPyRelation:
    conn = get_connection()
    if params:
        return conn.execute(sql, params)
    return conn.execute(sql)


def query_df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    conn = get_connection()
    if params:
        return conn.execute(sql, params).df()
    return conn.execute(sql).df()


def upsert_df(df: pd.DataFrame, table: str, pk_cols: list[str]) -> int:
    """Insert or replace rows by primary key."""
    conn = get_connection()
    conn.register("_upsert_tmp", df)
    pk_clause = " AND ".join(f"t.{c} = s.{c}" for c in pk_cols)
    update_cols = [c for c in df.columns if c not in pk_cols]
    if update_cols:
        set_clause = ", ".join(f"{c} = s.{c}" for c in update_cols)
        sql = f"""
            INSERT INTO {table}
            SELECT * FROM _upsert_tmp s
            ON CONFLICT ({', '.join(pk_cols)}) DO UPDATE SET {set_clause}
        """
    else:
        sql = f"""
            INSERT OR IGNORE INTO {table}
            SELECT * FROM _upsert_tmp s
        """
    conn.execute(sql)
    conn.unregister("_upsert_tmp")
    return len(df)


def insert_df(df: pd.DataFrame, table: str, if_exists: str = "ignore") -> int:
    """Bulk insert DataFrame into table."""
    if df.empty:
        return 0
    conn = get_connection()
    conn.register("_insert_tmp", df)
    if if_exists == "replace":
        conn.execute(f"DELETE FROM {table}")
    conflict = "OR IGNORE" if if_exists == "ignore" else ""
    conn.execute(f"INSERT {conflict} INTO {table} SELECT * FROM _insert_tmp")
    conn.unregister("_insert_tmp")
    return len(df)


def close() -> None:
    global _conn
    with _lock:
        if _conn:
            _conn.close()
            _conn = None
            logger.info("DuckDB connection closed")
