"""DuckDB query execution with parsed statement and table-ownership checks."""
from pathlib import Path
import re
from typing import Any
import duckdb
import sqlglot
from sqlglot import exp


def identifier(name: str) -> str:
    """Quote a deliberately narrow SQL identifier."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,62}", name):
        raise ValueError("Invalid table or column identifier")
    return '"' + name + '"'


def connection(path: Path, *, read_only: bool = False):
    """Disable DuckDB external file/network functions and extension loading."""
    return duckdb.connect(str(path), read_only=read_only,
                          config={"enable_external_access": "false", "threads": "2"})


def run_sql(query: str, db_path: Path | None = None, params: list | None = None,
            *, allow_destructive: bool = False, read_only: bool = False) -> dict[str, Any]:
    """Run one authorized statement; explicit permission is a trusted caller flag."""
    from config import Settings
    path = db_path or Settings.from_env().db_path
    statements = sqlglot.parse(query, read="duckdb")
    if len(statements) != 1 or statements[0] is None:
        raise ValueError("Exactly one SQL statement is permitted")
    tree = statements[0]
    permitted = (exp.Select, exp.Union, exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter)
    if not isinstance(tree, permitted):
        raise PermissionError("SQL operation is not permitted")
    if any(isinstance(node, (exp.Command, exp.Copy, exp.Into)) for node in tree.walk()):
        raise PermissionError("External or unparsed SQL is forbidden")
    mutating = not isinstance(tree, (exp.Select, exp.Union))
    if read_only and mutating:
        raise PermissionError("This interface permits read-only queries")
    with connection(path) as con:
        if mutating:
            target = tree.this
            if not isinstance(target, exp.Table) or target.db or target.catalog:
                raise PermissionError("Mutation must target one local managed table")
            name = target.name
            identifier(name)
            try:
                owned = con.execute("SELECT 1 FROM _agent_tables WHERE table_name = ?", [name]).fetchone()
            except duckdb.Error:
                owned = None
            if not owned or name.startswith("_"):
                raise PermissionError("Table is not agent-owned")
            if isinstance(tree, (exp.Drop, exp.Alter)) and not allow_destructive:
                raise PermissionError("Destructive schema operations require explicit permission")
            if isinstance(tree, (exp.Delete, exp.Update)) and not tree.args.get("where") and not allow_destructive:
                raise PermissionError("Unscoped mutation is forbidden")
        result = con.execute(query, params or [])
        columns = [column[0] for column in result.description]
        rows = result.fetchmany(1000)
        return {"columns": columns, "rows": rows, "truncated_at": 1000}
