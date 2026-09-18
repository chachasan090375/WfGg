#!/usr/bin/env python3
"""Pure Collector incremental-chain helpers for ChaCha DEV Storage Governor V1."""
from __future__ import annotations

import sqlite3
from typing import Any, Callable

CHAIN_SCHEMA="chacha.dev/collector-incremental-chain-state/v1"
PACKAGE_SCHEMA="chacha.dev/collector-incremental-package/v1"

TABLE_ORDER=[
    "masters",
    "master_players",
    "player_identity",
    "player_aliases",
    "identity_coverage",
    "cycles",
    "players",
    "cycle_baseline",
    "cycle_seen",
    "cycle_changes",
    "observations",
]

CYCLE_TABLES={
    "cycle_baseline":"cycle_id",
    "cycle_changes":"cycle_id",
    "cycle_seen":"cycle_id",
    "players":"last_change_cycle",
}
FULL_REFRESH_TABLES={
    "identity_coverage":"full-table-small",
    "master_players":"full-table-dimension",
    "player_aliases":"full-table-dimension",
    "player_identity":"full-table-dimension",
}
TIME_TABLES={
    "masters":("created_at","id"),
    "observations":("observed_at","id"),
}


def quote_ident(value: str) -> str:
    return '"' + value.replace('"','""') + '"'


def sqlite_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value,(bytes,bytearray,memoryview)):
        return "X'" + bytes(value).hex() + "'"
    if isinstance(value,bool):
        return "1" if value else "0"
    if isinstance(value,int):
        return str(value)
    if isinstance(value,float):
        if value != value:
            return "NULL"
        if value == float("inf"):
            return "9e999"
        if value == float("-inf"):
            return "-9e999"
        return repr(value)
    text=str(value).replace("'","''")
    return "'" + text + "'"


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows=conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall()
    if not rows:
        raise RuntimeError(f"TABLE_SCHEMA_MISSING:{table}")
    return [str(r[1]) for r in rows]


def insert_sql(table: str, columns: list[str], row: tuple[Any,...]) -> str:
    cols=",".join(quote_ident(c) for c in columns)
    vals=",".join(sqlite_literal(v) for v in row)
    return f"INSERT OR REPLACE INTO {quote_ident(table)} ({cols}) VALUES ({vals});"


def fetch_rows(
    conn: sqlite3.Connection,
    table: str,
    where: str="",
    params: tuple[Any,...]=(),
    order_by: str="",
):
    columns=table_columns(conn,table)
    sql=f"SELECT {','.join(quote_ident(c) for c in columns)} FROM {quote_ident(table)}"
    if where:
        sql+=" WHERE "+where
    if order_by:
        sql+=" ORDER BY "+order_by
    cur=conn.execute(sql,params)
    return columns,cur


def next_completed_cycle(conn: sqlite3.Connection, after_cycle: int):
    columns={str(r[1]) for r in conn.execute('PRAGMA table_info("cycles")').fetchall()}
    if "id" not in columns or "finished_at" not in columns:
        raise RuntimeError("CYCLES_COMPLETION_COLUMNS_MISSING")
    row=conn.execute(
        'SELECT "id","finished_at" FROM "cycles" '
        'WHERE "id">? AND "finished_at" IS NOT NULL AND trim("finished_at")<>"" '
        'ORDER BY "id" LIMIT 1',
        (int(after_cycle),),
    ).fetchone()
    if row is None:
        return None
    return {"cycle":int(row[0]),"finished_at":str(row[1])}


def _time_rows(
    conn: sqlite3.Connection,
    table: str,
    time_col: str,
    pk_col: str,
    previous: dict[str,Any],
    cutoff: str,
):
    prev_time=str(previous.get(time_col) or "")
    prev_pk=previous.get(pk_col)
    if prev_pk is None:
        prev_pk=-1
    where=(
        f"(({quote_ident(time_col)} > ?) OR "
        f"({quote_ident(time_col)} = ? AND {quote_ident(pk_col)} > ?)) "
        f"AND {quote_ident(time_col)} <= ?"
    )
    order=f"{quote_ident(time_col)},{quote_ident(pk_col)}"
    columns,cur=fetch_rows(conn,table,where,(prev_time,prev_time,prev_pk,cutoff),order)
    return columns,cur


def generate_incremental_sql(
    conn: sqlite3.Connection,
    state: dict[str,Any],
    write_line: Callable[[str],None],
) -> dict[str,Any] | None:
    if state.get("schema") != CHAIN_SCHEMA:
        raise RuntimeError("CHAIN_STATE_SCHEMA_INVALID")
    sequence=int(state.get("sequence") or 0)
    watermarks=state.get("watermarks") or {}
    from_cycle=int(watermarks.get("cycle") or 0)
    target=next_completed_cycle(conn,from_cycle)
    if target is None:
        return None
    to_cycle=int(target["cycle"])
    if to_cycle != from_cycle+1:
        raise RuntimeError(f"CHAIN_CYCLE_GAP:{from_cycle}->{to_cycle}")
    cutoff=str(target["finished_at"])

    write_line("-- chacha.dev Collector incremental SQL v1")
    write_line(f"-- sequence={sequence+1}")
    write_line(f"-- from_cycle={from_cycle}")
    write_line(f"-- to_cycle={to_cycle}")
    write_line("PRAGMA foreign_keys=OFF;")
    write_line("BEGIN TRANSACTION;")

    row_counts={}
    new_wm={
        "cycle":to_cycle,
        "masters":dict(watermarks.get("masters") or {}),
        "observations":dict(watermarks.get("observations") or {}),
    }

    for table in TABLE_ORDER:
        if table in FULL_REFRESH_TABLES:
            write_line(f"DELETE FROM {quote_ident(table)};")
            columns,cur=fetch_rows(conn,table,order_by=",".join(quote_ident(c) for c in table_columns(conn,table)))
            count=0
            for row in cur:
                write_line(insert_sql(table,columns,row))
                count+=1
            row_counts[table]=count
            continue

        if table=="cycles":
            columns,cur=fetch_rows(
                conn,table,
                f"{quote_ident('id')} = ?",
                (to_cycle,),
                quote_ident("id"),
            )
            count=0
            for row in cur:
                write_line(insert_sql(table,columns,row)); count+=1
            row_counts[table]=count
            if count != 1:
                raise RuntimeError(f"TARGET_CYCLE_ROW_COUNT_INVALID:{count}")
            continue

        if table in CYCLE_TABLES:
            wm=CYCLE_TABLES[table]
            pk_cols=table_columns(conn,table)
            order=",".join(quote_ident(c) for c in pk_cols)
            columns,cur=fetch_rows(
                conn,table,
                f"{quote_ident(wm)} = ?",
                (to_cycle,),
                order,
            )
            count=0
            for row in cur:
                write_line(insert_sql(table,columns,row)); count+=1
            row_counts[table]=count
            continue

        if table in TIME_TABLES:
            time_col,pk_col=TIME_TABLES[table]
            previous=dict(watermarks.get(table) or {})
            columns,cur=_time_rows(conn,table,time_col,pk_col,previous,cutoff)
            count=0
            last=None
            time_idx=columns.index(time_col)
            pk_idx=columns.index(pk_col)
            for row in cur:
                write_line(insert_sql(table,columns,row))
                last=row
                count+=1
            row_counts[table]=count
            if last is not None:
                new_wm[table]={time_col:str(last[time_idx]),pk_col:last[pk_idx]}
            continue

        raise RuntimeError(f"INCREMENTAL_TABLE_POLICY_MISSING:{table}")

    write_line("COMMIT;")
    write_line("PRAGMA foreign_keys=ON;")

    return {
        "schema":PACKAGE_SCHEMA,
        "sequence":sequence+1,
        "from_cycle":from_cycle,
        "to_cycle":to_cycle,
        "target_finished_at":cutoff,
        "row_counts":row_counts,
        "watermarks":new_wm,
    }


def make_anchor_state(
    *,
    master_archive: str,
    master_sha256: str,
    master_created_at: str,
    baseline_cycle: int,
    observations_watermark: dict[str,Any],
    masters_watermark: dict[str,Any],
    plan_digest: str,
) -> dict[str,Any]:
    return {
        "schema":CHAIN_SCHEMA,
        "sequence":0,
        "created_at":master_created_at,
        "master":{
            "archive":master_archive,
            "sha256":master_sha256,
            "baseline_cycle":int(baseline_cycle),
        },
        "watermarks":{
            "cycle":int(baseline_cycle),
            "observations":observations_watermark,
            "masters":masters_watermark,
        },
        "plan_digest":plan_digest,
        "package_format":"gzip-compressed SQLite SQL patch",
        "next_sequence":1,
        "immutable":True,
    }
